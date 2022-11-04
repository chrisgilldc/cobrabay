####
# Cobra Bay - Config Loader
####
import board
import busio
import logging
import yaml
from pathlib import Path
from pprint import PrettyPrinter
from time import sleep

from adafruit_aw9523 import AW9523
from digitalio import DigitalInOut
from adafruit_vl53l1x import VL53L1X
from pint import Quantity


class CBConfig():
    def __init__(self, config_file=None, reset_sensors=False):
        self._logger = logging.getLogger("CobraBay").getChild("Config")
        self._logger.info("Processing config...")

        # Initialize the internal config file variable
        self._config_file = None
        # Default search paths.
        search_paths = [
            Path('/etc/cobrabay/config.yaml'),
            Path.cwd().joinpath('config.yaml')
        ]
        if config_file is not None:
            search_paths.insert(0,Path(config_file))

        for path in search_paths:
            try:
                self.config_file = path
            except:
                pass
        if self._config_file is None:
            raise ValueError("Cannot find valid config file! Attempted: {}".format(search_paths))
        # Load the config file. This does validation as well!
        self.load_config()

    def load_config(self,reset_sensors=False):
        pp = PrettyPrinter()
        # Open the current config file and suck it into a staging variable.
        staging_yaml = self._open_yaml(self._config_file)
        # Do a formal validation here? Probably!
        try:
            validated_yaml = self._validate(staging_yaml)
        except:
            self._logger.exception("Could not validate config file. Will not load.")
        else:
            self._logger.info("Config file validated. Loading.")
            self._logger.debug(validated_yaml)
            # We're good, so assign the staging to the real config.
            self._config = validated_yaml

    @property
    def config_file(self):
        if self._config_file is None:
            return None
        else:
            return str(self._config_file)

    @config_file.setter
    def config_file(self,input):
        # IF a string, convert to a path.
        if isinstance(input,str):
            input = Path(input)
        if not isinstance(input,Path):
            # If it's not a Path now, we can't use this.
            raise TypeError("Config file must be either a string or a Path object.")
        if not input.is_file():
            raise ValueError("Provided config file {} is not actually a file!".format(input))
        # If we haven't trapped yet, assign it.
        self._config_file = input

    # Method for opening loading a Yaml file and slurping it in.
    @staticmethod
    def _open_yaml(config_path):
        with open(config_path, 'r') as config_file_handle:
                config_yaml = yaml.safe_load(config_file_handle)
        return config_yaml

    # Main validator.
    def _validate(self,staging_yaml):
        # Check for the main sections.
        for section in ('system','display','detectors','bays'):
            if section not in staging_yaml.keys():
                raise KeyError("Required section {} not in config file.".format(section))
        return staging_yaml

    def _validate_basic(self):
        pass

    def _validate_general(self):
        pass

    # Method to let modules get their proper logging levels.
    def get_loglevel(self, module):
        if 'logging' not in self._config['system']:
            # If there's no logging section at all, return info.
            self._logger.error("No logging section in config, using INFO as default.")
            return "INFO"
        else:
            # Is the name a bay?
            if module in self._config['bays'].keys():
                try:
                    # Does the bay have its own log level defined?
                    requested_level = self._config['bays'][module]['log_level']
                except KeyError:
                    # Nope. Change our module name to 'bays' and proceed with standard testing.
                    module = 'bays'
            try:
                # Does the module have its own logging level defined?
                requested_level = self._config['system']['logging'][module].lower()
            except KeyError:
                try:
                    # No, use the system default level?
                    requested_level = self._config['system']['logging']['default_level'].lower()
                except KeyError:
                    # That's not defined either!? Default to INFO.
                    return "INFO"

            # Ensure the requested log level if valid.
            if requested_level == "debug":
                return "DEBUG"
            elif requested_level == "info":
                return "INFO"
            elif requested_level == "warning":
                return "WARNING"
            elif requested_level == "error":
                return "ERROR"
            elif requested_level == "critical":
                return "CRITICAL"
            else:
                self._logger.error("Module {} had unknown level {}. Using INFO instead.".format(module,requested_level))
                return "INFO"

    # Return a settings dict to be used for the Display module.
    def display(self):
        # Initialize the config dict.
        config_dict = {}
        # Bring in the units system.
        config_dict['units'] = self._config['system']['units']
        # Set the strobe update speed.
        try:
            config_dict['strobe_speed'] = Quantity(self._config['display']['strobe_speed']).to('nanosecond').magnitude
        except KeyError:
            # IF not defined, default to 100ms
            config_dict['strobe_speed'] = Quantity("100 ms").to('nanosecond').magnitude
        # Matrix settings.
        config_dict['matrix_width'] = self._config['display']['matrix']['width']
        config_dict['matrix_height'] = self._config['display']['matrix']['height']
        config_dict['gpio_slowdown'] = self._config['display']['matrix']['gpio_slowdown']
        config_dict['mqtt_image'] = self._config['display']['mqtt_image']
        config_dict['mqtt_update_interval'] = Quantity(self._config['display']['mqtt_update_interval'])
        config_dict['core_font'] = 'fonts/OpenSans-Light.ttf'
        return config_dict

    # Return a settings dict to be used for the Network module.
    def network(self):
        config_dict = {}
        config_dict['units'] = self._config['system']['units']
        config_dict['system_name'] = self._config['system']['system_name']
        try:
            config_dict['homeassistant'] = self._config['system']['homeassistant']
        except KeyError:
            config_dict['homeassistant'] = False
        return config_dict

    def bay(self, bay_id):
        self._logger.info("Received config generate request for: {}".format(bay_id))
        if bay_id not in self._config['bays']:
            raise KeyError("No configuration defined for {}".format(bay_id))
        # Initialize the config dict. Include the bay ID, and default to metric.
        config_dict = {
            'bay_id': bay_id,
            'unit_system': 'metric',
            'output_unit': 'm'
        }
        # If Imperial is defined, set that.
        try:
            if self._config['system']['units'].lower() == 'imperial':
                config_dict['unit_system'] = 'imperial'
                config_dict['output_unit'] = 'in'
        except KeyError:
            pass

        # Set a 'friendly' name for use in HA discovery. If not defined, use the Bay ID.
        try:
            config_dict['bay_name'] = self._config['bays'][bay_id]['name']
        except KeyError:
            config_dict['bay_name'] = self._config['bays'][bay_id]['bay_id']

        # How long there should be no motion until we consider the bay to be parked. Convert to seconds and take out
        # magnitude.
        config_dict['park_time'] = Quantity(self._config['bays'][bay_id]['park_time']).to('second').magnitude
        # Actual bay depth.
        config_dict['bay_depth'] = Quantity(self._config['bays'][bay_id]['bay_depth']).to('cm')
        # Adjust the bay depth by the offset.
        config_dict['adjusted_depth'] = Quantity(config_dict['bay_depth']) - Quantity(
            self._config['bays'][bay_id]['longitudinal']['defaults']['offset']).to('cm')

        # Bring over the directional configs. These will get processed within the bay module.
        config_dict['longitudinal'] = self._config['bays'][bay_id]['longitudinal']
        config_dict['lateral'] = self._config['bays'][bay_id]['lateral']

        return config_dict

    # Properties!
    @property
    def bay_list(self):
        return self._config['bays'].keys()