from collections.abc import Callable, Iterable, Mapping
from copy import deepcopy
from typing import Any

from pymodbus.client.sync import ModbusSerialClient
from pymodbus.client.sync import ModbusTcpClient
from pymodbus.transaction import ModbusRtuFramer
from pymodbus import register_read_message
import paho.mqtt.client as mqtt

from multiprocessing import Process, Queue
from threading import Thread
from queue import Empty, Full
from time import sleep
import struct

from refrig_data_converters import RefrigDataConverter
from refrig_turbine_iface import TurbineControl


class BaseInterface(Process):
    def __init__(self, output_dict, err_queue:Queue, read_period:float = .5, name: str | None = None, daemon: bool | None = None) -> None:
        super().__init__(name=name, daemon=None)
        self.err_queue = err_queue
        self.output_dict = output_dict
        self.read_period = read_period
        self.cmd_queue = Queue(maxsize=10)


    def process_error(self, err, err_priority=0):
        """
        The function "process_error" adds an error and its priority to a queue, and if the queue is
        full, it prints an error message.
        
        :param err: The `err` parameter is the error message or error object that needs to be processed
        :param err_priority: The `err_priority` parameter is an optional argument that specifies the
        priority of the error. It is used to determine the order in which errors are processed from the
        error queue. The higher the priority value, the higher the priority of the error. If not
        specified, the default priority is 0, defaults to 0 (optional)
        :return: nothing.
        """
        try:
            self.err_queue.put_nowait({err:err_priority})
        except Full: # :( this should never happen
            print(f'process_error: Error queue is full!!! \n {err}')
            return


class ModbusComInterface(BaseInterface): # korobochki

    mb_client = None
    read_dev_conf = None
    control_dev_conf = None

    def __init__(self, core_path, output_dict, err_queue:Queue, modbus_con_info:dict, read_devices_config:dict, 
                 control_devices_config: dict, read_period = .5, name: str | None = None, ) -> None:
        try:
            super().__init__(output_dict=output_dict, err_queue=err_queue, read_period=read_period, name=name)
            self.read_dev_conf = read_devices_config
            self.control_dev_conf = control_devices_config
            self.con_info = modbus_con_info
            self.data_converter = RefrigDataConverter(core_path)
        except Exception as err:
            raise type(err)(f'{self.name} ModbusComInterface init: {err}')


    def connect_iface(self):
        """
        The function attempts to connect to a Modbus serial client using the provided connection
        information and raises an error if the connection fails.
        :return: an integer value of 0 if the connection is successful.
        """
        try:
            port = str(self.con_info['port'])
            baudrate = int(self.con_info['baudrate'])
            mb_client = ModbusSerialClient(method='rtu', port=port, stopbits=1, bytesize=8, parity='N',
                                        baudrate=baudrate)
            if not mb_client.connect():
                raise ConnectionError(f'Could not connect to {port} with baudrate {baudrate}')
            self.mb_client = mb_client
            return 0 # success
        except Exception as err:
            raise type(err)(f'{self.name} connect_modbus: {err}')


    def run(self):
        """
        The function runs a continuous loop that sleeps for a specified period, processes commands,
        reads devices, and handles any exceptions that occur.
        """
        while True:
            try:
                sleep(self.read_period)
                self.process_commands()
                self.read_devices()
            except Exception as err:
                self.process_error(type(err)(f'{self.name} {err}', 0))


    def process_commands(self):
        """
        The function `process_commands` sends commands from a queue to a device until the queue is
        empty.
        :return: when the command queue is empty.
        """
        while True: # send all commands from queue
            try:
                cfg = self.cmd_queue.get_nowait()
                dev_name = next(iter(cfg))
                value = cfg[dev_name]
                self.send_command(dev_name, value)
            except Empty:
                return
            except Exception as err:
                self.process_error(type(err)(f'{self.name} process_commands: {err}'), 0)
                continue


    def read_devices(self):
        """
        The function `read_devices` reads data from multiple devices using Modbus communication and
        stores the values in a dictionary.
        """
        try:
            dev_values = {}
            for dev_name, dev_conf in self.read_dev_conf.items():
                try:
                    if dev_conf['num_registers'] <= 0:
                        raise ValueError(f'ModbusComInterface.read_modbus_data: Invalid register config for {dev_name}')
                    data = self.mb_client.read_holding_registers(dev_conf['start_register'], dev_conf['num_registers'],
                                                                                    unit=dev_conf['modbus_id'])
                    if not isinstance(data, register_read_message.ReadHoldingRegistersResponse) or len(data.registers)<2: # no answer or incorrect answer format
                        dev_values[dev_name] = None
                        raise ValueError(f'ModbusComInterface.read_modbus_data: incorrect data: {data} for device {dev_name}')
                    #converting responce to str and sending to data converter to get human-readable output:
                    reg1 = '{0:016b}'.format(data.registers[0])
                    reg2 = '{0:016b}'.format(data.registers[1])
                    out_val = self.modbus_to_dec(f'{reg1}{reg2}')
                    out_val = self.data_converter.read_data_convert(dev_conf.get('converter_type', 'Default'), dev_name, out_val)
                    dev_values.update({dev_name:out_val})
                except Exception as err:
                    dev_values.update({dev_name:None})
                    self.process_error(f'read_devices: {err}')
                    continue
            self.output_dict.update(dev_values)
        except Exception as err:
            raise type(err)(f'read_devices: {err}')
        

    #modbus encoding and decoding:
    def to_bytes(self,value): # dec to binary
        return struct.pack('!f', value)
    

    def to_hex(self,value): # dec to hex
        return self.to_bytes(value).hex()


    def modbus_to_dec(self, raw_value:str):
        """
        The function `modbus_to_dec` converts a raw value from a IEEE754 protocol(with byte reverse) to a decimal number.
        
        :param raw_value: The `raw_value` parameter is a string representing a 32-bit Modbus value
        :type raw_value: str
        :return: the decimal value of the given raw_value.
        """
        
        #reverse bytes
        b0 = raw_value[0:8]
        b1 = raw_value[8:16]
        b2 = raw_value[16:24]
        b3 = raw_value[24:]
        raw_value = f'{b3}{b2}{b1}{b0}'
        
        sign = int(raw_value[0])  # sign, 1 bit (31)
        exp = int(raw_value[1:9], 2)  # exponent, 8 bits (30-23)
        mant = int(raw_value[9:], 2)  # fraction of mantissa, 23 bits (22-0)

        dec_number = ((-1) ** sign) * (2 ** (exp - 127)) * (1 + (mant / 2 ** 23))
        return dec_number
    

    def val_to_modbus(self, val):
        """
        The function `val_to_modbus` takes a Python float value and transforms it into a 4-byte
        refrigerator modbus format.
        
        :param val: The `val` parameter is a Python float value that needs to be transformed into a
        4-byte refrigerator modbus format
        :return: two values: `out_reg1` and `out_reg2`.
        """
        try:
            hex_num = self.to_hex(val)
            hex_str = str(hex_num)
            #reverse bytes and put them in 2 registers
            bytes = [hex_str[0:2], hex_str[2:4], hex_str[4:6], hex_str[6:8]]
            out_reg2 = int(f'{bytes[3]}{bytes[2]}', 16)
            out_reg1 = int(f'{bytes[1]}{bytes[0]}', 16)
            return out_reg1, out_reg2
        except Exception as err:
            raise type(err)(f'val_to_modbus encoding error: {err}')


    def send_command(self, dev_name, value):
        """
        The `send_command` function sends a command to a device using Modbus communication protocol.
        
        :param dev_name: The `dev_name` parameter is a string that represents the name of the device. It
        is used to identify the device configuration and determine the appropriate actions to take
        :param value: The `value` parameter in the `send_command` function is the value that you want to
        send to a device. It could be any data that needs to be transmitted to the device for processing
        or control purposes
        :return: In this code, the `send_command` function returns `None` if the `dev_name` parameter is
        equal to 'Service'. Otherwise, it does not explicitly return anything.
        """
        try:
            if dev_name == 'Service':
                pass # self.do_calib()
                return
            dev_conf = self.control_dev_conf.get(dev_name, None)
            if dev_conf is None:
                raise AttributeError(f'no config found for device {dev_name}')
            value = self.data_converter.write_data_convert(dev_name, value)
            val_reg1, val_reg2 = self.val_to_modbus(value) # encode decimal to modbus format (2 registers)
            self.mb_client.write_registers([dev_conf['start_register'], dev_conf['start_register']+1], [val_reg1, val_reg2], unit=dev_conf['modbus_id'])

            # self.mb_client.write_registers(dev_conf['start_register'], val_reg1, unit=dev_conf['modbus_id']) # send first register
            # self.mb_client.write_registers(dev_conf['start_register']+1, val_reg2, unit=dev_conf['modbus_id']) # send second register
        except Exception as err:
            raise type(err)(f'send_data: {err}')
    

class ModbusRtuOverTcpComInterface(BaseInterface): # PKT8

    
    def __init__(self, core_path, output_dict, err_queue:Queue, modbus_con_info:dict, read_devices_config:dict, 
                 read_period = .5, name: str | None = None, ) -> None:
        try:
            super().__init__(output_dict, err_queue, read_period, name, daemon = None)
            self.read_dev_conf = read_devices_config
            self.con_info = modbus_con_info
            self.data_converter = RefrigDataConverter(core_path)
        except Exception as err:
            raise type(err)(f'{self.name} ModbusComInterface init: {err}')
            

    def connect_iface(self):
        try:
            ip = self.con_info['ip']
            port = int(self.con_info['port'])
            mb_client = ModbusTcpClient(host=ip, port=int(port), framer=ModbusRtuFramer)
            if not mb_client.connect():
                raise ConnectionError(f'Could not connect to {ip}:{port}')
            self.mb_client = mb_client
        except Exception as err:
            raise type(err)(f'{self.name} connect_modbus: {err}')


    def run(self):
        while True:
            try:
                sleep(self.read_period)
                self.read_devices()
            except Exception as err:
                self.process_error(type(err)(f'{self.name} {err}', 0))


    def read_devices(self):
        try:
            dev_values = {}
            for dev_name, dev_conf in self.read_dev_conf.items():
                try:
                    if dev_conf['num_registers'] <= 0:
                        raise ValueError(f'ModbusComInterface.read_modbus_data: Invalid register config for {dev_name}')
                    data = self.mb_client.read_holding_registers(dev_conf['start_register'], dev_conf['num_registers'],
                                                                                    unit=dev_conf['modbus_id'])
                    if not isinstance(data, register_read_message.ReadHoldingRegistersResponse) or len(data.registers)<2: # no answer or incorrect answer format
                        dev_values[dev_name] = None
                        raise ValueError(f'ModbusComInterface.read_modbus_data: incorrect data: {data} for device {dev_name}')
                    #decoding responce and sending to data converter to get human-readable output:
                    msb = data.registers[1]
                    lsb = data.registers[0]
                    out_val = ((msb << 16) | (lsb) ) / 100
                    out_val = self.data_converter.read_data_convert(dev_conf.get('converter_type', 'Default'), dev_name, out_val)
                    dev_values.update({dev_name:out_val})
                except Exception as err:
                    dev_values.update({dev_name:None})
                    self.process_error(f'read_devices: {err}')
                    continue
            self.output_dict.update(dev_values)
        except Exception as err:
            raise type(err)(f'read_devices: {err}')
        

class TurbineComInterface(BaseInterface):
    def __init__(self, core_path, output_dict, err_queue:Queue, con_info:dict, read_devices_config:dict, 
                 control_devices_config:dict, read_period = .5, name: str | None = None, ) -> None:
        try:
            super().__init__(output_dict=output_dict, err_queue=err_queue, read_period=read_period, name=name)
            self.control_dev_conf = control_devices_config
            self.read_dev_conf = read_devices_config
            self.con_info = con_info
            
            self.data_converter = RefrigDataConverter(core_path)
        except Exception as err:
            raise type(err)(f'{self.name} ModbusComInterface init: {err}')
        

    def connect_iface(self):
        try:
            self.tc_client = TurbineControl(port=self.con_info['port'], baudrate=self.con_info['baudrate'])
            self.tc_client.connect_to_turbine()
        except Exception as err:
            raise type(err)(f'{self.name} connect: {err}')


    def run(self):
        while True:
            try:
                sleep(self.read_period)
                self.process_commands()
                self.read_devices() # read all turbine attributes
            except Exception as err:
                self.process_error(type(err)(f'{self.name} {err}', 0))


    def read_devices(self):
        try:
            self.tc_client.send_command('read_temp') # sending command to read values from turbine
            dev_values = {}
            for dev_name, dev_conf in self.read_dev_conf.items():
                try:
                    if not isinstance(dev_conf, dict):
                        converter_type = 'Default'
                    else:
                        converter_type = dev_conf.get('converter_type', 'Default')
                    out_val = self.tc_client.get_attr_value(attr_name=dev_name.split('_')[-1])
                    out_val = self.data_converter.read_data_convert(converter_type, dev_name, out_val)
                    dev_values.update({dev_name:out_val})
                except Exception as err:
                    dev_values.update({dev_name:None})
                    self.process_error(f'read_devices: {err}')
                    continue
            self.output_dict.update(dev_values)
        except Exception as err:
            raise type(err)(f'read_devices: {err}')
        

    def process_commands(self):
        while True: # send all commands from queue
            try:
                cfg = self.cmd_queue.get_nowait()
                dev_name = next(iter(cfg))
                cmd = cfg[dev_name].split(' ')
                cmd_name = cmd[0]
                if len(cmd)>1:
                    cmd_value = cmd[1]
                    cmd_value = self.data_converter.write_data_convert(dev_name=dev_name, value=cmd_value)
                else:
                    cmd_value = None
                self.tc_client.send_command(cmd_name, cmd_value)
            except Empty:
                return
            except Exception as err:
                self.process_error(type(err)(f'{self.name} process_commands: {err}'), 0)
                continue


class MqttComInterface(Thread): # devices, connected to WB extention modules (vacpumps, valves)

    local_values_dict = {}

    def __init__(self, core_path, output_dict, err_queue:Queue, con_info:dict, read_devices_config:dict, 
                 control_devices_config:dict, read_period = 1, name: str | None = None, ) -> None:
        try:
            super().__init__(name=name, daemon=True)
            self.cmd_queue = Queue(maxsize=10)
            self.output_dict = output_dict
            self.err_queue = err_queue
            self.read_period = read_period
            self.control_dev_conf = control_devices_config
            self.read_dev_conf = read_devices_config
            self.con_info = con_info
            
            # type(self).local_values_dict = {}
            self.data_converter = RefrigDataConverter(core_path)
            self.mqtt_client = mqtt.Client()
            self.topic_head = '/devices/control/'
        except Exception as err:
            print(err)
            raise type(err)(f'{self.name} ModbusComInterface init: {err}')
        

    def connect_iface(self):
        try:
            self.mqtt_client.username_pw_set(self.con_info['username'], self.con_info['password'])
            self.mqtt_client.connect(host=self.con_info['ip'], port=int(self.con_info['port']), keepalive=60, )
            for cur_dev_name, cur_dev_conf in self.read_dev_conf.items():
                if cur_dev_conf is None:
                    cur_dev_conf = {}
                cur_topic_name = cur_dev_conf.get('mqtt_topic', f'{cur_dev_name}')
                self.mqtt_client.subscribe(f'{self.topic_head}{cur_topic_name}')
            self.mqtt_client.on_message = self.update_value
            self.mqtt_client.loop_start()
        except Exception as err:
            print(err)
            raise type(err)(f'{self.name} MqttComInterface connection error: {err}')
        

    def update_value(self, client, userdata, msg):
        try:
            value = float(f'{msg.payload.decode()}')
            dev_name = msg.topic.split("/")[-1]
            dev_conf = self.read_dev_conf.get('dev_name', {})
            converter_type = dev_conf.get('converter_type', 'Default')
            value = self.data_converter.read_data_convert(converter_type, dev_name, value)
            lvd = type(self).local_values_dict
            lvd.update({dev_name:value})
        except Exception as err:
            print(err)
            self.process_error(type(err)(f'error reading value: {err}'), 0)


    def process_commands(self):
        """
        The function `process_commands` sends commands from a queue to a device until the queue is
        empty.
        :return: when the command queue is empty.
        """
        while True: # send all commands from queue
            try:
                cfg = self.cmd_queue.get_nowait()
                dev_name = next(iter(cfg))
                value = cfg[dev_name]
                self.send_command(dev_name, value)
            except Empty:
                return
            except Exception as err:
                self.process_error(type(err)(f'{self.name} process_commands: {err}'), 0)
                continue


    def send_command(self, dev_name, value):
        try:
            dev_conf = self.control_dev_conf.get(dev_name, {})
            converter_type = dev_conf.get('converter_type', 'Default')
            topic_name = dev_conf.get('mqtt_topic', f'{dev_name}')
            value = self.data_converter.write_data_convert(converter_type, dev_name, value)
            self.mqtt_client.publish(topic=f'{self.topic_head}{topic_name}', payload=f'{value}')
        except Exception as err:
            raise type(err)(f'send_command: {err}')


    def run(self):
        while True:
            try:
                sleep(self.read_period)
                self.process_commands()
                self.output_dict.update(self.local_values_dict)
            except Exception as err:
                print(err)
                self.process_error(type(err)(f'{self.name}: {err}'), 0)


    def process_error(self, err, err_priority=0):
        try:
            self.err_queue.put_nowait({err:err_priority})
        except Full: # :( this should never happen
            print(f'process_error: Error queue is full!!! \n {err}')
            return


class MultiDeviceCalculator(BaseInterface):
    def __init__(self, output_dict, multi_devices_conf: dict, err_queue: Queue, read_period: float = 1, name: str | None = None, daemon: bool | None = None) -> None:
        super().__init__(output_dict, err_queue, read_period, name, daemon)
        self.multi_devices_conf = multi_devices_conf


    def run(self):
        """
        The function runs an infinite loop that periodically updates the output dictionary based on the
        values in the input dictionary and the configuration of multiple devices.
        """
        while True:
            try:
                sleep(self.read_period)
                #create local copies of dicts to avoid blocking other processes:
                local_output_dict = {}
                in_values = deepcopy(self.output_dict)

                for cur_multi_dev_name, comp_devs_list in self.multi_devices_conf.items():
                    multi_dev_conf = {}
                    for cur_comp_dev_name in comp_devs_list: # get values of multi_dev's components
                        multi_dev_conf.update({cur_comp_dev_name:in_values.get(cur_comp_dev_name, None)})
                    try:
                        cur_out_value = self.calculate_device_value(cur_multi_dev_name, multi_dev_conf)
                    except (AttributeError, KeyError, TypeError) as err: # if no key found or some value is None - return None and send warning
                        cur_out_value = None
                        self.process_error(type(err)(f'{self.name} {err}'), 0)
                    local_output_dict.update({cur_multi_dev_name:cur_out_value}) # fill local dict
                self.output_dict.update(local_output_dict) # update global dict with local dict's values                   
            except Exception as err:
                self.process_error(type(err)(f'{self.name} {err}'), 0)


    def calculate_device_value(self, multi_dev_name, multi_dev_conf):
        """
        The function `calculate_device_value` calculates the value of a device based on its name and
        configuration.
        
        :param multi_dev_name: The parameter `multi_dev_name` is a string that represents the name of a
        multi-device.
        :param multi_dev_conf: The `multi_dev_conf` parameter is a dictionary that contains the
        configuration values for different devices. The keys in the dictionary represent the device
        names, and the values represent the corresponding configuration values for each device
        :return: The function `calculate_device_value` returns the calculated value based on the given
        `multi_dev_name` and `multi_dev_conf`.
        """
        try:
            out_value = None
            match multi_dev_name:
                case 'L1':
                    out_value = (multi_dev_conf.get('L1a') + multi_dev_conf.get('L1c')) * .5
                case 'L2':
                    out_value = (multi_dev_conf.get('L2a') + multi_dev_conf.get('L2c')) * .5
                case 'H1':
                    out_value = multi_dev_conf.get('P5d') - multi_dev_conf.get('P5a')
                case 'P3':
                    out_value = (multi_dev_conf.get('P2') + multi_dev_conf.get('P2d')) * .5
                case _:
                    raise AttributeError(f'unknown multi device name {multi_dev_name}')
            return out_value
        except TypeError as err:
            raise TypeError(f'calculate_device_value for {multi_dev_name}: value is missing')
        except Exception as err:
            raise type(err)(f'calculate_device_value for {multi_dev_name}: {err}')