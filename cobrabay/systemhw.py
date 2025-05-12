"""
Cobrabay - System Hardware

Gets System Hardware Status
"""

from math import floor

import psutil
from gpiozero import CPUTemperature
from pint import UnitRegistry
from rpi_bad_power import new_under_voltage
import ha_mqtt_discoverable as hmd
import ha_mqtt_discoverable.sensors as hmds
from cobrabay import CBBase
import time

class CBPiStatus(CBBase):
    def __init__(self,
                 availability_topic, client_id, device_info, mqtt_settings, system_name, unit_system):
        """
        Initialize the pi hardware status object. This only takes the standard CBBase parameters to create MQTT objects.

        :param availability_topic: Settings for entity availability
        :type availability_topic: dict
        :param client_id: Value for the client ID. Usually the MAC address.
        :type client_id: str
        :param device_info: Device Information object.
        :type device_info: ha_mqtt_discoverable.DeviceInfo
        :param mqtt_settings: MQTT Settings object.
        :type mqtt_settings: ha_mqtt_discoverable.Settings
        :param system_name: Name of the system.
        :type system_name: str
        :param unit_system: Unit system to use. 'metric' or 'imperial'.
        :type unit_system: str
        """
        super().__init__(availability_topic, client_id, device_info, mqtt_settings, system_name, unit_system)

        self._timestamp = time.monotonic() - 1000

        self._ureg = UnitRegistry()
        self._ureg.define('percent = 1 / 100 = %')
        # self._Q = self._ureg.Quantity

    def update(self):
        """
        Send updates to MQTT.
        """
        if time.monotonic() - self._timestamp > 60:
            self._timestamp = time.monotonic()
            if self._cpu_info() != self._mqtt_previous_values['cpu_pct']:
                self._mqtt_previous_values['cpu_pct'] = self._cpu_info()
                self._mqtt_obj['cpu_pct'].set_state(self._mqtt_previous_values['cpu_pct'])

            if self._cpu_temp() != self._mqtt_previous_values['cpu_temp']:
                self._mqtt_previous_values['cpu_temp'] = self._cpu_temp()
                self._mqtt_obj['cpu_temp'].set_state("{:0.2f}".format(
                    float(self._mqtt_previous_values['cpu_temp'].magnitude)))

            if self._undervoltage() != self._mqtt_previous_values['undervoltage']:
                self._mqtt_previous_values['undervoltage'] = self._undervoltage()
                self._mqtt_obj['undervoltage'].update_state(self._mqtt_previous_values['undervoltage'])

    def status(self,metric):
        if metric == 'cpu_pct':
            # CPU UseGet the CPU use
            return self._cpu_info()
        elif metric == 'cpu_temp':
            return self._cpu_temp()
        elif metric == 'mem_info':
            return self._mem_info()
        elif metric == 'undervoltage':
            return self._undervoltage()
        else:
            raise ValueError('Not a valid metric')

    @staticmethod
    def _cpu_info():
        return psutil.cpu_percent()

    def _cpu_temp(self):
        temp = self._ureg.Quantity(CPUTemperature().temperature, self._ureg.degC)
        if self.unit_system == 'imperial':
            temp = temp.to('degF')
        # return self._Q(CPUTemperature().temperature, self._ureg.degC)
        return temp

    def _mem_info(self):
        memory = psutil.virtual_memory()
        return_dict = {
            'mem_avail': self._ureg.Quantity(floor(memory.available), self._ureg.byte),
            'mem_total': self._ureg.Quantity(memory.total, self._ureg.byte)
        }
        return_dict['mem_avail_pct'] = self._ureg.Quantity(1 - floor(return_dict['mem_avail']) / return_dict['mem_total'], self._ureg.percent)
        return_dict['mem_used_pct'] = self._ureg.Quantity(1 - floor(return_dict['mem_total'] - return_dict['mem_avail']) / return_dict['mem_total'],
                                              self._ureg.percent)
        return return_dict

    @staticmethod
    def _undervoltage():
        under_voltage = new_under_voltage()
        if under_voltage is None:
            return "unavailable"
        elif under_voltage.get():
            return "true"
        else:
            return "false"

    def _make_mqtt_objects(self):
        """ Make the MQTT Objects"""

        # If we don't have both MQTT settings
        if self._mqtt_settings is None or self._device_info is None:
            return False

        # Make the CPU Percentage.
        self._mqtt_obj['cpu_pct'] = hmds.Sensor(
            hmd.Settings(mqtt=self._mqtt_settings,
                         entity=hmds.SensorInfo(
                             unique_id=self.client_id + "_cpu_pct",
                             name="{} CPU Use Percentage".format(self.system_name),
                             unit_of_measurement="%",
                             icon="mdi:chip",
                             device=self.device_info
                         ),
                     )
        )
        self._mqtt_obj['cpu_pct'].availability_topic = self.availability_topic
        self._mqtt_previous_values['cpu_pct'] = None

        # Determine CPU Temp unit.
        if self.unit_system == 'imperial':
            temp_uom = "°F"
        else:
            temp_uom = "°C"

        self._mqtt_obj['cpu_temp'] = hmds.Sensor(
            hmd.Settings(mqtt=self.mqtt_settings,
                         entity=hmds.SensorInfo(
                             unique_id=self.client_id + "_cpu_temp",
                             name="{} CPU Temperature".format(self.system_name),
                             unit_of_measurement=temp_uom,
                             icon="mdi:thermometer",
                             device=self.device_info
                         ),
                     )
        )
        self._mqtt_obj['cpu_temp'].availability_topic = self.availability_topic
        self._mqtt_previous_values['cpu_temp'] = None

        self._mqtt_obj['mem_info'] = hmds.Sensor(
            hmd.Settings(mqtt=self.mqtt_settings,
                        entity=hmds.SensorInfo(
                            unique_id=self.client_id + "_mem_free",
                            name="{} Memory Free".format(self.system_name),
                            unit_of_measurement='%',
                            icon="mdi:memory",
                            device=self.device_info
                        )
                    )
        )
        self._mqtt_obj['mem_info'].availability_topic = self.availability_topic
        self._mqtt_previous_values['mem_info'] = None

        self._mqtt_obj['undervoltage'] = hmds.BinarySensor(
            hmd.Settings(mqtt=self.mqtt_settings,
                         entity=hmds.BinarySensorInfo(
                             unique_id=self.client_id + "_undervoltage",
                             name="{} Undervoltage".format(self.system_name),
                             payload_on="true",
                             payload_off="false",
                             icon="mdi:alert-octagram",
                             device=self.device_info
                         )
                     )
        )
        self._mqtt_obj['undervoltage'].availability_topic = self.availability_topic
        self._mqtt_previous_values['undervoltage'] = None

        return None