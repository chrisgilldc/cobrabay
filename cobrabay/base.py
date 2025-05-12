"""
Cobrabay Base Object

This object is inherited by any object that needs to communicate with the network.
"""
from zoneinfo import available_timezones


class CBBase:
    """
    Base class for Cobrabay objects that need MQTT capability.
    """
    def __init__(self, availability_topic, client_id, device_info, mqtt_settings, system_name, unit_system):
        """
        Initialize the object.

        :param availability_topic: Settings for entity availability
        :type availability_topic: dict
        :param client_id: Value for the client ID. Usually the MAC address.
        :type client_id: str
        :param device_info: Device Information object.
        :type device_info: ha_mqtt_discoverable.DeviceInfo
        :param mqtt_settings: MQTT Settings object.
        :type mqtt_settings: ha_mqtt_discoverable.Settings.MQTT
        :param system_name: Name of the system.
        :type system_name: str
        :param unit_system: Unit system to use. 'metric' or 'imperial'.
        :type unit_system: str
        """
        # Initialize the variables to hold basic MQTT settings.
        self._mqtt_obj = {}
        self._mqtt_previous_values = {}
        self._client_id = None
        self._device_info = None
        self._mqtt_settings = None
        self._system_name = None
        # Assign the MQTT Settings. This will trigger MQTT object creation.
        # Assign the settings.
        self.availability_topic = availability_topic
        self.client_id = client_id
        self.device_info = device_info
        self.mqtt_settings = mqtt_settings
        self.system_name = system_name
        self.unit_system = unit_system

        # Make the objects.
        self._make_mqtt_objects()

    @property
    def availability_topic(self):
        """
        Entity availability settings
        """
        return self._availability_topic

    @availability_topic.setter
    def availability_topic(self, new_availability_topic):
        """
        Set the availabilty_topic as obtained from the network object.
        """
        self._availability_topic = new_availability_topic

    @property
    def client_id(self):
        """
        System Client ID as obtained from the network object.
        """
        return self._client_id

    @client_id.setter
    def client_id(self, new_client_id):
        """
        Set the system client id as obtained from the network object.
        """
        self._client_id = new_client_id

    @property
    def device_info(self):
        """
        MQTT device info object as obtained from the network object.
        """
        return self._device_info

    @device_info.setter
    def device_info(self, new_device_info):
        """
        Set the MQTT device info as obtained from the network object.
        """
        self._device_info = new_device_info

    @property
    def mqtt_settings(self):
        """
        MQTT settings object as obtained from the network object.
        """
        return self._mqtt_settings

    @mqtt_settings.setter
    def mqtt_settings(self, new_settings):
        """
        Set the MQTT settings object as obtained from the network object.
        Setting this triggers a recreation of all the MQTT objects.
        """
        self._mqtt_settings = new_settings

    @property
    def system_name(self):
        """
        System Name, as obtained from the configuration.
        """
        return self._system_name

    @system_name.setter
    def system_name(self, new_system_name):
        """
        Set the system name, as obtained from the configuration.
        """
        self._system_name = new_system_name

    @property
    def unit_system(self):
        """
        The current unit system of the display.
        :return:
        """
        return self._unit_system

    @unit_system.setter
    def unit_system(self, the_input):
        """
        Set the unit system

        :param the_input:
        :return:
        """
        if the_input.lower() not in ('imperial', 'metric'):
            raise ValueError("Unit system must be one of 'imperial' or 'metric'. Instead got '{}' ({})".
                             format(the_input, type(the_input)))
        self._unit_system = the_input.lower()

    def _make_mqtt_objects(self):
        raise NotImplemented("MQTT Object Creation should be implemented by the subclass.")