####
# Cobra Bay - System Hardware
#
# Gets System Hardware Status
####
from typing import Dict, Union, Any

import psutil
from gpiozero import CPUTemperature
from pint import UnitRegistry



class PiStatus:
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
        else:
            raise ValueError('Not a valid metric')

    def _cpu_info(self):
        return psutil.cpu_percent()

    def _cpu_temp(self):
        return self._Q(CPUTemperature().temperature, self._ureg.degC)

    def _mem_info(self):
        memory = psutil.virtual_memory()
        return_dict = {
            'mem_avail': self._Q(memory.available, self._ureg.byte),
            'mem_total': self._Q(memory.total, self._ureg.byte)
        }
        return_dict['mem_pct'] = self._Q(return_dict['mem_avail'] / return_dict['mem_total'], self._ureg.percent)
        return return_dict