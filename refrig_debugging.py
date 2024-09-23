# test classes for debugging without device connections
# random values are returned
from multiprocessing import Queue
from queue import Empty
from refrig_comm_ifaces import BaseInterface
from refrig_data_converters import RefrigDataConverter
from time import sleep

from random import uniform


class ModbusComInterface(BaseInterface):
    def __init__(self, core_path, output_dict, err_queue:Queue, modbus_con_info:dict, read_devices_config:dict, 
                 control_devices_config: dict, read_period = .5, name: str | None = None, ) -> None:
        try:
            super().__init__(output_dict=output_dict, err_queue=err_queue, read_period=read_period, name=name)
            self.output_dict = output_dict
            self.cmd_queue = Queue(maxsize=10)
            self.data_converter = RefrigDataConverter(core_path)
            self.read_dev_conf = read_devices_config
            self.control_dev_conf = control_devices_config
        except Exception as err:
            raise type(err)(f'{self.name} TestModbusComInterface init: {err}')
        

    def connect_iface(self):
        print('ModbusComInterface:connect_iface called')


    def run(self) -> None:
        while True:
            try:
                sleep(self.read_period)
                self.process_commands()
                self.read_devices()
            except Exception as err:
                self.process_error(type(err)(f'{self.name} {err}', 0))


    def process_commands(self):
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
        try:
            dev_values = {}
            for dev_name, dev_conf in self.read_dev_conf.items():
                try:
                    # out_val = self.data_converter.read_data_convert(dev_conf.get('converter_type', None), dev_name, 10)
                    out_val = uniform(-1000, 1000)
                    dev_values.update({dev_name:out_val})
                except Exception as err:
                    dev_values.update({dev_name:None})
                    self.process_error(f'read_devices: {err}')
                    continue
            self.output_dict.update(dev_values)
        except Exception as err:
            raise type(err)(f'read_devices: {err}')
        

    def send_command(self, dev_name, command):
        print(f'{self.name} recieved command for {dev_name}: {command}')


class ModbusRtuOverTcpComInterface(ModbusComInterface): # no control devices only sensors
    def __init__(self, core_path, output_dict, err_queue:Queue, modbus_con_info:dict, read_devices_config:dict, 
                 read_period = .5, name: str | None = None, ) -> None:
        super().__init__(core_path=core_path, output_dict=output_dict, err_queue=err_queue, modbus_con_info=modbus_con_info, 
                            read_devices_config=read_devices_config, control_devices_config={}, read_period=read_period, name=name)

    def connect_iface(self):
        print('ModbusTcpTestInterface:connect_iface called')


class TurbineComInterface(ModbusComInterface):
    def __init__(self, core_path, output_dict, err_queue: Queue, con_info: dict, read_devices_config: dict, control_devices_config: dict, read_period=0.5, name: str | None = None) -> None:
        super().__init__(core_path=core_path, output_dict=output_dict, err_queue=err_queue, modbus_con_info=con_info, 
                         read_devices_config=read_devices_config, control_devices_config=control_devices_config, 
                         read_period=read_period, name=name)


    def connect_iface(self):
        print('TurbineComInterface:connect_iface called')


class MqttComInterface(ModbusComInterface):
    def __init__(self, core_path, output_dict, err_queue: Queue, con_info: dict, read_devices_config: dict, control_devices_config: dict, read_period=0.5, name: str | None = None) -> None:
        super().__init__(core_path=core_path, output_dict=output_dict, err_queue=err_queue, modbus_con_info=con_info, 
                         read_devices_config=read_devices_config, control_devices_config=control_devices_config, 
                         read_period=read_period, name=name)
        
    def connect_iface(self):
        print('MqttComInterface:connect_iface called')