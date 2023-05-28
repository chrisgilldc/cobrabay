####
# Cobra Bay - Network
#
# Connects to the network to report bay status and take various commands.
####

import logging
from json import dumps as json_dumps
#from json import loads as json_loads
import time
import sys

# from getmac import get_mac_address
import psutil
from paho.mqtt.client import Client

from .util import Convertomatic
from .version import __version__

#
# {'units': 'imperial',
# 'system_name': 'CobraBay1',
# 'homeassistant': True,
# 'interface': 'eth0',
# 'mqtt':
#   {'broker': 'cnc.jumpbeacon.net',
#   'port': 1883,
#   'username': 'cobrabay',
#   'password': 'NbX2&38z@%H@$Cg0'}}

class CBNetwork:
    def __init__(self,
                 unit_system,
                 system_name,
                 interface,
                 mqtt_broker,
                 mqtt_port,
                 mqtt_username,
                 mqtt_password,
                 cbcore,
                 homeassistant=True,
                 log_level="WARNING",
                 mqtt_log_level="WARNING"):
        # Save parameters.
        self._pistatus = None
        self._display_obj = None
        self._mqtt_broker = mqtt_broker
        self._mqtt_port = mqtt_port
        self._mqtt_username = mqtt_username
        self._mqtt_password = mqtt_password
        self._use_homeassistant = homeassistant
        self._unit_system = unit_system
        self._system_name = system_name
        self._interface = interface
        self._cbcore = cbcore

        # Set up logger.
        self._logger = logging.getLogger("CobraBay").getChild("Network")
        self._logger.setLevel(log_level)
        self._logger.info("Network initializing...")

        # Sub-logger for just MQTT
        self._logger_mqtt = logging.getLogger("CobraBay").getChild("MQTT")
        self._logger_mqtt.setLevel(mqtt_log_level)
        if self._logger_mqtt.level != self._logger.level:
            self._logger.info("MQTT Logging level set to {}".format(self._logger_mqtt.level))

        # Create a convertomatic instance.
        self._cv = Convertomatic(self._unit_system)

        # Initialize variables
        self._reconnect_timestamp = None
        self._mqtt_connected = False
        self._discovery_log = { 'system': False }
        self._pistatus_timestamp = 0
        self._ha_repeat_override = False
        self._ha_timestamp = 0
        # Current device state. Will get updated every time we're polled.
        self._device_state = 'unknown'
        # List for commands received and to be passed upward.
        self._upward_commands = []
        # History of payloads, to determine if we need to repeat.
        self._topic_history = {}
        # Registry to keep extant bays.
        self._bay_registry = {}
        # Registry to keep triggers
        self._trigger_registry = {}

        # Pull out the MAC as the client ID.
        for address in psutil.net_if_addrs()[interface]:
            # Find the link address.
            if address.family == psutil.AF_LINK:
                self._client_id = address.address.replace(':', '').upper()
                break

        # Device info to include in all Home Assistant discovery messages.
        self._device_info = dict(
            name=self._system_name,
            identifiers=[self._client_id],
            suggested_area='Garage',
            manufacturer='ConHugeCo',
            model='CobraBay Parking System',
            sw_version=str(__version__)
        )

        self._logger.info("Defined Client ID: {}".format(self._client_id))

        # Create the MQTT Client.
        self._mqtt_client = Client(
            client_id=""
        )
        self._mqtt_client.username_pw_set(
            username=self._mqtt_username,
            password=self._mqtt_password
        )
        # Send MQTT logging to the network logger.
        # self._mqtt_client.enable_logger(self._logger)

        # Connect callback.
        self._mqtt_client.on_connect = self._on_connect
        # Disconnect callback
        self._mqtt_client.on_disconnect = self._on_disconnect

        self._logger.info('Network: Initialization complete.')

    # Registration methods
    
    # Method to register a bay.
    def register_bay(self, bay_obj):
        self._bay_registry[bay_obj.id] = bay_obj
        self._discovery_log[bay_obj.id] = False

    def unregister_bay(self, bay_id):
        try:
            del self._bay_registry[bay_id]
            del self._discovery_log[bay_id]
        except KeyError:
            self._logger.error("Asked to Unregister bay ID '{}' but bay by that ID does not exist.".format(bay_id))

    def register_trigger(self, trigger_obj):
        self._logger.debug("Received trigger registration for {}".format(trigger_obj.id))
        # Store the object!
        self._trigger_registry[trigger_obj.id] = trigger_obj
        self._logger.info("Stored trigger object '{}'".format(trigger_obj.id))
        # Add the MQTT Prefix to use to the object. Triggers set to override this will just ignore it.
        trigger_obj.topic_prefix = "CobraBay/" + self._client_id
        # Since it's possible we're already connected to MQTT, we call subscribe here separately.
        self._trigger_subscribe(trigger_obj.id)

    def _trigger_subscribe(self, trigger_id):
        trigger_obj = self._trigger_registry[trigger_id]
        self._logger.debug("Connecting trigger {}".format(trigger_id))
        self._logger.debug("Subscribing...")
        self._mqtt_client.subscribe(trigger_obj.topic)
        self._logger.debug("Connecting callback...")
        self._mqtt_client.message_callback_add(trigger_obj.topic, trigger_obj.callback)

    # Store a provided pistatus object. We can only need one, so this is easy.
    def register_pistatus(self, pistatus_obj):
        self._pistatus = pistatus_obj

    def _on_connect(self, userdata, flags, rc, properties=None):
        self._logger.info("Connected to MQTT Broker with result code: {}".format(rc))
        # # Connect to the static callback topics.
        # for type in self._topics:
        #     for item in self._topics[type]:
        #         if 'callback' in self._topics[type][item]:
        #             self._logger.debug("Network: Creating callback for {}".format(item))
        #             self._mqtt_client.message_callback_add(self._topics[type][item]['topic'],
        #                                                    self._topics[type][item]['callback'])
        # Connect to all trigger topic callbacks.
        for trigger_id in self._trigger_registry.keys():
            self._trigger_subscribe(trigger_id)
        # Attach the fallback message trapper.
        self._mqtt_client.on_message = self._on_message
        # Run Home Assistant Discovery
        self._ha_discovery()
        self._mqtt_connected = True

    def _on_disconnect(self, client, userdata, rc):
        if rc != 0:
            self._logger.warning("Unexpected disconnect with code: {}".format(rc))
        self._reconnect_timer = time.monotonic()
        self._mqtt_connected = False

    # Catchall for MQTT messages. Don't act, just log.
    def _on_message(self, client, user, message):
        self._logger.debug("Received message on topic {} with payload {}. No other handler, no action.".format(
            message.topic, message.payload
        ))

    # Message publishing method
    def _pub_message(self, topic, payload, repeat):
        # Set the send flag initially. If we've never seen the topic before or we're set to repeat, go ahead and send.
        # This skips some extra logic.
        if topic not in self._topic_history or repeat:
            send = True
        else:
            send = False

        # Put the message through conversion. This converts Quantities to proper units and then flattens to floats
        # that can be sent through MQTT and understood by Home Assistant
        message = self._cv.convert(payload)

        # If we're not already sending, then we've seen the topic before and should check for changes.
        if send is False:
            previous_state = self._topic_history[topic]
            # Both strings, compare and send if different
            if isinstance(message, str) and isinstance(previous_state, str):
                if message != previous_state:
                    send = True
                else:
                    return
            # For dictionaries, compare individual elements. This doesn't handle nested dicts, but those aren't used.
            elif isinstance(message, dict) and isinstance(previous_state, dict):
                for item in message:
                    if item not in previous_state:
                        send = True
                        break
                    if message[item] != previous_state[item]:
                        send = True
                        break
            else:
                # If type has changed, which is odd,  (and it shouldn't, usually), send it.
                if type(message) != type(previous_state):
                    send = True

        # If we're sending do it.
        if send:
            # New message becomes the previous message.
            self._topic_history[topic] = message
            # Convert the message to JSON if it's a dict, otherwise just send it.
            if isinstance(message, dict):
                outbound_message = json_dumps(message, default=str)
            else:
                outbound_message = message
            self._mqtt_client.publish(topic, outbound_message)

    # Method to be polled by the main run loop.
    # Main loop passes in the current state of the bay.
    #def poll(self, outbound_messages=None):
    def poll(self):
        # Set up the return data.
        return_data = {
            'online': self._iface_up(), # Is the interface up.
            'mqtt_status': self._mqtt_client.is_connected(),  # Are we connected to MQTT.
            'commands': {}
        }

        # If interface isn't up, not much to do, return immediately.
        if not self._iface_up():
            return return_data

        # If interface is up but broker is not connected, retry every 30s. This doesn't wait so that we can return data
        # to the main loop and let other tasks get handled. Proper docking/undocking shouldn't depend on the network so
        # we don't want to block for it.
        if not self._mqtt_connected:
            try_reconnect = False
            # Has is been 30s since the previous attempt?
            try:
                if time.monotonic() - self._reconnect_timestamp > 30:
                    try_reconnect = True
                    self._reconnect_timestamp = time.monotonic()
            except TypeError:
                try_reconnect = True
                self._reconnect_timestamp = time.monotonic()

            if try_reconnect:
                reconnect = self._connect_mqtt()
                # If we failed to reconnect, mark it as failure and return.
                if not reconnect:
                    return return_data

        # Network/MQTT is up, proceed.
        if self._mqtt_connected:
            # Send all the messages outbound.
            # For the first 100 polls after HA discovery, send everything. This makes sure
            # that values actually show up in HA.
            if self._ha_repeat_override:
                if time.monotonic() - self._ha_timestamp <= 15:
                    self._logger.debug("HA discovery {}s ago, sending all".format(time.monotonic() - self._ha_timestamp))
                    force_repeat = True
                else:
                    self._logger.debug("Have sent all messages for 15s after HA discovery. Disabling.")
                    self._ha_repeat_override = False
                    force_repeat = False
            else:
                force_repeat = False
            for message in self._mqtt_messages(force_repeat=force_repeat):
                self._logger_mqtt.debug("Publishing MQTT message: {}".format(message))
                self._pub_message(**message)
            # Check for any incoming commands.
            self._mqtt_client.loop()

        # Add the upward commands to the return data.
        return_data['commands'] = self._upward_commands
        # Remove the upward commands that are being forwarded.
        self._upward_commands = []
        return return_data

    # Check the status of the network interface.
    def _iface_up(self):
        # Pull out stats for our interface.
        stats = psutil.net_if_stats()[self._interface]
        return stats.isup

    def _connect_mqtt(self):
        # Set the last will prior to connecting.
        self._logger.info("Creating last will.")
        self._mqtt_client.will_set(
            "CobraBay/" + self._client_id + "/connectivity",
            payload='offline', qos=0, retain=True)
        try:
            self._mqtt_client.connect(host=self._mqtt_broker, port=self._mqtt_port)
        except Exception as e:
            self._logger.warning('Network: Could not connect to MQTT broker.')
            self._logger.warning('Network: ' + str(e))
            return False

        # Send a discovery message and an online notification.
        if self._use_homeassistant:
            self._ha_discovery()
            # Reset the topic history so any newly discovered entities get sent to.
            self._topic_history = {}
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
        self._logger.info('Planned disconnect with message "' + str(message) + '"')
        # If we have a disconnect message, send it to the device topic.
        if message is not None:
            self._mqtt_client.publish(self._topics['system']['device_state']['topic'], message)
        # When disconnecting, mark the device and the bay as unavailable.
        self._send_offline()
        # Disconnect from broker
        self._mqtt_client.disconnect()
        # SEt the internal tracker to disconnected.
        self._mqtt_connected = False

    @property
    def display(self):
        return self._display_obj

    @display.setter
    def display(self, display_obj):
        self._display_obj = display_obj



    # # Method to do discovery for
    # def _ha_discovery_bay(self, bay_obj:
    #     self._logger.debug("HA Discovery for Bay ID {} has been called.".format(bay_obj.id))
    #     # Get the bay name
    #     bay_name = self._bay_registry[bay_id]['bay_name']
    #     self._logger.debug("Have registry data: {}".format(self._bay_registry[bay_id]))
    #     # Create the single entities. There's one of these per bay.
    #     for entity in ('bay_occupied','bay_state', 'bay_speed', 'bay_motion', 'bay_dock_time', 'bay_command'):
    #         self._ha_create(topic_type='bay',
    #                         topic_name=entity,
    #                         fields={'bay_id': bay_id, 'bay_name': bay_name})
    #     for detector in self._bay_registry[bay_id]['detectors']:
    #         for entity in ('bay_detector','bay_quality'):
    #             self._ha_create(
    #                 topic_type='bay',
    #                 topic_name=entity,
    #                 fields={'bay_id': bay_id,
    #                         'bay_name': bay_name,
    #                         'detector_id': detector['detector_id'],
    #                         'detector_name': detector['name'] }
    #             )
    #
    # def _ha_discover_detector(self, detector_obj):
    #     pass

    # Method to create a properly formatted HA discovery message.
    # This expects *either* a complete config dict passed in as ha_config, or a topic_type and topic, from which
    # it will fetch the ha_discovery configuration.
    # def _ha_create(self, topic_type=None, topic_name=None, fields=None):
    #     self._logger.debug("HA Create input:\n\tTopic Type: {}\n\tTopic Name: {}\n\tFields: {}".format(topic_type,topic_name,fields))
    #     # Run all the items through a formatting filter. Static fields will just have nothing happen. If fields were
    #     # provided and strings have replacement, they'll get replaced, ie: for bay items.
    #     self._logger.debug("State topic:")
    #     self._logger.debug(self._topics[topic_type][topic_name]['topic'])
    #     # Camera uses 'topic', while everything else uses 'state_topic'.
    #     if self._topics[topic_type][topic_name]['ha_discovery']['type'] == 'camera':
    #         topic_key = 'topic'
    #     else:
    #         topic_key = 'state_topic'
    #     try:
    #         config_dict = {
    #             topic_key: self._topics[topic_type][topic_name]['topic'].format(fields),
    #             'type': self._topics[topic_type][topic_name]['ha_discovery']['type'],  ## Type shouldn't ever be templated.
    #             'name': self._topics[topic_type][topic_name]['ha_discovery']['name'].format(fields),
    #             'object_id': self._topics[topic_type][topic_name]['ha_discovery']['entity'].format(fields)
    #         }
    #     except KeyError:
    #         raise
    #
    #     # Set the Unique ID, which is the client ID plus the object ID.
    #     config_dict['unique_id'] = self._client_id + '.' + config_dict['object_id']
    #     # Always include the device info.
    #     config_dict['device'] = self._device_info
    #
    #     optional_params = (
    #         'command_template',
    #         'device_class',
    #         'image_encoding',
    #         'icon',
    #         'json_attributes_topic',
    #         'unit_of_measurement',
    #         'options',
    #         'payload_on',
    #         'payload_off',
    #         'payload_not_available',
    #         'value_template')
    #
    #     # Optional parameters
    #     for par in optional_params:
    #         try:
    #             config_dict[par] = self._topics[topic_type][topic_name]['ha_discovery'][par].format(fields)
    #         except KeyError:
    #             pass
    #
    #     # Set availability. Everything depends on device_connectivity, so we don't set this for device_connectivity.
    #
    #     # If this isn't device connectivity itself, make the entity depend on device connectivity
    #     if topic_name != 'device_connectivity':
    #         config_dict['availability_topic'] = self._topics['system']['device_connectivity']['topic']
    #         config_dict['payload_available'] = self._topics['system']['device_connectivity']['ha_discovery']['payload_on']
    #         config_dict['payload_not_available'] = self._topics['system']['device_connectivity']['ha_discovery']['payload_off']
    #
    #     # Configuration topic to which we'll send this configuration. This is based on the entity type and entity ID.
    #     config_topic = "homeassistant/{}/CobraBay-{}/{}/config".\
    #         format(config_dict['type'],
    #                self._client_id,
    #                config_dict['object_id'])
    #     # Send it!
    #     ha_json = json_dumps(config_dict)
    #     self._logger.debug("Publishing HA discovery to topic {}\n\t{}".format(config_topic, ha_json))
    #     self._mqtt_client.publish(config_topic, ha_json)


    # Helper method to determine the correct unit of measure to use. When we have reported sensor units, we use
    # this method to ensure the correct unit is being put in.
    def _uom(self, unit_type):
        if unit_type == 'length':
            if self._unit_system == 'imperial':
                uom = "in"
            else:
                uom = "cm"
        elif unit_type == 'temp':
            if self._unit_system == 'imperial':
                uom = "°F"
            else:
                uom = "°C"
        elif unit_type == 'speed':
            if self._unit_system == 'imperial':
                uom = 'mph'
            else:
                uom = 'kph'
        else:
            raise ValueError("{} isn't a valid unit type".format(unit_type))
        return uom

    # Quick helper methods to send online/offline messages correctly.
    def _send_online(self):
        self._mqtt_client.publish("CobraBay/" + self._client_id + "/connectivity",
                                  payload="online",
                                  retain=True)

    def _send_offline(self):
        self._mqtt_client.publish("CobraBay/" + self._client_id + "/connectivity",
                                  payload="offline",retain=True)
        
    # MQTT Message generators. Network module creates MQTT messages from object states. This centralizes MQTT message
    # creation.
    def _mqtt_messages(self, force_repeat=False):
        # Create the outbound list.
        outbound_messages = []
        # Send hardware status every 60 seconds.
        if time.monotonic() - self._pistatus_timestamp >= 60:
            self._logger.debug("Hardware status timer up, sending status.")
            # Start the outbound messages with the hardware status.
            outbound_messages.extend(self._mqtt_messages_pistatus(self._pistatus))
            self._pistatus_timestamp = time.monotonic()
        # Add the display. System can't seem to validly compare, so we should always send.
        outbound_messages.append(
            {'topic': 'CobraBay/' + self._client_id + '/display', 'payload': self.display.current, 'repeat': True})
        # Add in all bays.
        self._logger.debug("Generating messages for bays: {}".format(self._bay_registry))
        for bay in self._bay_registry:
            outbound_messages.extend(self._mqtt_messages_bay(self._bay_registry[bay]))

        # If repeat has been set to override, go through and replace the default with the override value.
        if force_repeat:
            self._logger.debug("Overriding MQTT message repeat state to True")
            for i in range(0,len(outbound_messages)):
                outbound_messages[i]['repeat'] = True
        return outbound_messages
    
    def _mqtt_messages_pistatus(self, input_obj):
        outbound_messages = [
            {'topic': 'CobraBay/' + self._client_id + '/cpu_pct', 'payload': input_obj.status('cpu_pct'), 'repeat': False },
            {'topic': 'CobraBay/' + self._client_id + '/cpu_temp', 'payload': input_obj.status('cpu_temp'), 'repeat': False},
            {'topic': 'CobraBay/' + self._client_id + '/mem_info', 'payload': input_obj.status('mem_info'), 'repeat': False},
            {'topic': 'CobraBay/' + self._client_id + '/undervoltage', 'payload': input_obj.status('undervoltage'), 'repeat': False}
        ]
        return outbound_messages
    
    def _mqtt_messages_bay(self, input_obj):
        outbound_messages = []
        # Topic base for convenience.
        topic_base = 'CobraBay/' + self._client_id + '/' + input_obj.id + '/'
        # Bay state
        outbound_messages.append({'topic': topic_base + 'state', 'payload': input_obj.state, 'repeat': False})
        # Bay vector
        outbound_messages.append({'topic': topic_base + 'vector', 'payload': input_obj.vector, 'repeat': False})
        # Bay vector
        outbound_messages.append({'topic': topic_base + 'motion_timer', 'payload': input_obj.motion_timer, 'repeat': False})


        # Bay occupancy. This value can get wonky as detectors are shutting down, so don't update during shutdown.
        if self._cbcore.system_state != 'shutdown':
            outbound_messages.append({'topic': topic_base + 'occupancy', 'payload': input_obj.occupied, 'repeat': False})

        detector_messages = []
        for detector in input_obj.detectors:
            detector_messages.extend(self._mqtt_messages_detector(input_obj.detectors[detector], topic_base + 'detectors/'))
        # self._logger.debug("Built detector messages:")
        # self._logger.debug(pformat(detector_messages))
        outbound_messages.extend(detector_messages)
        # self._logger.debug("Complete Bay Message Set:")
        # self._logger.debug(pformat(outbound_messages))
        return outbound_messages

    def _mqtt_messages_detector(self, input_obj, topic_base=None):
        self._logger_mqtt.debug("Building MQTT messages for detector: {}".format(input_obj.id))
        if topic_base is None:
            topic_base = 'CobraBay/' + self._client_id + '/independent_detectors'
        topic_base = topic_base + input_obj.id + '/'
        outbound_messages = []
        # Detector State, the assigned state of the detector by the system.
        outbound_messages.append({'topic': topic_base + 'state', 'payload': input_obj.state, 'repeat': False})
        # Detector status, its actual current state.
        outbound_messages.append({'topic': topic_base + 'status', 'payload': input_obj.status, 'repeat': False})
        # Is the detector in fault?
        outbound_messages.append({'topic': topic_base + 'fault', 'payload': input_obj.fault, 'repeat': False})
        # Send value, raw value and quality if detector is ranging.
        if input_obj.state == 'ranging':
            # Detector Value.
            outbound_messages.append({'topic': topic_base + 'reading', 'payload': input_obj.value, 'repeat': False})
            # Detector reading unadjusted by depth.
            outbound_messages.append({'topic': topic_base + 'raw_reading', 'payload': input_obj.value_raw, 'repeat': False})
            # Detector Quality
            outbound_messages.append({'topic': topic_base + 'quality', 'payload': input_obj.quality, 'repeat': False})
        self._logger_mqtt.debug("Have detector messages: {}".format(outbound_messages))
        return outbound_messages

    def _ha_discovery(self, force=False):
        for item in self._discovery_log:
            self._logger.debug("Discovery Log: {}".format(self._discovery_log))
            self._logger.debug("Checking discovery for: {}".format(item))
            # Run the discovery if we haven't before, or if force is requested.
            if not self._discovery_log[item] or force:
                if item == 'system':
                    self._logger.info("Sending Home Assistant discovery for '{}'.".format(item))
                    self._ha_discovery_system()
                else:
                    self._logger.info("Sending home assistant discovery for bay ID: {}".format(item))
                    self._ha_discovery_bay(item)
                self._discovery_log['system'] = True
        self._ha_repeat_override = True
        self._ha_timestamp = time.monotonic()

    # Create HA discovery message.
    def _ha_discover(self, name, topic, type, entity, device_info=True, system_avail=True, avail=None, avail_mode=None, **kwargs):

        # Trap unknown types.
        if type not in ('camera','binary_sensor','sensor'):
            raise ValueError("Type must be 'camera','binary_sensor' or 'sensor'")

        # Adjust the topic key based on the type, because the syntax varries.
        if type == 'camera':
            topic_key = 'topic'
        else:
            topic_key = 'state_topic'

        # Set up the initial discovery dictionary for all types.
        discovery_dict = {
            topic_key: topic,
            'type': type,
            'name': name,
            'object_id': entity,
            'unique_id': self._client_id + '.' + entity,
            'availability': []
        }
        # Add device info.
        if device_info:
            discovery_dict['device'] = self._device_info

        if type == 'camera':
            required_parameters = ['image_encoding']
            nullable_parameters = []
            optional_parameters = ['icon']
        elif type == 'binary_sensor':
            required_parameters = ['payload_on','payload_off']
            nullable_parameters = ['device_class']
            optional_parameters = ['icon','value_template']
        elif type == 'sensor':
            required_parameters = []
            nullable_parameters = []
            optional_parameters = ['icon','unit_of_measurement', 'value_template']
        else:
            raise

        for param in required_parameters:
            try:
                discovery_dict[param] = kwargs[param]
            except KeyError as e:
                raise e

        for param in nullable_parameters:
            try:
                discovery_dict[param] = kwargs[param]
            except KeyError:
                discovery_dict[param] = None

        for param in optional_parameters:
            try:
                discovery_dict[param] = kwargs[param]
            except KeyError:
                pass

        # Should we include the system availability? Obviously, we exclude this for the system availability itself!
        # May want to exclude in certain other cases.
        if system_avail:
            sa = {
                'topic': 'CobraBay/' + self._client_id + '/connectivity',
                'payload_available': 'online',
                'payload_not_available': 'offline' }
            discovery_dict['availability'].append(sa)

        # Are other availability topics defined? If so, check and include.
        if avail is not None:
            # If other avai
            for item in avail:
                # Must be a dict.
                if not isinstance(item,dict):
                    self._logger.warning("Additional availability '{}' not a dict, skipping.".format(item))
                    continue
                elif 'topic' not in item:
                    self._logger.warning("Additional availability '{}' does not have a topic defined.".format(item))
                else:
                    self._logger.debug("Adding additional availability '{}'".format(item))
                    discovery_dict['availability'].append(item)

        # Determine the availability mode automatically if not explicitly set.
        if avail_mode is None:
            discovery_dict['availability_mode'] = 'all'
        else:
            discovery_dict['availability_mode'] = avail_mode

        discovery_json = json_dumps(discovery_dict)
        discovery_topic = "homeassistant/{}/CobraBay_{}/{}/config".\
            format(type,self._client_id,discovery_dict['object_id'])
        self._logger.info("Publishing HA discovery to topic '{}'\n\t{}".format(discovery_topic, discovery_json))
        self._mqtt_client.publish(discovery_topic, discovery_json)
        # Remove this topic from the topic history if it exists.
        try:
            self._logger.debug("Removed previous value '{}' for topic '{}'".format(self._topic_history[topic], topic))
            self._topic_history[topic] = None
        except KeyError:
            self._logger.debug("Topic '{}' had no previous state to remove.".format(topic))

    def _ha_discovery_system(self):
        self._logger.info("Performing HA discovery for system")
        # Device connectivity
        self._ha_discover(
            name="{} Connectivity".format(self._system_name),
            topic="CobraBay/" + self._client_id + "/connectivity",
            type='binary_sensor',
            entity='{}_connectivity'.format(self._system_name.lower()),
            device_class='connectivity',
            payload_on='online',
            payload_off='offline',
        )
        # CPU Percentage
        self._ha_discover(
            name="{} CPU Use".format(self._system_name),
            topic="CobraBay/" + self._client_id + "/cpu_pct",
            type="sensor",
            entity="{}_cpu_pct".format(self._system_name.lower()),
            unit_of_measurement="%",
            icon="mdi:chip"
        )
        # CPU Temperature
        self._ha_discover(
            name="{} CPU Temperature".format(self._system_name),
            topic="CobraBay/" + self._client_id + "/cpu_temp",
            type="sensor",
            entity="{}_cpu_temp".format(self._system_name.lower()),
            unit_of_measurement=self._uom('temp'),
            icon="mdi:thermometer"
        )
        # Memory Info
        self._ha_discover(
            name="{} Memory Free".format(self._system_name),
            topic="CobraBay/" + self._client_id + "/mem_info",
            type="sensor",
            entity="{}_mem_info".format(self._system_name.lower()),
            value_template='{{ value_json.mem_pct }}',
            unit_of_measurement='%',
            icon="mdi:memory"
        )
        # Undervoltage
        self._ha_discover(
            name="{} Undervoltage".format(self._system_name),
            topic="CobraBay/" + self._client_id + "/undervoltage",
            type="binary_sensor",
            entity="{}_undervoltage".format(self._system_name.lower()),
            payload_on="true",
            payload_off="false",
            icon="mdi:alert-octagram"
        )
        # Display
        self._ha_discover(
            name="{} Display".format(self._system_name),
            topic="CobraBay/" + self._client_id + "/display",
            type="camera",
            entity="{}_display".format(self._system_name.lower()),
            image_encoding='b64',
            icon="mdi:image-area"
        )

    def _ha_discovery_bay(self, bay_id):
        bay_obj = self._bay_registry[bay_id]
        topic_base = "CobraBay/" + self._client_id + "/" + bay_obj.id + "/"
        # Discover the Bay level status items.
        # Bay State
        self._ha_discover(
            name="{} State".format(bay_obj.name),
            topic=topic_base + "state",
            type="sensor",
            entity="{}_state".format(bay_obj.id),
            value_template="{{ value|capitalize }}"
        )
        # Bay Vector
        self._ha_discover(
            name="{} Speed".format(bay_obj.name),
            topic=topic_base + "vector",
            type="sensor",
            entity="{}_speed".format(bay_obj.id),
            value_template="{{ value_json.speed }}",
            unit_of_measurement=self._uom('speed')

        )
        self._ha_discover(
            name="{} Direction".format(bay_obj.name),
            topic=topic_base + "vector",
            type="sensor",
            entity="{}_direction".format(bay_obj.id),
            value_template="{{ value_json.direction|capitalize }}",
        )

        # # Bay Motion Timer
        #
        # # Bay Occupancy
        self._ha_discover(
            name="{} Occupied".format(bay_obj.name),
            topic=topic_base + "occupancy",
            type="binary_sensor",
            entity="{}_occupied".format(bay_obj.id),
            payload_on="true",
            payload_off="false",
            payload_not_available="error"
        )

        # Discover the detectors....
        print(bay_obj.detectors)
        for detector in bay_obj.detectors:
            det_obj = bay_obj.detectors[detector]
            detector_base = topic_base + "detectors/" + det_obj.id + "/"
            # Detector reading.
            self._ha_discover(
                name="Detector - {} State".format(det_obj.name),
                topic=detector_base + "state",
                type="sensor",
                entity="{}_{}_{}_state".format(self._system_name, bay_obj.id, det_obj.id),
                value_template="{{ value|capitalize }}"
            )
            self._ha_discover(
                name="Detector - {} Status".format(det_obj.name),
                topic=detector_base + "status",
                type="sensor",
                entity="{}_{}_status".format(bay_obj.id, det_obj.id),
                value_template="{{ value|capitalize }}"
            )
            self._ha_discover(
                name="Detector - {} Fault".format(det_obj.name),
                topic=detector_base + "fault",
                type="binary_sensor",
                entity="{}_{}_{}_state".format(self._system_name, bay_obj.id, det_obj.id),
                payload_on = "true",
                payload_off = "false"
            )
            self._ha_discover(
                name="Detector - {} Reading".format(det_obj.name),
                topic=detector_base + "reading",
                type="sensor",
                entity="{}_{}_{}_reading".format(self._system_name, bay_obj.id, det_obj.id),
            )
            self._ha_discover(
                name="Detector - {} Raw Reading".format(det_obj.name),
                topic=detector_base + "raw_reading",
                type="sensor",
                entity="{}_{}_{}_raw_reading".format(self._system_name, bay_obj.id, det_obj.id),
            )