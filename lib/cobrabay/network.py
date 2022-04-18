####
# Cobra Bay - Network
#
# Connects to the network to report bay status and take various commands.
####

import board
import busio
import microcontroller
import json
from digitalio import DigitalInOut
import adafruit_esp32spi.adafruit_esp32spi_socket as socket
from adafruit_esp32spi import adafruit_esp32spi
import adafruit_minimqtt.adafruit_minimqtt as MQTT
from math import floor
import adafruit_logging as logging


class Network:
    def __init__(self, system_id, bay, homeassistant=False ):
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

        # Convert the system_id to lower case and use that.
        # Making everything in MQTT all lower-case just saves headache.
        self._system_id = system_id.lower()
        # Bay name
        self._bay_name = bay['name']
        # Set homeassistant integration state.
        self._homeassistant = homeassistant

        # Current device state. Will get updated every time we're polled.
        self._device_state = 'unknown'
        # Bay initial state.
        self._bay_state = 'unknown'

        # List for commands to send upward.
        self._upward_commands = []

        # Set up the on-board ESP32 pins. These are correct for the M4 Airlift. Check library reference for others.
        esp32_cs = DigitalInOut(board.ESP_CS)
        esp32_ready = DigitalInOut(board.ESP_BUSY)
        esp32_reset = DigitalInOut(board.ESP_RESET)
        
        # Create ESP object
        spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
        self.esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)

        # Setup ESP32

        if self.esp.status in (adafruit_esp32spi.WL_NO_SHIELD, adafruit_esp32spi.WL_NO_MODULE):
            self._logger.error('Network: No ESP32 module found!')
            raise IOError("No ESP32 module found!")
        elif self.esp.status is not adafruit_esp32spi.WL_IDLE_STATUS:
            # If ESP32 isn't idle, reset it.
            self._logger.warning('Network: ESP32 not idle. Resetting.')
            self.esp.reset()

        # Setup MQTT Client
        MQTT.set_socket(socket, self.esp)
        self._mqtt = MQTT.MQTT(
            broker=secrets['mqtt']['broker'],
            port=secrets['mqtt']['port'],
            username=secrets['mqtt']['user'],
            password=secrets['mqtt']['password'],
            client_id=self._system_id
            )

        # Define topic reference.
        self._topics = {
            'device_state': {'topic': 'cobrabay/device/' + self._system_id + '/state', 'ha_type': 'sensor',
                             'previous_state': None},
            'device_command': {'topic': 'cobrabay/device/' + self._system_id + '/set',
                             'callback': self._cb_device_command},
            'bay_state': {'topic': 'cobrabay/' + self._bay_name + '/state', 'ha_type': 'sensor',
                          'previous_state': None},
            'bay_command': {'topic': 'cobrabay/' + self._bay_name + 'set', 'ha_type': 'select',
                            'callback': self._cb_bay_command}
        }

        # For every topic that has a callback, add it.
        for item in self._topics:
            if 'callback' in self._topics[item]:
                self._logger.debug("Creating callback for {}".format(item))
                self._mqtt.add_topic_callback(self._topics[item]['topic'],self._topics[item]['callback'])
        # Create last will, goes to the device topic.
        self._logger.info("Setting up last will.")
        self._mqtt.will_set(self._topics['device_state']['topic'], 'offline')
            
        # Set up our last will. This ensures an offline message will be set if we go offline unexpectedly.
        # This sends to the 'device_state' topic.

        self._logger.info('Network: Initialization complete.')

    # Topic Callbacks

    # Device Command callback
    def _cb_device_command(self, client, topic, message):
        # Try to decode the JSON.
        try:
            message = json.loads(raw_message)
        except:
            self._logger.error("Could not decode JSON from MQTT message '{}' on topic '{}'".format(topic, raw_message))
            # Ignore the error itself, plow through.

        # Proceed on valid commands.
        if 'cmd' not in message:
            self._logger.error("MQTT message for topic {} does not contain a 'cmd' directive".format(topic))
        elif message['cmd'] in ('reset'):
            # For reset command, don't pass upward, just do it.
            self._logger.error("Received MQTT reset request. Doing it!")
            self.disconnect('requested_reset')
            microcontroller.reset()
        elif message['cmd'] == 'display_sensor':
            # If displaying a sensor, have to pass up other parameters as well.
            # Remove the command, since we already have that, then put the rest into the options field.
            del(message,'cmd')
            self._upward_commands({'cmd': 'display_sensor', 'options': message})
        elif message['cmd'] == 'rescan_sensors':
            self._upward_commands({'cmd': 'rescan_sensors'})
        else:
            self._logger.info("Received unknown MQTT device command '{}'".format(message['cmd']))

    # Bay Command callback
    def _cb_bay_command(self, client, topic, raw_message):
        # Try to decode the JSON.
        try:
            message = json.loads(raw_message)
        except:
            self._logger.error("Could not decode JSON from MQTT message '{}' on topic '{}'".format(topic,raw_message))
            # Ignore the message and return, as if we never got int.
            return

        # Proceed on valid commands.
        if 'cmd' not in message:
            self._logger.error("MQTT message for topic {} does not contain a cmd directive".format(topic))
        elif message['cmd'] in ('dock','undock','abort','verify'):
            # If it's a valid bay command, pass it upward.
            self._upward_commands.append({'cmd': message['cmd']})
        else:
            self._logger.info("Received unknown MQTT bay command '{}'".format(message['cmd']))

    # Message publishing method
    def _pub_message(self, topic, message, only_changed=False):
        # If we're only supposed to update on changes, and it hasn't changed, skip it.
        if only_changed:
            if message == self._topics[topic]['previous_state']:
                return
        self._topics[topic]['previous_state'] = message
        self._mqtt.publish(self._topics[topic]['topic'], message)

    # Method to be polled by the main run loop.
    # Main loop passes in the current state of the bay.
    def poll(self, outbound_messages = None):
        # Publish messages outbound
        if isinstance(outbound_messages,dict):
            # Send the device and bay state out for publishing.
            for message in outbound_messages:
                self._pub_message(message['topic'],message['message'],message['only_changed'])
        
        # Check for any incoming commands.
        self._mqtt.loop()
        
        # Yank any commands to send upward and clear it for the next run.
        upward_data = {
            'signal_strength': self._signal_strength(),
            'mqtt_status': self._mqtt.is_connected(),
            'commands': self._upward_commands
            }
        self._upward_commands = []
        
        return upward_data

    def _connect_wifi(self):
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

    def _connect_mqtt(self):
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
        self._mqtt.publish('cobrabay/binary_sensor/' + self._system_id + '/state', 'online')

        return True

    # Convenience method to start everything network related at once.
    def connect(self):
        try:
            self._connect_wifi()
        except Exception as e:
            raise
        try:
            self._connect_mqtt()
        except Exception as e:
            raise
            
        return None

    # Reconnect function to call from the main event loop to reconnect if need be.
    def reconnect(self):
        # If Wifi is down, we'll need to reconnect both Wifi and MQTT.
        if not self.esp.is_connected:
            self._logger.info('Network: Found network not connected. Reconnecting.')
            self.connect()
        # If only MQTT is down, retry that.
        try:
            mqtt_status = self._mqtt.is_connected
        except:
            self._logger.info('Network: Found MQTT not connected. Reconnecting.')
            self._connect_mqtt()
        return True

    def disconnect(self, message=None):
        self._logger.info('Network: Planned disconnect with message "' + str(message) + '"')
        # If we have a disconnect message, send it to the device topic.
        if message is not None:
            self._mqtt.publish(self._topics['device_state']['topic'], message)
        else:
            self._mqtt.publish(self._topics['device_state']['topic'], 'offline')
        self._mqtt.publish(self._topics['bay_state']['topic'], 'unavailable')
        # Disconnect from broker
        self._mqtt.disconnect()
        # Disconnect from Wifi.
        self.esp.disconnect()
        
    # Get a 'signal strength' out of RSSI. Based on the Android algorithm. Probably has issues, but hey, it's something.
    def _signal_strength(self):
        min_rssi = -100
        max_rssi = -55
        levels = 4
        if self.esp.rssi <= min_rssi:
            return 0
        elif self.esp.rssi >= max_rssi:
            return levels - 1
        else:
            input_range = -1*(min_rssi-max_rssi)
            output_range = levels - 1
            return floor((self.esp.rssi - min_rssi) * (output_range / input_range))
        