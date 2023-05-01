####
# Cobra Bay - Utility Methods
####

from pint import Quantity
import board
import busio
from time import sleep
from datetime import timedelta
import CobraBay


# General purpose converter.
class Convertomatic:
    def __init__(self, unit_system):
        self._unit_system = unit_system

    def convert(self, input):
        if isinstance(input, Quantity):
            # Check for various dimensionalities and convert as appropriate.
            # Distance
            if input.check('[length]'):
                # self._logger.debug("Quantity is a length.")
                if self._unit_system == "imperial":
                    output = input.to("in")
                else:
                    output = input.to("cm")
            # Temperature
            elif input.check('[temperature]'):
                if self._unit_system == "imperial":
                    output = input.to("degF")
                else:
                    output = input.to("degC")
            # Speed, ie: length over time
            elif input.check('[velocity]'):
                if self._unit_system == "imperial":
                    output = input.to("mph")
                else:
                    output = input.to("kph")
            # Bytes don't have a dimensionality, so we check the unit name.
            elif str(input.units) == 'byte':
                output = input.to("Mbyte")
            elif str(input.units) == 'second':
                output = str(timedelta(seconds=input.magnitude))
            # This should catch any dimensionless values.
            elif str(input.dimensionality) == 'dimensionless':
                output = input
            # Anything else is out of left field, raise an error.
            else:
                raise ValueError("Dimensionality of {} and/or units of {} is not supported by Convertomatic.".format(input.dimensionality, input.units))
            # If still a Quantity (ie: Not a string), take the magnitude, round and output as float.
            if isinstance(output, Quantity):
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
        if isinstance(input, bool):
            return str(input)
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
    def unit_system(self, input):
        if input.lower() in ('imperial', 'metric'):
            self._unit_system = input.lower()
        else:
            raise ValueError("Convertomatic unit system must be 'imperial' or 'metric'")


def mqtt_message_search(input, element, value, extract=None):
    if not isinstance(input, list):
        raise TypeError("MQTT Message Search expects a list of dicts.")
    matching_messages = []
    # Iterate the messages.
    for mqtt_message in input:
        try:
            # If the message's search element has the value we want, put it on the matching list.
            if mqtt_message[element] == value:
                matching_messages.append(mqtt_message)
        # If we get a key error, IE: the element doesn't exist, pass, we don't care.
        except KeyError:
            pass
    # If we haven't been asked to extract a particular value, return the complete list of matched messages.
    if extract is None:
        return matching_messages
    else:
        if len(matching_messages) == 1:
            # If there's only one matched message, return the extract value directly.
            return matching_messages[0][extract]
        else:
            return_values = []
            for matched_message in matching_messages:
                return_values.append(matched_message[extract])
            return return_values


def scan_i2c():
    i2c = busio.I2C(board.SCL, board.SDA)
    while not i2c.try_lock():
        pass
    found_addresses = [hex(device_address) for device_address in i2c.scan()]
    sleep(2)
    i2c.unlock()
    return found_addresses