####
# Cobra Bay - Network
#
# Connects to the network to report bay status and take various commands.
####

import logging
import pprint
from json import dumps as json_dumps
from json import loads as json_loads
# from math import floor
from pint import Quantity
import time

from getmac import get_mac_address
from paho.mqtt.client import Client

from .util import Convertomatic
from .version import __version__


class Network:
    def __init__(self, config):
        # Save the config
        self._config = config
        # Create the logger.
        self._logger = logging.getLogger("CobraBay").getChild("Network")
        self._logger.setLevel(logging.DEBUG)
        self._logger.info('Initializing...')

        try:
            from secrets import secrets
            self.secrets = secrets
        except ImportError:
            self._logger.error('Network: No secrets.py file, cannot get connection details.')
            raise

        if self._config['global']['units'].lower() == "imperial":
            self._unit_system = "imperial"
        else:
            self._unit_system = "metric"
        self._cv = Convertomatic(self._unit_system)

        # Find a MAC to use as client_id. Wireless is preferred, but if we don't have a wireless interface, fall back on
        # the ethernet interface.
        self._client_id = None
        for interface in ['eth0', 'wlan0']:
            while self._client_id is None:
                try:
                    self._client_id = get_mac_address(interface=interface).replace(':', '').upper()
                except:
                    pass
                else:
                    self._logger.info("Assigning Client ID {} from interface {}".format(self._client_id, interface))
                    break

        self._system_name = config['global']['system_name']

        # Set homeassistant integration state.
        self._logger.debug("Config file HA setting: {}".format(config['global']['homeassistant']))
        try:
            self._logger.debug("Setting Home Assistant true.")
            self._homeassistant = config['global']['homeassistant']
        except:
            self._logger.debug("Setting Home Assistant false.")
            self._homeassistant = False

        # Current device state. Will get updated every time we're polled.
        self._device_state = 'unknown'

        # List for commands received and to be passed upward.
        self._upward_commands = []
        # Registry to keep extant bays.
        self._bay_registry = {}

        # Create the MQTT Client.
        self._mqtt_client = Client(
            client_id=""
        )
        self._mqtt_client.username_pw_set(
            username=self.secrets['username'],
            password=self.secrets['password']
        )
        # Send MQTT logging to the network logger.
        # self._mqtt_client.enable_logger(self._logger)
        # MQTT host to connect to.
        self._mqtt_host = self.secrets['broker']
        # If port is set, us that.
        try:
            self._mqtt_port = self.secrets['port']
        except:
            self._mqtt_port = 1883

        # Set TLS options.
        if 'tls' in self.secrets:
            pass

        self._mqtt_client.on_connect = self._on_connect

        # Define topic reference.
        self._topics = {
            'device_connectivity': {
                'topic': 'cobrabay/' + self._client_id + '/connectivity',
                'previous_state': {},
                'enabled': True,
                'ha_discovery': {
                    'name': '{} Connectivity'.format(self._system_name),
                    'type': 'binary_sensor',
                    'entity': 'connectivity',
                    'device_class': 'connectivity',
                    'payload_on': 'online',
                    'payload_off': 'offline'
                }
            },
            'cpu_pct': {
                'topic': 'cobrabay/' + self._client_id + '/cpu_pct',
                'previous_state': {},
                'enabled': True,
                'ha_discovery': {
                    'name': '{} CPU Use'.format(self._system_name),
                    'type': 'sensor',
                    'entity': 'cpu_pct',
                    'unit_of_measurement': '%',
                    'icon': 'mdi:chip'
                }
            },
            'cpu_temp': {
                'topic': 'cobrabay/' + self._client_id + '/cpu_temp',
                'previous_state': {},
                'enabled': True,
                'ha_discovery': {
                    'name': '{} CPU Temperature'.format(self._system_name),
                    'type': 'sensor',
                    'entity': 'cpu_temp',
                    'device_class': 'temperature',
                    'unit_of_measurement': self._uom('temp')
                }
            },
            'mem_info': {
                'topic': 'cobrabay/' + self._client_id + '/mem_info',
                'previous_state': {},
                'enabled': True,
                'ha_discovery': {
                    'name': '{} Memory Use'.format(self._system_name),
                    'type': 'sensor',
                    'entity': 'mem_info',
                    'value_template': "{{ value_json.mem_pct }}",
                    'unit_of_measurement': '%',
                    'icon': 'mdi:memory',
                    'json_attributes_topic': 'cobrabay/' + self._client_id + '/mem_info'
                }
            },
            'device_command': {
                'topic': 'cobrabay/' + self._client_id + '/cmd',
                'enabled': False,
                'callback': self._cb_device_command
                # 'ha_discovery': {
                #     'type': 'select'
                # }
            },
            'bay_occupied': {
                'topic': 'cobrabay/' + self._client_id + '/{0[bay_id]}/occupied',
                'previous_state': 'Unknown',
                'enabled': True,
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
                'topic': 'cobrabay/' + self._client_id + '/{0[bay_id]}/state',
                'previous_state': None,
                'enabled': True,
                'ha_discovery': {
                    'type': 'sensor',
                    'name': 'Bay State',
                    'entity': 'state',
                    'value_template': '{{ value_json.state }}'
                }
            },
            # Adjusted readings from the sensors.
            'bay_position': {
                'topic': 'cobrabay/' + self._client_id + '/{0[bay_id]}/position',
                'enabled': True,
                'ha_type': 'sensor',
                'previous_state': None,
                'ha_discovery': {
                    'type': 'sensor_group',
                    'list': 'bay.position',
                }
            },
            # How good the parking job is.
            'bay_park_quality': {
                'topic': 'cobrabay/' + self._client_id + '/{0[bay_id]}/bay_alignment',
                'previous_state': {},
                'enabled': True,
                'ha_discovery': {
                    'type': 'sensor_group',
                    'list': 'bay_position',
                    'icon': 'mdi:traffic-light'
                }
            },
            'bay_command': {
                'topic': 'cobrabay/' + self._client_id + '/+/cmd',
                'ha_discovery': {
                    'type': 'select'
                },
                'callback': self._cb_bay_command
            }
        }
        self._logger.info('Network: Initialization complete.')

    def _on_connect(self, userdata, flags, rc, properties=None):
        self._logger.info("Connected to MQTT Broker with result code: {}".format(rc))
        # Create last will, goes to the device topic.
        self._logger.info("Network: Creating last will.")
        self._mqtt_client.will_set(self._topics['device_connectivity']['topic'], payload='offline')
        # Connect to the callback topics. This will only connect to the device command topic at this stage.
        for item in self._topics:
            if 'callback' in self._topics[item]:
                self._logger.debug("Network: Creating callback for {}".format(item))
                self._mqtt_client.message_callback_add(self._topics[item]['topic'], self._topics[item]['callback'])
        # Reconnect the bay command callbacks
        for bay in self._bay_registry:
            print("Adding callback for {}".format(bay))
            self._mqtt_client.message_callback_add(self._bay_registry[bay]['topic'], self._bay_registry[bay]['callback'])

    # Device Command callback
    def _cb_device_command(self, client, userdata, message):
        self._logger.debug("Received device command message: {}".format(message.payload))
        # Try to decode the JSON.
        try:
            message = json_loads(message.payload)
        except:
            self._logger.error(
                "Network: Could not decode JSON from MQTT message '{}' on topic '{}'".format(topic, raw_message))
            # Ignore the error itself, plow through.
            return False

        # Proceed on valid commands.
        if 'cmd' not in message:
            self._logger.error("Network: MQTT message for topic {} does not contain a 'cmd' directive".format(topic))
        elif message['cmd'] == 'rediscover':
            # Rerun Home Assistant discovery
            self._ha_discovery()
        elif message['cmd'] == 'display_sensor':
            # If displaying a sensor, have to pass up other parameters as well.
            # Remove the command, since we already have that, then put the rest into the options field.
            del message['cmd']
            self._upward_commands.append({'type': 'device', 'cmd': 'display_sensor', 'options': message})
        elif message['cmd'] == 'rescan_sensors':
            self._upward_commands.append({'type': 'device', 'cmd': 'rescan_sensors'})
        else:
            self._logger.info("Network: Received unknown MQTT device command '{}'".format(message['cmd']))

    # Bay Command callback
    def _cb_bay_command(self, client, userdata, message):
        self._logger.debug("Received bay command message: {}".format(message.payload))
        self._logger.debug("Incoming topic: {}".format(message.topic))

        # Pull out the bay ID.
        bay_id = message.topic.split('/')[-2]
        self._logger.debug("Using bay id: {}".format(bay_id))

        # Try to decode the JSON.
        try:
            message = json_loads(message.payload)
        except:
            self._logger.error("Network: Could not decode JSON from MQTT message '{}' on topic '{}'"
                               .format(message.topic, message.payload))
            # Ignore the message and return, as if we never got int.
            return

        # Proceed on valid commands.
        if 'cmd' not in message:
            self._logger.error(
                "Network: MQTT message for topic {} does not contain a cmd directive".format(message.topic))
        elif message['cmd'] in ('dock', 'undock', 'complete', 'abort', 'verify', 'reset'):
            # If it's a valid bay command, pass it upward.
            self._upward_commands.append({'type': 'bay', 'bay_id': bay_id, 'cmd': message['cmd']})
        else:
            self._logger.info("Network: Received unknown MQTT bay command '{}'".format(message['cmd']))

    # Message publishing method
    def _pub_message(self, topic, message, repeat=False, topic_mappings=None):
        previous_state = self._topics[topic]['previous_state']

        # Send flag. Default to assuming we *won't* send. We'll send if either repeat is True (ie: send no matter what)
        # or if repeat is false *and* content has been determined to have changed.
        send = False

        # If the topic is templated, take the topic_mappings and insert them.
        # This is currently onlu used to put in bay_id.
        # No real bounds checking, and could explode in strange ways.
        if topic_mappings is not None:
            target_topic = self._topics[topic]['topic'].format(topic_mappings)
        else:
            target_topic = self._topics[topic]['topic']

        # Put the message through conversion. This converts Quantities to proper units and then flattens to floats
        # that can be sent through MQTT and understood by Home Assistant
        message = self._cv.convert(message)

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
            else:
                # If type has changed (and it shouldn't, usually), send it.
                if type(message) != type(previous_state):
                    send = True
        elif repeat is True:
            send = True
        # The 'repeat' option can be used in cases when a caller wants to send no matter the changed state.
        # Using this too much can make things super chatty.
        if send:
            # If the enabled option is in the dict, it might be disabled for now, so check.
            if 'enabled' in self._topics[topic]:
                if not self._topics[topic]['enabled']:
                    return

            # New message becomes the previous message.
            self._topics[topic]['previous_state'] = message
            # Convert the message to JSON if it's a dict, otherwise just send it.
            if isinstance(message, dict):
                outbound_message = json_dumps(message, default=str)
            else:
                outbound_message = message
            self._mqtt_client.publish(target_topic, outbound_message)

    # Method to be polled by the main run loop.
    # Main loop passes in the current state of the bay.
    def poll(self, outbound_messages=None):
        # Send all the messages outbound.
        for message in outbound_messages:
            self._pub_message(**message)
        # Check for any incoming commands.
        self._mqtt_client.loop()
        # Yank any commands to send upward and clear it for the next run.
        upward_data = {
            # 'signal_strength': self._signal_strength(),
            'signal_strength': 5,  # Replace later with eth/not eth logic.
            'mqtt_status': self._mqtt_client.is_connected(),
            'commands': self._upward_commands
        }
        self._upward_commands = []
        return upward_data

    def _connect_mqtt(self):
        try:
            self._mqtt_client.connect(host=self._mqtt_host, port=self._mqtt_port)
        except Exception as e:
            self._logger.error('Network: Could not connect to MQTT broker.')
            self._logger.debug('Network: ' + str(e))
            raise

        # Subscribe to all the appropriate topics
        for item in self._topics:
            if 'callback' in self._topics[item]:
                try:
                    self._mqtt_client.subscribe(self._topics[item]['topic'])
                except RuntimeError as e:
                    self._logger.error("Caught error while subscribing to topic {}".format(item))
                    self._logger.error(e, exc_info=True)

        # Send a discovery message and an online notification.
        self._logger.info('Network: Sending online message')
        self._logger.debug("HA status: {}".format(self._homeassistant))
        if self._homeassistant:
            self._logger.debug("Running HA Discovery...")
            self._ha_discovery()
        self._mqtt_client.publish(self._topics['device_connectivity']['topic'], payload='online')
        return True

    # Convenience method to start everything network related at once.
    def connect(self):
        try:
            self._connect_mqtt()
        except Exception as e:
            raise

        return None

    def disconnect(self, message=None):
        self._logger.info('Network: Planned disconnect with message "' + str(message) + '"')
        # If we have a disconnect message, send it to the device topic.
        if message is not None:
            self._mqtt_client.publish(self._topics['device_state']['topic'], message)
        # When disconnecting, mark the device and the bay as unavailable.
        self._mqtt_client.publish(self._topics['device_connectivity']['topic'], 'offline')
        # self._mqtt_client.publish(self._topics['bay_state']['topic'], 'offline', )
        # self._mqtt_client.publish(self._topics['bay_state']['topic'], 'offline')
        # Disconnect from broker
        self._mqtt_client.disconnect()

    # Get a 'signal strength' out of RSSI. Based on the Android algorithm. Probably has issues, but hey, it's something.
    def _signal_strength(self):
        pass
        # min_rssi = -100
        # max_rssi = -55
        # levels = 4
        # if self._esp.rssi <= min_rssi:
        #     return 0
        # elif self._esp.rssi >= max_rssi:
        #     return levels - 1
        # else:
        #     input_range = -1 * (min_rssi - max_rssi)
        #     output_range = levels - 1
        #     return floor((self._esp.rssi - min_rssi) * (output_range / input_range))

    def _ha_discovery(self):
        # Build the device JSON to include in other updates.
        self._device_info = dict(
            name=self._system_name,
            identifiers=[self._client_id],
            suggested_area='Garage',
            manufacturer='ConHugeCo',
            model='CobraBay Parking System',
            sw_version=str(__version__)
        )

        # Process the topics.
        for item in self._topics:
            # Create items that have HA Discovery, and are enabled. Enabled/disabled is really 100% for development.
            if 'ha_discovery' in self._topics[item] and self._topics[item]['enabled']:
                # A sensor_group allows us to create multiple
                if self._topics[item]['ha_discovery']['type'] == 'sensor_group':
                    self._ha_create_sensor_group(item)
                else:
                    self._ha_create(item)

    # Special method for creating multiple sensors for a list. Should probably merge this with the main _ha_create
    # at some point.
    def _ha_create_sensor_group(self, mqtt_item):
        # Pull over some variables to shorten them for convenience.
        # Iterate the provided list, create a sensor for each one.
        for item in self._topics[mqtt_item]['ha_discovery']['list']:
            self._logger.debug("Multisensor now processing: {}".format(item))

            # Set up a config dict we can pass to the Sensor creator.
            config_dict = {
                'type': 'sensor',
                'entity': item,
                # Sensors in a group all use the same topic so we pull it out of the template.
                'value_template': '{{{{ value_json.{} }}}}'.format(item),
                'unit_of_measurement': self._uom('length')
            }

            try:
                # Use the item name a key to get an alias from the alias dict.
                config_dict['name'] = ha_config['aliases'][item]['alias']
            except:
                # Otherwise just default it.
                config_dict['name'] = item

            self._logger.debug("Created config for sensor {}: {}".format(item, config_dict))
            self._logger.debug("Sending to main creation routine.")
            self._ha_create(mqtt_item, ha_config=config_dict, sub_item=item)

    def _ha_create(self, mqtt_item, ha_config=None, sub_item=None):
        # If ha_config dict wasn't specified, use one defined on the object.
        if ha_config is None:
            ha_config = self._topics[mqtt_item]['ha_discovery']
        if sub_item is None:
            sub_item = mqtt_item

        # Build a config topic.
        config_topic = "homeassistant/{}/cobrabay-{}/{}/config".format(ha_config['type'], self._client_id,
                                                                       ha_config['entity'])
        # Base, required parameters.
        try:
            config_dict = {
                'name': ha_config['name'],
                'object_id': self._system_name.replace(" ", "").lower() + "_" + sub_item,
                'device': self._device_info,
                'state_topic': self._topics[mqtt_item]['topic'],
                'unique_id': self._client_id + '.' + ha_config['entity'],
            }
        except:
            raise

        optional_params = (
            'device_class',
            'icon',
            'json_attributes_topic',
            'unit_of_measurement',
            'payload_on',
            'payload_off',
            'value_template')

        # Optional parameters
        for par in optional_params:
            try:
                config_dict[par] = ha_config[par]
            except KeyError:
                pass

        # If this isn't device connectivity itself, make the entity depend on device connectivity
        if config_topic != 'device_connectivity':
            config_dict['availability_topic'] = self._topics['device_connectivity']['topic']
            config_dict['payload_available'] = self._topics['device_connectivity']['ha_discovery']['payload_on']
            config_dict['payload_not_available'] = self._topics['device_connectivity']['ha_discovery']['payload_off']

        # Send it!
        self._logger.debug("Publishing HA discovery to topic {}\n\t{}".format(config_topic, config_dict))
        self._mqtt_client.publish(config_topic, json_dumps(config_dict))

        # sensor.tester_state:
        # icon: mdi:test - tube
        # templates:
        # rgb_color: "if (state === 'on') return [251, 210, 41]; else return [54, 95, 140];"



    # Create a traffic-light style sensor. This is used for the parking position sensors.
    def _ha_create_trafficlight(self):
        # icon_template = \
        #     "{% if is_state('sensor.{}','Good') %}
        #         mdi:check-circle
        #     {% elif is_state('sensor.{}','OK') %}
        #         mdi:alert-circle
        #     {% elif is_state('sensor.{}','Bad') %}
        #         mdi:close-circle
        #     {% else %}
        #         mdi:eye-circle
        #     {% endif %}".format(entity_id)

        pass

    # Helper method to determine the correct unit of measure to use. When we have reported sensor units, we use
    # this method to ensure the correct unit is being put in.
    def _uom(self, unit_type):
        system = self._config['global']['units']
        if unit_type == 'length':
            if system == 'imperial':
                uom = "in"
            else:
                uom = "cm"
        elif unit_type == 'temp':
            if system == 'imperial':
                uom = "°F"
            else:
                uom = "°C"
        else:
            raise ValueError("{} isn't a valid unit type".format(unit_type))

        # Unit of Measure to use for distances, based on the global setting.
        uom = 'in' if self._config['global']['units'] == 'imperial' else 'cm'
        return uom