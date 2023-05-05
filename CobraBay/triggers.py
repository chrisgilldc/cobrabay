####
# Cobra Bay - Trigger
####

from json import loads as json_loads
import logging

class Trigger:
    def __init__(self, id, name, log_level="WARNING", **kwargs):
        """
        :param id: str
        :param name: str
        :param log_level: Log level for the bay, must be a Logging level.
        :param kwargs:
        """
        self.id = id
        self.name = name
        # Create a logger.
        self._logger = logging.getLogger("CobraBay").getChild("Triggers").getChild(self.id)
        self._logger.setLevel(log_level)
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

    # Return the first command from the stack.
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

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, input):
        self._name = input

    # @property
    # def type(self):
    #     return self._settings['type']

# Subclass for common MQTT elements
class MQTTTrigger(Trigger):
    def __init__(self, id, name, topic, topic_mode="full", topic_prefix = None, log_level="WARNING"):
        """
        General class for MQTT-based triggers.

        :param id: ID of this trigger. Case-insensitive, no spaces.
        :type id: str
        :param name: Name of this trigger.
        :type name: str
        :param topic: Topic for the trigger. If topic_mode is 'full', this will be the complete topic used.
        :param topic_mode: Use topic as-is or construct from elements. May be 'full' or 'suffix'.
        :type topic_mode: str
        :param topic_prefix: If using suffix topic mode, the topic prefix to use.
        :type topic_prefix: str
        :param log_level: Logging level for the trigger. Defaults to 'Warning'.
        :type log_level: str
        """
        super().__init__(id, name, log_level)

        self._topic = topic
        self._topic_mode = topic_mode
        self._topic_prefix = topic_prefix

    # This will need to be attached to a subscription.
    def callback(self, client, userdata, message):
        raise NotImplemented("MQTT Trigger callback should be implemented by a subclass.")

    @property
    def topic_prefix(self):
        return self._topic_prefix

    @topic_prefix.setter
    def topic_prefix(self, prefix):
        self._topic_prefix = prefix

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
    def __init__(self, id, name, topic, topic_prefix=None, log_level="WARNING"):
        super().__init__(id, name, topic, topic_mode='suffix')

        # Outbound command queues. These are separate based on their destination.
        ## Core queue
        self._cmd_stack_core = []
        ## Network queue
        self._cmd_stack_network = []

    def callback(self, client, userdata, message):
        # Decode the JSON.
        message = str(message.payload, 'utf-8').lower()

        # Commands need to get routed to the right module.
        # Core commands
        if message.lower() in ('reboot', 'rescan'):
            self._cmd_stack_core.append(message.lower())
        elif message.lower() in ('rediscover'):
            self._cmd_stack_core.append(message.lower())
        else:
            self._logger.warning("Ignoring invalid command: {}".format(message.text))

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
    def __init__(self, id, name, topic, bay_obj, log_level="WARNING"):
        super().__init__(id, name, topic=bay_obj.id + "/" + topic, topic_mode="suffix", log_level=log_level)

        # Store the bay object reference.
        self._bay_obj = bay_obj

        # Outbound command stack, so multiple commands can be queued.
        self._cmd_stack = []

    def callback(self, client, userdata, message):
        # Do a string convert.
        message_text = str(message.payload, 'utf-8').lower()

        # Check the commands and filter based on bay state.
        # Dock, undock or verify, only if bay isn't already docking or undocking.
        if message_text in ('dock', 'undock', 'verify') and self._bay_obj.state not in ('Docking', 'Undocking'):
            self._cmd_stack.append(message_text)
        elif message_text in ('abort'):
            self._cmd_stack.append(message_text)
        else:
            self._logger.warning("Ignoring invalid command: {}".format(message.text))

    # Get the ID of the bay object to be returned. This is used by the core to find the bay object directly.
    @property
    def bay_id(self):
        return self._bay_obj.id
    #
    # @property
    # def topic(self):
    #     if self._settings['topic_mode'] == 'full':
    #         return self._settings['topic']
    #     else:
    #         return self._topic_prefix + "/" + self.bay_id + "/" + self._settings['topic']


# State-based MQTT triggers
class MQTTSensor(MQTTTrigger):
    def __init__(self, id, name, topic, bay_obj, change_type, trigger_value, when_triggered, topic_mode="full",
                 topic_prefix=None, log_level="WARNING"):
        """
        Trigger which will take action based on an MQTT value change. Defining an MQTT Sensor trigger subscribes the system
        to that topic. When the topic's payload changes to or from a defined state, the defined action will be executed.

        :param id: ID of this trigger. Case-insensitive, no spaces.
        :type id: str
        :param name: Name of this trigger.
        :type name: str
        :param topic: Topic for the trigger. If topic_mode is 'full', this will be the complete topic used.
        :param topic_mode: Use topic as-is or construct from elements. May be 'full' or 'suffix'.
        :type topic_mode: str
        :param topic_prefix: If using suffix topic mode, the topic prefix to use.
        :type topic_prefix: str
        :param bay_obj: The object of the bay this trigger is attached to.
        :param change_type: Type of payload change to monitor for. May be 'to' or 'from'.
        :type change_type: str
        :param trigger_value: Value which will activate this trigger. If change_type is 'to', trigger activates when the
        topic changes to this value. If change_type is 'from', trigger activates when the topic changes to any value
        other than this value. Only strings are supported currently, not more complex structures (ie: JSON)
        :type trigger_value: str
        :param when_triggered: Action taken when trigger is activated. May be 'dock', 'undock', or 'occupancy'. The
        'occupancy' setting will choose 'dock' or 'undock' contextually based on the current occupancy of the bay. If
        unoccupied, dock, if occupied dock. You're presumably not going to park again when there's already a car there!
        :type when_triggered: str
        :param log_level: Logging level for the trigger. Defaults to 'Warning'.
        :type log_level: str
        """
        super().__init__(id, name, topic, topic_mode, topic_prefix, log_level)

        # Save settings
        self._change_type = change_type
        self._trigger_value = trigger_value
        self._when_triggered = when_triggered
        self._bay_obj = bay_obj

        # Initialize a previous value variable.
        self._previous_value = None

    # Callback interface for Paho MQTT
    def callback(self, client, userdata, message):
        # Convert to a flat string
        message_text = str(message.payload, 'utf-8').lower()

        # Check the message text against our trigger value.
        # For 'to' type, previous value doesn't matter, just check it!
        if self._change_type == 'to':
            if message_text == self._trigger_value:
                self._trigger_action()
        elif self._change_type == 'from':
            if (
                    (self._previous_value is None and message_text != self._trigger_value)
                    or
                    (self._previous_value == self._trigger_value and message_text != self._trigger_value)
            ):
                self._trigger_action()
            # Always save the most-recently seen value as the 'previous value'
            self._previous_value = message_text

    def _trigger_action(self):
        # If action is supposed to be occupancy determined, check the bay.
        if self._when_triggered == 'occupancy':
            if self._bay_obj.occupied == 'Occupied':
                # If bay is occupied, vehicle must be leaving.
                self._cmd_stack.append('undock')
            elif self._bay_obj.occupied == 'Unoccupied':
                # Bay is unoccupied, so vehicle approaching.
                self._cmd_stack.append('dock')
        else:
            # otherwise drop the action through.
            self._cmd_stack.append(self._when_triggered)

    @property
    def bay_id(self):
        return self._bay_obj.id

class Range(Trigger):
    def __init__(self, config, bay_obj, detector_obj):
        super().__init__(config)

        # Store the bay object reference.
        self._bay_obj = bay_obj

        # Store the detector object reference.
        self._detector_obj = detector_obj

    def check(self):
        if self._detector_obj.motion:
            self._trigger_action()

    def _trigger_action(self):
        # If action is supposed to be occupancy determined, check the bay.
        if self._settings['when_triggered'] == 'occupancy':
            if self._bay_obj.occupied == 'Occupied':
                # If bay is occupied, vehicle must be leaving.
                self._cmd_stack.append('undock')
            elif self._bay_obj.occupied == 'Unoccupied':
                # Bay is unoccupied, so vehicle approaching.
                self._cmd_stack.append('dock')
        else:
            # otherwise drop the action through.
            self._cmd_stack.append(self._settings['when_triggered'])

    # Bay ID this trigger is linked to.
    @property
    def bay_id(self):
        return self._bay_obj.id