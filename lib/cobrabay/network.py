####
# Cobra Bay - Network
#
# Connects to the network to report bay status and take basic start/stop commands.
####

import board, busio, microcontroller, supervisor
from digitalio import DigitalInOut
import adafruit_requests as requests
import adafruit_esp32spi.adafruit_esp32spi_socket as socket
from adafruit_esp32spi import adafruit_esp32spi
from adafruit_esp32spi import adafruit_esp32spi_wifimanager
import adafruit_esp32spi.adafruit_esp32spi_socket as socket
import adafruit_minimqtt.adafruit_minimqtt as MQTT
from math import floor
import adafruit_logging as logging

class Network:
    def __init__(self,config):
        # Create the logger.
        self._logger = logging.getLogger('network')
        self._logger.info('Network: Initializing...')
        # Save the config.
        self._config = config
        try:
            from secrets import secrets
            self.secrets = secrets
        except ImportError:
            self._logger.error('Network: No secrets.py file, cannot get connection details.')
            raise

        # Convert the system_id to lower case and use that. Making everything in MQTT all lower-case just saves headache.
        self._system_id = self._config['global']['system_id'].lower()

        # List for commands to send upward.
        self._upward_commands = []

        self._bay_state = 'unknown'
        self._device_state = 'unknown'
        
        # Set up the on-board ESP32 pins. These are correct for the M4 Airlift. Check library reference for others.
        esp32_cs = DigitalInOut(board.ESP_CS)
        esp32_ready = DigitalInOut(board.ESP_BUSY)
        esp32_reset = DigitalInOut(board.ESP_RESET)
        
        # Create ESP object
        spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
        self.esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)

        # Setup ESP32

        if self.esp.status in (adafruit_esp32spi.WL_NO_SHIELD,adafruit_esp32spi.WL_NO_MODULE):
            self._logger.error('Network: No ESP32 module found!')
            raise IOError("No ESP32 module found!")
        elif self.esp.status is not adafruit_esp32spi.WL_IDLE_STATUS:
            # If ESP32 isn't idle, reset it.
            self._logger.warning('Network: ESP32 not idle. Resetting.')
            self.esp.reset()

        # Setup MQTT Client
        MQTT.set_socket(socket,self.esp)
        self._mqtt = MQTT.MQTT(
            broker = secrets['mqtt']['broker'],
            port = secrets['mqtt']['port'],
            username = secrets['mqtt']['user'],
            password = secrets['mqtt']['password'],
            client_id = self._system_id
            )

        # Set up Topics.
        self._topics = {
            'device_config': { 'topic': 'cobrabay/binary_sensor/' + self._system_id + '/config'},
            'device_state': { 'topic': 'cobrabay/binary_sensor/' + self._system_id + '/state' },
            'device_control': { 'topic': 'cobrabay/device/' + self._system_id + '/reset', 'callback': self._cb_device_reset },
            'bay_state': { 'topic': 'cobrabay/sensor/' + self._system_id + '/state' },
            'bay_dock': { 'topic': 'cobrabay/' + self._system_id + '/dock', 'callback': self._cb_bay_dock },
            'bay_undock': { 'topic': 'cobrabay/' + self._system_id + '/undock', 'callback': self._cb_bay_undock },
            'bay_abort': { 'topic': 'cobrabay/' + self._system_id + '/abort', 'callback': self._cb_bay_abort },
            'bay_verify': { 'topic': 'cobrabay/' + self._system_id + '/verify', 'callback': self._cb_bay_verify }
        }

        # Set up our last will. This ensures an offline message will be set if we go offline unexpectedly.
        self._mqtt.will_set('cobrabay/binary_sensor/' + self._system_id + '/state','offline')
        # Set up callbacks for topics we need to listen to.
        self._logger.info('Network: Attaching MQTT callbacks.')
        for item in self._topics:
            if 'callback' in self._topics[item]:
                self._mqtt.add_topic_callback(self._topics[item]['topic'],self._topics[item]['callback'])
                      
        self._logger.info('Network: Initialization complete.')

    # Topic Callbacks
    def _cb_message(self,client,topic,message):
        print("Got message on topic " + topic + ": " + message)

    def _cb_device_state(self,client,topic,message):
        pass

    def _cb_device_rescan_sensors(self,client,topic,message):
        self._upward_commands.append('rescan_sensors')

    # Reset command to the entire device. Does a hard reset to the controller.
    def _cb_device_reset(self,client,topic,message):
        self.Disconnect('resetting')
        microcontroller.reset()

    def _cb_bay_state(self,client,topic,message):
        pass

    # Command to start docking process.
    def _cb_bay_dock(self,client,topic,message):
        self._logger.debug('Network: Received dock command')
        self._upward_commands.append('dock')
        
    # Command to start undocking process. NOT YET IMPLEMENTED.
    def _cb_bay_undock(self,client,topic,message):
        self._logger.debug('Network: Received undock command')
        self._upward_commands.append('undock')
        
    # Command to immediately abort any in-progress dock or undock.
    def _cb_bay_abort(self,client,topic,message):
        self._logger.debug('Network: Received abort command')
        self._upward_commands.append('abort')
        
    # Command to verify occupancy status.
    def _cb_bay_verify(self,client,topic,message):
        self._logger.debug('Network: Received verify command')
        self._upward_commands.append('verify')

    # Publish out the bay's state.
    def _pub_bay_state(self,state):
        # If the state has changed, record it and publish it out. Otherwise, do nothing.
        if state != self._bay_state:
            self._bay_state = state
            self._mqtt.publish(self._topics['bay_state']['topic'],self._bay_state)

    def _pub_device_state(self,state):
        # If the state has changed, record it and publish it out. Otherwise, do nothing.
        if state != self._device_state:
            self._device_state = state
            self._mqtt.publish(self._topics['device_state']['topic'],self._device_state)

    # Method to be polled by the main run loop.
    # Main loop passes in the current state of the bay.
    def Poll(self,device_state,bay_state):
        # Send the device and bay state out for publishing.
        self._pub_device_state(device_state)
        self._pub_bay_state(bay_state)
        
        # Check for any incoming commands.
        self._mqtt.loop()
        
        # Yank any commands to send upward and clear it for the next run.
        upward_data = {
            'signal_strength': self._SignalStrength(),
            'mqtt_status': self._mqtt.is_connected(),
            'commands': self._upward_commands
            }
        self._upward_commands = []
        
        return upward_data

    def _Connect_Wifi(self):
        if self.esp.is_connected:
            raise UserWarning("Already connected. Recommended to explicitly disconnect first.")

        try_counter = 0
        while not self.esp.is_connected and try_counter < 5:
            try:
                self.esp.connect_AP(self.secrets["ssid"], self.secrets["password"])
            except RuntimeError as e:
                if try_counter >= 5:
                    self._logger.error('Network: Failed to connect to AP after five attempts.')
                    raise IOError("Could not connect to AP." + e)
                try_counter += 1
                continue
        
        self._logger.info('Network: Connected to ' + self.secrets["ssid"])
        
        return True

    def _Connect_MQTT(self):
        try:
            self._mqtt.connect()
        except Exception as e:
            self._logger.error('Network: Could not connect to MQTT broker.')
            self._logger.debug('Network: ' + str(e))
            raise

        # Subscribe to all the appropriate topics
        for item in self._topics:
            if 'callback' in self._topics[item]:
                    self._mqtt.subscribe(self._topics[item]['topic'])
        # Send a discovery message and an online notification.
        self._logger.info('Network: Sending online message')
        self._mqtt.publish('cobrabay/binary_sensor/' + self._system_id + '/state','online')

        return True

    # Convenience method to start everything network related at once.
    def Connect(self):
        try:
            self._Connect_Wifi()
        except Exception as e:
            raise
        try:
            self._Connect_MQTT()
        except Exception as e:
            raise
            
        return None

    # Reconnect function to call from the main event loop to reconnect if need be.
    def Reconnect(self):
        # If Wifi is down, we'll need to reconnect both Wifi and MQTT.
        if not self.esp.is_connected:
            self._logger.info('Network: Found network not connected. Reconnecting.')
            self.Connect()
        # If only MQTT is down, retry that.
        try:
            mqtt_status = self._mqtt.is_connected
        except:
            self._logger.info('Network: Found MQTT not connected. Reconnecting.')
            self._Connect_MQTT()
        return True

    def Disconnect(self,message = None):
        self._logger.info('Network: Planned disconnect with message "' + str(message) + '"')
        # If we have a disconnect message, send it to the device topic.
        if message is not None:
            self._mqtt.publish(self._topics['device_state']['topic'],message)
        else:
            self._mqtt.publish(self._topics['device_state']['topic'],'offline')
        self._mqtt.publish(self._topics['bay_state']['topic'],'unavailable')
        # Disconnect from broker
        self._mqtt.disconnect()
        # Disconnect from Wifi.
        self.esp.disconnect()
        
    # Get a 'signal strength' out of RSSI. Based on the Android algorithm. Probably has issues, but hey, it's something.
    def _SignalStrength(self):
        min_rssi = -100
        max_rssi = -55
        levels = 4
        if self.esp.rssi <= min_rssi:
            return 0
        elif self.esp.rssi >= max_rssi:
            return levels - 1
        else:
            input_range = -1*((min_rssi)-(max_rssi))
            output_range = levels - 1
            return floor((self.esp.rssi - min_rssi) * (output_range / input_range))
        