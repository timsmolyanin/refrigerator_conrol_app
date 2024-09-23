#interface to communicate with leybold turbovac pump
#use send_command(cmd, value) to operate
#cycle send_command('read_temp') to get metrics from turbine
#call get_attr_value to get last values
import serial
from time import sleep

class TurbineControl():
    
    def __init__(self, serial_port = 'COM1', baudrate = 19200) -> None:
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.cur_running = False
        self.cur_setpoint = 1000
        self.cur_freq_temper = 0
        self.cur_freq = 0
        self.cur_bearing_temper = 0
        self.cur_voltage = 0


    def connect_to_turbine(self):
        try:
            self.ser = serial.Serial(timeout=2)
            self.ser.baudrate = int(self.baudrate)
            self.ser.port = self.serial_port
            self.ser.open()
            self.ser.flush()
        except Exception as err:
            raise type(err)(f'turbine_control::connect_to_turbine : {err}')


    def exec_command(self, tele:bytearray):
        try:
            self.ser.write(tele)
        except Exception as err:
            raise type(err)(f'exec_command (serial error): {err}')


    #encoding/Decoding
    #control words process (bytes 12-13):
    def control_word_encode(self, start_bit, epd=1, PZD2=0):
        try:
            # c_word  = 0 | 1 << 10 # 10's bit is always 1
            c_word  = 0 | epd << 10 # enable processing data
            c_word |= start_bit << 0 # start/stop bit
            c_word |= PZD2 << 6 # setpoint
            #print(c_word)
            c_word = f'{c_word:04x}'
            return c_word
        except Exception as err:
            raise type(err)(f'control_word_encode: ')
    

    def control_word_decode(self, c_word):
        try:
            c_word = int(c_word,16)
            cur_running = bool(c_word & 0b1)
            is_setpoint = bool(c_word & 0b1000000)
            return cur_running, is_setpoint
        except Exception as err:
            raise type(err)(f'control_word_decode: ')
    

    #assemble message:
    def telegram_encode(self, start_bit = None, PZD2 = None, epd = None, in_bytes:dict|None = None):
        try:
            #process arguments default values
            if start_bit is None:
                start_bit = int(self.cur_running)
            if PZD2 is None:
                PZD2 = int(self.cur_running)
            if epd is None:
                epd = 1
            if in_bytes is None: # by default we set setpoint to cur_setpoint if running 
                if self.cur_running:
                    in_bytes = {13:f'{self.cur_setpoint:04x}'}
            # init with zeros:
            tele = f'{0:048x}'
            # fixed bytes add:
            tele = '02' + tele[2:]# start bit
            tele = tele[:2] + f'{22:02x}' + tele[4:]# tele length
            # bytes 12-13:
            cword = self.control_word_encode(start_bit, epd, PZD2)
            tele = tele[:11*2] + cword + tele[13*2:]
            # insert all other bytes:
            if in_bytes is not None:
                for cur_start_pos, cur_in_bytes in in_bytes.items():
                    tele = tele[:cur_start_pos*2] + cur_in_bytes + tele[(cur_start_pos * 2 + len(cur_in_bytes)):] 
            # calc checksum and encode:
            tele = self.telegram_checksum_add(tele)
            tele_bytes = bytearray()
            for i in range (0,len(tele),2):
                tele_bytes.append(int(tele[i:i+2],16))
            return tele_bytes
        except Exception as err:
            raise type(err)(f'telegram_encode: {err}')


    def telegram_checksum_add(self, tele:str):
        try:
            checksum = int(tele[0:2],16)
            for i in range (2,len(tele),2):
                cur_byte = int(tele[i:i+2],16)
                checksum = checksum ^ cur_byte
            tele=tele[:-2] + f'{checksum:02x}'
            return tele
        except Exception as err:
            raise type(err)(f'telegram_checksum_add: {err}')
    

    def telegram_decode(self, tele):
        try:
            tele = tele.hex()
            cur_control_word = tele[11*2:12*2]
            cur_running, cur_is_setpoint = self.control_word_decode(cur_control_word)
            if cur_is_setpoint:
                self.cur_setpoint = int(tele[13*2:15*2],16)
            else:
                self.cur_freq = int(tele[13*2:15*2],16)
            self.cur_freq_temper = int(tele[15*2:16*2],16)
            self.cur_bearing_temper = int(tele[19*2:21*2],16)
            return
        except Exception as err:
            raise type(err)(f'telegram_decode: {err}')


    #UNUSED
    def data_to_bytes(self, data): # convert 2-byte value to list of bytes
        data = f'{data:04x}'
        out_bytes_list = []
        for i in range (0,len(data),2):
            out_bytes_list.append(data[i:i+2])


    #control commands:
    def request_control(self):
        tele = self.telegram_encode()
        self.exec_command(tele)


    def start_turbine(self):
        setpoint = {13:f'{self.cur_setpoint:04x}'}
        tele = self.telegram_encode(start_bit=1, PZD2=1, in_bytes=setpoint)
        self.exec_command(tele)
        self.cur_running = True


    def stop_turbine(self):
        tele = self.telegram_encode(start_bit=0, PZD2=0, in_bytes={13:'0000'})
        self.exec_command(tele)
        sleep(0.1)
        tele = self.telegram_encode(start_bit=0, PZD2=0, epd=0, in_bytes={13:'0000'})
        self.exec_command(tele)
        self.cur_running = False

    
    def set_setpoint(self, value:int):
        setpoint = {13:f'{value:04x}'}
        tele = self.telegram_encode(in_bytes=setpoint)
        self.exec_command(tele)
        self.cur_setpoint = value

    
    def get_temperature(self):
        params = {3:'10', 4:'01'} # FIXME what's this????
        if self.cur_running:
            params.update({13:f'{self.cur_setpoint:04x}'})
        tele = self.telegram_encode(in_bytes=params)
        self.exec_command(tele)



    #external methods
    def get_attr_value(self, attr_name):
        try:
            match attr_name:
                case 'TBearing':
                    return self.cur_bearing_temper
                case 'TFreq':
                    return self.cur_freq_temper
                case 'Freq':
                    return self.cur_freq
                case 'Setpoint':
                    return self.cur_setpoint
                case 'State':
                    return int(self.cur_running)
                case 'Voltage':
                    return self.cur_voltage
                case _:
                    raise AttributeError('Unknown attribute name')
        except Exception as err:
            raise type(err)(f'TurbineControl.get_attr_value error for {attr_name}: {err}')
            
    
    def send_command(self, cmd_name, cmd_value):
        try:
            match cmd_name:
                case 'control':
                    self.request_control()
                case 'start':
                    self.start_turbine()
                case 'stop':
                    self.stop_turbine()
                case 'setpoint':
                    self.set_setpoint(value=int(cmd_value))
                case 'read_temp':
                    self.get_temperature()
        except Exception as err:
            raise type(err)(f'TurbineControl error while executing command \"{cmd_name}\": {err}')    


    #debugging tools:
    def print_tele(self, tele):
        tele1 = ''
        for i in range (0,len(tele)):
            if i%2 == 0:
                tele1 += ' '
            tele1 += tele[i]
        print(tele1.lstrip())


    def print_params(self):
        print(f'bearing temperature: {self.cur_bearing_temper}')
        print(f'frequency converter temperature: {self.cur_freq_temper}')
        print(f'frequency: {self.cur_freq}') 