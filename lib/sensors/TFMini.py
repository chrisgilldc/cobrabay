#####
# Cobra Bay Sensor - TFMini
# This uses Wolfgang Schmied's TFMini-I2C library to standardize the interface.
#####

from . import BaseSensor
from .TFmini_I2C import TFminiI2C
from pint import Quantity

class TFMini(BaseSensor):
    def __init__(self, board_options):
        super().__init__(board_options)
        self._performance = {
            'max_range': Quantity('12m'),
            'min_range': Quantity('0.3m')
        }

    def _setup_sensor(self, board_options):
        self.max_range = Quantity('12m')
        options = ['i2c_bus','i2c_address']
        for item in options:
            if item not in board_options:
                raise ValueError("Required board_option '{}' missing.".format(item))

