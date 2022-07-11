####
# Cobra Bay - Network
#
# Connects to the network to report bay status and take various commands.
####
from time import sleep

from pint import Quantity

from .version import __version__
from json import loads as json_loads
from json import dumps as json_dumps
from paho.mqtt.client import Client
from math import floor
from getmac import get_mac_address
import logging
import pint

class Network:
    def __init__(self, config, bay):
        # Save the config
        self._config = config
        # Create the logger.
        self._logger = logging.getLogger("cobrabay").getChild("network")
        self._logger.info('Network: Initializing...')

        try:
            from secrets import secrets
            self.secrets = secrets
        except ImportError:
            self._logger.error('Network: No secrets.py file, cannot get connection details.')
            raise

        # Find a MAC to use as client_id. Wireless is preferred, but if we don't have a wireless interface, fall back on
        # the ethernet interface.
        self._client_id = None
        for interface in ['eth0','wlan0']:
            while self._client_id is None:
                try:
                    self._client_id = get_mac_address(interface=interface).replace(':','').upper()
                except:
                    pass
                else:
                    self._logger.info("Assining Client ID {} from interface {}".format(self._client_id,interface))
                    break

        self._system_name = config['global']['system_name']

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

        # List for commands received and to be passed upward.
        self._upward_commands = []

        # Create the MQTT Client.
        self._mqtt_client = Client(
            client_id=""
        )
        self._mqtt_client.username_pw_set(
            username=self.secrets['mqtt']['username'],
            password=self.secrets['mqtt']['password']
        )
        # MQTT host to connect to.
        self._mqtt_host = self.secrets['mqtt']['broker']
        # If port is set, us that.
        try:
            self._mqtt_port = self.secrets['mqtt']['port']
        except:
            self._mqtt_port = 1883

        # Set TLS options.
        if 'tls' in self.secrets['mqtt']:
            pass

        self._mqtt_client.on_connect = self._on_connect
        self._mqtt_client.on_message = self._on_message

        # Unit of Measure to use for distances, based on the global setting.
        self.dist_uom = 'in' if self._config['global']['units'] == 'imperial' else 'cm'

        # Define topic reference.
        self._topics = {
            'device_connectivity': {
                'topic': 'cobrabay/' + self._client_id + '/connectivity',
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
                'topic': 'cobrabay/' + self._client_id + '/mem',
                'previous_state': {},
                'ha_discovery': {
                    'type': 'sensor',
                    'name': 'Available Memory',
                    'entity': 'memory_free',
                    'unit_of_measurement': 'kB'
                }
            },
            'device_command': {
                'topic': 'cobrabay/' + self._client_id + '/cmd',
                'callback': self._cb_device_command
                # 'ha_discovery': {
                #     'type': 'select'
                # }
            },
            'bay_occupied': {
                'topic': 'cobrabay/' + self._client_id + '/' + self._bay.name + '/occupied',
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
                'topic': 'cobrabay/' + self._client_id + '/' + self._bay.name + '/state',
                'previous_state': None,
                'ha_discovery': {
                    'type': 'sensor',
                    'name': 'Bay State',
                    'entity': 'state'
                }
            },
            'bay_position': {
                'topic': 'cobrabay/' + self._client_id + '/' + self._bay.name + '/position',
                'ha_type': 'sensor',
                'previous_state': {
                    'type': 'multisensor',
                    'list': bay.position,
                }
            },
            'bay_sensors': {
                'topic': 'cobrabay/' + self._client_id + '/' + self._bay.name + '/sensors',
                'previous_state': {},
                'ha_discovery': {
                    'type': 'multisensor',
                    'list': bay.sensor_list,  # Dict from which separate sensors will be created.
                    'aliases': config['sensors'],  # Dict with list alias names.
                    'icon': 'mdi:ruler',
                    # Conveniently, we use the same string identifier for units as Home Assistant!
                    'unit_of_measurement': self.dist_uom
                }
            },
            'bay_command': {
                'topic': 'cobrabay/' + self._client_id + '/' + self._bay.name + '/cmd',
                # 'ha_discovery': {
                #     'type': 'select'
                # },
                'callback': self._cb_bay_command
            }
        }
        self._logger.info('Network: Initialization complete.')

    def _on_connect(self, userdata, flags, rc, properties=None):
        self._logger.info("Connected to MQTT Broker with result code: {}".format(rc))
        # Create last will, goes to the device topic.
        self._logger.info("Network: Creating last will.")
        self._mqtt_client.will_set(self._topics['device_connectivity']['topic'], payload='offline')
        # For every topic that has a callback, add it.
        for item in self._topics:
            if 'callback' in self._topics[item]:
                self._logger.debug("Network: Creating callback for {}".format(item))
                self._mqtt_client.message_callback_add(self._topics[item]['topic'], self._topics[item]['callback'])

    def _on_message(self):
        pass

    # Topic Callbacks

    # Device Command callback
    def _cb_device_command(self, client, topic, raw_message):
        # Try to decode the JSON.
        try:
            message = json_loads(raw_message)
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
            mc_reset()
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
            message = json_loads(raw_message)
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
    def _pub_message(self, topic, message):
        # Convert the message
        if isinstance(message,dict):
            outbound_message = json_dumps(self._dict_unit_convert(message, flatten=True))
        else:
            outbound_message = message
        self._mqtt_client.publish(self._topics[topic]['topic'], outbound_message)

    # Method to be polled by the main run loop.
    # Main loop passes in the current state of the bay.
    def poll(self, outbound_messages=None):
        # Publish messages outbound
        for message in outbound_messages:
            self._pub_message(message['topic'], message['message'])

        # Check for any incoming commands.
        self._mqtt_client.loop()

        # Yank any commands to send upward and clear it for the next run.
        upward_data = {
            # 'signal_strength': self._signal_strength(),
            'signal_strength': 5,
            'mqtt_status': self._mqtt_client.is_connected(),
            'commands': self._upward_commands
        }
        self._upward_commands = []
        return upward_data

    def _connect_mqtt(self):
        try:
            self._mqtt_client.connect(host=self._mqtt_host,port=self._mqtt_port)
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
                    self._logger.error(e,exc_info=True)

        # Send a discovery message and an online notification.
        self._logger.info('Network: Sending online message')
        # if self._homeassistant:
        #     self._ha_discovery()
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
        self._mqtt_client.publish(self._topics['bay_state']['topic'], 'offline')
        self._mqtt_client.publish(self._topics['bay_state']['topic'], 'offline')
        # Disconnect from broker
        self._mqtt_client.disconnect()

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
            identifiers=[self._client_id],
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

    # Utility method to go through an convert all quantities in nested dicts to a common unit. Optionally, flatten
    # quantities to a string.
    def _dict_unit_convert(self, the_dict, flatten=False):
        new_dict = {}
        for key in the_dict:
            if isinstance(key,Quantity):
                new_dict[key] = the_dict[key].to(self.dist_uom)
                if flatten:
                    new_dict[key] = str(the_dict[key])
            if isinstance(key,dict):
                new_dict[key] = self._dict_unit_convert(self,the_dict[key],flatten)
        return new_dict

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
            config_topic = "homeassistant/sensor/cobrabay-{}/{}/config".format(self._client_id, item)
            config_dict = {
                'object_id': self._system_name.replace(" ", "").lower() + "_" + mqtt_item,
                # Use the master device info.
                'device': self._device_info,
                'unique_id': self._client_id + '.' + item,
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
            print("Payload q: {}".format(json_dumps(config_dict)))
            self._mqtt.publish(config_topic, json_dumps(config_dict))

    def _ha_create(self, mqtt_item):
        # Go get the details from the main topics dict.
        ha_config = self._topics[mqtt_item]['ha_discovery']
        config_topic = "homeassistant/{}/cobrabay-{}/{}/config".format(ha_config['type'],self._client_id,ha_config['entity'])
        config_dict = {
            'name': ha_config['name'],
            'object_id': self._system_name.replace(" ","").lower() + "_" + mqtt_item,
            'device': self._device_info,
            'state_topic': self._topics[mqtt_item]['topic'],
            'unique_id': self._client_id + '.' + ha_config['entity'],
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
        self._mqtt.publish(config_topic,json_dumps(config_dict))

        # sensor.tester_state:
        # icon: mdi:test - tube
        # templates:
        # rgb_color: "if (state === 'on') return [251, 210, 41]; else return [54, 95, 140];"

