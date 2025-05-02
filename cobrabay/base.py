"""
Cobrabay Base Object

This object is inherited by any object that needs to communicate with the network.
"""

class CBBase():
    def __init__(self, client_id, device_info, mqtt_settings, system_name, unit_system):
        """
        Initialize and create the objects.
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
        self.client_id = client_id
        self.device_info = device_info
        self.mqtt_settings = mqtt_settings
        self.system_name = system_name
        self.unit_system = unit_system

        # Make the objects.
        self._make_mqtt_objects()

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

    def _make_mqtt_objects(self):
        raise NotImplemented("MQTT Object Creation should be implemented by the subclass.")