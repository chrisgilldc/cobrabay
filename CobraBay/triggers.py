####
# Cobra Bay - Trigger
####

from json import loads as json_loads
import logging

class Trigger:
    def __init__(self, id, log_level="DEBUG", **kwargs):
        """
        :param id: str
        :param log_level: Log level for the bay, must be a Logging level.
        :param kwargs:
        """
        self.id = id
        # Create a logger.
        self._logger = logging.getLogger("CobraBay").getChild("Trigger").getChild(self.id)
        self._logger.setLevel(log_level.upper())
        self._logger.info("Initializing trigger: {}".format(self.id))

        # Initialize command stack.
        self._cmd_stack = []

    # Flag to enable quick boolean checks if there are waiting commands.
    @property
    def triggered(self):
        if len(self._cmd_stack) > 0:
            return True
        else:
            return False

    @property
    def cmd_stack(self):
        return self._cmd_stack

    # Store a trigger ID internally for reference.
    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, input):
        self._id = input.replace(" ","_").lower()

    # @property
    # def type(self):
    #     return self._settings['type']

# Subclass for common MQTT elements
class MQTTTrigger(Trigger):
    def __init__(self, id, topic, topic_mode="full", topic_prefix = None, log_level="DEBUG"):
        """
        General class for MQTT-based triggers.

        :param id: ID of this trigger. Case-insensitive, no spaces.
        :type id: str
        :param topic: Topic for the trigger. If topic_mode is 'full', this will be the complete topic used.
        :param topic_mode: Use topic as-is or construct from elements. May be 'full' or 'suffix'.
        :type topic_mode: str
        :param topic_prefix: If using suffix topic mode, the topic prefix to use.
        :type topic_prefix: str
        :param log_level: Logging level for the trigger. Defaults to 'Warning'.
        :type log_level: str
        """
        super().__init__(id, log_level.upper())

        self._topic = topic
        self._topic_mode = topic_mode
        self._topic_prefix = topic_prefix
        try:
            self._logger.info("Trigger '{}' listening to MQTT topic '{}'".format(self.id, self.topic))
        except TypeError:
            self._logger.info("Trigger '{}' initialized, MQTT prefix not yet set".format(self.id))

    # This will need to be attached to a subscription.
    def callback(self, client, userdata, message):
        raise NotImplemented("MQTT Trigger callback should be implemented by a subclass.")

    @property
    def topic_prefix(self):
        return self._topic_prefix

    @topic_prefix.setter
    def topic_prefix(self, prefix):
        self._topic_prefix = prefix
        self._logger.info("Trigger '{}' prefix updated, MQTT topic is now '{}'".format(self.id, self.topic))

    @property
    def topic_mode(self):
        return self._topic_mode

    @topic_mode.setter
    def topic_mode(self, mode):
        if mode.lower() not in ('full','suffix'):
            raise ValueError("Topic mode must be 'full' or 'assemble'")
        else:
            self._topic_mode = mode.lower()

    @property
    def topic(self):
        if self.topic_mode == 'full':
            return self._topic
        else:
            return self.topic_prefix + "/" + self._topic

# Take System commands directly from an outside agent.
class SysCommand(MQTTTrigger):
    def __init__(self, id, topic, topic_prefix=None, log_level="WARNING"):
        super().__init__(id, topic, topic_mode='suffix', topic_prefix = topic_prefix, log_level = log_level)

        # Outbound command queues. These are separate based on their destination.
        ## Core queue
        self._cmd_stack_core = []
        ## Network queue
        self._cmd_stack_network = []

    def callback(self, client, userdata, message):
        # Decode the JSON.
        message_text = str(message.payload, 'utf-8').lower()
        self._logger.debug("Received message: '{}'".format(message_text))

        # Commands need to get routed to the right module.
        # Core commands
        if message_text in ('restart', 'rescan', 'save_config'):
            self._logger.info("Received command {}. Adding to core command stack.".format(message_text))
            self._cmd_stack_core.append(message_text)
        elif message_text in ('rediscover'):
            self._logger.info("Received command {}. Not yet implemented.".format(message_text))
            # Do a call to Network HA here...
        else:
            self._logger.warning("Ignoring invalid command: {}".format(message_text))

    # Return the first command from the stack.
    @property
    def next_command(self):
        return self._cmd_stack_core.pop(0)

    @property
    def next_command_network(self):
        return self._cmd_stack_network.pop(0)

    @property
    def triggered(self):
        if len(self._cmd_stack_core) > 0:
            return True
        else:
            return False

    @property
    def triggered_network(self):
        if len(self._cmd_stack_network) > 0:
            return True
        else:
            return False


# Take and handle bay commands.
class BayCommand(MQTTTrigger):
    def __init__(self, id, topic, bay_obj, log_level="WARNING"):
        super().__init__(id, topic=bay_obj.id + "/" + topic, topic_mode="suffix", log_level=log_level)

        # Store the bay object reference.
        self._bay_obj = bay_obj

        # Outbound command stack, so multiple commands can be queued.
        self._cmd_stack = []

    def callback(self, client, userdata, message):
        # Do a string convert.
        message_text = str(message.payload, 'utf-8').lower()
        self._logger.debug("Received message: '{}'".format(message_text))

        # Check the commands and filter based on bay state.
        # Dock, undock or verify, only if bay isn't already docking or undocking.
        if message_text in ('dock', 'undock', 'verify') and self._bay_obj.state not in ('Docking', 'Undocking'):
            self._cmd_stack.append(message_text)
        elif message_text in ('abort'):
            self._cmd_stack.append(message_text)
        else:
            self._logger.warning("Ignoring invalid command: {}".format(message_text))

    # Get the ID of the bay object to be returned. This is used by the core to find the bay object directly.
    @property
    def bay_id(self):
        return self._bay_obj.id


# State-based MQTT triggers
class MQTTSensor(MQTTTrigger):
    def __init__(self, id, topic, bay_obj,
                 to_value=None,
                 from_value=None,
                 action=None,
                 topic_mode="full",
                 topic_prefix=None, log_level="WARNING"):
        """
        Trigger which will take action based on an MQTT value change. Defining an MQTT Sensor trigger subscribes the system
        to that topic. When the topic's payload changes to or from a defined state, the defined action will be executed.

        :rtype: object
        :param id: ID of this trigger. Case-insensitive, no spaces.
        :type id: str
        :param topic: Topic for the trigger. If topic_mode is 'full', this will be the complete topic used.
        :param topic_mode: Use topic as-is or construct from elements. May be 'full' or 'suffix'.
        :type topic_mode: str
        :param topic_prefix: If using suffix topic mode, the topic prefix to use.
        :type topic_prefix: str
        :param bay_obj: The object of the bay this trigger is attached to.
        :param action: Action taken when trigger is activated. May be 'dock', 'undock', or 'occupancy'. The
        'occupancy' setting will choose 'dock' or 'undock' contextually based on the current occupancy of the bay. If
        unoccupied, dock, if occupied dock. You're presumably not going to park again when there's already a car there!
        :type action: str
        :param log_level: Logging level for the trigger. Defaults to 'Warning'.
        :type log_level: str
        """
        super().__init__(id, topic, topic_mode, topic_prefix, log_level)

        # Save settings
        if to_value is not None and from_value is not None:
            raise ValueError("Cannot have both a 'to' and 'from' value set.")

        # This is arguably a hack from the old method and should be replaced eventually.
        if to_value is not None:
            self._change_type = 'to'
            self._trigger_value = to_value
        elif from_value is not None:
            self._change_type = 'from'
            self._trigger_value = from_value

        self._action = action
        self._bay_obj = bay_obj

        # Initialize a previous value variable.
        self._previous_value = None

    # Callback interface for Paho MQTT
    def callback(self, client, userdata, message):
        # Convert to a flat string
        message_text = str(message.payload, 'utf-8').lower()
        self._logger.debug("Received message: '{}'".format(message_text))

        # Check the message text against our trigger value.
        # For 'to' type, previous value doesn't matter, just check it!
        if self._change_type == 'to':
            if message_text == self._trigger_value:
                self._logger.debug("Triggering action.")
                self._trigger_action()
        elif self._change_type == 'from':
            if (
                    (self._previous_value is None and message_text != self._trigger_value)
                    or
                    (self._previous_value == self._trigger_value and message_text != self._trigger_value)
            ):
                self._logger.debug("Triggering action.")
                self._trigger_action()
            # Always save the most-recently seen value as the 'previous value'
            self._previous_value = message_text

    def _trigger_action(self):
        # If action is supposed to be occupancy determined, check the bay.
        if self._action == 'occupancy':
            try:
                if self._bay_obj.occupied:
                    # If bay is occupied, vehicle must be leaving.
                    self._logger.debug("Appending 'undock' command.")
                    self._cmd_stack.append('undock')
                else:
                    # Bay is unoccupied, so vehicle approaching.
                    self._logger.debug("Appending 'dock' command.")
                    self._cmd_stack.append('dock')
            except TypeError:
                self._logger.warning("Bay has occupancy state '{}', cannot set command.".format(self._bay_obj.occupied))
        else:
            # otherwise drop the action through.
            self._logger.debug("Appending '{}' command.".format(self._action))
            self._cmd_stack.append(self._action)

    @property
    def bay_id(self):
        return self._bay_obj.id

# Old Range Trigger class. May rework someday.
# class Range(Trigger):
#     def __init__(self, config, bay_obj, detector_obj):
#         super().__init__(config)
#
#         # Store the bay object reference.
#         self._bay_obj = bay_obj
#
#         # Store the detector object reference.
#         self._detector_obj = detector_obj
#
#     def check(self):
#         if self._detector_obj.motion:
#             self._trigger_action()
#
#     def _trigger_action(self):
#         # If action is supposed to be occupancy determined, check the bay.
#         if self._settings['when_triggered'] == 'occupancy':
#             if self._bay_obj.occupied == 'Occupied':
#                 # If bay is occupied, vehicle must be leaving.
#                 self._cmd_stack.append('undock')
#             elif self._bay_obj.occupied == 'Unoccupied':
#                 # Bay is unoccupied, so vehicle approaching.
#                 self._cmd_stack.append('dock')
#         else:
#             # otherwise drop the action through.
#             self._cmd_stack.append(self._settings['when_triggered'])
#
#     # Bay ID this trigger is linked to.
#     @property
#     def bay_id(self):
#         return self._bay_obj.id