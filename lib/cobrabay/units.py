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

class Units:
    def __init__(self,mode):
        self._logger = logging.getLogger('cobrabay')
        if mode not in ("metric","imperial"):
            self._logger.error("Requested unit mode '{}' is not supported!")
            sys.exit(1)
        # Save the mode
        self._mode = mode

    # General-purpose converter.
    def convert(self,value, input_unit,output_unit):
        if input_unit not in CONVERSION_TABLE:
            raise ValueError("{} is not a supported unit.".format(input_unit))
        if output_unit not in CONVERSION_TABLE[input_unit]:
            raise ValueError("Cannot make a conversion from {} to {}. (Be serious!)".format(input_unit,output_unit))
        if output_unit is 'ft':
            # Special handling to make a foot-inches dict. First convert to inches.
            ( val_inches, unit ) = self.convert(value,input_unit,'in')
            val_feet = floor(val_inches/12)
            val_inches = val_inches % 12
            return ({'ft': val_feet, 'in': val_inches}, output_unit)
        else:
            return (value * CONVERSION_TABLE[input_unit][output_unit], output_unit)

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

