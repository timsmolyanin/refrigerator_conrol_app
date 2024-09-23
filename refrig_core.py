# from refrig_comm_ifaces import ModbusComInterface, ModbusRtuOverTcpComInterface, TurbineComInterface
from refrig_comm_ifaces import MultiDeviceCalculator, MqttComInterface
from refrig_debugging import ModbusComInterface, ModbusRtuOverTcpComInterface, TurbineComInterface

from refrig_external_ifaces import mqtt_iface
from refrig_auto_controls import refrigAutoControls

from time import sleep
from multiprocessing import Queue, Manager, Lock
from queue import Empty, Full
from pathlib import Path
import logging

from time import sleep

# Core component for controlling a refrigerator.
class RefrigControlsCore():

    state = 'INIT' # INIT/OK/WARNING/ERROR/CRITICAL
    status = 'Manual' # Manual/Heating to/cooling to/ etc
    ext_iface = None

    def __init__(self) -> None:
        try: # pre-logger error handling
            self.cur_path = self.get_cur_path()
            self.logger = self.init_logger(self.cur_path.joinpath('logs'))
        except Exception as err:
            print(f'Critical error at logger init, stopping: {err.__class__.__name__}:{err}')
            exit()
        try:
            self.err_queue = Queue(maxsize=20) # process shared queue for storing errors
            self.pool_lock = Lock()
            pool_manager = type(self).pool_manager = Manager()
            self.values_dict = pool_manager.dict() 

            self.ext_iface_cfg, self.iface_cfg, self.device_cfg = self.read_main_config(self.cur_path.joinpath('config.yaml'))
            self.silicon_therm_cfg = self.read_silicon_therm_config(self.cur_path.joinpath('data','silicon_thermometry'))
            self.init_ifaces()

            del self.ext_iface_cfg, self.iface_cfg, self.device_cfg, self.silicon_therm_cfg # not needed anymore
            self.update_state('OK')
            self.update_status(self.status)
        except Exception as err:
            self.process_error(err, 2)


    def get_cur_path(self):
        """
        The function `get_cur_path` returns the current path of the script or executable file.
        :return: the current path of the file or the executable.
        """
        import os, sys
        if getattr(sys, 'frozen', False):
            cur_path = os.path.dirname(sys.executable)
        elif __file__:
            cur_path = os.path.dirname(__file__)
        return Path(cur_path)


    def init_logger(self, logs_path):
        """
        The function initializes a logger object that writes log messages to a file.
        
        :param logs_path: The `logs_path` parameter is the path where the log files will be stored. It
        should be a directory path where the log files will be created
        :return: a logger object.
        """
        from datetime import date
        try:
            logs_path.mkdir(parents=True, exist_ok=True)
            logs_fname = logs_path.joinpath(f'log_{date.today()}.txt')
            self.logger_handler = logging.FileHandler(filename=logs_fname, mode='a')
            self.logger_handler.setFormatter(logging.Formatter(fmt='[%(asctime)s: %(levelname)s] %(message)s'))
            logger = logging.getLogger('refrig_logger')
            logger.setLevel(logging.DEBUG)
            logger.addHandler(self.logger_handler)
            return logger
        except Exception as err:
            raise type(err)(f'init_logger: {err}')


    #init configs
    def read_main_config(self, cfg_path):
        """
        The function `read_main_config` reads a YAML configuration file, extracts relevant information,
        and returns it.
        
        :param cfg_path: The `cfg_path` parameter is a string that represents the path to the
        configuration file that needs to be read
        :return: three variables: ext_iface_cfg, iface_cfg, and device_cfg.
        """
        import yaml
        try:
            with open(cfg_path, "r") as stream:
                cfg = dict(yaml.safe_load(stream))
                if len(cfg)==0:
                    raise ValueError(f'config file is empty')
                self.logger.setLevel(logging.getLevelName(cfg.pop('logging')['level'])) # set logging level from file
                
                iface_cfg = cfg['connections']
                ext_iface_cfg = iface_cfg.pop('external_iface')
                device_cfg = cfg['devices']

                # for cur_con_type, cur_devs in device_cfg.values():
                #     for cur_dev_name, cur_dev_conf in dict(cur_devs).values():
                #         if 'converter_type' not in list(cur_dev_conf.keys()):
                #             cur_dev_conf.update({'converter_type':'Default'})

            return ext_iface_cfg, iface_cfg, device_cfg
        except Exception as err:
            raise type(err)(f'read_main_config: {err}')
        

    def read_silicon_therm_config(self, cfg_dir):
        """
        The function reads configuration files in a specified directory and returns the data in a
        dictionary format.
        
        :param cfg_dir: The `cfg_dir` parameter is a directory path where the configuration files are
        located
        :return: a dictionary `si_therm_data` which contains the sensor names as keys and their
        corresponding coefficients as values.
        """
        try:
            si_therm_data = {}
            for cur_file_name in list(cfg_dir.iterdir()):
                cur_file = open(cfg_dir.joinpath(cur_file_name), 'r')
                cur_sensor_name = cur_file.readline().split()[0]
                cur_sens_coefs = []
                while True:
                    cur_line = cur_file.readline()
                    if len(cur_line) == 0:
                        break
                    cur_sens_coefs.append(float(cur_line.split('=')[-1]))
                cur_file.close()
                si_therm_data.update({cur_sensor_name: cur_sens_coefs})
            return si_therm_data
        except Exception as err:
            raise type(err)(f'read_silicon_therm_config: {err}')
    

    def init_ifaces(self):
        """
        The `init_ifaces` function initializes various interface devices and starts their respective
        threads/processes.
        """
        try:
            self.dev_iface_rel = {} # stores which interface devices belong to

            #ext iface
            self.ext_iface = mqtt_iface(self.ext_iface_cfg, self.send_command, self.err_queue)

            #box
            box_connect_info = self.iface_cfg.pop('box_serial')
            box_sensor_dev_cfg = self.device_cfg.pop('box_sensor_devices')
            box_control_dev_cfg = self.device_cfg.pop('box_control_devices')
            self.update_dev_ifaces_rel('box_iface', list(box_sensor_dev_cfg.keys())+list(box_control_dev_cfg.keys()))


            box_iface = ModbusComInterface(core_path=self.cur_path, output_dict=self.values_dict, err_queue=self.err_queue, 
                                           modbus_con_info=box_connect_info, read_devices_config=box_sensor_dev_cfg, control_devices_config=box_control_dev_cfg, 
                                           read_period=.5, name='box_iface' )
            self.box_iface_queue = box_iface.cmd_queue # queue to push commands
            box_iface.connect_iface()
            box_iface.start()

            #therm
            therm_connect_info = self.iface_cfg.pop('therm_serial')
            therm_sensor_dev_cfg = self.device_cfg.pop('therm_sensor_devices')
            self.update_dev_ifaces_rel('therm_iface', list(therm_sensor_dev_cfg.keys()))
            therm_iface = ModbusRtuOverTcpComInterface(core_path=self.cur_path, output_dict=self.values_dict, err_queue=self.err_queue, 
                                           modbus_con_info=therm_connect_info, read_devices_config=therm_sensor_dev_cfg,
                                           read_period=.5, name='therm_iface' )
            self.therm_iface_queue = therm_iface.cmd_queue # queue to push commands
            therm_iface.connect_iface()
            therm_iface.start()


            #turbopump 1
            turb1_connect_info = self.iface_cfg.pop('turb1_serial')
            turb1_sensor_dev_cfg = self.device_cfg.pop('turb1_sensor_devices')
            turb1_control_dev_cfg = self.device_cfg.pop('turb1_control_devices')
            
            self.update_dev_ifaces_rel('turb1_iface', list(turb1_sensor_dev_cfg.keys())+list(turb1_control_dev_cfg.keys()) )
            turb1_iface = TurbineComInterface(core_path=self.cur_path, output_dict=self.values_dict, err_queue=self.err_queue, 
                                           con_info=turb1_connect_info, read_devices_config=turb1_sensor_dev_cfg, 
                                           control_devices_config=turb1_control_dev_cfg, read_period=.5, name='turb1_iface' )
            self.turb1_iface_queue = turb1_iface.cmd_queue # queue to push commands
            turb1_iface.connect_iface()
            turb1_iface.start()

            #turbopump 2
            turb2_connect_info = self.iface_cfg.pop('turb2_serial')
            turb2_sensor_dev_cfg = self.device_cfg.pop('turb2_sensor_devices')
            turb2_control_dev_cfg = self.device_cfg.pop('turb2_control_devices')

            self.update_dev_ifaces_rel('turb2_iface', list(turb2_sensor_dev_cfg.keys())+list(turb2_control_dev_cfg.keys()))
            turb2_iface = TurbineComInterface(core_path=self.cur_path, output_dict=self.values_dict, err_queue=self.err_queue, 
                                           con_info=turb2_connect_info, read_devices_config=turb2_sensor_dev_cfg, 
                                           control_devices_config=turb2_control_dev_cfg, read_period=.5, name='turb2_iface' )
            self.turb2_iface_queue = turb2_iface.cmd_queue # queue to push commands
            turb2_iface.connect_iface()
            turb2_iface.start()

            #vacuum stuff (devices, connected to WB extention modules)
            vac_connect_info = self.iface_cfg.pop('vac_mqtt')
            vac_sensor_dev_cfg = self.device_cfg.pop('vac_sensor_devices')
            vac_control_dev_cfg = self.device_cfg.pop('vac_control_devices')

            self.update_dev_ifaces_rel('vac_iface', list(vac_sensor_dev_cfg.keys())+list(vac_control_dev_cfg.keys()))
            vac_iface = MqttComInterface(core_path=self.cur_path, output_dict=self.values_dict, err_queue=self.err_queue, 
                                           con_info=vac_connect_info, read_devices_config=vac_sensor_dev_cfg, 
                                           control_devices_config=vac_control_dev_cfg, read_period=1, name='vac_iface' )
            self.vac_iface_queue = vac_iface.cmd_queue # queue to push commands
            vac_iface.connect_iface()
            vac_iface.start()

            #multi_device_calculator:
            multi_dev_cfg = self.device_cfg.pop('multi_devices')
            self.multi_dev_calculator = MultiDeviceCalculator(output_dict=self.values_dict, multi_devices_conf=multi_dev_cfg, 
                                                              err_queue=self.err_queue, read_period=1, name='multi_dev_calculator')
            self.multi_dev_calculator.start()


            #auto_control_thread
            self.auto_ctrl_thread = refrigAutoControls(values_dict=self.values_dict, error_queue=self.err_queue, 
                                                       cmd_func=self.send_command, update_period=1, name='auto_controls')
            self.auto_ctrl_thread.start()

        except Exception as err:
            raise type(err)(f'init_ifaces: {err}')


    def update_dev_ifaces_rel(self, iface_name:str, devices_list:list): # update relations dict with new interface
        """
        The function updates the relations dictionary with a new interface for each device in the
        devices list.
        
        :param iface_name: The name of the interface that needs to be updated in the relations
        dictionary
        :type iface_name: str
        :param devices_list: A list of device names that are related to the given interface name
        :type devices_list: list
        """
        for cur_dev_name in devices_list:
            self.dev_iface_rel.update({cur_dev_name:iface_name})


    def run(self):
        """
        The function runs a continuous loop that sends data to external interface
        and processes any errors that occur.
        """
        while True:
            try:
                self.ext_iface.send(self.values_dict)
                while True:
                    cur_error = self.err_queue.get_nowait()
                    if isinstance(cur_error, dict):
                        for cur_err_desc, cur_err_prio in cur_error:
                            self.process_error(cur_err_desc, cur_err_prio)
                    else:
                        self.process_error(cur_error, 0)
            except Empty:
                sleep(1)
                continue
            except KeyboardInterrupt:
                self.stop_app()
            except Exception as err:
                self.process_error(err, 1)


    def send_command(self, dev_name:str, cmd):
        """
        The `send_command` function is used to send commands to different devices and handle any errors
        that may occur.
        
        :param dev_name: The `dev_name` parameter is a string that represents the name of the device for
        which the command is being sent. It is used to identify the device and determine the appropriate
        command queue to put the command into
        :type dev_name: str
        :param cmd: The `cmd` parameter in the `send_command` method is a command that needs to be sent
        to a device. It can be any valid command that the device can understand and execute
        :return: The function does not explicitly return anything.
        """
        try:
            print(f'RefrigControlsCore send_command: recieved cmd for {dev_name} : {cmd}')
            if dev_name == 'State': # GUI/UI sent command to set app state
                self.update_state(cmd)
                return
            iface_name = self.dev_iface_rel.get(dev_name, None)
            if iface_name is None:
                raise AttributeError(f'unknown device {dev_name}')
            cmd_queue = getattr(self, f'{iface_name}_queue')
            try:
                cmd_queue.put_nowait({dev_name:cmd})
            except Full:
                raise BufferError(f'command queue of {iface_name} is full, unable to execute command')
        except Exception as err:
            self.process_error(type(err)(f'RefrigControlsCore.send_command: {err}'))
        

    #state and status
    def update_status(self, new_status, log_status=True):
        """
        The function updates the status of an object and logs the new status if specified.
        
        :param new_status: The new status that you want to update to. It can be any value that
        represents the current status of the object
        :param log_status: The `log_status` parameter is a boolean flag that determines whether or not
        to log the new status. If `log_status` is `True`, the new status will be logged using the
        `logger.info()` method. If `log_status` is `False`, the new status will not be logged, defaults
        to True (optional)
        """
        self.state = new_status
        if self.ext_iface is not None:
            self.ext_iface.send({'Status':self.state}, retain=True)
        if log_status:
            self.logger.info(f'Status is now {new_status}')


    def update_state(self, new_state, log_state=True):
        """
        The function updates the state of an object and optionally logs the new state.
        
        :param new_state: The new state that you want to update to
        :param log_state: The `log_state` parameter is a boolean flag that determines whether or not to
        log the new state. If `log_state` is `True`, the new state will be logged using the
        `logger.info()` method. If `log_state` is `False`, the new state will not be logged, defaults to
        True (optional)
        :return: a boolean value. If the state is not updated (i.e., the current state is the same as
        the new state), then it returns False. Otherwise, it updates the state, sends the new state to
        the external interface (if available), logs the new state (if log_state is True), and returns
        True.
        """
        if self.state == new_state: # avoids showing/logging same state multiple times
            return False
        self.state = new_state
        if self.ext_iface is not None:
            self.ext_iface.send({'State':self.state}, retain=True)
        if log_state:
            self.logger.info(f'State is now {new_state}')
        return True


    #error handling
    def process_error(self, err, err_priority=0):
        """
        The function `process_error` handles and logs errors based on their priority level.
        
        :param err: The `err` parameter is the error object or message that needs to be processed. It
        can be an exception object or a string representing the error message
        :param err_priority: The `err_priority` parameter is used to determine the severity of the
        error. It is an optional parameter with a default value of 0. The possible values for
        `err_priority` are:, defaults to 0 (optional)
        """
        try:
            err = f'{err.__class__.__name__}: {err}'
            match err_priority:
                case 0:
                    if self.update_state(f'WARNING: {err}', False):
                        self.logger.warning(err)
                case 1:
                    if self.update_state(f'ERROR: {err}', False):
                        self.logger.error(err)
                case 2:
                    self.logger.critical(err)
                    self.update_state(f'CRITICAL: {err}', False)
                    sleep(.5)
                    exit()
        except Exception as err1: # something happened to the logger
            print(f'Couldn\'t log error!!! {err1} \n {err}')


    def stop_app(self):
        try:
            exit()
        except Exception as err:
            self.process_error(err, 1)
            exit()

    
if __name__ == '__main__':
    refrig_core = RefrigControlsCore()
    refrig_core.run()