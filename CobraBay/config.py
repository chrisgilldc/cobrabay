####
# Cobra Bay - Config Manager
####
import logging
import pprint
import yaml
from pathlib import Path
import pint
import cerberus
from collections import namedtuple
from pprint import pformat
import importlib.resources

# Subclass Validator to add custom rules, maybe types.
class CBValidator(cerberus.Validator):
    types_mapping = cerberus.Validator.types_mapping.copy()
    types_mapping['quantity'] = cerberus.TypeDefinition('quantity', (pint.Quantity,), ())

    # # Checks to see if a value can be converted by Pint, and if it has a given dimensionality.
    def _validate_dimensionality(self, constraint, field, value):
        """
        {'type': 'string'}
        """
        if str(value.dimensionality) != constraint:
            self._error(field, "Not in proper dimension {}".format(constraint))

class CBConfig:
    """
    Class to manage a single instance of a CobraBay configuration.
    Create an instance for each config version managed.
    """
    SCHEMA_SENSOR_VL53L1X = {
        'i2c_bus': {'type': 'integer', 'default': 1},
        'i2c_address': {'type': 'integer', 'required': True},
        'enable_board': {'type': 'integer', 'required': True},
        'enable_pin': {'type': 'integer', 'required': True},
        'distance_mode': {'type': 'string', 'allowed': ['long','short'], 'default': 'long'},
        'timing': {'type': 'string', 'default': '200ms'}
    }
    SCHEMA_SENSOR_TFMINI = {
        'port': { 'type': 'string', 'required': True },
        'baud': { 'type': 'integer', 'default': 115200,
                 'allowed': [9600, 14400, 19200, 56000, 115200, 460800, 921600] },
        'clustering': { 'type': 'integer', 'default': 1, 'min': 1, 'max': 5 }
    }
    SCHEMA_MAIN = {
        'system': {
            'type': 'dict',
            'required': True,
            'schema': {
                'unit_system': {'type': 'string', 'allowed': ['metric', 'imperial'], 'default': 'metric'},
                'system_name': {'type': 'string'},
                'mqtt': {
                    'type': 'dict',
                    'schema': {
                        'broker': {'type': 'string'},
                        'port': {'type': 'integer', 'default': 1883},
                        'username': {'type': 'string'},
                        'password': {'type': 'string'},
                        'accept_commands': {'type': 'boolean', 'default': True},
                        'ha_discover': {'type': 'boolean', 'default': True}
                    }
                },
                'interface': {'type': 'string'},  ## Define a method to determine default.
                'logging': {
                    'type': 'dict',
                    'required': True,
                    'schema': {
                        'console': {'type': 'boolean', 'required': True, 'default': False},
                        'file': {'type': 'boolean', 'required': True, 'default': True},
                        'file_path': {'type': 'string', 'default': str(Path.cwd() / 'cobrabay.log')},
                        'log_format': {'type': 'string', 'default': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'},
                        'default_level': {'type': 'string',
                                          'allowed': ['debug', 'info', 'warning', 'error', 'critical'],
                                          'required': True, 'default': 'warning'},
                        'bays': {'type': 'string',
                                 'allowed': ['debug', 'info', 'warning', 'error', 'critical'],
                                 'default_setter': lambda doc: doc['default_level']},
                        'config': {'type': 'string', 'allowed': ['debug', 'info', 'warning', 'error', 'critical'],
                                   'default_setter': lambda doc: doc['default_level']},
                        'core': {'type': 'string', 'allowed': ['debug', 'info', 'warning', 'error', 'critical'],
                                 'default_setter': lambda doc: doc['default_level']},
                        'detectors': {'type': 'string', 'allowed': ['debug', 'info', 'warning', 'error', 'critical'],
                                      'default_setter': lambda doc: doc['default_level']},
                        'display': {'type': 'string', 'allowed': ['debug', 'info', 'warning', 'error', 'critical'],
                                    'default_setter': lambda doc: doc['default_level']},
                        'mqtt': {'type': 'string', 'allowed': ['debug', 'info', 'warning', 'error', 'critical', 'DISABLE'],
                                    'default': 'DISABLE'},
                        'network': {'type': 'string', 'allowed': ['debug', 'info', 'warning', 'error', 'critical'],
                                    'default_setter': lambda doc: doc['default_level']},
                        'triggers': {'type': 'string', 'allowed': ['debug', 'info', 'warning', 'error', 'critical'],
                                    'default_setter': lambda doc: doc['default_level']}
                    }  # Figure out how to handle specific sensors detectors and bays.
                }
            }
        },
        'triggers': {
            'type': 'dict',
            'required': True,
            'keysrules': {
                'type': 'string',
                'regex': '[\w]+'
            },
            'valuesrules': {
                'type': 'dict',
                'schema': {
                    'type': {'type': 'string', 'required': True, 'allowed': ['mqtt_state','syscmd','baycmd']},
                    'bay': {'type': 'string', 'required': True, 'dependencies': {'type': 'mqtt_state'}},
                    'topic': {'type': 'string', 'required': True},
                    'to': {'type': 'string', 'dependencies': {'type': 'mqtt_state'}, 'excludes': 'from'},
                    'from': {'type': 'string', 'dependencies': {'type': 'mqtt_state'}, 'excludes': 'to'},
                    'action': {'type': 'string', 'required': True, 'allowed': ['dock','undock','occupancy']}
                }
            }
        },
        'display': {
            'type': 'dict',
            'required': True,
            'schema': {
                'width': {'type': 'integer', 'required': True},
                'height': {'type': 'integer', 'required': True},
                'gpio_slowdown': {'type': 'integer', 'required': True, 'default': 4},
                'font': {'type': 'string',
                         'default_setter':
                             lambda doc: str(importlib.resources.files('CobraBay.data').joinpath('OpenSans-Light.ttf')) },
                'strobe_speed': { 'type': 'quantity', 'dimensionality': '[time]', 'coerce': pint.Quantity },
                'mqtt_image': {'type': 'boolean', 'default': True},
                'mqtt_update_interval': {'type': 'quantity', 'dimensionality': '[time]', 'coerce': pint.Quantity}
            }
        },
        'detectors': {
            'type': 'dict',
            'required': True,
            'keysrules': {
                'type': 'string',
                'allowed': ['longitudinal', 'lateral']
            },
            'valuesrules': {
                'type': 'dict',
                'keysrules': {
                    'type': 'string',
                    'regex': '[\w]+'
                },
                'valuesrules': {
                    'type': 'dict',
                    'schema': {
                        'name': {'type': 'string'},
                        'error_margin': {'type': 'quantity', 'dimensionality': '[length]', 'coerce': pint.Quantity },
                        'sensor_type': {'type': 'string', 'required': True, 'allowed': ['TFMini', 'VL53L1X']},
                        # 'timing': {'type': 'quantity', 'dimensionality': '[time]', 'coerce': pint.Quantity},
                        'sensor_settings': {
                            'type': 'dict',
                            # 'required': True,
                            'oneof': [
                                {'dependencies': {'sensor_type': 'TFMini'}, 'schema': SCHEMA_SENSOR_TFMINI},
                                {'dependencies': {'sensor_type': 'VL53L1X'}, 'schema': SCHEMA_SENSOR_VL53L1X}
                            ]
                        }
                    }
                }
            }
        },
        'bays': {
            'type': 'dict',
            'required': True,
            'keysrules': {
                'type': 'string',
                'regex': '[\w]+'
            },
            'valuesrules': {
                'type': 'dict',
                'allow_unknown': True,
                'schema': {
                    'name': { 'type': 'string' },
                    'motion_timeout': { 'type': 'quantity', 'dimensionality': '[time]', 'coerce': pint.Quantity },
                    'depth': { 'type': 'quantity', 'dimensionality': '[length]', 'coerce': pint.Quantity },
                    'longitudinal': {
                        'type': 'dict',
                        'allow_unknown': True,
                        'schema': {
                            'defaults': {
                                'type': 'dict',
                                'schema': {
                                    'spread_park': { 'type': 'quantity', 'dimensionality': '[length]',
                                                     'coerce': pint.Quantity, 'default': '2 in' },
                                    'offset': { 'type': 'quantity', 'dimensionality': '[length]',
                                                'coerce': pint.Quantity, 'default': '0 in' },
                                    'pct_warn': { 'type': 'number', 'min': 0, 'max': 100, 'default': 70 },
                                    'pct_crit': { 'type': 'number', 'min': 0, 'max': 100, 'default': 90 }
                                }
                            },
                            'detectors': {
                                'type': 'list',
                                'schema': {
                                    'type': 'dict',
                                    'schema': {
                                        'spread_park': {'type': 'quantity', 'dimensionality': '[length]',
                                                        'coerce': pint.Quantity},
                                        'offset': {'type': 'quantity', 'dimensionality': '[length]',
                                                   'coerce': pint.Quantity},
                                        'pct_warn': {'type': 'number', 'min': 0, 'max': 100},
                                        'pct_crit': {'type': 'number', 'min': 0, 'max': 100}
                                    }
                                }
                            }
                        }
                    },
                    'lateral': {
                        'type': 'dict',
                        'allow_unknown': True,
                        'schema': {
                            'defaults': {
                                'type': 'dict',
                                'schema': {
                                    'offset': {'type': 'quantity', 'dimensionality': '[length]',
                                               'coerce': pint.Quantity, 'default': '0 in'},
                                    'spread_ok': {'type': 'quantity', 'dimensionality': '[length]',
                                                  'coerce': pint.Quantity, 'default': '1 in'},
                                    'spread_warn': {'type': 'quantity', 'dimensionality': '[length]',
                                                    'coerce': pint.Quantity, 'default': '3 in'},
                                    'limit': {'type': 'quantity', 'dimensionality': '[length]',
                                              'coerce': pint.Quantity, 'default': '96 in'},
                                    'side': {'type': 'string', 'allowed': ['L', 'R']}
                                }
                            },
                            'detectors': {
                                'type': 'list',
                                'schema': {
                                    'type': 'dict',
                                    'schema': {
                                        'detector': {'type': 'string', 'required': True},
                                        'offset': {'type': 'quantity', 'dimensionality': '[length]',
                                                   'coerce': pint.Quantity},
                                        'spread_ok': {'type': 'quantity', 'dimensionality': '[length]',
                                                      'coerce': pint.Quantity},
                                        'spread_warn': {'type': 'quantity', 'dimensionality': '[length]',
                                                        'coerce': pint.Quantity},
                                        'limit': {'type': 'quantity', 'dimensionality': '[length]',
                                                  'coerce': pint.Quantity},
                                        'intercept': {'type': 'quantity', 'required': True, 'dimensionality': '[length]',
                                                      'coerce': pint.Quantity},
                                        'side': {'type': 'string', 'allowed': ['L', 'R']}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }



    def __init__(self, config_file=None, auto_load=True, log_level="WARNING"):
        """
        Create a new config object.

        :param config_file: Config file to be attached to this object.
        :type: string *OR* Path object.
        :param auto_load: Load and validate config file on init
        :type: bool
        :param log_level: Logging level for Configuration processing
        :type: str
        """
        self._config = None
        self._logger = logging.getLogger("CobraBay").getChild("Config")
        self._logger.setLevel(log_level)

        # Initialize the internal config file variable
        self._config_path = config_file
        if auto_load:
            # Load the config file. This does validation as well!
            try:
                valid = self.load_config()
            except BaseException as e:
                raise e
            else:
                if not valid:
                    raise ValueError("Configuration not valid, cannot continue!")

        # If necessary, adjust our own log level.
        new_loglevel = self.get_loglevel('config')
        if new_loglevel != log_level:
            self._logger.setLevel(new_loglevel)
            self._logger.warning("Adjusted config module logging level to '{}'".format(new_loglevel))

    def load_config(self):
        """
        Load and validate config from the specified file.
        :return:
        """
        self._logger.info("Loading file '{}'".format(self._config_path))
        staging_yaml = self._read_yaml(self._config_path)
        try:
            validator_result = self._validator(staging_yaml)
        except KeyError as e:
            raise e
        else:
            if validator_result.valid:
                self._logger.info("Configuration is valid! Saving.")
                self._config = validator_result.result
                return True
            else:
                self._logger.error("Loaded configuration is not valid. Has the following errors:")
                self._logger.error(pformat(validator_result.result))
                return False

    @property
    def config_path(self):
        if self._config_path is None:
            return None
        else:
            return self._config_path

    @config_path.setter
    def config_path(self, the_input):
        # IF a string, convert to a path.
        if isinstance(the_input, str):
            the_input = Path(the_input)
        if not isinstance(the_input, Path):
            # If it's not a Path now, we can't use this.
            raise TypeError("Config path must be either a string or a Path object.")
        # If we haven't trapped yet, assign it.
        self._config_path = the_input

    @staticmethod
    def _read_yaml(file_path):
        """
        Open a YAML file and return its contents.

        :param config_path:
        :return:
        """
        with open(file_path, 'r') as file_handle:
            config_yaml = yaml.safe_load(file_handle)
        return config_yaml

    @staticmethod
    def _write_yaml(self, file_path, contents):
        """
        Write out to a YAML file.
        """
        with open(file_path, 'w') as file_handle:
            yaml.dump(contents, file_handle)

    def validate(self):
        """
        Confirm the currently loaded configuration is valid.

        :return:
        """
        if isinstance(self._config, dict):
            return self._validator(self._config)
        else:
            raise ValueError("Cannot validate before config is loaded!")

    def _validator(self, validation_target):
        """
        Validate the validation target against the CobraBay Schema.

        :param validation_target:
        :return:
        """
        # Create a named tuple for return to prevent type changing. Will return
        CBValidation = namedtuple("CBValidation", ['valid', 'result'])
        # Create the main validator
        mv = CBValidator(self.SCHEMA_MAIN)

        try:
            returnval = mv.validated(validation_target)
        except BaseException as e:
            self._logger.error("Could not validate. '{}'".format(e))
            return CBValidation(False, mv.errors)

        # Trap return failures and kick back false and the errors.
        if returnval is None:
            return CBValidation(False, mv.errors)
        else:

            # Inject the system command handler.
            returnval['triggers']['syscmd'] = {
                'type': 'syscmd',
                'topic': 'cmd',
                'topic_mode': 'suffix'
            }
            # Inject a bay command handler trigger for every define defined bay.
            for bay_id in returnval['bays']:
                returnval['triggers'][bay_id] = {
                    'type': 'baycmd',
                    'topic': 'cmd',
                    'topic_mode': 'suffix',
                    'bay_id': bay_id
                }

            # Because the 'oneof' options in the schema don't normalize, we need to go back in and normalize those.
            # Subvalidate detectors.
            sv = CBValidator()
            for direction in ('longitudinal', 'lateral'):
                for detector_id in returnval['detectors'][direction]:
                    # print("Detector settings before subvalidation.")
                    # pprint.pprint(returnval['detectors'][direction][detector_id]['sensor_settings'])
                    # Select the correct target schema based on the sensor type.
                    if returnval['detectors'][direction][detector_id]['sensor_type'] == 'VL53L1X':
                        target_schema = self.SCHEMA_SENSOR_VL53L1X
                    elif returnval['detectors'][direction][detector_id]['sensor_type'] == 'TFMini':
                        target_schema = self.SCHEMA_SENSOR_TFMINI
                    else:
                        # Trap unknown sensor types. This should never happen!
                        return CBValidation(False, "Incorrect sensor type during detector normalization '{}'".format(
                            detector_id))

                    # Do it.
                    try:
                        validated_ds = sv.validated(
                            returnval['detectors'][direction][detector_id]['sensor_settings'], target_schema)
                    except BaseException as e:
                        self._logger.error("Could not validate. '{}'".format(e))
                        return CBValidation(False, sv.errors)
                    if validated_ds is None:
                        return CBValidation(False, "During subvalidation of detector '{}', received errors '{}".
                                            format(detector_id, sv.errors))
                    else:
                        # Merge the validated/normalized sensor settings into the main config.
                        returnval['detectors'][direction][detector_id]['sensor_settings'] = validated_ds

            return CBValidation(True, returnval)

    # Quick fetchers.
    # These allow fetching subsections of the config.
    @property
    def config(self):
        return self._config

    def log_handlers(self):
        include_items = ['console', 'file', 'file_path', 'log_format']
        return dict(
            filter(
                lambda item: item[0] in include_items, self._config['system']['logging'].items()
            )
        )

    def network(self):
        """ Get network settings from the config."""
        the_return = {
            'unit_system': self._config['system']['unit_system'],
            'system_name': self._config['system']['system_name'],
            'interface': self._config['system']['interface'],
            **self._config['system']['mqtt'],
            'log_level': self._config['system']['logging']['network'],
            'mqtt_log_level': self._config['system']['logging']['mqtt']}
        return the_return

    @property
    def detectors_longitudinal(self):
        """
        All defined longitudinal detectors
        :return: list
        """
        return list(self._config['detectors']['longitudinal'].keys())

    @property
    def detectors_lateral(self):
        """
        All defined lateral detectors
        :return: list
        """
        return list(self._config['detectors']['lateral'].keys())

    @property
    def bays(self):
        """
        All defined bays
        :return: list
        """
        return list(self._config['bays'].keys())

    @property
    def triggers(self):
        """
        All defined triggers
        :return: list
        """
        return list(self._config['triggers'].keys())

    def detector(self, detector_id, detector_type):
        """
        Retrieve configuration for a specific detector

        :param detector_id: ID of the requested detector.
        :type detector_id: str
        :param detector_type: Detector type, either "longitudinal" or "lateral"
        :type detector_type: str
        :return: dict
        """
        return {'detector_id': detector_id,
                **self._config['detectors'][detector_type][detector_id],
                'log_level': self._config['system']['logging']['detectors']}

    def bay(self, bay_id):
        """
        Retrieve configuration for a specific bay.
        :param bay_id: ID of the requested bay
        :return: dict
        """
        return { **self._config['bays'][bay_id], 'log_level': self._config['system']['logging']['bays']}

    def display(self):
        """
        Retrieve configuration for the display
        :return: dict
        """
        return { **self._config['display'],
                 'unit_system': self._config['system']['unit_system'],
                 'log_level': self._config['system']['logging']['display']}

    def trigger(self, trigger_id):
        """
        Retrieve configuration for a specific trigger.
        :param trigger_id:
        :return: list
        """
        ### Can probably do this in Cerberus, but that's being fiddly, so this is a quick hack.
        # Ensure both 'to' and 'from' are set, even if only to None.
        if 'to' not in self._config['triggers'][trigger_id] and 'to_value' not in self._config['triggers'][trigger_id]:
            self._config['triggers'][trigger_id]['to'] = None
        if 'from' not in self._config['triggers'][trigger_id] and 'from_value' not in self._config['triggers'][trigger_id]:
            self._config['triggers'][trigger_id]['from'] = None

        # Convert to _value.
        self._config['triggers'][trigger_id]['to_value'] = self._config['triggers'][trigger_id]['to']
        del self._config['triggers'][trigger_id]['to']
        self._config['triggers'][trigger_id]['from_value'] = self._config['triggers'][trigger_id]['from']
        del self._config['triggers'][trigger_id]['from']

        return {
            **self._config['triggers'][trigger_id],
            'log_level': self._config['system']['logging']['triggers']
        }

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

### Old Things
#
# def _check_path(self, config_file):
#     # Default search paths.
#     search_paths = [
#         Path('/etc/cobrabay/config.yaml'),
#         Path.cwd().joinpath('config.yaml')
#     ]
#     if isinstance(config_file, Path):
#         search_paths.insert(0, Path(config_file))
#
#     for path in search_paths:
#         try:
#             self.config_file = path
#         except:
#             pass
#     if self._config_file is None:
#         raise ValueError("Cannot find valid config file! Attempted: {}".format([str(i) for i in search_paths]))
