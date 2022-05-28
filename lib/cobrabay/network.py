####
# Cobra Bay - Network
#
# Connects to the network to report bay status and take various commands.
####
import time

from .version import __version__
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
from unit import Unit
from unit import NaN


class Network:
    def __init__(self, config, bay):
        # Save the config
        self._config = config
        # Create the logger.
        self._logger = logging.getLogger('cobrabay')
        self._logger.info('Network: Initializing...')

        try:
            from secrets import secrets
            self.secrets = secrets
        except ImportError:
            self._logger.error('Network: No secrets.py file, cannot get connection details.')
            raise

        self._system_name = config['global']['system_name']
        # Bay name
        self._bay_name = bay.name
        # Set homeassistant integration state.
        try:
            self._homeassistant = config['global']['homeassistant']
        except:
            self._homeassistant = False

        # Save the bay object.
        self._bay = bay

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
        self._esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)
        self._mac_address = "".join([f"{i:X}" for i in self._esp.MAC_address_actual])

        # Set the Socket' library's interface to this ESP instance.
        socket.set_interface(self._esp)

        # Setup ESP32

        if self._esp.status in (adafruit_esp32spi.WL_NO_SHIELD, adafruit_esp32spi.WL_NO_MODULE):
            self._logger.error('Network: No ESP32 module found!')
            raise IOError("No ESP32 module found!")
        elif self._esp.status is not adafruit_esp32spi.WL_IDLE_STATUS:
            # If ESP32 isn't idle, reset it.
            self._logger.warning('Network: ESP32 not idle. Resetting.')
            self._esp.reset()

        # Setup MQTT Client
        MQTT.set_socket(socket, self._esp)
        self._mqtt = MQTT.MQTT(
            broker=secrets['mqtt']['broker'],
            port=secrets['mqtt']['port'],
            username=secrets['mqtt']['user'],
            password=secrets['mqtt']['password'],
            client_id=self._system_name.lower()
        )

        # Define topic reference.
        self._topics = {
            'device_connectivity': {
                'topic': 'cobrabay/' + self._mac_address + '/connectivity',
                'previous_state': {},
                'ha_discovery': {
                    'name': '{} Connectivity'.format(self._system_name),
                    'type': 'binary_sensor',
                    'entity': 'connectivity',
                    'device_class': 'connectivity',
                    'payload_on': 'online',
                    'payload_off': 'offline'
                }
            },
            'device_mem': {
                'topic': 'cobrabay/' + self._mac_address + '/mem',
                'previous_state': {},
                'ha_discovery': {
                    'type': 'sensor',
                    'name': 'Available Memory',
                    'entity': 'memory_free',
                    'unit_of_measurement': 'kB'
                }
            },
            'device_command': {
                'topic': 'cobrabay/' + self._mac_address + '/cmd',
                'callback': self._cb_device_command
                # 'ha_discovery': {
                #     'type': 'select'
                # }
            },
            'bay_occupied': {
                'topic': 'cobrabay/' + self._mac_address + '/' + self._bay_name + '/occupied',
                'previous_state': None,
                'ha_discovery': {
                    'type': 'binary_sensor',
                    'availability_topic': 'bay_state',
                    'name': 'Bay Occupied',
                    'entity': 'occupied',
                    'class': 'occupancy',
                    'payload_on': 'occupied',
                    'payload_off': 'vacant'
                }
            },
            'bay_state': {
                'topic': 'cobrabay/' + self._mac_address + '/' + self._bay_name + '/state',
                'previous_state': None,
                'ha_discovery': {
                    'type': 'sensor',
                    'name': 'Bay State',
                    'entity': 'state'
                }
            },
            'bay_position': {
                'topic': 'cobrabay/' + self._mac_address + '/' + self._bay_name + '/position',
                'ha_type': 'sensor',
                'previous_state': {
                    'type': 'multisensor',
                    'list': bay.position,
                }
            },
            'bay_sensors': {
                'topic': 'cobrabay/' + self._mac_address + '/' + self._bay_name + '/sensors',
                'previous_state': {},
                'ha_discovery': {
                    'type': 'multisensor',
                    'list': bay.sensor_list,  # Dict from which separate sensors will be created.
                    'aliases': config['sensors'],  # Dict with list alias names.
                    'icon': 'mdi:ruler'
                    # Conveniently, we use the same string identifier for units as Home Assistant!
                    # 'unit_of_measurement':
                }
            },
            'bay_command': {
                'topic': 'cobrabay/' + self._mac_address + '/' + self._bay_name + '/cmd',
                # 'ha_discovery': {
                #     'type': 'select'
                # },
                'callback': self._cb_bay_command
            }
        }

        # For every topic that has a callback, add it.
        for item in self._topics:
            if 'callback' in self._topics[item]:
                self._logger.debug("Network: Creating callback for {}".format(item))
                self._mqtt.add_topic_callback(self._topics[item]['topic'], self._topics[item]['callback'])
        # Create last will, goes to the device topic.
        self._logger.info("Network: Setting up last will.")
        self._mqtt.will_set(self._topics['device_connectivity']['topic'], 'offline')
        self._logger.info('Network: Initialization complete.')

    # Topic Callbacks

    # Device Command callback
    def _cb_device_command(self, client, topic, raw_message):
        # Try to decode the JSON.
        try:
            message = json.loads(raw_message)
        except:
            self._logger.error(
                "Network: Could not decode JSON from MQTT message '{}' on topic '{}'".format(topic, raw_message))
            # Ignore the error itself, plow through.
            return False

        # Proceed on valid commands.
        if 'cmd' not in message:
            self._logger.error("Network: MQTT message for topic {} does not contain a 'cmd' directive".format(topic))
        elif message['cmd'] in ('reset'):
            # For reset command, don't pass upward, just do it.
            self._logger.error("Network: Received MQTT reset request. Doing it!")
            self.disconnect('requested_reset')
            microcontroller.reset()
        elif message['cmd'] == 'rediscover':
            # Rerun Home Assistant discovery
            self._ha_discovery()
        elif message['cmd'] == 'display_sensor':
            # If displaying a sensor, have to pass up other parameters as well.
            # Remove the command, since we already have that, then put the rest into the options field.
            del message['cmd']
            self._upward_commands.append({'cmd': 'display_sensor', 'options': message})
        elif message['cmd'] == 'rescan_sensors':
            self._upward_commands.append({'cmd': 'rescan_sensors'})
        else:
            self._logger.info("Network: Received unknown MQTT device command '{}'".format(message['cmd']))

    # Bay Command callback
    def _cb_bay_command(self, client, topic, raw_message):
        # Try to decode the JSON.
        try:
            message = json.loads(raw_message)
        except:
            self._logger.error("Network: Could not decode JSON from MQTT message '{}' on topic '{}'"
                               .format(topic, raw_message))
            # Ignore the message and return, as if we never got int.
            return
        # Proceed on valid commands.
        if 'cmd' not in message:
            self._logger.error("Network: MQTT message for topic {} does not contain a cmd directive".format(topic))
        elif message['cmd'] in ('dock', 'undock', 'complete', 'abort', 'verify'):
            # If it's a valid bay command, pass it upward.
            self._upward_commands.append({'cmd': message['cmd']})
        else:
            self._logger.info("Network: Received unknown MQTT bay command '{}'".format(message['cmd']))

    # Message publishing method
    def _pub_message(self, topic, message, repeat=False):
        previous_state = self._topics[topic]['previous_state']
        # Send flag.
        send = False
        # By default, check to see if the data changed before sending it.
        if repeat is False:
            # Both strings, compare, process if different
            if isinstance(message, str) and isinstance(previous_state, str):
                if message != previous_state:
                    send = True
                else:
                    return
            elif isinstance(message, dict) and isinstance(previous_state, dict):
                for item in message:
                    if item not in previous_state:
                        send = True
                        break
                    if message[item] != previous_state[item]:
                        send = True
                        break
                return
            else:
                if type(message) != type(previous_state):
                    send = True
                else:
                    return
        # The 'repeat' option can be used in cases when a caller wants to send no matter the changed state.
        # Using this too much can make things super chatty.
        elif repeat is True:
            send = True
        if send:
            self._topics[topic]['previous_state'] = message
            if isinstance(message, dict):
                message = json.dumps(message)
            self._mqtt.publish(self._topics[topic]['topic'], message)

    # Method to be polled by the main run loop.
    # Main loop passes in the current state of the bay.
    def poll(self, outbound_messages=None):
        # Publish messages outbound
        for message in outbound_messages:
            if 'repeat' in message:
                repeat = True
            else:
                repeat = False
            self._pub_message(message['topic'], message['message'], repeat)

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
        if self._esp.is_connected:
            raise UserWarning("Already connected. Recommended to explicitly disconnect first.")
        connect_attempts = 0
        while not self._esp.is_connected:
            try:
                self._esp.connect_AP(self.secrets["ssid"], self.secrets["password"])
            except RuntimeError as e:
                    connect_attempts += 1
                    sleep_time = 30 * connect_attempts
                    self._logger.error('Network: Could not connect to AP. Made {} attempts. Sleeping for {}s'.
                                       format(connect_attempts,sleep_time))
                    time.sleep(sleep_time)
                    continue

        self._logger.info("Network: Connected to {} (RSSI: {})".format(str(self._esp.ssid, "utf-8"), self._esp.rssi))
        self._logger.info("Network: Have IP: {}".format(self._esp.pretty_ip(self._esp.ip_address)))
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
        print("Triggering Home Assistant Discovery...")
        if self._homeassistant:
            self._ha_discovery()
        self._mqtt.publish(self._topics['device_connectivity']['topic'], 'online')

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
        if not self._esp.is_connected:
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
        # if message is not None:
        #     self._mqtt.publish(self._topics['device_state']['topic'], message)
        # else:
        # When disconnecting, mark the device and the bay as unavailable.
        self._mqtt.publish(self._topics['device_connectivity']['topic'], 'offline')
        self._mqtt.publish(self._topics['bay_state']['topic'], 'offline')
        self._mqtt.publish(self._topics['bay_state']['topic'], 'offline')
        # Disconnect from broker
        self._mqtt.disconnect()
        # Disconnect from Wifi.
        self._esp.disconnect()

    # Get a 'signal strength' out of RSSI. Based on the Android algorithm. Probably has issues, but hey, it's something.
    def _signal_strength(self):
        min_rssi = -100
        max_rssi = -55
        levels = 4
        if self._esp.rssi <= min_rssi:
            return 0
        elif self._esp.rssi >= max_rssi:
            return levels - 1
        else:
            input_range = -1 * (min_rssi - max_rssi)
            output_range = levels - 1
            return floor((self._esp.rssi - min_rssi) * (output_range / input_range))

    def _ha_discovery(self):
        # Build the device JSON to include in other updates.
        self._device_info = dict(
            name=self._system_name,
            identifiers=[self._mac_address],
            suggested_area='Garage',
            sw_version=str(__version__)
        )

        # Process the topics.
        for item in self._topics:
            # Only create items that have HA Discovery defined!
            if 'ha_discovery' in self._topics[item]:
                # Multisensor isn't a pure Home Assistant type, but a special type here that will build multiple sensors
                # out of a list.
                if self._topics[item]['ha_discovery']['type'] == 'multisensor':
                    self._ha_create_multisensor(item)
                else:
                    self._ha_create(item)

    # Special method for creating multiple sensors for a list. Should probably merge this with the main _ha_create
    # at some point.
    def _ha_create_multisensor(self, mqtt_item):
        # Pull over some variables to shortem them for convenience.
        # HA discovery config.
        ha_config = self._topics[mqtt_item]['ha_discovery']
        print(ha_config)
        # Iterate the provided list, create a sensor for each one.
        for item in ha_config['list']:
            print("Multisensor now processing: {}".format(item))
            config_topic = "homeassistant/sensor/cobrabay-{}/{}/config".format(self._mac_address, item)
            config_dict = {
                'object_id': self._system_name.replace(" ", "").lower() + "_" + mqtt_item,
                # Use the master device info.
                'device': self._device_info,
                'unique_id': self._mac_address + '.' + item,
                # Each sensor gets the same state topic.
                'state_topic': self._topics[mqtt_item]['topic'],
                'value_template': '{{{{ value_json.{} }}}}'.format(item)
            }
            try:
                # Use the item name a key to get an alias from the alias dict.
                config_dict['name'] = ha_config['aliases'][item]['alias']
            except:
                # Otherwise just default it.
                config_dict['name'] = item

            # Optional parameters for sensors. All sensors in the group need to be the same, which really,
            # they should be.
            for par in ('device_class', 'icon', 'unit_of_measurement'):
                try:
                    config_dict[par] = ha_config[par]
                except KeyError:
                    pass

            # Send the discovery!
            print("Target topic: {}".format(config_topic))
            print("Payload q: {}".format(json.dumps(config_dict)))
            self._mqtt.publish(config_topic, json.dumps(config_dict))

    def _ha_create(self, mqtt_item):
        # Go get the details from the main topics dict.
        ha_config = self._topics[mqtt_item]['ha_discovery']
        config_topic = "homeassistant/{}/cobrabay-{}/{}/config".format(ha_config['type'],self._mac_address,ha_config['entity'])
        config_dict = {
            'name': ha_config['name'],
            'object_id': self._system_name.replace(" ","").lower() + "_" + mqtt_item,
            'device': self._device_info,
            'state_topic': self._topics[mqtt_item]['topic'],
            'unique_id': self._mac_address + '.' + ha_config['entity'],
        }
        # Optional parameters
        for par in ('device_class', 'icon','unit_of_measurement', 'payload_on','payload_off'):
            try:
                config_dict[par] = ha_config[par]
            except KeyError:
                pass

        # If this isn't device connectivity itself, make the entity depend on device connectivity
        config_dict['availability_topic'] = self._topics['device_connectivity']['topic']

        # Send it!
        self._mqtt.publish(config_topic,json.dumps(config_dict))

        # sensor.tester_state:
        # icon: mdi:test - tube
        # templates:
        # rgb_color: "if (state === 'on') return [251, 210, 41]; else return [54, 95, 140];"

