####
# Cobrabay Units Processor
####

# Helper class for unit conversion

from math import floor
import adafruit_logging as logging

CONVERSION_TABLE = {
    'cm': {
        'mm': 10,
        'cm': 1,
        'in': 0.393701
    },
    'in': {
        'mm': 25.4,
        'cm': 2.54,
        'in': 1
    },
    'ft': {},
    'mm': {
        'cm': 0.1,
        'in': 0.0393701,
        'mm': 1
    }
}

class UnitsConverter:
    def __init__(self,mode):
        self._logger = logging.getLogger('cobrabay')
        if mode not in ("metric","imperial"):
            self._logger.error("Requested unit mode '{}' is not supported!")
            sys.exit(1)
        # Save the mode
        self._mode = mode

    # General-purpose converter.


    # Standardize a sensor to the system's mode.
    # By default sensors are measured in centimeters.
    def sensor(self, value):
        if self._mode == 'imperial':
            output_unit = 'in'
        else:
            output_unit = 'cm'
        return self.convert(value, unit, output_unit)

    # These are ranges, convert them to centimeters.
    def normalize(self, value, unit = None):
        if unit is None:
            unit = self.mode_unit()
        return self.convert(value, unit, "cm")

    @property
    def mode(self):
        return self._mode

    @mode.setter
    def mode(self, new_mode):
        if new_mode.lower() in ('metric','imperial'):
            self._mode = new_mode.lower()
        else:
            raise ValueError("Mode must be 'metric' or 'imperial'")

    def mode_unit(self):
        if self._mode == 'imperial':
            return 'in'
        else:
            return 'cm'

class Unit:
    def __init__(self, value: , unit: str) -> object:
        self._value = value
        self._unit = unit

    @property
    def unit(self):
        return self._unit

    @property
    def value(self):
        return self._value

    @unit.setter
    def unit(self,unit):
        if unit not in CONVERSION_TABLE:
            raise ValueError("Unit {} is not supported.".format(unit))
        self._unit = unit

    @value.setter
    def value(self,value):
        if not isinstance(value, (int,float)):
            raise ValueError("Unit value must be int or float, {} input".format(type(value)))
        self._value = value

    def convert(self,output_unit):
        if output_unit in CONVERSION_TABLE[self._unit]:
            return Unit(self.value * CONVERSION_TABLE[self.unit][output_unit], output_unit)
        else:
            raise ValueError("Cannot make a conversion from {} to {}. (Be serious!)".format(self._unit,output_unit))

    def _ft_in(self):
        # Special handling to make a foot-inches dict. First convert to inches.
        (val_inches, unit) = self.convert('in')
        val_feet = floor(val_inches / 12)
        val_inches = val_inches % 12
        if val_inches == 0:
            return Unit(val_feet, 'ft'), None
        else:
            return Unit(val_feet, 'ft'), Unit(val_inches, 'in')
