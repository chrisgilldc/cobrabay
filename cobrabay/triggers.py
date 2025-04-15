"""
Cobra Bay Triggers
"""

# from json import loads as json_loads
import logging

class Trigger:
    """
    Base CobraBay Trigger Class
    """
    def __init__(self, trigger_id, log_level="DEBUG", **kwargs):
        """
        :param trigger_id: ID for this trigger
        :type trigger_id: str
        :param log_level: Log level for the bay, must be a Logging level.
        :param kwargs:
        """
        self.id = trigger_id
        # Create a logger.
        self._logger = logging.getLogger("cobrabay").getChild("Trigger").getChild(self.id)
        self._logger.setLevel(log_level.upper())
        self._logger.info("Initializing trigger: {}".format(self.id))

        # Initialize command stack.
        self._cmd_stack = []

    @property
    def triggered(self):
        """
        Used to see if there are waiting commands.
        """
        if len(self._cmd_stack) > 0:
            return True
        else:
            return False

    @property
    def cmd_stack(self):
        """
        The stack of waiting commands.
        """
        return self._cmd_stack

    @property
    def id(self):
        """
        The trigger ID.
        """
        return self._id

    @id.setter
    def id(self, the_input):
        """
        Setter for the trigger ID.
        """
        self._id = the_input.replace(" ","_").lower()

    # @property
    # def type(self):
    #     return self._settings['type']

# Subclass for common MQTT elements
class MQTTTrigger(Trigger):
    """
    MQTT-based Triggers
    """
    def __init__(self, trigger_id, topic, topic_mode="full", topic_prefix = None, log_level="DEBUG"):
        """
        General class for MQTT-based triggers.

        :param trigger_id: ID of this trigger. Case-insensitive, no spaces.
        :type trigger_id: str
        :param topic: Topic for the trigger. If topic_mode is 'full', this will be the complete topic used.
        :param topic_mode: Use topic as-is or construct from elements. May be 'full' or 'suffix'.
        :type topic_mode: str
        :param topic_prefix: If using suffix topic mode, the topic prefix to use.
        :type topic_prefix: str|None
        :param log_level: Logging level for the trigger. Defaults to 'Warning'.
        :type log_level: str
        """
        super().__init__(trigger_id, log_level.upper())

        self._outbound_messages = []
        self._topic = topic
        self._topic_mode = topic_mode
        self._topic_prefix = topic_prefix
        try:
            self._logger.info("Trigger '{}' listening to MQTT topic '{}'".format(self.id, self.topic))
        except TypeError:
            self._logger.info("Trigger '{}' initialized, MQTT prefix not yet set".format(self.id))

    # This will need to be attached to a subscription.
    def callback(self, client, userdata, message):
        """
        Callback the network module will call when a message is received.
        """
        raise NotImplemented("MQTT Trigger callback should be implemented by a subclass.")

    @property
    def topic_prefix(self):
        """
        Topic prefix to use. Defaults to 'cobrabay/'
        """
        return self._topic_prefix

    @topic_prefix.setter
    def topic_prefix(self, prefix):
        self._topic_prefix = prefix
        self._logger.info("Trigger '{}' prefix updated, MQTT topic is now '{}'".format(self.id, self.topic))

    @property
    def outbound_messages(self):
        """
        Messages to send out. Should always be empty because this is a trigger.
        """
        return self._outbound_messages

    @property
    def topic_mode(self):
        """
        Topic mode we are in.
        """
        return self._topic_mode

    @topic_mode.setter
    def topic_mode(self, mode):
        """
        Set the topic mode. May be 'full' or 'suffix'.
        """
        if mode.lower() not in ('full','suffix'):
            raise ValueError("Topic mode must be 'full' or 'assemble'")
        else:
            self._topic_mode = mode.lower()

    @property
    def topic(self):
        """
        The topic this trigger subscribes to. Will assemble appropriately depending on topic_mode setting.
        """
        if self.topic_mode == 'full':
            return self._topic
        else:
            return self.topic_prefix + "/" + self._topic

class SysCommand(MQTTTrigger):
    """
    System Command Trigger
    Used alert the overall system it needs to do something.
    See documentation for details on options.
    """
    def __init__(self, trigger_id, topic, topic_prefix=None, log_level="WARNING"):
        super().__init__(trigger_id, topic, topic_mode='suffix', topic_prefix = topic_prefix, log_level = log_level)

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
        elif message_text in 'rediscover':
            self._logger.info("Received command {}. Not yet implemented.".format(message_text))
            # Do a call to Network HA here...
        else:
            self._logger.warning("Ignoring invalid command: {}".format(message_text))

    # Return the first command from the stack.
    @property
    def next_command(self):
        """
        Fetch the next system commands.
        """
        return self._cmd_stack_core.pop(0)

    @property
    def next_command_network(self):
        """
        Fetch the next network command.
        """
        return self._cmd_stack_network.pop(0)

    @property
    def triggered(self):
        if len(self._cmd_stack_core) > 0:
            return True
        else:
            return False

    @property
    def triggered_network(self):
        """
        Are there waiting network commands?
        """
        if len(self._cmd_stack_network) > 0:
            return True
        else:
            return False


# Take and handle bay commands.
class BayCommand(MQTTTrigger):
    """
    Bay Command Trigger. Used to take in a command for a particular bay.
    """
    def __init__(self, trigger_id, topic, bay_obj, log_level="WARNING"):
        super().__init__(trigger_id, topic=bay_obj.id + "/" + topic, topic_mode="suffix", log_level=log_level)

        # Store the bay object reference.
        self._bay_obj = bay_obj

        # Outbound command stack, so multiple commands can be queued.
        self._cmd_stack = []

    def callback(self, client, userdata, message):
        # Do a string convert.
        message_text = str(message.payload, 'utf-8').lower()
        self._logger.debug("Received message: '{}'".format(message_text))

        # Check the commands and filter based on bay state.
        # Dock, undock or verify, only if bay isn't already in an active state
        if message_text in ('dock', 'undock', 'verify', 'save position') and not self._bay_obj.active:
            self._cmd_stack.append(message_text)
        # Abort the action, only if it's active.
        elif message_text in 'abort' and self._bay_obj.active:
            self._cmd_stack.append(message_text)
        else:
            self._logger.warning("Ignoring invalid command: {}".format(message_text))

    @property
    def bay_id(self):
        """
        ID of the bay object to be returned.
        This is used by the core to find the object in core._bays.
        """
        return self._bay_obj.id


# State-based MQTT triggers
class MQTTSensor(MQTTTrigger):
    """
    MQTT Sensor trigger. Used to track the state of an MQTT topic and trigger based on value changes.
    """
    def __init__(self, trigger_id, topic, bay_obj,
                 payload_to_value=None,
                 payload_from_value=None,
                 action=None,
                 topic_mode="full",
                 topic_prefix=None, log_level="WARNING"):
        """
        Trigger which will take action based on an MQTT value change. Defining an MQTT Sensor trigger subscribes the system
        to that topic. When the topic's payload changes to or from a defined state, the defined action will be executed.

        :rtype: object
        :param trigger_id: ID of this trigger. Case-insensitive, no spaces.
        :type trigger_id: str
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
        super().__init__(trigger_id, topic, topic_mode, topic_prefix, log_level)

        # Save settings
        if payload_to_value is not None and payload_from_value is not None:
            raise ValueError("Cannot have both a 'to' and 'from' value set.")

        # This is arguably a hack from the old method and should be replaced eventually.
        if payload_to_value is not None:
            self._change_type = 'to'
            self._trigger_value = payload_to_value
        elif payload_from_value is not None:
            self._change_type = 'from'
            self._trigger_value = payload_from_value

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
            self._logger.debug("Trigger action is occupancy-based. Attached bay occupancy state: {}".
                               format(self._bay_obj.occupied))
            if self._bay_obj.occupied == 'true':
                # If bay is occupied, vehicle must be leaving.
                self._logger.debug("Appending 'undock' command.")
                self._cmd_stack.append('undock')
            elif self._bay_obj.occupied == 'false':
                # Bay is unoccupied, so vehicle approaching.
                self._logger.debug("Appending 'dock' command.")
                self._cmd_stack.append('dock')
            else:
                self._logger.warning("Bay had occupancy state '{}'. Cannot determine action.".
                                     format(self._bay_obj.occupied))
        else:
            # otherwise drop the action through.
            self._logger.debug("Appending '{}' command.".format(self._action))
            self._cmd_stack.append(self._action)

    @property
    def bay_id(self):
        """
        ID of the bay this trigger is linked to
        """
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