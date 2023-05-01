####
# Cobra Bay - Config Loader
####
import logging
import os.path
import sys
import yaml
from pathlib import Path
from pint import Quantity
from pprint import pformat
import importlib


class CBConfig:
    def __init__(self, config_file=None, reset_sensors=False, log_level="WARNING"):
        self._config = None
        self._logger = logging.getLogger("CobraBay").getChild("Config")
        self._logger.setLevel(log_level)

        # Initialize the internal config file variable
        self._config_file = None
        # Default search paths.
        search_paths = [
            Path('/etc/cobrabay/config.yaml'),
            Path.cwd().joinpath('config.yaml')
        ]
        if isinstance(config_file,Path):
            search_paths.insert(0, Path(config_file))

        for path in search_paths:
            try:
                self.config_file = path
            except:
                pass
        if self._config_file is None:
            raise ValueError("Cannot find valid config file! Attempted: {}".format([str(i) for i in search_paths]))
        # Load the config file. This does validation as well!
        self.load_config()
        # If necessary, adjust our own log level.
        new_loglevel = self.get_loglevel('config')
        if new_loglevel != log_level:
            self._logger.setLevel(new_loglevel)
            self._logger.warning("Adjusted config module logging level to '{}'".format(new_loglevel))

    def load_config(self, reset_sensors=False):
        # Open the current config file and suck it into a staging variable.
        staging_yaml = self._open_yaml(self._config_file)
        # Do a formal validation here? Probably!
        try:
            validated_yaml = self._validator(staging_yaml)
        except KeyError as e:
            raise e
        else:
            self._logger.info("Config file validated.")
            # We're good, so assign the staging to the real config.
            self._logger.debug("Active configuration:")
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
        valid_keys = ('unit_system', 'system_name', 'mqtt', 'mqtt_commands', 'interface', 'homeassistant', 'logging')
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
        if system_config['unit_system'].lower() not in ('metric', 'imperial'):
            self._logger.debug("Unit setting {} not valid, defaulting to metric.".format(system_config['unit_system']))
            # If not metric or imperial, default to metric.
            system_config['unit_system'] = 'metric'

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
        requested_level = None
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
            if requested_level is None:
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
                    "Module {} had unknown level {}. Using WARNING.".format(mod_id, requested_level))
                return "WARNING"

    # Return a settings dict to be used for the Display module.
    def display(self):
        # Initialize the config dict.
        config_dict = {}
        # Bring in the unit system.
        config_dict['unit_system'] = self._config['system']['unit_system']
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
        # Default font is the packaged-in OpenSans Light.
        with importlib.resources.path("CobraBay.data", 'OpenSans-Light.ttf') as p:
            core_font_path = p
        self._logger.debug("Using default font at path: {}".format(core_font_path))
        config_dict['core_font'] = str(core_font_path)
        # If the font is defined and exists, use that.
        if 'font' in self._config['display']:
            if os.path.isfile(self._config['display']['font']):
                config_dict['core_font'] = self._config['display']['font']
        return config_dict

    # Return a settings dict to be used for the Network module.
    def network(self):
        config_dict = {
            'unit_system': self._config['system']['unit_system'],
            'system_name': self._config['system']['system_name'],
            'log_level': self.get_loglevel('network'),
            'mqtt_log_level': self.get_loglevel('mqtt')
        }

        try:
            config_dict['homeassistant'] = self._config['system']['homeassistant']
        except KeyError:
            config_dict['homeassistant'] = False
        config_dict['interface'] = self._config['system']['interface']
        # Check for MQTT definition
        if 'mqtt' not in self._config['system'].keys():
            raise ValueError("MQTT must be defined in system block.")
        elif not isinstance(self._config['system']['mqtt'],dict):
            raise TypeError("MQTT definition must be a dictionary of values.")
        else:
            required_keys = ['broker','port','username','password']
            for rk in required_keys:
                if rk not in self._config['system']['mqtt']:
                    raise ValueError("Required key '{}' not in system MQTT definition".format(rk))
                else:
                    config_dict["mqtt_" + rk] = self._config['system']['mqtt'][rk]
            if 'port' in self._config['system']['mqtt']:
                config_dict["mqtt_port"] = self._config['system']['mqtt']['port']
            else:
                config_dict["mqtt_port"] = 1883
        return config_dict

    def bay(self, bay_id):
        self._logger.debug("Received config generate request for: {}".format(bay_id))
        if bay_id not in self._config['bays']:
            raise KeyError("No configuration defined for {}".format(bay_id))
        # Initialize the config dict. Include the bay ID, and default to metric.
        config_dict = {
            'bay_id': bay_id,
            'output_unit': 'm',
            'selected_range': None,
            'settings': {},
            'intercepts': {},
            'detector_settings': {},
            'log_level': self.get_loglevel(bay_id, mod_type='bay')
        }
        # If Imperial is defined, bay should output in inches.
        try:
            if self._config['system']['unit_system'].lower() == 'imperial':
                config_dict['output_unit'] = 'in'
        except KeyError:
            pass

        # Set a 'friendly' name for use in HA discovery. If not defined, use the Bay ID.
        try:
            config_dict['bay_name'] = self._config['bays'][bay_id]['name']
        except KeyError:
            config_dict['bay_name'] = self._config['bays'][bay_id]['bay_id']

        # How long there should be no motion until we consider the bay to be parked.
        config_dict['motion_timeout'] = Quantity(self._config['bays'][bay_id]['motion_timeout']).to('second')
        # Actual bay depth, from the range sensor to the garage door.
        config_dict['bay_depth'] = Quantity(self._config['bays'][bay_id]['bay_depth']).to('cm')
        # Stop point, the distance from the sensor to the point where the vehicle should stop.
        config_dict['stop_point'] = Quantity(self._config['bays'][bay_id]['stop_point']).to('cm')

        # Create the detector configuration for the bay.
        # Each bay applies bay-specific options to a detector when it initializes.
        long_fallback = { 'offset': Quantity("0 cm"), 'spread_park': '2 in', 'pct_warn': 90, 'pct_crit': 95 }
        long_required = ['spread_park', 'pct_warn', 'pct_crit']
        lat_fallback = { 'offset': Quantity("0 cm"), 'spread_ok': '1 in', 'spread_warn': '3 in' }
        lat_required = ['side', 'intercept']
        available_long = []  # We'll save available longitudinal sensors here to select a range sensor from later.
        for direction in ('longitudinal', 'lateral'):
            # Pull the defaults as a base. Otherwise, it's an empty dict.
            try:
                # Use defaults for this direction.
                direction_defaults = self._config['bays'][bay_id][direction]['defaults']
            except KeyError:
                # If no defined defaults, empty list.
                direction_defaults = {}
            for detector in self._config['bays'][bay_id][direction]['detectors']:
                # Longitudinal check.
                if direction == 'longitudinal':
                    # Merge in the fallback items. User-defined defaults take precedence.
                    dd = dict( long_fallback.items() | direction_defaults.items() )
                    # Merge in the defaults with the detector specific settings. Detector-specific items take precedence.
                    config_dict['detector_settings'][detector['detector']] = dict( dd.items() | detector.items() )
                    for setting in long_required:
                        if setting not in config_dict['detector_settings'][detector['detector']]:
                            raise ValueError("Required setting '{}' not present in configuration for detector '{}' in "
                                             "bay '{}'. Must be set directly or have default set.".
                                format(setting, detector, bay_id ))
                    available_long.append(detector['detector'])
                    # Calculate the offset for this detector
                    # This detector will be offset by the bay's stop point, adjusted by the original offset of the detector.
                    config_dict['detector_settings'][detector['detector']]['offset'] = \
                        Quantity(self._config['bays'][bay_id]['stop_point']) - \
                        Quantity(config_dict['detector_settings'][detector['detector']]['offset'])
                # Lateral check.
                if direction == 'lateral':
                    # Merge in the fallback items. User-defined defaults take precedence.
                    dd = dict( lat_fallback.items() | direction_defaults.items() )
                    # Merge in the defaults with the detector specific settings. Detector-specific items take precedence.
                    config_dict['detector_settings'][detector['detector']] = dict( dd.items() | detector.items() )
                    # Check for required settings.
                    for setting in lat_required:
                        if setting not in config_dict['detector_settings'][detector['detector']]:
                            raise ValueError("Required setting '{}' not present in configuration for detector '{}' in "
                                             "bay '{}'. Must be set directly or have default set.".
                                format(setting, detector, bay_id ))
                    # Add to the intercepts list.
                    config_dict['intercepts'][detector['detector']] = Quantity(detector['intercept'])

            # Pick a range sensor to use as 'primary'.
            if config_dict['selected_range'] is None:
                # If there's only one longitudinal detector, that's the one to use for range.
                if len(available_long) == 0:
                    raise ValueError("No longitudinal sensors defined, cannot select one for range!")
                elif len(available_long) == 1:
                    config_dict['selected_range'] = available_long[0]
                else:
                    raise NotImplementedError("Multiple longitudinal sensors not yet supported.")
        return config_dict

    # Config dict for a detector.
    def detector(self, detector_id):
        self._logger.debug("Received config generate request for: {}".format(detector_id))
        if detector_id not in self._config['detectors']:
            raise KeyError("No configuration defined for detector '{}'".format(detector_id))
        # Assemble the config dict
        config_dict = {
            'detector_id': detector_id,
            'name': self._config['detectors'][detector_id]['name'],
            'type': self._config['detectors'][detector_id]['type'].lower(),
            'sensor_type': self._config['detectors'][detector_id]['sensor']['type'],
            'sensor_settings': self._config['detectors'][detector_id]['sensor'],
            'log_level': self.get_loglevel(detector_id, mod_type='detector')
        }

        # Add the logger to the sensor settings, so the sensor can log directly.
        config_dict['sensor_settings']['logger'] = 'CobraBay.sensors'
        del config_dict['sensor_settings']['type']

        # Optional parameters if included.
        if config_dict['type'] == 'range':
            try:
                config_dict['error_margin'] = self._config['detectors'][detector_id]['error_margin']
            except KeyError:
                config_dict['error_margin'] = Quantity("0 cm")
        elif config_dict['type'] == 'lateral':
            pass

        self._logger.debug("Returning config: {}".format(config_dict))
        return config_dict

    def trigger(self, trigger_id):
        self._logger.debug("Received config generate request for trigger: {}".format(trigger_id))
        if trigger_id not in self._config['triggers']:
            raise KeyError("No configuration defined for trigger: '{}'".format(trigger_id))
        config_dict = {
            'id': trigger_id,
            'log_level': self.get_loglevel(trigger_id)
        }
        self._logger.debug("Trigger has config: {}".format(self._config['triggers'][trigger_id]))
        try:
            config_dict['name'] = self._config['triggers'][trigger_id]['name']
        except KeyError:
            self._logger.debug("Trigger {} has no name, using ID instead.")
            config_dict['name'] = trigger_id
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
            else:
                try:
                    config_dict['trigger_value'] = self._config['triggers'][trigger_id]['to']
                    config_dict['change_type'] = 'to'
                except KeyError:
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
