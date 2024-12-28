import logging
import yaml
from pathlib import Path
import cerberus
from pprint import pformat
from datetime import datetime

import CobraBay.config.schemas
from CobraBay.config import CBValidator
from CobraBay.datatypes import CBValidation, ENVOPTIONS_EMPTY


class CBConfig:
    """
    Configuration management for CobraBay.
    """

    def __init__(self, config_file=None, schema=None, auto_load=False, log_level="WARNING",
                 environment=ENVOPTIONS_EMPTY):
        """
        Create a new config object.

        :param config_file: Config file to be attached to this object.
        :type: string *OR* Path object.
        :param schema: Schema to use for validation
        :type: schema object
        :param auto_load: Load and validate config file on init
        :type: bool
        :param log_level: Logging level for Configuration processing
        :type: str
        :param environment: Environment options from upstream (ie: command line invoker). Defaults to all None.
        :type: ENVOPTIONS named tuple.
        """
        self._config = None
        if schema is None:
            raise ValueError("Schema must be set!")
        else:
            self._schema = schema
        self._environment = environment
        self._logger = logging.getLogger("CobraBay").getChild("Config")
        if environment.loglevel is not None:
            self._logger.setLevel(environment.loglevel)
        else:
            self._logger.setLevel(log_level)

        # Initialize the internal config file variable
        self._config_path = config_file
        if auto_load:
            # Load and validate the config file.
            try:
                valid = self.load_config()
            except BaseException as e:
                raise e
            else:
                if not valid:
                    raise ValueError("Configuration not valid, cannot continue!")

    def load_config(self):
        """
        Load and validate config from the specified file.
        :return:
        """
        self._logger.info("Loading file '{}'".format(self._config_path))

        # Pulls in the YAML
        staging_yaml = self._read_yaml(self._config_path)

        self._logger.debug("Loaded contents: {}".format(pformat(staging_yaml)))

        # Run the validator on the config. This will raise an exception if the validator cannot run.
        try:
            validator_result = self._validator(staging_yaml)
        except BaseException as e:
            self._logger.error("Config processor '{}' could not validate. Received error '{}'".format(self.__class__, e))
            raise e
        else:
            # Possible for the config to be validate*able*, but not validate.
            if validator_result.valid:
                self._logger.info("Configuration is valid! Saving.")
                self._config = validator_result.result
                return True
            else:
                self._logger.error("Loaded configuration is not valid. Has the following errors:")
                self._logger.error(pformat(validator_result.result))
                return False

    def save_config(self):
        """

        :return:
        """
        save_path = self._config_path.stem + datetime.now().strftime("%Y%M%D%h%m%s") + ".yaml"
        if save_path.exists():
            self._logger.error("Will not save file, already exists! Target path was: {}".format(save_path))
            return
        self._logger.warning("Saving current config to: {}".format(save_path))

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

    def _adjust_loglevel(self):
        """
        Adjust the logging level for the config object.

        :return:
        """
        # The 'passed_loglevel' is a flag that comes in from higher up as an override to prevent stomping override
        # loglevels set by the command line or environment. We never want to auto-override those!
        if self._environment.loglevel is not None:
            return False
        else:
            if self._config is None:
                # Config hasn't been initialized yet, nothing to do.
                return False
            else:
                if self._logger.level != self._config['system']['logging']['config']:
                    self._logger.warning("Adjusting config module logging to that specified by config file, '{}'".
                                         format(self._config['system']['logging']['config']))
                    self._logger.setLevel(self._config['system']['logging']['config'])
                    return True
                else:
                    self._logger.info("Config module already at '{}', nothing to adjust.".format(self._logger.level))
                    return False

    def get_loglevel(self, item_id, item_type=None):
        # If a loglevel was set at the command line, that overrides everything else, return it.
        if self._environment.loglevel is not None:
            return self._environment.loglevel
        if item_type == 'sensor':
            try:
                return self._config['system']['logging']['sensor'][item_id]
            except KeyError:
                # If no specific level, use the general detectors level.
                return self._config['system']['logging']['sensors']
        elif item_type == 'bay':
            try:
                return self._config['system']['logging']['bay'][item_id]
            except KeyError:
                # If no specific level, use the general bay level.
                return self._config['system']['logging']['bays']
        elif item_type == 'trigger':
            try:
                return self._config['system']['logging']['trigger'][item_id]
            except KeyError:
                # If no specific level, use the general detectors level.
                return self._config['system']['logging']['triggers']
        else:
            return self._config['system']['logging'][item_id]

    def _read_yaml(self, file_path):
        """
        Open a YAML file and return its contents.

        :param file_path:
        :return:
        """
        try:
            file_handle = open(file_path, 'r')
        except TypeError as oe:
            self._logger.critical("Cannot open config file '{}'! Received error '{}'.".
                                  format(file_path, oe))
            raise oe
        else:
            config_yaml = yaml.safe_load(file_handle)
        return config_yaml

    @staticmethod
    def _write_yaml(file_path, contents):
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

        # Create the main validator
        # self._logger.debug("Creating validator with schema: {}".format(pformat(self._schema)))
        mv = CBValidator(self._schema)

        try:
            returnval = mv.validated(validation_target)
        except cerberus.validator.DocumentError as e:
            raise e

        # Trap return failures and kick back false and the errors.
        if returnval is None:
            return CBValidation(False, mv.errors)
        else:
            self._logger.debug("Base validated config:")
            self._logger.debug(pformat(returnval))

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
            # sv = CBValidator()
            # for sensor_name in returnval['sensors']:
            #     # Select the correct target schema based on the sensor type.
            #     if returnval['sensors'][sensor_name]['hw_type'] == 'VL53L1X':
            #         target_schema = CobraBay.config.schemas.SCHEMA_SENSOR_VL53L1X
            #     elif returnval['sensors'][sensor_name]['hw_type'] == 'TFMini':
            #         target_schema = CobraBay.config.schemas.SCHEMA_SENSOR_TFMINI
            #     else:
            #         # Trap unknown sensor types. This should never happen!
            #         return CBValidation(False, "Incorrect sensor type during detector normalization '{}'".format(
            #             sensor_name))
            #
            #     # Do it.
            #     try:
            #         validated_ds = sv.validated(
            #             returnval['sensors'][sensor_name], target_schema)
            #     except BaseException as e:
            #         self._logger.error("Could not validate. '{}'".format(e))
            #         return CBValidation(False, sv.errors)
            #     if validated_ds is None:
            #         return CBValidation(False, "During subvalidation of detector '{}', received errors '{}".
            #                             format(sensor_name, sv.errors))
            #     else:
            #         # Merge the validated/normalized sensor settings into the main config.
            #         returnval['sensors'][sensor_name]['hw_settings'] = validated_ds

            return CBValidation(True, returnval)

    # @property
    # def detectors_longitudinal(self):
    #     """
    #     All defined longitudinal detectors
    #     :return: list
    #     """
    #     return list(self._config['detectors']['longitudinal'].keys())
    #
    # @property
    # def detectors_lateral(self):
    #     """
    #     All defined lateral detectors
    #     :return: list
    #     """
    #     return list(self._config['detectors']['lateral'].keys())
    #
    # def detector(self, detector_id, detector_type):
    #     """
    #     Retrieve configuration for a specific detector
    #
    #     :param detector_id: ID of the requested detector.
    #     :type detector_id: str
    #     :param detector_type: Detector type, either "longitudinal" or "lateral"
    #     :type detector_type: str
    #     :return: dict
    #     """
    #     return {'detector_id': detector_id,
    #             **self._config['detectors'][detector_type][detector_id],
    #             'log_level': self.get_loglevel(item_id=detector_id, item_type='detector')
    #             }

class CBCoreConfig(CBConfig):
    def __init__(self, config_file=None, auto_load=True, log_level="WARNING", environment=ENVOPTIONS_EMPTY):
        # Call the super init with the schema set.
        super().__init__(config_file, CobraBay.config.schemas.CB_CORE, auto_load, log_level, environment)

    # Enumeration methods.
    @property
    def bays(self):
        """
        All defined bays
        :return: list
        """
        return list(self._config['bays'].keys())

    @property
    def sensors(self):
        """
        All defined sensors
        :return: list
        """
        return list(self._config['sensors'].keys())

    @property
    def triggers(self):
        """
        All defined triggers
        :return: list
        """
        return list(self._config['triggers'].keys())

    # Retrievers
    @property
    def config(self):
        return self._config

    def bay(self, bay_id):
        """
        Retrieve configuration for a specific bay.
        :param bay_id: ID of the requested bay
        :return: dict
        """
        return {**self._config['bays'][bay_id],
                'log_level': self.get_loglevel(item_id=bay_id, item_type='bay')
                }

    def display(self):
        """
        Retrieve configuration for the display
        :return: dict
        """
        return {**self._config['display'],
                'unit_system': self._config['system']['unit_system'],
                'log_level': self.get_loglevel(item_id='display')}

    def i2c_config(self):
        """
        Retrieve configuration for I2C bus
        :return: dict
        """
        return self._config['system']['i2c']

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
            'log_level': self.get_loglevel(item_id='network'),
            'mqtt_log_level': self._config['system']['logging']['mqtt']}
        return the_return

    def sensors_config(self):
        """
        Retrieve all sensors.

        :return:
        """
        return self._config['sensors']

    def sensor(self, sensor_name):
        """
        Retrieve configuration for a specific detector

        :param sensor_name: ID of the requested detector.
        :type sensor_name: str
        :return: dict
        """
        return {'name': sensor_name,
                **self._config['sensors'][sensor_name],
                'log_level': self.get_loglevel(item_id=sensor_name, item_type='sensor')
                }

    def trigger(self, trigger_id):
        """
        Retrieve configuration for a specific trigger.
        :param trigger_id:
        :return: list
        """
        # Can probably do this in Cerberus, but that's being fiddly, so this is a quick hack.
        # Ensure both 'to' and 'from' are set, even if only to None.
        if 'to' not in self._config['triggers'][trigger_id] and 'to_value' not in self._config['triggers'][trigger_id]:
            self._config['triggers'][trigger_id]['to'] = None
        if 'from' not in self._config['triggers'][trigger_id] and 'from_value' not in self._config['triggers'][
            trigger_id]:
            self._config['triggers'][trigger_id]['from'] = None

        # Convert to _value.
        self._config['triggers'][trigger_id]['to_value'] = self._config['triggers'][trigger_id]['to']
        del self._config['triggers'][trigger_id]['to']
        self._config['triggers'][trigger_id]['from_value'] = self._config['triggers'][trigger_id]['from']
        del self._config['triggers'][trigger_id]['from']

        return {
            **self._config['triggers'][trigger_id],
            'log_level': self.get_loglevel(item_id=trigger_id, item_type='trigger')
        }
