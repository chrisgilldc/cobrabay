####
# Cobrabay Units Processor
####

# Helper class for unit conversion

from math import floor
import adafruit_logging as logging
import sys


class Unit:
    def __init__(self, value, unit):
        # Lookup to assign units to certain tables
        self.CONVERSION_LOOKUP = {
            'mm': 'DISTANCE_CONVERSION',
            'cm': 'DISTANCE_CONVERSION',
            'in': 'DISTANCE_CONVERSION',
            'ft': 'DISTANCE_CONVERSION',
            'ft_in': None  # This will get handled specially.
        }

        self.DISTANCE_CONVERSION = {
            'base_unit': 'cm',
            'ft': 30.48,
            'in': 2.54,
            'mm': 0.1
        }
        # Set the unit first
        self.unit = unit
        # Value will get converted
        self.value = value

    @property
    def unit(self):
        return self._unit

    @property
    def value(self):
        conversion_factor = self._get_conversion_factor(self._unit)
        return self._value / conversion_factor

    @unit.setter
    def unit(self, unit):
        """Set the unit of the object. Does *not* convert values.

        :param unit: The level of the message
        """
        if unit not in self.CONVERSION_LOOKUP:
            raise ValueError("Unit {} is not supported.".format(unit))
        else:
            self._unit = unit

    # When value is set, convert it.
    @value.setter
    def value(self, value):
        """Set the scalar value of the unit. Will be converted to the base unit type for the unit class.
        IE: all distances are stored in cm internally.
        Most units require int or float types. Foot-inches must be a dict.

        :param value: The level of the message
        """
        if self._unit is "ft-in" and not isinstance(value,dict):
            raise TypeError("Foot-inches unit type requires dict with 'ft' and 'in' elements.")
        if not isinstance(value, (int, float)):
            raise TypeError("Unit value must be int or float, got {} input".format(type(value)))
        # Convert from the given unit to the base unit.
        if self._unit == 'ft-in':
            pass
        else:
            print("Setting internal value: {}".format( value * self._get_conversion_factor(self._unit)))
            self._value = value * self._get_conversion_factor(self._unit)

    # Finds the conversion factor to/from the base unit of this unit class.
    # To go *to* the base unit, multiply. To go from the base unit, divide.
    def _get_conversion_factor(self, input_unit):
        """
        Finds the correct conversion factor to use for the particular unit requested.

        :param input_unit: The target unit to find. Must be in the same class (can't convert Hours to Miles!)
        :return: float
        """
        unit_class = getattr(self, self.CONVERSION_LOOKUP[input_unit])
        if self._unit == unit_class['base_unit']:
            return 1
        else:
            return unit_class[input_unit]

    def _get_base_unit(self):
        """
        Get the base storage unit for this class of units. ie: centimeters for distances.

        :return:
        """
        type_dict = getattr(self, self.CONVERSION_LOOKUP[self._unit])
        return type_dict['base_unit']

    def __str__(self):
        return "{} {}".format(self.value, self.unit)

    def _ft_in_normalize(self, value):
        pass

    def _ft_in_old(self):
        # Special handling for feet-inches.
        (val_inches, unit) = self.convert('in')
        val_feet = floor(val_inches / 12)
        val_inches = val_inches % 12
        if val_inches == 0:
            return Unit(val_feet, 'ft'), None
        else:
            return Unit(val_feet, 'ft'), Unit(val_inches, 'in')

    def __comparator(self,other,operator):
        if not isinstance(other,Unit):
            raise TypeError("Can only compare Units to other Units.")
        elif self._get_base_unit() is not other._get_base_unit():
            raise TypeError("Units are not the same class.")

        if operator =='lt':
            print("Is {} less than {}".format(self._value,other._value))
            return self._value < other._value
        elif operator =='le':
            return self._value <= other._value
        elif operator == 'gt':
            return self._value > other._value
        elif operator == 'ge':
            return self._value >= other._value
        elif operator == 'eq':
            return self._value == other._value
        elif operator == 'ne':
            return self._value != other._value
        else:
            raise ValueError("Not a valid operator")

    def __lt__(self, other):
        return self.__comparator(other,'lt')

    def __le__(self, other):
        return self.__comparator(other,'le')

    def __gt__(self, other):
        return self.__comparator(other,'gt')

    def __ge__(self, other):
        return self.__comparator(other,'ge')

    def __eq__(self, other):
        return self.__comparator(other,'eq')

    def __ne__(self,other):
        return self.__comparator(other,'ne')

    def convert(self, output_unit):
        # Check for issues.
        if output_unit not in self.CONVERSION_LOOKUP:
            raise ValueError("Requested output unit '{}' is not supported.".format(output_unit))

        conversion_factor = self._get_conversion_factor(output_unit)
        # Since this is a 'convert' output, to go *from* the base unit to the output unit, we divide.
        # Return a new Unit object with the new value and unit.
        return Unit(self._value / conversion_factor, output_unit)