####
# Cobra Bay - Utility Methods
####

from pint import Quantity
import board
import busio
from time import sleep
from datetime import timedelta
from CobraBay.exceptions import SensorValueException


# General purpose converter.
class Convertomatic:
    def __init__(self, unit_system):
        self._unit_system = unit_system

    def convert(self, input_value):
        result = None
        if isinstance(input_value, Quantity):
            # Check for various dimensionalities and convert as appropriate.
            # Distance
            if input_value.check('[length]'):
                # self._logger.debug("Quantity is a length.")
                if self._unit_system == "imperial":
                    output = input_value.to("in")
                else:
                    output = input_value.to("cm")
            # Temperature
            elif input_value.check('[temperature]'):
                if self._unit_system == "imperial":
                    output = input_value.to("degF")
                else:
                    output = input_value.to("degC")
            # Speed, ie: length over time
            elif input_value.check('[velocity]'):
                if self._unit_system == "imperial":
                    output = input_value.to("mph")
                else:
                    output = input_value.to("kph")
            # Bytes don't have a dimensionality, so we check the unit name.
            elif str(input_value.units) == 'byte':
                output = input_value.to("Mbyte")
            elif str(input_value.units) == 'second':
                output = str(timedelta(seconds=input_value.magnitude))
            # This should catch any dimensionless values.
            elif str(input_value.dimensionality) == 'dimensionless':
                output = input_value
            # Anything else is out of left field, raise an error.
            else:
                raise ValueError("Dimensionality of {} and/or units of {} is not supported by Convertomatic.".format(input_value.dimensionality, input_value.units))
            # If still a Quantity (ie: Not a string), take the magnitude, round and output as float.
            if isinstance(output, Quantity):
                output = round(output.magnitude, 2)
            result = output
        elif isinstance(input_value, dict):
            new_dict = {}
            for key in input_value:
                new_dict[key] = self.convert(input_value[key])
            result = new_dict
        elif isinstance(input_value, list):
            new_list = []
            for item in input_value:
                new_list.append(self.convert(item))
            result = new_list
        elif isinstance(input_value, bool):
            result = str(input_value).lower()
        elif isinstance(input_value, SensorValueException):
            result = "Sensor Value Exception: {}".format(input_value.status)
        elif isinstance(input_value, BaseException):
            print("Cannot convert {}: {}".format(type(input_value), str(input_value)))
        else:
            try:
                # If this can be rounded, round it, otherwise, pass it through.
                result = round(float(input_value), 2)
            except (ValueError, TypeError):
                result = input_value
        return result

    @property
    def unit_system(self):
        return self._unit_system

    @unit_system.setter
    def unit_system(self, input_value):
        if input_value.lower() in ('imperial', 'metric'):
            self._unit_system = input_value.lower()
        else:
            raise ValueError("Convertomatic unit system must be 'imperial' or 'metric'")


def mqtt_message_search(input_value, element, value, extract=None):
    if not isinstance(input_value, list):
        raise TypeError("MQTT Message Search expects a list of dicts.")
    matching_messages = []
    # Iterate the messages.
    for mqtt_message in input_value:
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