from abc import ABC, abstractmethod
import struct
from pathlib import Path
from math import sqrt


#to-be-called converter
class RefrigDataConverter():
    def __init__(self, core_path: Path | str) -> None:
        self.default_converter = DefaultConverter()
        self.valve_converter = ValveConverter()
        self.pressure_converter = PressureConverter()
        self.si_temp_converter = SiliconTemperatureConverter(core_path)

    
    def read_data_convert(self, converter_type, dev_name, value):
        match converter_type:
            case 'Valve':
                return self.valve_converter.read_data_convert(dev_name, value)
            case 'Pressure':
                return self.pressure_converter.read_data_convert(dev_name, value)
            case 'SiTemp':
                return self.si_temp_converter.read_data_convert(dev_name, value)
            case _:
                return self.default_converter.read_data_convert(dev_name, value)
            

    def write_data_convert(self, converter_type, dev_name, value):
        match converter_type:
            case 'Valve':
                return self.valve_converter.write_data_convert(dev_name, value)
            case _:
                return self.default_converter.write_data_convert(dev_name, value)


#Default converter
class DefaultConverter():

    def read_data_convert(self, dev_name, value): # convert data coming FROM device (with special cases)
        return value


    def write_data_convert(self, dev_name, value): # convert commands coming TO device
        return value
    

#VALVES
class ValveConverter(DefaultConverter):

    acc_range = [-2, 102] # range of acceptance [lower_bound, upper_bound]

    def read_data_convert(self, dev_name, value):
        try:
            match dev_name:
                case 'V13':
                    value = 100 - value
                    value = self.border_value_correct(value)
                case _:
                    value = self.border_value_correct(value)
            return value
        except Exception as err:
            raise type(err)(f'ValveConverter for {dev_name}: {err}')


    def border_value_correct(self, value):
        '''
        valves can return values slightly outside of (0,100) range 
        due to calibration errors
        correct those values to avoid user confusion;
        values that are far outside of this range are not touched, so
        they can be treated as incorrect
        '''
        if value<0 and value > self.acc_range[0]:
            value = 0
        elif value>100 and value < self.acc_range[1]:
            value = 100
        return value
    

    def write_data_convert(self, dev_name, value):
        if dev_name == 'V13':
            value = 100 - value
        return value


#PRESSURES
class PressureConverter(DefaultConverter):

    def read_data_convert(self, dev_name, value):
        try:
            match dev_name:
                case 'Pvac1' | 'Pvac2':
                    value*=1000
                case 'P2':
                    value+=12
                case _:
                    value = self.pressure_to_dec(value)
                    value = round(value,2)
            return value
        except Exception as err:
            raise type(err)(f'PressureConverter for {dev_name}: {err}')
    

    def pressure_to_dec(self, raw_data):
        '''
        transform keller pressure sensors to float decimal
        '''
        data = struct.unpack('!f',struct.pack('!I', int(raw_data[0:32], 2)))[0]
        data -=1
        # data *= 1000 # bar to mbar
        return data

    
#SiliconThermometry
class SiliconTemperatureConverter(DefaultConverter):
    def __init__(self, core_path:str | Path) -> None:
        try:
            self.si_therm_data = {}
            si_data_path = Path(core_path).joinpath('data', 'silicon_thermometry')
            for cur_file_name in list(si_data_path.iterdir()):
                cur_file = open(si_data_path.joinpath(cur_file_name), 'r')
                cur_sensor_name = cur_file.readline().split()[0]
                cur_sens_coefs = []
                while True:
                    cur_line = cur_file.readline()
                    if len(cur_line) == 0:
                        break
                    cur_sens_coefs.append(float(cur_line.split('=')[-1]))
                cur_file.close()
                self.si_therm_data.update({cur_sensor_name: cur_sens_coefs})
        except Exception as err:
            raise type(err)(f'SiliconTemperatureConverter init: {err}')
        

    def read_data_convert(self, dev_name, value):
        try:
            if dev_name not in self.si_therm_data.keys():
                T = round(-(sqrt((-0.00232 * value) + 17.59246) - 3.908) / 0.00116, 3)
                T += 273.15
                return T
            K = self.si_therm_data[dev_name]
            T = K[0] + K[1] * (1000.0 / value) + K[2] * (1000.0 / value) ** 2 + K[3] * (1000.0 / value) ** 3 + K[4] * (
                        1000.0 / value) ** 4 + K[5] * (1000.0 / value) ** 5 + K[6] * (1000.0 / value) ** 6
            return T
        except Exception as err:
            raise type(err)(f'SiliconTemperatureConverter for {dev_name}: {err}')