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
        # Get our settings.
        self._settings = config.network()
        # Set up logger.
        self._logger = logging.getLogger("CobraBay").getChild("Network")
        self._logger.setLevel(config.get_loglevel('network'))
        self._logger.info("Network initializing...")
        self._logger.debug("Network has settings: {}".format(self._settings))

        # Sub-logger for just MQTT
        self._logger_mqtt = logging.getLogger("CobraBay").getChild("MQTT")
        self._logger_mqtt.setLevel(config.get_loglevel('mqtt'))
        if self._logger_mqtt.level != self._logger.level:
            self._logger.info("MQTT Logging level set to {}".format(self._logger_mqtt.level))

        try:
            from secrets import secrets
            self.secrets = secrets
        except ImportError:
            self._logger.error('No secrets file, cannot get connection details.')
            raise

        # Create a convertomatic instance.
        self._cv = Convertomatic(self._settings['units'])

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

        # Initialize the MQTT connected variable.
        self._mqtt_connected = False

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

        # Connect callback.
        self._mqtt_client.on_connect = self._on_connect
        # Disconnect callback
        self._mqtt_client.on_disconnect = self._on_disconnect

        # Define topic reference.
        self._topics = {
            'system': {
                'device_connectivity': {
                    'topic': 'cobrabay/' + self._client_id + '/connectivity',
                    'previous_state': {},
                    'enabled': True,
                    'ha_discovery': {
                        'name': '{} Connectivity'.format(self._settings['system_name']),
                        'type': 'binary_sensor',
                        'entity': '{}_connectivity'.format(self._settings['system_name'].lower()),
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
                        'name': '{} CPU Use'.format(self._settings['system_name']),
                        'type': 'sensor',
                        'entity': '{}_cpu_pct'.format(self._settings['system_name'].lower()),
                        'unit_of_measurement': '%',
                        'icon': 'mdi:chip'
                    }
                },
                'cpu_temp': {
                    'topic': 'cobrabay/' + self._client_id + '/cpu_temp',
                    'previous_state': {},
                    'enabled': True,
                    'ha_discovery': {
                        'name': '{} CPU Temperature'.format(self._settings['system_name']),
                        'type': 'sensor',
                        'entity': '{}_cpu_temp'.format(self._settings['system_name'].lower()),
                        'device_class': 'temperature',
                        'unit_of_measurement': self._uom('temp')
                    }
                },
                'mem_info': {
                    'topic': 'cobrabay/' + self._client_id + '/mem_info',
                    'previous_state': {},
                    'enabled': True,
                    'ha_discovery': {
                        'name': '{} Memory Use'.format(self._settings['system_name']),
                        'type': 'sensor',
                        'entity': '{}_mem_info'.format(self._settings['system_name'].lower()),
                        'value_template': "{{{{ value_json.mem_pct }}}}",
                        'unit_of_measurement': '%',
                        'icon': 'mdi:memory',
                        'json_attributes_topic': 'cobrabay/' + self._client_id + '/mem_info'
                    }
                },
                'undervoltage': {
                    'topic': 'cobrabay/' + self._client_id + '/undervoltage',
                    'previous_state': {},
                    'ha_discovery': {
                        'name': '{} Undervoltage'.format(self._settings['system_name']),
                        'type': 'binary_sensor',
                        'entity': '{}_undervoltage'.format(self._settings['system_name'].lower()),
                        'payload_on': 'Under voltage detected',
                        'payload_off': 'Voltage normal',
                        'icon': 'mdi:lightning-bolt'
                    }
                },
                'device_command': {
                    'topic': 'cobrabay/' + self._client_id + '/cmd',
                    'enabled': False,
                    'callback': self._cb_device_command
                    # May eventually do discovery here to create selectors, but not yet.
                },
                'display': {
                    'topic': 'cobrabay/' + self._client_id + '/display',
                    'previous_state': {},
                    'ha_discovery': {
                        'name': '{} Display'.format(self._settings['system_name']),
                        'type': 'camera',
                        'entity': '{}_display'.format(self._settings['system_name'].lower()),
                        'icon': 'mdi:monitor',
                        'encoding': 'b64'
                    }
                },
            },
            'bay': {
                'bay_occupied': {
                    'topic': 'cobrabay/' + self._client_id + '/{0[bay_id]}/state',
                    'previous_state': 'Unknown',
                    'ha_discovery': {
                        'name': '{0[bay_name]} Occupied',
                        'type': 'binary_sensor',
                        'entity': '{0[bay_id]}_occupied',
                        'class': 'occupancy',
                        'value_template': "{{% if value_json.state == 'occupied' %}} ON {{% else %}} OFF {{% endif %}}"
                    }
                },
                'bay_state': {
                    'topic': 'cobrabay/' + self._client_id + '/{0[bay_id]}/state',
                    'previous_state': None,
                    'ha_discovery': {
                        'name': '{0[bay_name]} State',
                        'type': 'sensor',
                        'entity': '{0[bay_id]}_state'
                    }
                },
                'bay_laterals': {
                    'topic': 'cobrabay/' + self._client_id + '/{0[bay_id]}/{0[lateral]/display',
                    'previous_state': {},
                    'ha_discovery': {
                        'name': '{0[bay_name]} {0[lateral]} Display',
                        'type': 'camera',
                        'entity': '{0[bay_id]}_{0[lateral]}_display',
                        'encoding': 'b64'
                    }
                },
                # Which detector is selected for active range use.
                'bay_range_selected': {
                    'topic': 'cobrabay/' + self._client_id + '/{0[bay_id]}/range_selected',
                    'previous_state': None,
                    'ha_discovery': {
                        'name': '{0[bay_name]} Selected Range Detector',
                        'type': 'sensor',
                        'entity': '{0[bay_id]}_range_selected'
                    }
                },
                # Adjusted readings from the sensors.
                'bay_position': {
                    'topic': 'cobrabay/' + self._client_id + '/{0[bay_id]}/position',
                    'previous_state': None,
                    'ha_discovery': {
                        'name': '{0[bay_name]} Detector Position: {0[detector_name]}',
                        'type': 'sensor',
                        'entity': '{0[bay_id]}_position_{0[detector_id]}',
                        'value_template': '{{{{ value_json.{0[detector_id]} }}}}',
                        'unit_of_measurement': self._uom('length'),
                        'icon': 'mdi:ruler'
                    }
                },
                # How good the parking job is.
                'bay_quality': {
                    'topic': 'cobrabay/' + self._client_id + '/{0[bay_id]}/quality',
                    'previous_state': None,
                    'enabled': True,
                    'ha_discovery': {
                        'name': '{0[bay_name]} Detector Quality: {0[detector_name]}',
                        'type': 'sensor',
                        'entity': '{0[bay_id]}_quality_{0[detector_id]}',
                        'value_template': '{{{{ value_json.{0[detector_id]} }}}}',
                        'icon': 'mdi:traffic-light'
                    }
                },
                'bay_motion': {
                    'topic': 'cobrabay/' + self._client_id + '/{0[bay_id]}/motion',
                    'previous_state': 'Unknown',
                    'enabled': True,
                    'ha_discovery': {
                        'name': '{0[bay_name]} Motion',
                        'type': 'binary_sensor',
                        'entity': '{0[bay_id]}_motion',
                        'class': 'motion',
                        'payload_on': 'True',
                        'payload_off': 'False'
                    }
                },
                'bay_speed': {
                    'topic': 'cobrabay/' + self._client_id + '/{0[bay_id]}/vector',
                    'previous_state': None,
                    'ha_discovery': {
                        'name': '{0[bay_name]} Speed',
                        'type': 'sensor',
                        'entity': '{0[bay_id]}_speed',
                        'value_template': '{{{{ value_json.speed }}}}',
                        'class': 'speed',
                        'unit_of_measurement': self._uom('speed')
                    }
                },
                'bay_dock_time': {
                    'topic': 'cobrabay/' + self._client_id + '/{0[bay_id]}/dock_time',
                    'previous_state': None,
                    'ha_discovery': {
                        'name': '{0[bay_name]} Time Until Docked',
                        'type': 'sensor',
                        'entity': '{0[bay_id]}_dock_time_remaining',
                        'unit_of_measurement': 'seconds'
                    }
                },

                # This is a generic callback that will work for all bays.
                'bay_command': {
                    'topic': 'cobrabay/' + self._client_id + '/+/cmd',
                    'ha_discovery': {
                        'type': 'select'
                    },
                    'callback': self._cb_bay_command
                }
            }
        }
        self._logger.info('Network: Initialization complete.')

    # Method to register a bay.
    def register_bay(self, discovery_reg_info):
        # We only need the names of things.
        self._bay_registry[discovery_reg_info['bay_id']] = discovery_reg_info
        self._logger.debug("Have registered new bay info: {}".format(self._bay_registry[discovery_reg_info['bay_id']]))
        # If Home Assistant is enabled, and we're already connected, run just the Bay discovery.
        if self._mqtt_connected and self._settings['homeassistant']:
            self._logger.debug("Running HA discovery for bay {}".format(discovery_reg_info['bay_id']))
            self._ha_discovery_bay(discovery_reg_info['bay_id'])

    def unregister_bay(self, bay_id):
        try:
            del self._bay_registry[bay_id]
        except KeyError:
            self._logger.error("Asked to Unregister bay ID {} but bay by that ID does not exist.".format(bay_id))

    def _on_connect(self, userdata, flags, rc, properties=None):
        self._logger.info("Connected to MQTT Broker with result code: {}".format(rc))
        # Connect to the callback topics. This will only connect to the device command topic at this stage.
        for type in self._topics:
            for item in self._topics[type]:
                if 'callback' in self._topics[type][item]:
                    self._logger.debug("Network: Creating callback for {}".format(item))
                    self._mqtt_client.message_callback_add(self._topics[type][item]['topic'],
                                                           self._topics[type][item]['callback'])
        self._mqtt_connected = True

    def _on_disconnect(self):
        self._mqtt_connected = False

    # Device Command callback
    def _cb_device_command(self, client, userdata, message):
        self._logger_mqtt.debug("Received device command message: {}".format(message.payload))
        # Try to decode the JSON.
        try:
            message = json_loads(message.payload)
        except:
            self._logger_mqtt.error(
                "Could not decode JSON from MQTT message '{}' on topic '{}'".format(topic, raw_message))
            # Ignore the error itself, plow through.
            return False

        # Proceed on valid commands.
        if 'cmd' not in message:
            self._logger_mqtt.error("MQTT message for topic {} does not contain a 'cmd' directive".format(topic))
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
            self._logger.info("Received unknown MQTT device command '{}'".format(message['cmd']))

    # Bay Command callback
    def _cb_bay_command(self, client, userdata, message):
        self._logger_mqtt.debug("Received bay command message: {}".format(message.payload))
        self._logger_mqtt.debug("Incoming topic: {}".format(message.topic))

        # Pull out the bay ID.
        bay_id = message.topic.split('/')[-2]
        self._logger.debug("Using bay id: {}".format(bay_id))

        # Try to decode the JSON.
        try:
            message = json_loads(message.payload)
        except:
            self._logger_mqtt.error("Could not decode JSON from MQTT message '{}' on topic '{}'"
                               .format(message.topic, message.payload))
            # Ignore the message and return, as if we never got int.
            return

        # Proceed on valid commands.
        if 'cmd' not in message:
            self._logger_mqtt.error(
                "MQTT message for topic {} does not contain a cmd directive".format(message.topic))
        elif message['cmd'] in ('dock', 'undock', 'complete', 'abort', 'verify', 'reset'):
            # If it's a valid bay command, pass it upward.
            self._upward_commands.append({'type': 'bay', 'bay_id': bay_id, 'cmd': message['cmd']})
        else:
            self._logger.info("Received unknown MQTT bay command '{}'".format(message['cmd']))

    # Message publishing method
    def _pub_message(self, topic_type, topic, message, repeat=False, topic_mappings=None):
        previous_state = self._topics[topic_type][topic]['previous_state']

        # Send flag. Default to assuming we *won't* send. We'll send if either repeat is True (ie: send no matter what)
        # or if repeat is false *and* content has been determined to have changed.
        send = False

        # If the topic is templated, take the topic_mappings and insert them.
        # This is currently only used to put in bay_id.
        # No real bounds checking, and could explode in strange ways.
        if topic_mappings is not None:
            target_topic = self._topics[topic_type][topic]['topic'].format(topic_mappings)
        else:
            target_topic = self._topics[topic_type][topic]['topic']

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
                # # If type has changed (and it shouldn't, usually), send it.
                # print("Mesage type: {}".format(type(message)))
                # print("Previous message type: {}".format(type(message)))
                if type(message) != type(previous_state):
                    send = True
        elif repeat is True:
            send = True
        # The 'repeat' option can be used in cases when a caller wants to send no matter the changed state.
        # Using this too much can make things super chatty.
        if send:
            # New message becomes the previous message.
            self._topics[topic_type][topic]['previous_state'] = message
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
            self._logger_mqtt.debug("Publishing MQTT message: {}".format(message))
            self._pub_message(**message)
        # Check for any incoming commands.
        self._mqtt_client.loop()
        # Yank any commands to send upward and clear it for the next run.
        upward_data = {
            'online': True,  # Replace later with eth/not eth logic.
            'mqtt_status': self._mqtt_client.is_connected(),
            'commands': self._upward_commands
        }
        self._upward_commands = []
        return upward_data

    def _connect_mqtt(self):
        # Set the last will prior to connecting.
        self._logger.info("Creating last will.")
        self._mqtt_client.will_set(
            self._topics['system']['device_connectivity']['topic'],
            payload='offline', qos=0, retain=True)
        try:
            self._mqtt_client.connect(host=self._mqtt_host, port=self._mqtt_port)
        except Exception as e:
            self._logger.error('Network: Could not connect to MQTT broker.')
            self._logger.debug('Network: ' + str(e))
            raise

        # Subscribe to all the appropriate topics
        for type in self._topics:
            for item in self._topics[type]:
                if 'callback' in self._topics[type][item]:
                    try:
                        self._mqtt_client.subscribe(self._topics[type][item]['topic'])
                    except RuntimeError as e:
                        self._logger.error("Caught error while subscribing to topic {}".format(item))
                        self._logger.error(e, exc_info=True)

        # Send a discovery message and an online notification.
        if self._settings['homeassistant']:
            self._ha_discovery()
        self._send_online()
        # Set the internal MQTT tracker to True. Surprisingly, the client doesn't have a way to track this itself!
        self._mqtt_connected = True
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
            self._mqtt_client.publish(self._topics['system']['device_state']['topic'], message)
        # When disconnecting, mark the device and the bay as unavailable.
        self._send_offline()
        # Disconnect from broker
        self._mqtt_client.disconnect()
        # SEt the internal tracker to disconnected.
        self._mqtt_connected = False

    def _ha_discovery(self):
        self._logger.debug("HA Discovery has been called.")
        # Build the device JSON to include in other updates.
        self._device_info = dict(
            name=self._settings['system_name'],
            identifiers=[self._client_id],
            suggested_area='Garage',
            manufacturer='ConHugeCo',
            model='CobraBay Parking System',
            sw_version=str(__version__)
        )

        # Always do discovery for the system topics.
        for item in self._topics['system']:
            # Create items that have HA Discovery, and are enabled. Enabled/disabled is really 100% for development.
            if 'ha_discovery' in self._topics['system'][item]:
                self._logger.debug("Performing HA discovery for: {}".format(item))
                self._ha_create(topic_type='system', topic_name=item)

        for bay in self._bay_registry:
            self._ha_discovery_bay(bay)

    # Method to do discovery for
    def _ha_discovery_bay(self,bay_id):
        self._logger.debug("HA Discovery for Bay ID {} has been called.".format(bay_id))
        # Get the bay name
        bay_name = self._bay_registry[bay_id]['bay_name']
        self._logger.debug("Have registry data: {}".format(self._bay_registry[bay_id]))
        # Create the single entities. There's one of these per bay.
        # Create the single entities. There's one of these per bay.
        # Bay_display discovery is broken for now, so skipping it.
        for entity in ('bay_occupied','bay_state', 'bay_speed', 'bay_motion', 'bay_dock_time'):
            self._ha_create(topic_type='bay',
                            topic_name=entity,
                            fields={'bay_id': bay_id, 'bay_name': bay_name})
        for detector in self._bay_registry[bay_id]['detectors']:
            for entity in ('bay_position','bay_quality'):
                self._ha_create(
                    topic_type='bay',
                    topic_name=entity,
                    fields={'bay_id': bay_id,
                            'bay_name': bay_name,
                            'detector_id': detector['detector_id'],
                            'detector_name': detector['name'] }
                )

    # Method to create a properly formatted HA discovery message.
    # This expects *either* a complete config dict passed in as ha_config, or a topic_type and topic, from which
    # it will fetch the ha_discovery configuration.
    def _ha_create(self, topic_type=None, topic_name=None, fields=None):
        self._logger.debug("HA Create input:\n\tTopic Type: {}\n\tTopic Name: {}\n\tFields: {}".format(topic_type,topic_name,fields))
        # Run all the items through a formatting filter. Static fields will just have nothing happen. If fields were
        # provided and strings have replacement, they'll get replaced, ie: for bay items.
        self._logger.debug("State topic:")
        self._logger.debug(self._topics[topic_type][topic_name]['topic'])
        # Camera uses 'topic', while everything else uses 'state_topic'.
        if self._topics[topic_type][topic_name]['ha_discovery']['type'] == 'camera':
            topic_key = 'topic'
        else:
            topic_key = 'state_topic'
        try:
            config_dict = {
                topic_key: self._topics[topic_type][topic_name]['topic'].format(fields),
                'type': self._topics[topic_type][topic_name]['ha_discovery']['type'],  ## Type shouldn't ever be templated.
                'name': self._topics[topic_type][topic_name]['ha_discovery']['name'].format(fields),
                'object_id': self._topics[topic_type][topic_name]['ha_discovery']['entity'].format(fields)
            }
        except KeyError:
            raise

        # Set the Unique ID, which is the client ID plus the object ID.
        config_dict['unique_id'] = self._client_id + '.' + config_dict['object_id']
        # Always include the device info.
        config_dict['device'] = self._device_info

        optional_params = (
            'device_class',
            'encoding',
            'icon',
            'json_attributes_topic',
            'unit_of_measurement',
            'payload_on',
            'payload_off',
            'value_template')

        # Optional parameters
        for par in optional_params:
            try:
                config_dict[par] = self._topics[topic_type][topic_name]['ha_discovery'][par].format(fields)
            except KeyError:
                pass

        # Set availability. Everything depends on device_connectivity, so we don't set this for device_connectivity.

        # If this isn't device connectivity itself, make the entity depend on device connectivity
        if topic_name != 'device_connectivity':
            config_dict['availability_topic'] = self._topics['system']['device_connectivity']['topic']
            config_dict['payload_available'] = self._topics['system']['device_connectivity']['ha_discovery']['payload_on']
            config_dict['payload_not_available'] = self._topics['system']['device_connectivity']['ha_discovery']['payload_off']

        # Configuration topic to which we'll send this configuration. This is based on the entity type and entity ID.
        config_topic = "homeassistant/{}/cobrabay-{}/{}/config".\
            format(config_dict['type'],
                   self._client_id,
                   config_dict['object_id'])
        # Send it!
        ha_json = json_dumps(config_dict)
        self._logger.debug("Publishing HA discovery to topic {}\n\t{}".format(config_topic, ha_json))
        self._mqtt_client.publish(config_topic, ha_json)

    # Helper method to determine the correct unit of measure to use. When we have reported sensor units, we use
    # this method to ensure the correct unit is being put in.
    def _uom(self, unit_type):
        system = self._settings['units']
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
        elif unit_type == 'speed':
            if system == 'imperial':
                uom = 'mph'
            else:
                uom = 'kph'
        else:
            raise ValueError("{} isn't a valid unit type".format(unit_type))
        return uom

    # Quick helper methods to send online/offline messages correctly.
    def _send_online(self):
        self._mqtt_client.publish(self._topics['system']['device_connectivity']['topic'], payload='online',retain=True)

    def _send_offline(self):
        self._mqtt_client.publish(self._topics['system']['device_connectivity']['topic'], payload='offline',retain=True)