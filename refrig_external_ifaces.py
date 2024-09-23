# interface services for external applications (MQTT/OPC/???)
import paho.mqtt.client as mqtt

class mqtt_iface():
    def __init__(self, iface_cfg, cmd_callback, err_queue) -> None:
        self.con_info = iface_cfg
        self.cmd_callback = cmd_callback
        self.mqtt_client = mqtt.Client()
        self.err_queue = err_queue
        self.connect_iface()


    def connect_iface(self):
        try:
            self.mqtt_client.username_pw_set(self.con_info['username'], self.con_info['password'])
            self.mqtt_client.connect(host=self.con_info['ip'], port=int(self.con_info['port']), keepalive=60, )
            self.mqtt_client.on_message = self.process_command
            self.mqtt_client.subscribe(f'refrig/Command')
            self.mqtt_client.loop_start()
        except Exception as err:
            raise type(err)(f'External mqtt_iface: connect_iface: {err}')
        

    def send(self, values_dict:dict, retain=False):
        try:
            for cur_device, cur_value in values_dict.items():
                self.mqtt_client.publish(f'refrig/{cur_device}', cur_value, retain=retain)
        except Exception as err:
            raise type(err)(f'External mqtt_iface: send: {err}')
        return
    

    def process_command(self, client, userdata, msg):
        try:
            cmd = f'{msg.payload.decode()}'
            dev_name = cmd.split(' ')[0]
            cmd_value = cmd.replace(f'{dev_name} ', '', 1)
            self.cmd_callback(dev_name, cmd_value)
        except Exception as err:
            self.process_error(type(err)(f'process_command: {err}'))


    def on_connect(self, client, userdata, flags, rc):
        if rc!=0:
            self.process_error(ConnectionError(err = f'Could not connect to MQTT broker, return code: {rc}'), err_priority=1)


    def on_disconnect(self, client, userdata, rc):
        if rc!=0:
            self.process_error(ConnectionError(err = f'Lost connection to MQTT broker, return code: {rc}'), err_priority=1)


    def process_error(self, err, err_priority=0):
        try:
            self.err_queue.put_nowait({err:err_priority})
        except Exception as err1:
            print(f'{err.__class__.__name__}: {err1}')
