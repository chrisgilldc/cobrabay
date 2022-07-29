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

    def status(self):
        return_dict = {}
        # Get the CPU use
        return_dict['cpu_pct'] = self._cpu_info()
        # Get the cpu temp
        return_dict['cpu_temp'] = self._cpu_temp()
        # Get the memory
        return_dict = return_dict | self._mem_info()

        return return_dict

    def _cpu_info(self):
        cpu_pct = self._Q(psutil.cpu_percent(), self._ureg.percent)
        return cpu_pct

    def _cpu_temp(self):
        return self._Q(CPUTemperature(), self._ureg.degC)

    def _mem_info(self):
        memory = psutil.virtual_memory()
        return_dict = {
            'mem_avail': self._Q(memory.available, self._ureg.byte),
            'mem_total': self._Q(memory.total, self._ureg.byte)
        }
        return_dict['mem_pct'] = self._Q(return_dict['mem_avail'] / return_dict['mem_total'], self._ureg.percent)
        return return_dict