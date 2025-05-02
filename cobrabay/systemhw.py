####
# Cobra Bay - System Hardware
#
# Gets System Hardware Status
####

from math import floor

import psutil
from gpiozero import CPUTemperature
from pint import UnitRegistry
from rpi_bad_power import new_under_voltage
import ha_mqtt_discoverable as hmd
import ha_mqtt_discoverable.sensors as hmds
from cobrabay import CBBase

class CBPiStatus(CBBase):
    def __init__(self, mqtt_settings, device_info, client_id, system_name, unit_system):
        super().__init__(client_id, device_info, mqtt_settings, system_name, unit_system)
        print("PiStatus settings:")
        print("client_id: {}".format(self.client_id))
        print("device_info: {}".format(self.device_info))
        print("mqtt_settings: {}".format(self.mqtt_settings))
        print("system_name: {}".format(self.system_name))
        print("unit_system: {}".format(self.unit_system))

        self._ureg = UnitRegistry()
        self._ureg.define('percent = 1 / 100 = %')
        self._Q = self._ureg.Quantity

    def poll(self):
        if self._cpu_info() != self._mqtt_previous_values['cpu_pct']:
            self._mqtt_previous_values['cpu_pct'] = self._cpu_info()
            self._mqtt_obj['cpu_pct'].set_state(self._mqtt_previous_values['cpu_pct'])

        if self._cpu_temp() != self._mqtt_previous_values['cpu_temp']:
            self._mqtt_previous_values['cpu_temp'] = self._cpu_temp()
            self._mqtt_obj['cpu_temp'].set_state(self._mqtt_previous_values['cpu_temp']) #TODO: Unit conversion for output.

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

    def _cpu_info(self):
        return psutil.cpu_percent()

    def _cpu_temp(self):
        return self._Q(CPUTemperature().temperature, self._ureg.degC)

    def _mem_info(self):
        memory = psutil.virtual_memory()
        return_dict = {
            'mem_avail': self._Q(floor(memory.available), self._ureg.byte),
            'mem_total': self._Q(memory.total, self._ureg.byte)
        }
        return_dict['mem_avail_pct'] = self._Q(1 - floor(return_dict['mem_avail']) / return_dict['mem_total'], self._ureg.percent)
        return_dict['mem_used_pct'] = self._Q(1 - floor(return_dict['mem_total'] - return_dict['mem_avail']) / return_dict['mem_total'],
                                              self._ureg.percent)
        return return_dict

    def _undervoltage(self):
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
                             unique_id=self.client_id + "cpu_pct",
                             name="{} CPU Use Percentage".format(self.system_name),
                             unit_of_measurement="%",
                             icon="mdi:chip",
                             device=self.device_info
                         ),
                     ),
        )
        self._mqtt_previous_values['cpu_pct'] = None

        self._mqtt_obj['cpu_temp'] = hmds.Sensor(
            hmd.Settings(mqtt=self.mqtt_settings,
                         entity=hmds.SensorInfo(
                             unique_id=self.client_id + "cpu_temp",
                             name="{} CPU Temperature".format(self.system_name),
                             unit_of_measurement="%",
                             icon="mdi:thermometer",
                             device=self.device_info
                         ),
                     ),
        )
        self._mqtt_previous_values['cpu_temp'] = None

        self._mqtt_obj['mem_info'] = hmds.Sensor(
            hmd.Settings(mqtt=self.mqtt_settings,
                        entity=hmds.SensorInfo(
                            unique_id=self.client_id + "mem_free",
                            name="{} Memory Free".format(self.system_name),
                            unit_of_measurement='%',
                            icon="mdi:memory",
                            device=self.device_info
                        )
                    )
        )
        self._mqtt_previous_values['mem_info'] = None

        #     # Memory Info
        #     self._ha_discover(
        #         name="{} Memory Free".format(self._system_name),
        #         topic=f"{self._mqtt_base}/{self._client_id}/system/mem_info",
        #         entity_type='sensor',
        #         entity="{}_mem_info".format(self._system_name.lower()),
        #         value_template='{{ value_json.mem_avail_pct }}',
        #         unit_of_measurement='%',
        #         icon="mdi:memory"
        #     )

        self._mqtt_obj['undervoltage'] = hmds.BinarySensor(
            hmd.Settings(mqtt=self.mqtt_settings,
                         entity=hmds.BinarySensorInfo(
                             unique_id=self.client_id + "undervoltage",
                             name="{} Undervoltage".format(self.system_name),
                             payload_on="true",
                             payload_off="false",
                             icon="mdi:alert-octogram",
                             device=self.device_info
                         )
                     )
        )
        self._mqtt_previous_values['undervoltage'] = None

        return None