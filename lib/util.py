####
# Cobra Bay - Utility Methods
####

from pint import Quantity

# General purpose converter.
class Convertomatic:
    def __init__(self,unit_system):
        self._unit_system = unit_system

    def convert(self, input):
        if isinstance(input, Quantity):
            # self._logger.debug("Converting Quantity...")
            # Check for various dimensionalities and convert as appropriate.
            if input.check('[length]'):
                # self._logger.debug("Quantity is a length.")
                if self._unit_system == "imperial":
                    output = input.to("in")
                else:
                    output = input.to("cm")
            if input.check('[temperature]'):
                if self._unit_system == "imperial":
                    output = input.to("degF")
                else:
                    output = input.to("degC")
            # Doesn't have a dimensionality to check, so we check for the unit name itself.
            if str(input.units) == 'byte':
                output = input.to("Mbyte")
            # Percents need no conversion.
            if str(input.units) == 'percent':
                output = input
            output = round(output.magnitude, 2)
            return output
        if isinstance(input, dict):
            new_dict = {}
            for key in input:
                new_dict[key] = self.convert(input[key])
            return new_dict
        if isinstance(input, list):
            new_list = []
            for item in input:
                new_list.append(self.convert(item))
            return new_list
        else:
            try:
                # If this can be rounded, round it, otherwise, pass it through.
                return round(float(input), 2)
            except:
                return input

    @property
    def unit_system(self):
        return self._unit_system

    @unit_system.setter
    def unit_system(self,input):
        if input.lower() in ('imperial','metric'):
            self._unit_system = input.lower()
        else:
            raise ValueError("Convertomatic unit system must be 'imperial' or 'metric'")
