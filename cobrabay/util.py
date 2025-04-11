####
# Cobra Bay - Utility Methods
####

from pint import Quantity
import board
import busio
from time import sleep
from datetime import timedelta
import logging
import cobrabay.const
from cobrabay.datatypes import ENVOPTIONS
import pathlib

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
            # elif str(input_value.units) == 'second':
            #     output = str(timedelta(seconds=round(input_value.magnitude)))
            elif str(input_value.units) == 'second':
                output = round(input_value.magnitude)
            # This should catch any dimensionless values.
            elif str(input_value.dimensionality) == 'dimensionless':
                output = input_value
            # Anything else is out of left field, raise an error.
            else:
                raise ValueError("'{}' has unsupported dimensionality '{}' and/or units of '{}'.".format(input_value,
                                                                                                         input_value.dimensionality,
                                                                                                         input_value.units))
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
        # Convert sensor warning exceptions....
        elif isinstance(input_value, IOError):
            result = "sensor_error"
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


def aw9523_reset(aw9523_obj):
    """
    Reset all pins on an AW9523 to outputs and turn them off.
    :param aw9523_obj: AW9523
    """
    for pin in range(15):
        pin_obj = aw9523_obj.get_pin(pin)
        pin_obj.switch_to_output()
        pin_obj.value = False


def aw9523_status(aw9523_obj, summarize=True):
    """
    Check status of all pins.
    Assembles a string, tab
    """
    active = 0
    inactive = 0
    output_string = ""
    for pin in range(15):
        pin_obj = aw9523_obj.get_pin(pin)
        if pin_obj.value:
            active += 1
        else:
            inactive += 1
        if pin == 0:
            output_string = "Pin {}: {}".format(pin, pin_obj.value)
        else:
            output_string = output_string + "\n\tPin {}: {}".format(pin, pin_obj.value)
    if summarize:
        output_string = "Active: {}\tInactive:{}\n\t".format(active, inactive) + output_string
    return output_string

def scan_i2c():
    """
    Scan the I2C Bus.
    :return: Active addresses on the bus.
    :rtype List
    """
    i2c = busio.I2C(board.SCL, board.SDA)
    while not i2c.try_lock():
        pass
    found_addresses = [hex(device_address) for device_address in i2c.scan()]
    sleep(2)
    i2c.unlock()
    return found_addresses

def typeconv(payload, tgt_type):
    """ Convert a string to another type based on target name. Is there a built-in for this? IDK. """
    if not isinstance(payload, str):
        raise TypeError("Payload must be a string.")
    else:
        if tgt_type == 'int':
            return int(payload)
        elif tgt_type == 'float':
            return float(payload)
        elif tgt_type == 'bool':
            if payload.lower() in ['true','on'] or payload == '1':
                return True
            else:
                return False
        elif tgt_type == 'str':
            # This is silly, but support it.
            return payload
        else:
            raise ValueError("Target type '{}' not supported.".format(tgt_type))


def default_logger(name, parent_logger=None, log_level="WARNING"):
    """
    General
    :param name: Name to be logging as.
    :type name: str
    :param parent_logger: Logger to make a child logger of.
    :type parent_logger: logging.Logger or None
    :param log_level: Level to log at, defaults to WARNING.
    :type log_level: str
    :return: logging.Logger
    """

    if parent_logger is None:
        # If no parent is given, create a direct stream logger.
        the_logger = logging.getLogger(name)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(cobrabay.const.LOG_FORMAT))
        console_handler.setLevel(log_level)
        the_logger.addHandler(console_handler)
        the_logger.setLevel(log_level)
    else:
        the_logger = parent_logger.getChild(name)
        the_logger.setLevel(log_level)
    return the_logger

# Don't think this is needed anymore.
# def _validate_environment(input_base,
#                           input_rundir,
#                           input_configdir,
#                           input_configfile,
#                           input_logdir,
#                           input_logfile,
#                           input_loglevel):
#     # Check the base directory.
#     try:
#         base = pathlib.Path(input_base)
#     except TypeError as e:
#         print("Cannot make a valid path for base directory from option '{}'.".format(input_base))
#         raise e
#     else:
#         # Make the base absolute.
#         basedir = base.absolute()
#         if not basedir.is_dir():
#             raise TypeError("Base directory '{}' is not a directory.".format(basedir))
#         print("Base directory: {}".format(basedir))
#
#     # Run directory, for the PID file.
#     try:
#         rundir = pathlib.Path(input_rundir)
#     except TypeError as e:
#         print("Cannot make a valid path for run directory from option '{}'.".format(input_rundir))
#         raise e
#     else:
#         if not rundir.is_absolute():
#             rundir = basedir / rundir
#         if not rundir.is_dir():
#             raise ValueError("Run directory '{}' not a directory. Cannot continue!".format(rundir))
#         print("Run directory: {}".format(rundir))
#
#     # Config directory, to allow versioned configs.
#     try:
#         configdir = pathlib.Path(input_configdir)
#     except TypeError as e:
#         print("Cannot make a valid path for config directory from option '{}'.".format(input_configdir))
#         raise e
#     else:
#         if not configdir.is_absolute():
#             configdir = basedir / configdir
#         if not configdir.is_dir():
#             raise ValueError("Config directory '{}' not a directory. Cannot continue!".format(configdir))
#         if configdir != basedir:
#             print("Config directory: {}".format(configdir))
#
#     try:
#         configfile = pathlib.Path(input_configfile)
#     except TypeError:
#         configfile = None
#         print("No config file specified on command line. Will search default locations.")
#     else:
#         # If config isn't absolute, make it relative to the base.
#         if not configfile.is_absolute():
#             configfile = configdir / configfile
#         if not configfile.exists():
#             raise ValueError("Config file '{}' does not exist. Cannot continue!".format(configfile))
#         if not configfile.is_file():
#             raise ValueError("Config file '{}' is not a file. Cannot continue!".format(configfile))
#         print("Config file: {}".format(configfile))
#
#     # Logging directory.
#     try:
#         logdir = pathlib.Path(input_logdir)
#     except TypeError as e:
#         print("Cannot make a valid path for log directory from option '{}'.".format(input_configdir))
#         raise e
#     else:
#         if not logdir.is_absolute():
#             logdir = basedir / logdir
#         if not logdir.is_dir():
#             raise ValueError("Log directory '{}' not a directory.".format(logdir))
#         if logdir != basedir:
#             print("Log directory: {}".format(logdir))
#
#     # Log file
#     try:
#         logfile = pathlib.Path(input_logfile)
#     except TypeError as e:
#         print("Cannot make a valid path for run directory from option '{}'.".format(input_logdir))
#         raise e
#     else:
#         # If config isn't absolute, make it relative to the base.
#         if not logfile.is_absolute():
#             logfile = logdir / logfile
#         # Don't need to check if the file exists, will create on start.
#         print("Log file: {}".format(logfile))
#
#     # Log level.
#     if input_loglevel is not None:
#         if input_loglevel.upper() in ('DEBUG,INFO,WARNING,ERROR,CRITICAL'):
#             loglevel = input_loglevel.upper()
#         else:
#             raise ValueError('{} is not a valid log level.'.format(input_loglevel))
#     else:
#         loglevel = None
#
#     valid_environment = ENVOPTIONS(
#         base=basedir,
#         rundir=rundir,
#         configdir=configdir,
#         configfile=configfile,
#         logdir=logdir,
#         logfile=logfile,
#         loglevel=loglevel
#     )
#
#     return valid_environment