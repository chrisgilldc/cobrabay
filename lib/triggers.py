####
# Cobra Bay - Trigger
####

from json import loads as json_loads


class Trigger:
    def __init__(self, config):
        # Save the config.
        self._settings = config
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
    # Note that Triggers don't have *names* since they aren't presented externally.
    @property
    def id(self):
        return self._settings['id']

    @property
    def type(self):
        return self._settings['type']

# Subclass for common MQTT elements
class MQTTTrigger(Trigger):
    def __init__(self, config):
        super().__init__(config)
        print("MQTT trigger received config: {}".format(config))

        # Save the config
        self._settings = config

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
    def topic(self):
        if self._settings['topic_mode'] == 'full':
            return self._settings['topic']
        else:
            return self._topic_prefix + "/" + self._settings['topic']


# Take System commands directly from an outside agent.
class SysCommand(MQTTTrigger):
    def __init__(self, config):
        super().__init__(config)

        # Core
        self._cmd_stack_core = []
        # Network
        self._cmd_stack_network = []

    def callback(self, client, userdata, message):
        # Decode the JSON.
        message = str(message.payload, 'utf-8').lower()

        # Commands need to get routed to the right module.
        # Core commands
        if message.lower() in ('reboot', 'rescan'):
            self._cmd_stack_core.append(message.lower())
        if message.lower() in ('rediscover'):
            self._cmd_stack_core.append(message.lower())
        else:
            print("Command {} not valid.".format(message))

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


# Take Bay commands directly from an outside agent.
class BayCommand(MQTTTrigger):
    def __init__(self, config, bay_obj):
        super().__init__(config)

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
            print("Command {} not valid.".format(message_text))

    @property
    def bay_id(self):
        return self._bay_obj.bay_id

    @property
    def topic(self):
        if self._settings['topic_mode'] == 'full':
            return self._settings['topic']
        else:
            return self._topic_prefix + "/" + self.bay_id + "/" + self._settings['topic']


# State-based MQTT triggers
class MQTTSensor(MQTTTrigger):
    def __init__(self, config, bay_obj):
        # Do the main class init first.
        super().__init__(config)
        # Initialize a previous value variable.
        self._previous_value = None

        # Store the bay object reference.
        self._bay_obj = bay_obj

    # Callback interface for Paho MQTT
    def callback(self, client, userdata, message):
        # Convert to a flat string
        message_text = str(message.payload, 'utf-8').lower()

        # Check the message text against our trigger value.
        # For 'to' type, previous value doesn't matter, just check it!
        if self._settings['change_type'] == 'to':
            if message_text == self._settings['trigger_value']:
                self._trigger_action()
        elif self._settings['change_type'] == 'from':
            if self._previous_value == self._settings['trigger_value'] & message_text != self._settings['trigger_value']:
                self._trigger_action()
            self._previous_value = message_text

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

    @property
    def bay_id(self):
        return self._bay_obj.bay_id

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
        return self._bay_obj.bay_id