import refrig_ui_mainwindow
from PySide6 import QtCore, QtWidgets
from PySide6.QtWidgets import QMessageBox
import refrig_widgets
from time import sleep
import paho.mqtt.client as mqtt
import logging
from pathlib import Path


class refrigMainWindow(refrig_ui_mainwindow.Ui_MainWindow):

    update_time_milisecs = 2000
    main_window = None
    sens_data = {}

    def __init__(self, mw) -> None:
        try:
            #init logger:
            self.cur_path = self.get_cur_path()
            self.logger = self.init_logger(self.cur_path.joinpath('logs'))
        except Exception as err:
            print(f'Critical error at logger init, stopping: {err.__class__.__name__}:{err}')
            exit()
        try:
            self.ext_iface_cfg, self.indicator_cfg = self.read_config(self.cur_path.joinpath('gui_config.yaml'))
            super().__init__()
            self.setupUi(mw) # init interface
            for obj in self.main_window.findChildren(refrig_widgets.ValveWidget):
                obj.mw = self
            self.mqtt_iface = mqtt_iface(self.ext_iface_cfg, self.read_callback, self.process_error)
            self.update_state('OK')
            # make update timer (SHOULD BE SET AT THE VERY END OF INIT):
            self.update_timer = QtCore.QTimer(self.main_window)
            self.update_timer.timeout.connect(self.get_metrics)
            self.update_timer.start(self.update_time_milisecs)
        except Exception as err:
            self.process_error(err, 2)


    def get_cur_path(self):
        import os, sys
        if getattr(sys, 'frozen', False):
            cur_path = os.path.dirname(sys.executable)
        elif __file__:
            cur_path = os.path.dirname(__file__)
        return Path(cur_path)


    def init_logger(self, logs_path):
        from datetime import date
        try:
            logs_path.mkdir(parents=True, exist_ok=True)
            logs_fname = logs_path.joinpath(f'gui_log_{date.today()}.txt')
            self.logger_handler = logging.FileHandler(filename=logs_fname, mode='a')
            self.logger_handler.setFormatter(logging.Formatter(fmt='[%(asctime)s: %(levelname)s] %(message)s'))
            logger = logging.getLogger('refrig_gui_logger')
            logger.setLevel(logging.DEBUG)
            logger.addHandler(self.logger_handler)
            return logger
        except Exception as err:
            raise type(err)(f'init_logger: {err}')


    def read_config(self, cfg_path):
        import yaml
        try:
            with open(cfg_path, "r") as stream:
                cfg = yaml.safe_load(stream)
                self.logger.setLevel(logging.getLevelName(cfg['logging']['level'])) # set logging level from file
                ext_iface_cfg = cfg.pop('external_iface')
                indicator_cfg = cfg['indicators']
            return ext_iface_cfg, indicator_cfg
        except Exception as err:
            raise type(err)(f'read_config: {err}')


    def setupUi(self, mw):
        '''
        Init interface, widgets, set thresholds for sensor widgets
        '''
        try:
            super().setupUi(mw)
            bcg_path = str(self.cur_path.joinpath('icons','bcg.png')).replace('\\','/') # PySide is retarded
            self.frame.setStyleSheet(f"background: url({bcg_path})")
            self.main_window = mw
            for obj in self.main_window.findChildren(refrig_widgets.SensWidget):  # set thresholds
                vals = self.indicator_cfg.get(obj.objectName())
                if vals:
                    if len(vals) == 2: # no unit specified
                        obj.set_thresholds(float(vals['min_value']), float(vals['max_value']), '')
                    else: # thresholds and unit specified
                        obj.set_thresholds(float(vals['min_value']), float(vals['max_value']), vals['unit'])
        except Exception as err:
            self.process_error(f'setupUI: {err}')


    def read_callback(self, dev_name, value):
        self.sens_data.update({dev_name:value})


    def get_metrics(self): 
        try:
            #look for every sensor device name in response dict and update widget values
            for obj in self.main_window.findChildren(refrig_widgets.SensWidget):
                val = self.sens_data.get(obj.objectName(), None)
                if val==None: # log no responce
                    self.logger.info(f'No responce from {obj.objectName()}')
                obj.update_value(val)
            #same for valves (feedback)
            for obj in self.main_window.findChildren(refrig_widgets.ValveWidget):
                val = self.sens_data.get(f'{obj.objectName()}_fb', None)
                if val==None: # log no responce
                    self.logger.info(f'No responce from {obj.objectName()}_fb')
                obj.update_value(val)
            #and for turbo pumps
            for obj in self.main_window.findChildren(refrig_widgets.TurboPumpWidget):
                val = self.sens_data.get(f'{obj.objectName()}_State', None)
                obj.update_value(val)
            self.update_timer.start(self.update_time_milisecs)  # reset timer
        except Exception as err:
            self.process_error(type(err)(f'get_metrics: {err}'))


    def send_command(self, device_name: str, command: int):
        self.mqtt_iface.send_command({device_name:command})


    #error handling
    def update_state(self, new_state, log_state=True):
        self.state = new_state
        if log_state:
            self.logger.info(f'State is now {new_state}')


    def process_error(self, err, err_priority=0):
        try:
            err = f'{err.__class__.__name__}: {err}'
            print(err)
            match err_priority:
                case 0:
                    self.logger.warn(err)
                    self.update_state(f'WARNING: {err}', False)
                case 1:
                    self.logger.error(err)
                    self.update_state(f'ERROR: {err}', False)
                    self.show_error(f'ERROR: {err}')
                case 2:
                    self.logger.critical(err)
                    self.update_state(f'CRITICAL: {err}', False) 
                    self.show_error(f'CRITICAL: {err}')
                    exit()               
        except Exception as err1:
            print(f'Couldn\'t show/log error!!! {err1} \n {err}')


    def show_error(self, msg: str): 
        '''
        show error and terminate application
        '''
        self.logger.critical(msg)
        error_dialog = QMessageBox()
        error_dialog.setIcon(QMessageBox.Critical)
        error_dialog.setText("Error")
        error_dialog.setInformativeText(msg)
        error_dialog.setWindowTitle("Error")
        error_dialog.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        error_dialog.exec_()
        

class mqtt_iface():
    def __init__(self, iface_cfg, read_callback, err_handler) -> None:
        self.process_error = err_handler
        self.con_info = iface_cfg
        self.read_callback = read_callback
        self.mqtt_client = mqtt.Client()
        self.connect_iface()


    def connect_iface(self):
        try:
            self.mqtt_client.username_pw_set(self.con_info['username'], self.con_info['password'])
            self.mqtt_client.connect(host=self.con_info['ip'], port=int(self.con_info['port']), keepalive=60, )
            self.mqtt_client.on_message = self.process_read
            self.mqtt_client.subscribe(f'refrig/#')
            self.mqtt_client.unsubscribe(f'refrig/Command')
            self.mqtt_client.loop_start()
        except Exception as err:
            raise type(err)(f'External mqtt_iface: connect_iface: {err}')
        

    def send_command(self, values_dict:dict):
        try:
            for cur_device, cur_value in values_dict.items():
                self.mqtt_client.publish(f'refrig/Command', f'{cur_device} {cur_value}')
        except Exception as err:
            raise type(err)(f'External mqtt_iface: send: {err}')
        return
    

    def process_read(self, client, userdata, msg):
        try:
            dev_name = msg.topic.split("/")[-1]
            value = f'{msg.payload.decode()}'
            if dev_name not in ['State', 'Status', 'Command']:
                value = float(value)
            self.read_callback(dev_name, value)
        except Exception as err:
            self.process_error(type(err)(f'process_read: {err}'))