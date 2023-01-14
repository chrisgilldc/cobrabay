####
# Cobra Bay - Config Loader
####
import logging
import sys
import yaml
from pathlib import Path
from pint import Quantity
from pprint import pformat


class CBConfig:
    def __init__(self, config_file=None, reset_sensors=False):
        self._config = None
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
            search_paths.insert(0, Path(config_file))

        for path in search_paths:
            try:
                self.config_file = path
            except:
                pass
        if self._config_file is None:
            raise ValueError("Cannot find valid config file! Attempted: {}".format(search_paths))
        # Load the config file. This does validation as well!
        self.load_config()

    def load_config(self, reset_sensors=False):
        # Open the current config file and suck it into a staging variable.
        staging_yaml = self._open_yaml(self._config_file)
        # Do a formal validation here? Probably!
        try:
            validated_yaml = self._validator(staging_yaml)
        except KeyError as e:
            raise e
        else:
            self._logger.info("Config file validated. Loading.")
            # We're good, so assign the staging to the real config.
            self._logger.debug(pformat(validated_yaml))
            self._config = validated_yaml

    @property
    def config_file(self):
        if self._config_file is None:
            return None
        else:
            return str(self._config_file)

    @config_file.setter
    def config_file(self, the_input):
        # IF a string, convert to a path.
        if isinstance(the_input, str):
            the_input = Path(the_input)
        if not isinstance(the_input, Path):
            # If it's not a Path now, we can't use this.
            raise TypeError("Config file must be either a string or a Path object.")
        if not the_input.is_file():
            raise ValueError("Provided config file {} is not actually a file!".format(the_input))
        # If we haven't trapped yet, assign it.
        self._config_file = the_input

    # Method for opening loading a Yaml file and slurping it in.
    @staticmethod
    def _open_yaml(config_path):
        with open(config_path, 'r') as config_file_handle:
            config_yaml = yaml.safe_load(config_file_handle)
        return config_yaml

    # Main validator.
    def _validator(self, staging_yaml):
        # Check for the main sections.
        for section in ('system', 'triggers', 'display', 'detectors', 'bays'):
            if section not in staging_yaml.keys():
                raise KeyError("Required section {} not in config file.".format(section))
        staging_yaml['system'] = self._validate_system(staging_yaml['system'])
        # If MQTT Commands are enabled, create that trigger config. Will be picked up by the core.
        if staging_yaml['system']['mqtt_commands']:
            self._logger.info("Enabling MQTT Command processors.")
            try:
                staging_yaml['triggers']['sys_cmd'] = { 'type': 'syscommand' }
            except TypeError:
                staging_yaml['triggers'] = {}
                staging_yaml['triggers']['sys_cmd'] = {'type': 'syscommand'}

            for bay_id in staging_yaml['bays'].keys():
                trigger_name = bay_id + "_cmd"
                staging_yaml['triggers'][trigger_name] = {'type': 'baycommand', 'bay_id': bay_id }
        return staging_yaml

    # Validate the system section.
    def _validate_system(self, system_config):
        valid_keys = ('units', 'system_name', 'network', 'mqtt_commands', 'interface', 'homeassistant', 'logging')
        required_keys = ('system_name', 'interface')
        # Remove any key values that aren't valid.
        for actual_key in system_config:
            if actual_key not in valid_keys:
                # Delete unknown keys.
                self._logger.error("System config has unknown item '{}'. Ignoring.".format(actual_key))
        # Required keys for which we must have a value, but not a *specific* value.
        for required_key in required_keys:
            if required_key not in system_config:
                self._logger.critical("System config requires '{}' to be set. Cannot continue.".format(required_key))
                sys.exit(1)
            elif not isinstance(system_config[required_key], str):
                self._logger.critical("Required system config item '{}' must be a string. Cannot continue.".format(required_key))
                sys.exit(1)
            else:
                # Strip spaces and we're good to go.
                system_config[required_key] = system_config[required_key].replace(" ", "_")
        # Specific value checks.
        if system_config['units'].lower() not in ('metric', 'imperial'):
            self._logger.debug("Unit setting {} not valid, defaulting to metric.".format(system_config['units']))
            # If not metric or imperial, default to metric.
            system_config['units'] = 'metric'

        return system_config

    def _validate_general(self):
        pass

    def log_handlers(self):
        # Set defaults.
        config_dict = {
            'console': False,
            'file': False,
            'file_path': Path.cwd() / ( self._config['system']['system_name'] + '.log' ),
            'syslog': False,
            'format': logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        }

        # Check for Console
        try:
            if self._config['system']['logging']['console']:
                config_dict['console'] = True
        except KeyError:
            pass

        # Check for file
        try:
            if self._config['system']['logging']['file']:
                config_dict['file'] = True
                try:
                    config_dict['file_path'] = Path(self._config['system']['logging']['file_path'])
                except KeyError:
                    pass
        except KeyError:
            pass

        return config_dict

    # Method to let modules get their proper logging levels.
    def get_loglevel(self, mod_id, mod_type=None):
        if 'logging' not in self._config['system']:
            # If there's no logging section at all, return info.
            self._logger.error("No logging section in config, using INFO as default.")
            return "WARNING"
        else:
            # For bays and detectors, check for log settings of *specific instances* before checking for the overall module.
            if mod_type == 'bay':
                try:
                    requested_level = self._config['system']['logging']['bays'][mod_id].lower()
                except KeyError:
                    mod_id = 'bays'
                except TypeError:
                    mod_id = 'bays'
            elif mod_type == 'detector':
                try:
                    requested_level = self._config['system']['logging']['detectors'][mod_id].lower()
                except KeyError:
                    mod_id = 'detectors'
                except TypeError:
                    mod_id = 'detectors'
            # Check for module-level setting.
            try:
                requested_level = self._config['system']['logging'][mod_id].lower()
            except KeyError:
                try:
                    # No module-level logging, use the system default level.
                    requested_level = self._config['system']['logging']['default_level'].lower()
                except KeyError:
                    # Not defined either, default to Warning.
                    requested_level = "WARNING"

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
                self._logger.error(
                    "Module {} had unknown level {}. Using WARNING instead.".format(mod_id, requested_level))
                return "WARNING"

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
        config_dict['interface'] = self._config['system']['interface']
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

        # Get the defined defaults for detectors
        defaults = {'lateral': {}, 'longitudinal': {}}
        detector_options = {
            'longitudinal': ('offset', 'bay_depth', 'spread_park'),
            'lateral': ('offset', 'spread_ok', 'spread_warn', 'side', 'intercept')
        }
        for direction in ('lateral', 'longitudinal'):
            for item in detector_options[direction]:
                try:
                    defaults[direction][item] = self._config['bays'][bay_id][direction]['defaults'][item]
                except KeyError:
                    pass

        self._logger.debug("Assembled Longitudinal defaults: {}".format(defaults['longitudinal']))
        self._logger.debug("Assembled Lateral defaults: {}".format(defaults['lateral']))

        config_dict['detectors'] = {}
        config_dict['detectors'] = {
            'selected_range': None,
            'settings': {},
            'intercepts': {},
            'longitudinal': [],
            'lateral': []

        }
        # Create the actual detector configurations.
        for direction in ('longitudinal', 'lateral'):
            for detector in self._config['bays'][bay_id][direction]['detectors']:
                # Build the detector config for this detector. Check the config file for overrides first, then use
                # defaults. If we can't do either, then raise an error.
                detector_config = {}
                for config_item in detector_options[direction]:
                    try:
                        detector_config[config_item] = detector[config_item]
                    except KeyError:
                        # No detector_specific option. Try to use the default.
                        try:
                            detector_config[config_item] = defaults[direction][config_item]
                        except KeyError:
                            # Couldn't find this either. That's a problem!
                            raise
                self._logger.debug("Assembled detector config: {}".format(detector_config))
                # Store the settings.
                config_dict['detectors']['settings'][detector['detector']] = detector_config
                # Save the name in the right place.
                if direction == 'longitudinal':
                    config_dict['detectors']['longitudinal'].append(detector['detector'])

                # Lateral detectors have an intercept distance.
                if direction == 'lateral':
                    config_dict['detectors']['lateral'].append(detector['detector'])
                    try:
                        config_dict['detectors']['intercepts'][detector['detector']] = Quantity(detector['intercept'])
                    except KeyError as ke:
                        raise Exception('Lateral detector {} does not have intercept distance defined!'
                                        .format(detector['detector'])) from ke

            # Pick a range sensor to use as 'primary'.
            if config_dict['detectors']['selected_range'] is None:
                # If there's only one longitudinal detector, that's the one to use for range.
                if len(config_dict['detectors']['longitudinal']) == 1:
                    config_dict['detectors']['selected_range'] = config_dict['detectors']['longitudinal'][0]
        return config_dict

    # Config dict for a detector.
    def detector(self, detector_id):
        self._logger.info("Received config generate request for: {}".format(detector_id))
        if detector_id not in self._config['detectors']:
            raise KeyError("No configuration defined for detector '{}'".format(detector_id))
        # Assemble the config dict
        config_dict = {
            'id': detector_id,
            'name': self._config['detectors'][detector_id]['name'],
            'sensor': self._config['detectors'][detector_id]['sensor']
        }

        # Initialize required setting values so they exist. This is required so readiness can be checked.
        # If they're defined in the config, great, use those values, otherwise initialize as None.
        if self._config['detectors'][detector_id]['type'].lower() == 'range':
            required_settings = ['offset', 'bay_depth', 'spread_park', 'pct_warn', 'pct_crit', 'error_margin']
        elif self._config['detectors'][detector_id]['type'].lower() == 'lateral':
            required_settings = ['offset', 'spread_ok', 'spread_warn', 'side']
        else:
            raise ValueError("Detector {} has unknown type.".format(detector_id))

        # The required settings list is stored in settings itself, so it can be used by the check_ready decorator.
        config_dict['required'] = required_settings

        for required_setting in required_settings:
            try:
                config_dict[required_setting] = self._config['detectors'][detector_id][required_setting]
            except KeyError:
                config_dict[required_setting] = None

        self._logger.debug("Returning config: {}".format(config_dict))
        return config_dict

    def trigger(self, trigger_id):
        self._logger.info("Received config generate request for trigger: {}".format(trigger_id))
        if trigger_id not in self._config['triggers']:
            raise KeyError("No configuration defined for trigger: '{}'".format(trigger_id))
        config_dict = {
            'id': trigger_id
        }
        self._logger.debug("Trigger has config: {}".format(self._config['triggers'][trigger_id]))
        # Validate the type.
        try:
            if self._config['triggers'][trigger_id]['type'] not in ('mqtt_sensor', 'syscommand', 'baycommand', 'range'):
                raise ValueError("Trigger {} has unknown type.")
            else:
                config_dict['type'] = self._config['triggers'][trigger_id]['type']
        except KeyError:
            raise KeyError("Trigger {} does not have a defined type.")

        # Both MQTT command and MQTT sensor can have an MQTT topic defined. This will override auto-generation.
        if config_dict['type'] == 'mqtt_sensor':
            try:
                config_dict['topic'] = self._config['triggers'][trigger_id]['topic']
                config_dict['topic_mode'] = 'full'
            except KeyError:
                config_dict['topic'] = trigger_id
                config_dict['topic_mode'] = 'suffix'

        # Set topic and topic mode for the command handlers. These will always be 'cmd', and always a suffix.
        if config_dict['type'] in ('syscommand','baycommand'):
            config_dict['topic'] = 'cmd'
            config_dict['topic_mode'] = 'suffix'

        # Bay command needs the Bay ID to build the topic correctly.
        if config_dict['type'] == 'baycommand':
            config_dict['bay_id'] = self._config['triggers'][trigger_id]['bay_id']

        # MQTT Sensor requires some additional checks.
        if config_dict['type'] == 'mqtt_sensor':
            try:
                config_dict['bay_id'] = self._config['triggers'][trigger_id]['bay']
            except KeyError:
                raise KeyError("Trigger {} must have a bay defined and doesn't.".format(trigger_id))

            # Make sure either to or from is defined, but not both.
            if all(key in self._config['triggers'][trigger_id] for key in ('to', 'from')):
                raise ValueError("Trigger {} has both 'to' and 'from' options set, can only use one.")
            elif self._config['triggers'][trigger_id]['to']:
                config_dict['trigger_value'] = self._config['triggers'][trigger_id]['to']
                config_dict['change_type'] = 'to'
            elif self._config['triggers'][trigger_id]['from']:
                config_dict['trigger_value'] = self._config['triggers'][trigger_id]['from']
                config_dict['change_type'] = 'from'

        # Check the when_triggered options for both mqtt_sensor and range triggers.
        if config_dict['type'] in ('mqtt_sensor', 'range'):
            if self._config['triggers'][trigger_id]['when_triggered'] in ('dock', 'undock', 'occupancy', 'verify'):
                config_dict['when_triggered'] = self._config['triggers'][trigger_id]['when_triggered']
            else:
                raise ValueError("Trigger {} has unknown when_triggered setting.".format(trigger_id))

        return config_dict

    # Properties!
    @property
    def bay_list(self):
        return self._config['bays'].keys()

    @property
    def detector_list(self):
        return self._config['detectors'].keys()

    @property
    def trigger_list(self):
        return self._config['triggers'].keys()
