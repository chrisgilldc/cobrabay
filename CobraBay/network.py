####
# Cobra Bay - Network
#
# Connects to the network to report bay status and take various commands.
####

import logging
from json import dumps as json_dumps
from json import loads as json_loads
import time
# from getmac import get_mac_address
import psutil
from paho.mqtt.client import Client
from .util import Convertomatic
from .version import __version__
from CobraBay.const import *

# TODO: Reorganize class to standard.
# FixMe: Maybe MQTT server reconnect issue.


class CBNetwork:
    def __init__(self,
                 unit_system,
                 system_name,
                 interface,
                 broker,
                 port,
                 username,
                 password,
                 cbcore,
                 ha_discover=True,
                 chattiness=None,
                 accept_commands=True,
                 log_level="WARNING",
                 mqtt_log_level="DISABLED"):
        """

        :param unit_system: Unit system for sending messages. May be 'metric' or 'imperial'.
        :param unit_system: str
        :param system_name:
        :param interface:
        :param broker: IP or hostname of the MQTT broker.
        :param port: Port of the MQTT broker. Defaults to 1883.
        :param username:
        :param password:
        :param cbcore:
        :param ha_discover:
        :param accept_commands:
        :param log_level:
        :param mqtt_log_level:
        """

        # Set up logger.
        self._logger = logging.getLogger("CobraBay").getChild("Network")
        self._logger.setLevel(log_level.upper())
        self._logger.info("Network initializing...")

        # Save parameters.
        # Reference to the CobraBay Core.
        self._cbcore = cbcore
        # How chatty sending should be
        if chattiness is None:
            # Make sure this defaults out. Should be covered by the config handler, but you never know!
            self._chattiness = {
                'sensors_raw': False,
                'sensors_always_send': False
            }
        else:
            self._chattiness = chattiness
            if self._chattiness['sensors_raw']:
                self._logger.info("Raw sensor chattiness enabled!")
            if self._chattiness['sensors_always_send']:
                self._logger.info("Sensors always send enabled! Prepare to be deluged!")
        # Interface to use.
        self._interface = interface
        self._mqtt_broker = broker
        self._mqtt_port = port
        self._mqtt_username = username
        self._mqtt_password = password
        # Dict for all the Home Assistant info.
        self._ha_info = {
            'discover': ha_discover,
            'override': False,
            'start': time.monotonic()
        }
        self._system_name = system_name
        self._unit_system = unit_system

        # Initialize variables.
        # Reference to the CBDisplay object.
        self._display_obj = None
        # Reference to the Hardware Monitor
        self._pistatus = None

        # Create a sublogger for the MQTT client.
        self._logger_mqtt = logging.getLogger("CobraBay").getChild("MQTT")
        # If MQTT logging is disabled, send it to a null logger.
        if mqtt_log_level == 'DISABLE':
            self._logger.info("MQTT client logging is disabled. Set 'mqtt' in logging section if you want it enabled.")
            self._logger_mqtt.addHandler(logging.NullHandler())
            self._logger_mqtt.propagate = False
        else:
            self._logger_mqtt.setLevel(mqtt_log_level.upper())

        # Create a convertomatic instance.
        self._cv = Convertomatic(self._unit_system)

        # Initialize variables
        self._reconnect_timestamp = None
        self._mqtt_connected = False
        self._discovery_log = {'system': False, 'sensors': False}
        self._pistatus_timestamp = 0

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
        # Send MQTT logging to the MQTT sublogger
        if mqtt_log_level != 'DISABLE':
            self._mqtt_client.enable_logger(self._logger_mqtt)

        # Connect callback.
        self._mqtt_client.on_connect = self._on_connect
        # Disconnect callback
        self._mqtt_client.on_disconnect = self._on_disconnect

        self._logger.info('Network: Initialization complete.')

    # Registration methods

    # Method to register a bay.
    def register_bay(self, bay_obj):
        self._logger.debug("Registered Bay ID '{}'".format(bay_obj.id))
        self._bay_registry[bay_obj.id] = bay_obj
        self._discovery_log[bay_obj.id] = False

    def deregister_bay(self, bay_id):
        self._logger.debug("Deregistering Bay ID '{}'".format(bay_id))
        try:
            del self._bay_registry[bay_id]
            del self._discovery_log[bay_id]
        except KeyError:
            self._logger.error("Asked to deregister Bay ID '{}' but bay with that ID does not exist.".format(bay_id))
        else:
            self._logger.debug("Bay ID '{}' deregistered.".format(bay_id))

    def register_sensormgr(self, sensormgr_obj):
        """Register the Sensor Manager with the Network handler"""
        self._sensormgr = sensormgr_obj

    def register_trigger(self, trigger_obj):
        self._logger.debug("Received trigger registration for {}".format(trigger_obj.id))
        # Store the object!
        self._trigger_registry[trigger_obj.id] = trigger_obj
        self._logger.info("Stored trigger object '{}'".format(trigger_obj.id))
        # Add the MQTT Prefix to use to the object. Triggers set to override this will just ignore it.
        trigger_obj.topic_prefix = "CobraBay/" + self._client_id
        # Since it's possible we're already connected to MQTT, we call subscribe here separately.
        self._trigger_subscribe(trigger_obj.id)

    def deregister_trigger(self, trigger_id):
        self._logger.debug("Deregistering Trigger ID '{}'".format(trigger_id))
        try:
            # Remove the callback
            self._mqtt_client.message_callback_remove(self._trigger_registry[trigger_id].callback)
            # Unsubscribe from the MQTT topic.
            self._mqtt_client.unsubscribe(self._trigger_registry[trigger_id].topic)
            # Remove the trigger from the registry.
            del self._trigger_registry[trigger_id]
        except KeyError:
            self._logger.error(
                "Asked to deregister Trigger ID '{}' but trigger with that ID does not exist.".format(trigger_id))
        else:
            self._logger.debug("Trigger ID '{}' deregistered.".format(trigger_id))

    def _trigger_subscribe(self, trigger_id):
        trigger_obj = self._trigger_registry[trigger_id]
        self._logger.debug("Connecting trigger {}".format(trigger_id))
        self._logger.debug("Subscribing to '{}'".format(trigger_obj.topic))
        self._mqtt_client.subscribe(trigger_obj.topic)
        self._logger.debug("Connecting callback...'{}'".format(trigger_obj.callback))
        self._mqtt_client.message_callback_add(trigger_obj.topic, trigger_obj.callback)

    # Store a provided pistatus object. We can only need one, so this is easy.
    def register_pistatus(self, pistatus_obj):
        self._pistatus = pistatus_obj

    def _on_connect(self, userdata, flags, rc, properties=None):
        self._logger.info("Connected to MQTT Broker with result code: {}".format(rc))
        self._mqtt_connected = True
        # Connect to all trigger topic callbacks.
        for trigger_id in self._trigger_registry.keys():
            self._trigger_subscribe(trigger_id)
        # Attach the fallback message trapper.
        self._mqtt_client.on_message = self._on_message
        # Run Home Assistant Discovery
        self._ha_discovery()

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
        self._logger.debug("Processing message publication on topic '{}'".format(topic))
        # Set the send flag initially. If we've never seen the topic before or we're set to repeat, go ahead and send.
        # This skips some extra logic.
        if topic not in self._topic_history:
            self._logger.debug("Topic not in history, sending...")
            send = True
        elif repeat:
            self._logger.debug("Repeat explicitly enabled, sending...")
            send = True
        else:
            send = False

        # Put the message through conversion. This converts Quantities to proper units and then flattens to floats
        # that can be sent through MQTT and understood by Home Assistant
        message = self._cv.convert(payload)

        # If we're not already sending, then we've seen the topic before and should check for changes.
        if send is False:
            previous_payload = self._topic_history[topic]
            # Both strings, compare and send if different
            if (isinstance(message, str) and isinstance(previous_payload, str)) or \
                    (isinstance(message, (int, float)) and isinstance(previous_payload, (int, float))):
                if message != previous_payload:
                    self._logger.debug("Payload '{}' does not match previous payload '{}'. Publishing.".
                                       format(payload, previous_payload))
                    send = True
                else:
                    self._logger.debug("Payload has not changed, will not publish")
                    return
            # For dictionaries, compare individual elements. This doesn't handle nested dicts, but those aren't used.
            elif isinstance(message, dict) and isinstance(previous_payload, dict):
                for item in message:
                    if item not in previous_payload:
                        self._logger.debug("Payload dict contains new key, publishing.")
                        send = True
                        break
                    if message[item] != previous_payload[item]:
                        self._logger.debug("Payload dict key '{}' has changed value, publishing.".format(item))
                        send = True
                        break
            # If type has changed, which is odd,  (and it shouldn't, usually), send it.
            elif type(message) is not type(previous_payload):
                self._logger.debug("Payload type has changed from '{}' to '{}'. Unusual, but publishing anyway.".
                                   format(type(previous_payload), type(payload)))
                send = True

        # If we're sending do it.
        if send:
            self._logger.debug("Publishing message...")
            # New message becomes the previous message.
            self._topic_history[topic] = message
            # Convert the message to JSON if it's a dict, otherwise just send it.
            if isinstance(message, dict):
                outbound_message = json_dumps(message, default=str)
            else:
                outbound_message = message
            try:
                self._mqtt_client.publish(topic, outbound_message)
            except TypeError as te:
                self._logger.error("Received TypeError when publishing outbound message '{}' ({})"
                                   .format(outbound_message, type(outbound_message)))
                self._logger.exception(te)

    # Method to be polled by the main run loop.
    # Main loop passes in the current state of the bay.
    def poll(self, status=None):
        # Set up the return data.
        return_data = {
            'online': self._iface_up(),  # Is the interface up.
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
                    self._logger.info("30s since previous connection attempt. Retrying...")
                    try_reconnect = True
                    self._reconnect_timestamp = time.monotonic()
            except TypeError:
                try_reconnect = True
                self._reconnect_timestamp = time.monotonic()

            if try_reconnect:
                reconnect = self._connect_mqtt()
                # If we failed to reconnect, mark it as failure and return.
                if not reconnect:
                    self._logger.warning("Could not connect to MQTT server. Will retry in 30s.")
                    return return_data

        # Network/MQTT is up, proceed.
        if self._mqtt_connected:
            # Send all the messages outbound.
            # For the first 15s after HA discovery, send everything. This makes sure data arrives after HA has
            # established entities.
            if self._ha_info['override']:
                if time.monotonic() - self._ha_info['start'] <= 15:
                    self._logger.debug("HA discovery {}s ago, sending all".format(time.monotonic() -
                                                                                  self._ha_info['start']))
                    force_repeat = True
                else:
                    self._logger.info("Have sent all messages for 15s after HA discovery. Disabling.")
                    self._ha_info['override'] = False
                    force_repeat = False
            else:
                force_repeat = False
            # Publish messages.
            for message in self._mqtt_messages(force_repeat=force_repeat):
                # self._logger_mqtt.debug("Publishing MQTT message: {}".format(message))
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
            self._logger.warning("Could not connect to MQTT broker. Received exception '{}'".format(e))
            return False

        # Send a discovery message and an online notification.
        if self._ha_info['discover']:
            self._ha_discovery()
            # Reset the topic history so any newly discovered entities get sent to.
            self._topic_history = {}
        self._send_online()
        # Set the internal MQTT tracker to True. Surprisingly, the client doesn't have a way to track this itself!
        self._mqtt_connected = True
        return True

    def connect(self):
        """
        Convenience method to connect to MQTT.
        :return:
        """
        try:
            self._connect_mqtt()
        except Exception as e:
            raise
        return None

    def disconnect(self, message=None):
        """
        Convenience method to perform planned disconnects. Will log with specific 'message' if provided.
        :param message:
        """
        self._logger.info('Planned disconnect with message "' + str(message) + '"')
        # If we have a disconnect message, send it to the device topic.
        # if message is not None:
        #     self._mqtt_client.publish(self._topics['system']['device_state']['topic'], message)
        # When disconnecting, mark the device and the bay as unavailable.
        self._send_offline()
        # Disconnect from broker
        self._mqtt_client.disconnect()
        # Set the internal tracker to disconnected.
        self._mqtt_connected = False

    @property
    def display(self):
        return self._display_obj

    @display.setter
    def display(self, display_obj):
        self._display_obj = display_obj

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
                                  payload="offline", retain=True)

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
        # Add the direct sensor readings if requested.
        if self._chattiness['sensors_raw']:
            outbound_messages.extend(self._mqtt_messages_sensors(force_publish=self._chattiness['sensors_always_send']))

        # Add in all bays.
        self._logger.debug("Generating messages for bays: {}".format(self._bay_registry))
        for bay in self._bay_registry:
            outbound_messages.extend(self._mqtt_messages_bay(self._bay_registry[bay]))

        # If repeat has been set to override, go through and replace the default with the override value.
        if force_repeat:
            self._logger.debug("Overriding MQTT message repeat state to True")
            for i in range(0, len(outbound_messages)):
                outbound_messages[i]['repeat'] = True
        return outbound_messages

    def _mqtt_messages_sensors(self, force_publish=False):
        outbound_messages = []
        for sensor_id in self._cbcore.configured_sensors:
            outbound_messages.extend(self._mqtt_messages_sensor(sensor_id, force_publish=force_publish))
        self._logger.debug("Compiled sensor messages: {}".format(outbound_messages))
        return outbound_messages


    def _mqtt_messages_pistatus(self, input_obj):
        outbound_messages = [
            {'topic': 'CobraBay/' + self._client_id + '/cpu_pct', 'payload': input_obj.status('cpu_pct'),
             'repeat': False},
            {'topic': 'CobraBay/' + self._client_id + '/cpu_temp', 'payload': input_obj.status('cpu_temp'),
             'repeat': False},
            {'topic': 'CobraBay/' + self._client_id + '/mem_info', 'payload': input_obj.status('mem_info'),
             'repeat': False},
            {'topic': 'CobraBay/' + self._client_id + '/undervoltage', 'payload': input_obj.status('undervoltage'),
             'repeat': False}
        ]
        return outbound_messages

    def _mqtt_messages_bay(self, input_obj):
        """

        :param input_obj:
        :type input_obj: CobraBay.CBBay
        :return:
        """
        outbound_messages = []
        # Topic base for convenience.
        topic_base = 'CobraBay/' + self._client_id + '/' + input_obj.id + '/'
        # Bay state
        outbound_messages.append({'topic': topic_base + 'state', 'payload': input_obj.state, 'repeat': False})

        # if self._ha_info['override']:
        #     outbound_messages.append({'topic': topic_base + 'occupancy', 'payload': input_obj.occupied, 'repeat': False})

        # # Only create sensor-based messages if the sensors are active, which happens when the bay is running.
        # if input_obj.state in (BAYSTATE_DOCKING, BAYSTATE_UNDOCKING, BAYSTATE_VERIFY) or self._ha_info['override']:
        # Bay Occupancy
        outbound_messages.append({'topic': topic_base + 'occupancy', 'payload': input_obj.occupied, 'repeat': False})
        # Bay vector
        self._logger.debug("Sending vector value '{}'".format(input_obj.vector))
        # Directly casting the Vector namedtuple to dict throws ValueErrors in some cases, so doing this manually.
        outbound_messages.append(
            {'topic': topic_base + 'vector',
             'payload':
                 {'speed': input_obj.vector.speed, 'direction': input_obj.vector.direction},
             'repeat': False})
        # Bay motion timer
        outbound_messages.append(
            {'topic': topic_base + 'motion_timer', 'payload': input_obj.motion_timer, 'repeat': False})
        # Sensors. They can get wonky during shutdown, so skip them then.
        self._logger.debug("Bay sensor info has: {}".format(input_obj.sensor_info))
        self._logger.debug("Bay state is: {}".format(input_obj.state))

        if (self._cbcore.system_state != 'shutdown' and
                ( input_obj.state in (BAYSTATE_DOCKING, BAYSTATE_UNDOCKING, BAYSTATE_VERIFY)
                    or self._chattiness['sensors_always_send']) ):
            self._logger.debug("Sending bay sensor information.")
            # Values which exist for both longitudinal and lateral sensors.
            for sensor_id in input_obj.configured_sensors['long'] + input_obj.configured_sensors['lat']:
                self._logger.debug("Sending for '{}'".format(sensor_id))
                # Only send if the sensor actually has a value. This will usually be right at startup.
                # Quality
                # TODO: Streamline this logic once the underlying Bay issues are fixed.
                try:
                    outbound_messages.append(
                        {'topic': topic_base + 'sensors/' + sensor_id + '/quality',
                         'payload': input_obj.sensor_info['quality'][sensor_id],
                         'repeat': self._chattiness['sensors_always_send']})
                except KeyError:
                    outbound_messages.append(
                        {'topic': topic_base + 'sensors/' + sensor_id + '/quality',
                         'payload': GEN_UNKNOWN,
                         'repeat': self._chattiness['sensors_always_send']})

                # Adjusted Range
                try:
                    outbound_messages.append(
                        {'topic': topic_base + 'sensors/' + sensor_id + '/reading',
                         'payload': input_obj.sensor_info['reading'][sensor_id],
                         'repeat': self._chattiness['sensors_always_send']})
                except KeyError:
                    outbound_messages.append(
                        {'topic': topic_base + 'sensors/' + sensor_id + '/reading',
                         'payload': GEN_UNKNOWN, 'repeat': self._chattiness['sensors_always_send']})

            # Lateral-Only values.
            for sensor_id in input_obj.configured_sensors['lat']:
                self._logger.debug("Sending lateral-specific for '{}'".format(sensor_id))
                # Intercepted status.
                try:
                    outbound_messages.append(
                        {'topic': topic_base + 'sensors/' + sensor_id + '/intercepted',
                         'payload': input_obj.sensor_info['intercepted'][sensor_id],
                         'repeat': self._chattiness['sensors_always_send']})
                except KeyError:
                    outbound_messages.append(
                        {'topic': topic_base + 'sensors/' + sensor_id + '/intercepted',
                         'payload': GEN_UNKNOWN, 'repeat': self._chattiness['sensors_always_send']})

        # If performing a VERIFY on the bay, we now have all the messages, set bay back to ready.
        if input_obj.state == BAYSTATE_VERIFY:
            input_obj.state = BAYSTATE_READY
        return outbound_messages

    # def publish_bay_detectors(self, bay_id, publish=False):
    #     try:
    #         bay_obj = self._bay_registry[bay_id]
    #     except KeyError:
    #         self._logger.error("Asked to publish detectors for non-existent Bay ID '{}'. Cannot do!".format(bay_id))
    #         return
    #
    #     sensor_messages = []
    #     topic_base = 'CobraBay/' + self._client_id + '/' + bay_obj.id + '/'
    #     #TODO: Update this to handle bay-adjusted sensor values.
    #     # for sensor in bay_obj.detectors:
    #     #     sensor_messages.extend(
    #     #         self._mqtt_messages_sensor(bay_obj.detectors[detector], topic_base + 'sensors/'))
    #
    #
    #     if publish:
    #         for message in sensor_messages:
    #             self._pub_message(**message)
    #     else:
    #         return sensor_messages

    def _mqtt_messages_sensor(self, sensor_id, topic_base=None, force_publish=False):
        """
        Create messages for a given sensor id.

        :param sensor_id: Sensor to send
        :param topic_base: Base topic
        :param force_publish: Public even if value hasn't changed.
        :return:
        """
        self._logger_mqtt.debug("Building MQTT messages for sensor: {}".format(sensor_id))
        if topic_base is None:
            topic_base = 'CobraBay/' + self._client_id + '/sensors/'
        topic_base = topic_base + sensor_id + '/'
        try:
            sensor_latest_data = self._cbcore.sensor_latest_data[sensor_id]
        except KeyError:
            self._logger.debug("No data available for sensor id '{}'. Nothing to send.".format(sensor_id))
            # Must return an empty list, None isn't iterable, duh.
            return []
        else:
            self._logger.debug("Latest sensor data: {}".format(sensor_latest_data))
            outbound_messages = [
                # Sensor State - The requested state for the sensor.
                {'topic': topic_base + 'state', 'payload': sensor_latest_data.state, 'repeat': force_publish},
                # Sensor Status - What the sensor is actually doing. Should be the same!
                {'topic': topic_base + 'status', 'payload': sensor_latest_data.status, 'repeat': force_publish},
                # Fault - If Status != State -> Fault. This is a boolean for easy conversion to an HA binary_sensor.
                {'topic': topic_base + 'fault', 'payload': sensor_latest_data.fault, 'repeat': force_publish},
            ]
            # Send value, raw value and quality if detector is ranging.
            if sensor_latest_data.response_type == SENSOR_RESP_OK:
                # Detector Range.
                outbound_messages.append(
                    {'topic': topic_base + 'reading',
                     'payload': sensor_latest_data.range,
                     'repeat': force_publish})
                # Detector Temperature
                outbound_messages.append(
                    {'topic': topic_base + 'temp',
                     'payload': sensor_latest_data.temp,
                     'repeat': force_publish})

            self._logger_mqtt.debug("Have sensor messages: {}".format(outbound_messages))
            return outbound_messages

    def _ha_discovery(self, force=False):
        for item in self._discovery_log:
            self._logger.debug("Discovery Log: {}".format(self._discovery_log))
            self._logger.debug("Checking discovery for: {}".format(item))
            # Run the discovery if we haven't before, or if force is requested.
            # TODO: Update Discovery processing.
            if not self._discovery_log[item] or force:
                if item == 'system':
                    self._logger.info("Sending Home Assistant discovery for '{}'.".format(item))
                    self._ha_discovery_system()
                elif item == 'sensors':
                    if self._chattiness['sensors_raw']:
                        # Only discover the raw sensors if we're going to be sending it.
                        self._logger.info("Sending Home Assistant discovery for '{}'.".format(item))
                        self._ha_discovery_sensors()
                else:
                    self._logger.info("Sending home assistant discovery for bay ID: {}".format(item))
                    self._ha_discovery_bay(item)
                self._discovery_log['system'] = True
        # Enable the repeat override. This ensures that messages are repeated for long enough after discovery so
        # they aren't missed.
        self._ha_info['override'] = True
        self._logger.info("HA discovery performed. Will send all topics for the next 15s.")
        self._ha_info['start'] = time.monotonic()

    # Create HA discovery message.
    def _ha_discover(self, name, topic, entity_type, entity, device_info=True, system_avail=True, avail=None,
                     avail_mode=None,
                     **kwargs):
        allowed_types = ('camera', 'binary_sensor', 'sensor', 'select')
        # Trap unknown types.
        if entity_type not in allowed_types:
            raise ValueError("Type must be one of {}".format(allowed_types))

        # Adjust the topic key based on the type, because the syntax varries.
        if entity_type == 'camera':
            topic_key = 'topic'
        elif entity_type == 'select':
            topic_key = 'command_topic'
        else:
            topic_key = 'state_topic'

        # Set up the initial discovery dictionary for all types.
        discovery_dict = {
            topic_key: topic,
            'type': entity_type,
            'name': name,
            'object_id': entity,
            'unique_id': self._client_id + '.' + entity,
            'availability': []
        }
        # Add device info if asked to.
        if device_info:
            discovery_dict['device'] = self._device_info

        # This is how we handle varying requirements for different types.
        # 'required' - must exist *and* be defined
        # 'nullable' - must exist, may be null
        # 'optional' - may be defined or undefined.
        if entity_type == 'camera':
            required_parameters = ['image_encoding']
            nullable_parameters = []
            optional_parameters = ['icon']
        elif entity_type == 'binary_sensor':
            required_parameters = ['payload_on', 'payload_off']
            nullable_parameters = ['device_class']
            optional_parameters = ['icon', 'value_template']
        elif entity_type == 'sensor':
            required_parameters = []
            nullable_parameters = ['device_class']
            optional_parameters = ['icon', 'unit_of_measurement', 'value_template']
        elif entity_type == 'select':
            required_parameters = ['options']
            nullable_parameters = []
            optional_parameters = []
        else:
            raise ValueError('Discovery is of unknown type {}'.format(entity_type))

        # Requirement parameters *must* be passed, raise an exception if they aren't set.
        for param in required_parameters:
            try:
                discovery_dict[param] = kwargs[param]
            except KeyError as e:
                raise e

        # Nullable parameters must exist when we send discovery, if not included set to None.
        for param in nullable_parameters:
            try:
                discovery_dict[param] = kwargs[param]
            except KeyError:
                discovery_dict[param] = None

        # Optional parameters don't need to be included at all.
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
                'payload_not_available': 'offline'}
            discovery_dict['availability'].append(sa)

        # Are other availability topics defined? If so, check and include.
        if avail is not None:
            # If other avai
            for item in avail:
                # Must be a dict.
                if not isinstance(item, dict):
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
        discovery_topic = "homeassistant/{}/CobraBay_{}/{}/config". \
            format(entity_type, self._client_id, discovery_dict['object_id'])
        self._logger.info("Publishing HA discovery to topic '{}'\n\t{}".format(discovery_topic, discovery_json))
        # All discovery messages should be retained.
        self._mqtt_client.publish(topic=discovery_topic, payload=discovery_json, retain=True)
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
            entity_type='binary_sensor',
            entity='{}_connectivity'.format(self._system_name.lower()),
            device_class='connectivity',
            payload_on='online',
            payload_off='offline',
        )
        # CPU Percentage
        self._ha_discover(
            name="{} CPU Use".format(self._system_name),
            topic="CobraBay/" + self._client_id + "/cpu_pct",
            entity_type='sensor',
            entity="{}_cpu_pct".format(self._system_name.lower()),
            unit_of_measurement="%",
            icon="mdi:chip"
        )
        # CPU Temperature
        self._ha_discover(
            name="{} CPU Temperature".format(self._system_name),
            topic="CobraBay/" + self._client_id + "/cpu_temp",
            entity_type='sensor',
            entity="{}_cpu_temp".format(self._system_name.lower()),
            unit_of_measurement=self._uom('temp'),
            icon="mdi:thermometer"
        )
        # Memory Info
        self._ha_discover(
            name="{} Memory Free".format(self._system_name),
            topic="CobraBay/" + self._client_id + "/mem_info",
            entity_type='sensor',
            entity="{}_mem_info".format(self._system_name.lower()),
            value_template='{{ value_json.mem_avail_pct }}',
            unit_of_measurement='%',
            icon="mdi:memory"
        )
        # Undervoltage
        self._ha_discover(
            name="{} Undervoltage".format(self._system_name),
            topic="CobraBay/" + self._client_id + "/undervoltage",
            entity_type='binary_sensor',
            entity="{}_undervoltage".format(self._system_name.lower()),
            payload_on="true",
            payload_off="false",
            icon="mdi:alert-octagram"
        )
        # Display
        self._ha_discover(
            name="{} Display".format(self._system_name),
            topic="CobraBay/" + self._client_id + "/display",
            entity_type='camera',
            entity="{}_display".format(self._system_name.lower()),
            image_encoding='b64',
            icon="mdi:image-area"
        )

        # System Commands
        # By this point, a syscmd trigger *should* exist. Not existing is...odd.
        try:
            syscmd_trigger = self._trigger_registry['syscmd']
        except KeyError:
            self._logger.error("No System Command trigger defined. Cannot perform discovery on it.")
        else:
            self._ha_discover(
                name="{} Command".format(self._system_name),
                topic=syscmd_trigger.topic,
                entity_type='select',
                entity='{}_cmd'.format(self._system_name.lower()),
                options=["-", "Rediscover", "Restart", "Rescan"]
            )

    def _ha_discovery_bay(self, bay_id):
        bay_obj = self._bay_registry[bay_id]
        topic_base = "CobraBay/" + self._client_id + "/" + bay_obj.id + "/"
        # Discover the Bay level status items.
        # Bay State
        self._ha_discover(
            name="{} State".format(bay_obj.name),
            topic=topic_base + "state",
            entity_type='sensor',
            entity="{}_{}_state".format(self._system_name.lower(), bay_obj.id),
            value_template="{{ value|capitalize }}"
        )

        # Bay Select, to allow setting state manually. Mostly useful for testing.
        try:
            baycmd_trigger = self._trigger_registry[bay_id]
        except KeyError:
            self._logger.error(
                "No Command Trigger defined for bay '{}'. Cannot perform discovery for it.".format(bay_id))
            self._logger.error("Available triggers: {}".format(self._trigger_registry.keys()))
        else:
            self._ha_discover(
                name="{} Command".format(bay_obj.name),
                topic=baycmd_trigger.topic,
                entity_type='select',
                entity="{}_{}_cmd".format(self._system_name.lower(), bay_obj.id),
                options=["-", "Dock", "Undock", "Verify", "Abort", "Save Position"]
            )
        # Bay Vector
        self._ha_discover(
            name="{} Speed".format(bay_obj.name),
            topic=topic_base + "vector",
            entity_type='sensor',
            entity="{}_{}_speed".format(self._system_name.lower(), bay_obj.id),
            value_template="{{ value_json.speed }}",
            device_type="speed",
            unit_of_measurement=self._uom('speed')
        )
        # Bay Direction
        self._ha_discover(
            name="{} Direction".format(bay_obj.name),
            topic=topic_base + "vector",
            entity_type='sensor',
            entity="{}_{}_direction".format(self._system_name.lower(), bay_obj.id),
            value_template="{{ value_json.direction|capitalize }}",
        )

        # Bay Motion Timer
        self._ha_discover(
            name="{} Motion Timer".format(bay_obj.name),
            topic=topic_base + "motion_timer",
            entity_type="sensor",
            entity="{}_{}_motion_timer".format(self._system_name.lower(), bay_obj.id),
            unit_of_measurement="s"
        )

        # Bay Occupancy
        self._ha_discover(
            name="{} Occupied".format(bay_obj.name),
            topic=topic_base + "occupancy",
            entity_type="binary_sensor",
            entity="{}_{}_occupied".format(self._system_name.lower(), bay_obj.id),
            payload_on="true",
            payload_off="false",
            payload_not_available="error"
        )

        # Bay sensors.
        # Do common long/lat items first.
        for sensor_id in bay_obj.configured_sensors['lat'] + bay_obj.configured_sensors['long']:
            sen_obj = self._sensormgr.get_sensor(sensor_id)
            if sen_obj == SENSTATE_FAULT:
                self._logger.info("Skipping sensor '{}', not initialized.".format(sensor_id))
                break
            sensor_base = topic_base + "sensors/" + sensor_id + "/"
            # Bay-adjusted range reading.
            # Reading direct from the sensor.
            self._ha_discover(
                name="{} Sensor - {} Reading".format(bay_obj.name, sen_obj.name),
                topic=sensor_base + "reading",
                entity_type="sensor",
                entity="{}_{}_{}_reading".format(self._system_name.lower(), bay_id, sensor_id),
                device_class="distance",
                unit_of_measurement=self._uom('length')
            )

            # Quality
            self._ha_discover(
                name="{} Sensor - {} Quality".format(bay_obj.name, sen_obj.name),
                topic=sensor_base + "quality",
                entity_type="sensor",
                entity="{}_{}_{}_quality".format(self._system_name.lower(), bay_id, sensor_id),
                value_template="{{ value|capitalize }}"
            )

        # Lateral only elements.
        for sensor_id in bay_obj.configured_sensors['lat']:
            sen_obj = self._sensormgr.get_sensor(sensor_id)
            if sen_obj == SENSTATE_FAULT:
                self._logger.info("Skipping sensor '{}', not initialized.".format(sensor_id))
                break
            sensor_base = topic_base + "sensors/" + sensor_id + "/"
            self._ha_discover(
                name="{} Sensor - {} Intercepted".format(bay_obj.name, sen_obj.name),
                topic=sensor_base + "intercepted",
                entity_type="binary_sensor",
                entity="{}_{}_{}_intercepted".format(self._system_name.lower(), bay_id, sensor_id),
                payload_on="true",
                payload_off="false"
            )

    def _ha_discovery_sensors(self):
        """
        Send Home Assistant messages for sensors.
        :return:
        """
        # Discover the sensors....
        topic_base = "CobraBay/" + self._client_id + '/'
        for sensor_id in self._cbcore.configured_sensors:
            sen_obj = self._sensormgr.get_sensor(sensor_id)
            if sen_obj == SENSTATE_FAULT:
                self._logger.info("Skipping sensor '{}', not initialized.".format(sensor_id))
                break
            sensor_base = topic_base + "sensors/" + sensor_id + "/"

            # Current state of the detector.
            self._ha_discover(
                name="Sensor - {} State".format(sen_obj.name),
                topic=sensor_base + "state",
                entity_type="sensor",
                entity="{}_{}_state".format(self._system_name.lower(), sensor_id),
                value_template="{{ value|capitalize }}"
            )
            self._ha_discover(
                name="Sensor - {} Status".format(sen_obj.name),
                topic=sensor_base + "status",
                entity_type="sensor",
                entity="{}_{}_status".format(self._system_name.lower(), sensor_id),
                value_template="{{ value|capitalize }}"
            )

            # Is the detector in fault?
            self._ha_discover(
                name="Sensor - {} Fault".format(sen_obj.name),
                topic=sensor_base + "fault",
                entity_type="binary_sensor",
                entity="{}_{}_fault".format(self._system_name.lower(), sensor_id),
                payload_on="true",
                payload_off="false"
            )

            # Reading direct from the sensor.
            self._ha_discover(
                name="Sensor - {} Direct Reading".format(sen_obj.name),
                topic=sensor_base + "reading",
                entity_type="sensor",
                entity="{}_{}_reading".format(self._system_name.lower(), sensor_id),
                device_class="distance",
                unit_of_measurement=self._uom('length')
            )
