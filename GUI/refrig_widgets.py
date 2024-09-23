from PySide6 import QtCore, QtGui, QtWidgets
import os, sys

# cur_path = str(os.path.dirname(os.path.realpath(__file__))).replace('\\', '/')
if getattr(sys, 'frozen', False):
    cur_path = os.path.dirname(sys.executable)
elif __file__:
    cur_path = os.path.dirname(__file__)

cur_path = str(cur_path.replace('\\', '/'))

ref_font = QtGui.QFont("Arial", 13, weight=700)
int_validator = QtGui.QIntValidator()
int_validator.setRange(0, 100)

turbine_validator = QtGui.QIntValidator()
turbine_validator.setRange(0, 1000)


class ValveWidget(QtWidgets.QWidget):
    '''
    abstract class for valve widgets
    '''
    value = None
    red_icon_pathname = None
    green_icon_pathname = None
    purple_icon_pathname = None
    label_height = None
    label_width = None
    label_indent = None
    label_spacer = None
    p_win = None
    mw = None

    def __init__(self, parent):
        super().__init__(parent)
        # make label
        self.label = QtWidgets.QLabel(self)
        self.label.setGeometry(QtCore.QRect(0, 0, self.label_width, self.label_height))
        self.label.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.label.setAutoFillBackground(False)
        self.label.setLineWidth(0)
        self.label.setAlignment(QtCore.Qt.AlignmentFlag.AlignBottom | QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.NoTextInteraction)
        self.label.setStyleSheet(f"background: url({self.red_icon_pathname}.png); border: 0px")
        self.label.setFont(ref_font)
        self.label.setIndent(self.label_indent)
        self.label.mousePressEvent = self.call_control_window


    def setObjectName(self,
                      name: str):  # set object name and label text simultaneously (т.к. десигнер даёт имя объекту в самую последнюю очередь, на момент _init_ мы не знаем его имя)
        super().setObjectName(name)
        self.label.setText(self.label_spacer + name)


    def call_control_window(self, event):
        # print('window')
        if self.p_win is None:
            self.p_win = ValvePopupWindow(self, position=self.pos())
        else:
            self.p_win.activateWindow()
            self.p_win.raise_()


    def update_value(self, val):
        '''
        Updates value and color of widget
        '''
        if val is None or val<0 or val>100:  # input value is not a number or incorrect value:
            val = 'N/A'
            self.label.setStyleSheet(f"background:  url({self.purple_icon_pathname}.png); border: 0px")
        elif val <= 2:
            self.label.setStyleSheet(f"background:  url({self.red_icon_pathname}.png); border: 0px")
            val = "%0.f" % val
        else:
            self.label.setStyleSheet(f"background:  url({self.green_icon_pathname}.png); border: 0px")
            val = "%0.f" % val
        self.value = val
        if self.p_win is not None:
            self.p_win.update_state(val)


    def set_value(self, val):
        if val not in range(0, 101):
            print(f'{self.objectName()} - Incorrect value')
            return
        self.mw.send_command(self.objectName(), int(val))


class ValveHorVidget(ValveWidget):
    def __init__(self, parent):
        self.red_icon_pathname = f'{cur_path}/icons/valve_hor_red'
        self.green_icon_pathname = f'{cur_path}/icons/valve_hor_green'
        self.purple_icon_pathname = f'{cur_path}/icons/valve_hor_purple'
        self.label_height = 70
        self.label_width = 60
        self.label_indent = 4
        self.value = 0
        self.label_spacer = ''
        super().__init__(parent)


class ValveVertVidget(ValveWidget):
    def __init__(self, parent):
        self.red_icon_pathname = f'{cur_path}/icons/valve_vert_red'
        self.green_icon_pathname = f'{cur_path}/icons/valve_vert_green'
        self.purple_icon_pathname = f'{cur_path}/icons/valve_vert_purple'
        self.label_height = 60
        self.label_width = 90
        self.label_indent = 20
        self.value = 0
        self.label_spacer = '     '
        super().__init__(parent)


class ForVacPumpWidget(ValveWidget):
    def __init__(self, parent):
        self.red_icon_pathname = f'{cur_path}/icons/forvac_pump_red'
        self.green_icon_pathname = f'{cur_path}/icons/forvac_pump_green'
        self.purple_icon_pathname = f'{cur_path}/icons/forvac_pump_purple'
        self.label_height = 50
        self.label_width = 50
        self.label_indent = 4
        self.value = 0
        self.label_spacer = ''
        super().__init__(parent)
    

    def setObjectName(self, name: str): # override ValveWidget
        super().setObjectName(name)
        self.label.setText('')


class RegulatedValveWidget(ValveWidget):
    def __init__(self, parent):
        super().__init__(parent)


    def update_value(self, val):
        '''
        Override of ValveWidget function.
        Updates value and sets new icon depending on current position
        '''
        if val is None:  # input value is not a number (or no value):
            val = 'N/A'
            self.label.setStyleSheet(f"background:  url({self.purple_icon_pathname}.png); border: 0px")
        elif val<0 or val>100: # incorrect feedback value check
            self.label.setStyleSheet(f"background:  url({self.purple_icon_pathname}.png); border: 0px")
            val = "%0.f" % val
        elif val <= 2: # less then 2% = closed (red)
            self.label.setStyleSheet(f"background:  url({self.red_icon_pathname}.png); border: 0px")
            val = "%0.f" % val
        else: # opened to some extend
            cur_rang = int((val // 25+1) *25) # get the range of current value (0-25, 25-50, 50-75, 75-100), gives bad result for 100%
            if cur_rang>100: # check for bad result
                cur_rang = 100
            # choose an icon depending on current valve position:
            self.label.setStyleSheet(f"background:  url({self.green_icon_pathname+str(cur_rang)}.png); border: 0px") 
            val = "%0.f" % val
        self.value = val # update value
        # we need to update values for popup window if it exists:
        if self.p_win is not None:
            self.p_win.update_state(val)
        self.label.setText(f'{self.label_spacer + self.objectName()}\n {self.label_spacer}{self.value}% ')


    def call_control_window(self, event):  # override ValveWidget's method
        if self.p_win is None:
            self.p_win = ValveRegPopupWindow(self, position=self.pos())
        else:
            self.p_win.activateWindow
            self.p_win.raise_()


class ValveRegHorWidget(RegulatedValveWidget):
    '''
    regulated horizontal valve widget
    '''
    def __init__(self, parent):
        self.red_icon_pathname = f'{cur_path}/icons/reg_valve_hor_red'
        self.green_icon_pathname = f'{cur_path}/icons/reg_valve_hor_green'
        self.purple_icon_pathname = f'{cur_path}/icons/reg_valve_hor_purple'
        self.label_height = 95
        self.label_width = 60
        self.label_indent = 0
        self.value = 0
        self.label_spacer = ' '
        super().__init__(parent)


class ValveRegVertWidget(RegulatedValveWidget):
    '''
    regulated vertical valve widget
    '''
    def __init__(self, parent):
        self.red_icon_pathname = f'{cur_path}/icons/reg_valve_vert_red'
        self.green_icon_pathname = f'{cur_path}/icons/reg_valve_vert_green'
        self.purple_icon_pathname = f'{cur_path}/icons/reg_valve_vert_purple'
        self.label_height = 60
        self.label_width = 110
        self.label_indent = 10
        self.value = 0
        self.label_spacer = '           '
        super().__init__(parent)


class ValvePopupWindow(QtWidgets.QWidget):
    '''
    Popup control window for non-regulated valve
    '''
    cur_obj = None

    def __init__(self, obj, position):
        super().__init__()
        self.cur_obj = obj
        self.setGeometry(QtCore.QRect(position.x(), position.y(), 262, 89))
        self.setWindowTitle(str(obj.objectName()) + ' control panel')
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.make_elements()
        self.show()


    def make_elements(self):
        '''
        make interface
        '''
        self.open_button = QtWidgets.QPushButton(self)
        self.open_button.setGeometry(QtCore.QRect(0, 50, 131, 41))
        self.open_button.setText("Open")
        self.open_button.clicked.connect(lambda: self.cur_obj.set_value(1))
        self.close_button = QtWidgets.QPushButton(self)
        self.close_button.setGeometry(QtCore.QRect(130, 50, 131, 41))
        self.close_button.setText("Close")
        self.close_button.clicked.connect(lambda: self.cur_obj.set_value(0))
        self.label = QtWidgets.QLabel(self)
        self.label.setGeometry(QtCore.QRect(20, 0, 91, 51))
        self.label.setText(str(self.cur_obj.objectName()) + ' state: ')
        self.label_2 = QtWidgets.QLabel(self)
        self.label_2.setGeometry(QtCore.QRect(130, 0, 91, 51))
        self.update_state(self.cur_obj.value)


    def update_state(self, val):
        '''
        update interface with new position
        '''
        if val == 0:
            self.label_2.setText('CLOSED')
            self.label_2.setStyleSheet('font-weight: bold; color: red')
        else:
            self.label_2.setText('ONLINE')
            self.label_2.setStyleSheet('font-weight: bold; color: green')


    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        '''
        delete window from widget attributes
        '''
        self.cur_obj.p_win = None
        super().closeEvent(event)


class ValveRegPopupWindow(QtWidgets.QWidget):
    '''
    Popup control window for regulated valve
    '''
    cur_obj = None


    def __init__(self, obj, position):
        super().__init__()
        self.cur_obj = obj
        self.setGeometry(QtCore.QRect(position.x(), position.y(), 200, 130))
        self.setWindowTitle(str(obj.objectName()) + ' control panel')
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.make_elements()
        self.show()


    def make_elements(self):
        '''
        make interface
        '''
        self.label = QtWidgets.QLabel(self)
        self.label.setGeometry(QtCore.QRect(10, 10, 90, 30))
        self.label.setText(str(self.cur_obj.objectName()) + ' state: ')
        self.label_2 = QtWidgets.QLabel(self)
        self.label_2.setGeometry(QtCore.QRect(90, 10, 100, 30))
        self.posSlider = QtWidgets.QSlider(self)
        self.posSlider.setGeometry(QtCore.QRect(10, 100, 180, 24))
        self.posSlider.setRange(0, 100)
        self.posSlider.setSingleStep(1)
        self.posSlider.setPageStep(10)
        self.posSlider.setOrientation(QtCore.Qt.Orientation.Horizontal)
        self.posSlider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        self.posSlider.setTickInterval(10)
        self.posSlider.setObjectName("posSlider")
        if self.cur_obj.value == 'N/A':
            self.posSlider.setSliderPosition(0)
        else:
            self.posSlider.setSliderPosition(int(self.cur_obj.value))
        self.label_3 = QtWidgets.QLabel(self)
        self.label_3.setGeometry(QtCore.QRect(10, 60, 80, 30))
        self.label_3.setText("Set to:")
        self.posEdit = QtWidgets.QLineEdit(self)
        self.posEdit.setGeometry(QtCore.QRect(80, 60, 40, 30))
        self.posEdit.setText("0")
        self.posEdit.setValidator(int_validator)
        self.pushButton = QtWidgets.QPushButton(self)
        self.pushButton.setGeometry(QtCore.QRect(120, 60, 75, 30))
        self.pushButton.setText("Set")
        self.update_state(self.cur_obj.value)

        self.posSlider.valueChanged.connect(lambda: self.posEdit.setText(str(self.posSlider.value())))
        self.pushButton.clicked.connect(lambda: self.cur_obj.set_value(int(self.posEdit.text())))

    def update_state(self, val):
        '''
        update interface with new position
        '''
        if val == 0:
            self.label_2.setText('CLOSED')
            self.label_2.setStyleSheet('font-weight: bold; color: red')
        else:
            self.label_2.setText(f'OPENED AT {val}%')
            self.label_2.setStyleSheet('font-weight: bold; color: green')
        if val in range(0, 101):
            self.posSlider.setValue(val)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        '''
        delete window from widget attributes
        '''
        self.cur_obj.p_win = None
        super().closeEvent(event)


class SensWidget(QtWidgets.QWidget): 

    '''
    Class for sensor widgets (temperature and pressure)
    '''

    red_icon_pathname = f'{cur_path}/icons/sens_red'
    green_icon_pathname = f'{cur_path}/icons/sens_green'
    purple_icon_pathname = f'{cur_path}/icons/sens_purple'
    widget_height = 40
    widget_width = 90
    mw = None


    def __init__(self, parent):
        super().__init__(parent)
        self.state = 0  # 0 = red, 1 = green, -1 = purple

        # pre init of thresholds, low is bigger then high so it stays forever red
        self.low_threshold = 0
        self.high_threshold = -1
        self.unit = ''
        self.make_elements()


    def make_elements(self):
        self.label = QtWidgets.QLabel(self)
        self.label.setGeometry(QtCore.QRect(0, 0, self.widget_width, self.widget_height))
        self.label.setAutoFillBackground(False)
        self.label.setLineWidth(0)
        self.label.setAlignment(QtCore.Qt.AlignmentFlag.AlignBottom | QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.NoTextInteraction)
        self.label.setStyleSheet(f"background: url({self.purple_icon_pathname}.png); border: 0px;")
        self.label.setFont(ref_font)
        self.label.setMargin(0)
        self.label.setText(f'{self.objectName()}\nN/A')
        # self.label.setMargin(8)


    def set_thresholds(self, low_val, high_val, unit):
        if (not isinstance(low_val, (int, float))) or (not isinstance(high_val, (int, float))):
            return  # :(
        self.low_threshold = low_val
        self.high_threshold = high_val
        if isinstance(unit, str):
            self.unit = unit

    def update_value(self, value):
        '''
        Updates value and sets widget icon depending on value and thresholds
        '''
        if not isinstance(value, (int, float)):  # input value is not a number (or no value)
            self.label.setText(f'{self.objectName()}\nN/A')
            self.set_purple()
            # print(f'aaa {self.objectName()} {value}')
            return
        # change label text and colour
        self.label.setText(f'{self.objectName()}\n {self.format_value(value)} {self.unit} ')
        if (value < self.low_threshold) or (value > self.high_threshold):
            self.set_red()
        else:
            self.set_green()


    def format_value(self, val):
        if val == 0:
            return '0'
        if val%1==0:
            return "%d" % val
        if abs(val) >= 0.01 and abs(val) <= 9999:
            return "%0.2f" % val
        return "%0.1e" % val


    def set_red(self):
        self.label.setStyleSheet(f"background: url({self.red_icon_pathname}.png); border: 0px;")
        self.state = 0


    def set_green(self):
        self.label.setStyleSheet(f"background: url({self.green_icon_pathname}.png); border: 0px;")
        self.state = 1


    def set_purple(self):
        self.label.setStyleSheet(f"background: url({self.purple_icon_pathname}.png); border: 0px;")
        self.state = -1


class TemperatureSensWidget(SensWidget):

    '''
    Overrides SensWidget with round icons
    '''

    def __init__(self, parent):
        self.red_icon_pathname = f'{cur_path}/icons/round_sens_red'
        self.green_icon_pathname = f'{cur_path}/icons/round_sens_green'
        self.purple_icon_pathname = f'{cur_path}/icons/round_sens_purple'
        super().__init__(parent)


class TurboPumpWidget(ValveWidget):

    def __init__(self, parent):
        self.red_icon_pathname = f'{cur_path}/icons/vac_pump_red'
        self.green_icon_pathname = f'{cur_path}/icons/vac_pump_green'
        self.purple_icon_pathname = f'{cur_path}/icons/vac_pump_purple'
        self.label_height = 50
        self.label_width = 50
        self.label_indent = 4
        self.value = 0
        self.label_spacer = ''
        super().__init__(parent)
    

    def setObjectName(self, name: str): # override ValveWidget
        super().setObjectName(name)
        self.label.setText('')


    def call_control_window(self, event):
        # print('window')
        if self.p_win is None:
            self.p_win = TurboPumpPopupWindow(self, position=self.pos())
        else:
            self.p_win.activateWindow()
            self.p_win.raise_()


    def set_value(self, cmd):
        self.mw.send_command(self.objectName(), f'{cmd}')


    def update_value(self, val):
        if val is None:
            self.set_purple()
            return
        if val ==1:#== 'True':
            self.set_green()
        elif val==0:# == 'False':
            self.set_red()
        else:
            self.set_purple()
        if self.p_win is not None:
            self.p_win.update_state(val)


    def set_red(self):
        self.label.setStyleSheet(f"background: url({self.red_icon_pathname}.png); border: 0px;")
        self.state = 0


    def set_green(self):
        self.label.setStyleSheet(f"background: url({self.green_icon_pathname}.png); border: 0px;")
        self.state = 1


    def set_purple(self):
        self.label.setStyleSheet(f"background: url({self.purple_icon_pathname}.png); border: 0px;")
        self.state = -1

        


class TurboPumpPopupWindow(QtWidgets.QWidget):
    '''
    Popup control window for turbo pump control
    '''
    cur_obj = None

    def __init__(self, obj, position):
        super().__init__()
        self.cur_obj = obj
        self.setGeometry(QtCore.QRect(position.x(), position.y(), 450, 130))
        self.setWindowTitle(str(obj.objectName()) + ' control panel')
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.make_elements()
        self.show()


    def make_elements(self):
        '''
        make interface
        '''
        self.label = QtWidgets.QLabel(self)
        self.label.setGeometry(QtCore.QRect(10, 10, 90, 30))
        self.label.setText(str(self.cur_obj.objectName()) + ' state')
        self.label_2 = QtWidgets.QLabel(self)
        self.label_2.setGeometry(QtCore.QRect(90, 10, 100, 30))
        self.posSlider = QtWidgets.QSlider(self)
        self.posSlider.setGeometry(QtCore.QRect(10, 100, 180, 24))
        self.posSlider.setRange(0, 1000)
        self.posSlider.setSingleStep(1)
        self.posSlider.setPageStep(10)
        self.posSlider.setOrientation(QtCore.Qt.Orientation.Horizontal)
        self.posSlider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        self.posSlider.setTickInterval(100)
        self.posSlider.setObjectName("posSlider")
        if self.cur_obj.value == 'N/A':
            self.posSlider.setSliderPosition(0)
        else:
            self.posSlider.setSliderPosition(int(self.cur_obj.value))
        self.label_3 = QtWidgets.QLabel(self)
        self.label_3.setGeometry(QtCore.QRect(10, 60, 80, 30))
        self.label_3.setText("Set to:")
        self.posEdit = QtWidgets.QLineEdit(self)
        self.posEdit.setGeometry(QtCore.QRect(80, 60, 40, 30))
        self.posEdit.setText("0")
        self.posEdit.setValidator(turbine_validator)
        self.setpointButton = QtWidgets.QPushButton(self)
        self.setpointButton.setGeometry(QtCore.QRect(120, 60, 75, 30))
        self.setpointButton.setText("Set freq")
        self.startButton = QtWidgets.QPushButton(self)
        self.startButton.setGeometry(QtCore.QRect(200, 60, 75, 30))
        self.startButton.setText("Start")
        self.stopButton = QtWidgets.QPushButton(self)
        self.stopButton.setGeometry(QtCore.QRect(280, 60, 75, 30))
        self.stopButton.setText("Stop")
        self.controlButton = QtWidgets.QPushButton(self)
        self.controlButton.setGeometry(QtCore.QRect(360, 60, 75, 30))
        self.controlButton.setText("Control")
        self.update_state(self.cur_obj.value)

        self.posSlider.valueChanged.connect(lambda: self.posEdit.setText(str(self.posSlider.value())))
        self.setpointButton.clicked.connect(lambda: self.cur_obj.set_value(f'setpoint {self.posEdit.text()}'))
        self.startButton.clicked.connect(lambda: self.cur_obj.set_value(f'start'))
        self.stopButton.clicked.connect(lambda: self.cur_obj.set_value(f'stop'))
        self.controlButton.clicked.connect(lambda: self.cur_obj.set_value(f'control'))


    def update_state(self, val):
        '''
        update interface with new position
        '''
        if val == 0:
            self.label_2.setText(' OFF')
            self.label_2.setStyleSheet('font-weight: bold; color: red')
            # self.cur_obj.set_red()
        elif val == 1:
            self.label_2.setText(f' RUNNING')
            self.label_2.setStyleSheet('font-weight: bold; color: green')
        else:
            self.label_2.setText(f' UNKNOWN')
            self.label_2.setStyleSheet('font-weight: bold; color: purple')
            # self.cur_obj.set_green()
        # if val in range(0, 1000):
        #     self.posSlider.setValue(val)


    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        '''
        delete window from widget attributes
        '''
        self.cur_obj.p_win = None
        super().closeEvent(event)
