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

class CBPiStatus:
    def __init__(self):
        self._ureg = UnitRegistry()
        self._ureg.define('percent = 1 / 100 = %')
        self._Q = self._ureg.Quantity

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
        return_dict['mem_pct'] = self._Q(1 - floor(return_dict['mem_avail']) / return_dict['mem_total'], self._ureg.percent)
        return return_dict

    def _undervoltage(self):
        under_voltage = new_under_voltage()
        if under_voltage is None:
            return "unavailable"
        elif under_voltage.get():
            return "true"
        else:
            return "false"

