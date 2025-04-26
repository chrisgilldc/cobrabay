"""
Cobra Bay configuration management
Marshmallow style.
"""
import copy
import logging
from marshmallow import ValidationError
import pathlib
import platform
import yaml
from pprint import pformat
from datetime import datetime

from cobrabay.datatypes import CBValidation, ENVOPTIONS_EMPTY
import cobrabay.const
from cobrabay.config.schema import CBSchema

class CBConfig:
    """
    A configuration instance.
    """
    def __init__(self, name, configfile, cmd_options=ENVOPTIONS_EMPTY, env_options=ENVOPTIONS_EMPTY, parent_logger=None, log_level="WARNING"):
        """
        Create a new Cobrabay Config object

        :param name: Name of this config object.
        :type name: str
        :param configfile: Config file to read from.
        :type configfile: str or Path
        :param cmd_options: The options coming from the command line in a valid ENVOPTIONS tuple.
        :type cmd_options: cobrabay.datatypes.ENVOPTIONS
        :param env_options: The options coming from the environment in a valid ENVOPTIONS tuple.
        :type env_options: cobrabay.datatypes.ENVOPTIONS
        :param parent_logger: A parent logger to be a child of.
        :type parent_logger: logger or none
        :param log_level: Logging level for configuration
        :type log_level: str
        """

        # Save our name.
        self._name = name

        # Create a logger for ourselves.
        if parent_logger is None:
            # If no parent detector is given this sensor is being used in a testing capacity. Create a null logger.
            self._logger = logging.getLogger(self._name)
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter(cobrabay.const.LOG_FORMAT))
            console_handler.setLevel(log_level)
            self._logger.addHandler(console_handler)
            self._logger.setLevel(log_level)
        else:
            self._logger = parent_logger.getChild(self._name)

        # Save input parameters.
        self.configfile = configfile
        self._cmd_options = cmd_options
        self._env_options = env_options

        # Load the config.
        self.load_config()

    @property
    def configfile(self):
        """
        Defined config file for this configuration.
        """
        return self._configfile

    @configfile.setter
    def configfile(self, target_file):
        """
        Set the configuration file.
        :param target_file: Config file to use
        :type target_file: str, Path or None
        """

        if target_file is None:
            self._configfile = None
        elif isinstance(target_file, pathlib.Path):
            self._configfile = target_file
        elif isinstance(target_file, str):
            self._configfile = pathlib.Path(target_file)

    def load_config(self):
        """
        Load the config from the defined file and merge it with the environment and command line options, and validate.
        """
        # Load the config from the YAML.
        self._loaded_config = self._yaml_read(self.configfile)
        self._logger.debug("YAML dump:")
        self._logger.debug(pformat(self._loaded_config))

        # Merge the configs.
        # merged_config = self._merge_config_environment(copy.deepcopy(self._loaded_config))
        # Put the config through the deserializer to normalize and validate.
        try:
            self._config = CBSchema().load(self._loaded_config)
        except ValidationError as err:
            self._logger.error("Could not validate.")
            self._logger.error(err.messages)
            return False
        return True

    @property
    def config(self):
        """
        The Active Config is the combination of the config file, the environment and any config settings from MQTT.
        """
        return self._config

    # @config.setter
    # def config(self, the_config):
    #     """
    #     Update some or all of the config.
    #     """
    #     pass

    def get_enumeration(self, elements):
        """
        Get a list version of the available elements

        :param elements: The item to get the elements of. May be bays, sensors or subscriptions
        :type elements: str

        returns list
        """
        if 'elements' not in ('bays', 'sensors', 'subscriptions'):
            raise ValueError("Cannot get an enumeration for '{}'. Must be one of 'bays','sensors' or 'subscriptions'".format(elements))

        if self.config is None:
            return []

        return list(self.config[elements].keys())

    # def network(self):
    #     """ Get network settings from the config."""
    #     the_return = {
    #         'unit_system': self.active_config['system']['unit_system'],
    #         'system_name': self.active_config['system']['system_name'],
    #         'interface': self.active_config['system']['interface'],
    #         **self.active_config['system']['mqtt'],
    #         'log_level': self.get_loglevel(item_id='network'),
    #         'mqtt_log_level': self.active_config['system']['logging']['mqtt']}
    #     return the_return

    def get_loglevel(self, item_id, item_type=None):
        """
        Get the log level for a specific item.
        """
        try:
            return self.config['system']['logging'][item_id]
        except KeyError:
            return self.config['system']['logging']['default']

    def _get_param(self, parameter):
        """
        Get a configurable parameter from the appropriate source, based on priority.
        """

        if self._priority_map[parameter]['pri'] is not None:
            return self._priority_map[parameter]['pri']
        elif self._priority_map[parameter]['sec'] is not None:
            return self._priority_map[parameter]['sec']
        elif self._priority_map[parameter]['ter'] is not None:
            return self._priority_map[parameter]['ter']
        else:
            return self._priority_map[parameter]['def']

    @property
    def _priority_map(self):
        """
        The priority map of the config. Sets replacement priorities based on command line, environment and config file.

        return dict
        """
        return_dict = {
            'basedir': {
                'pri': self._cmd_options.basedir,
                'sec': self._env_options.basedir,
                'ter': None,
                'def': pathlib.Path.cwd()
            },
            'rundir': {
                'pri': self._cmd_options.rundir,
                'sec': self._env_options.rundir,
                'ter': None,
                'def': pathlib.Path('/tmp')
            },
            'configdir': {
                'pri': self._cmd_options.configdir,
                'sec': self._env_options.configdir,
                'ter': None,
                'def': pathlib.Path.cwd() / 'config'
            },
            'configfile': {
                'pri': self._cmd_options.configfile,
                'sec': self._env_options.configfile,
                'ter': None,
                'def': pathlib.Path('config.yaml')
            },
            'logdir': {
                'pri': self._cmd_options.logdir,
                'sec': self._env_options.logdir,
                'ter': None,
                'def': pathlib.Path.cwd() / 'logs'
            },
            'logfile': {
                'pri': self._cmd_options.basedir,
                'sec': self._env_options.basedir,
                'ter': None,
                'def': 'cobrabay.log'
            },
            'loglevel': {
                'pri': self._cmd_options.loglevel,
                'sec': self._env_options.loglevel,
                'ter': None,
                'def': logging.WARNING
            },
            'mqttbroker': {
                'pri': self._cmd_options.mqttbroker,
                'sec': self._env_options.mqttbroker,
                'ter': None,
                'def': None
            },
            'mqttport': {
                'pri': self._cmd_options.mqttport,
                'sec': self._env_options.mqttport,
                'ter': None,
                'def': 1883
            },
            'mqttuser': {
                'pri': self._cmd_options.mqttuser,
                'sec': self._env_options.mqttuser,
                'ter': None,
                'def': None
            },
            'mqttpassword': {
                'pri': self._env_options.mqttpassword,
                'sec': None,
                'ter': None,
                'def': None
            },
            'unitsystem': {
                'pri': self._cmd_options.unitsystem,
                'sec': self._env_options.unitsystem,
                'ter': None,
                'def': 'metric'
            },
        }

        # Try to put in values from the config file, if present.
        # Log Level
        try:
            return_dict['loglevel']['ter'] = self._config['system']['logging']['default_level']
        except KeyError:
            pass

        # MQTT Broker
        try:
            return_dict['mqttbroker']['ter'] = self._config['system']['mqtt']['broker']
        except KeyError:
            pass

        # MQTT Port
        try:
            return_dict['mqttport']['ter'] = self._config['system']['mqtt']['port']
        except KeyError:
            pass

        # MQTT User
        try:
            return_dict['mqttuser']['ter'] = self._config['system']['mqtt']['username']
        except KeyError:
            pass

        # MQTT Password
        try:
            return_dict['mqttpassword']['ter'] = self._config['system']['mqtt']['password']
        except KeyError:
            pass

        # Unit System
        try:
            return_dict['unitsystem']['ter'] = self._config['system']['unit_system']
        except KeyError:
            pass

        return return_dict

    def _merge_config_environment(self, input_config):
        """
        Merge the environment with the config.

        :param input_config: Config to merge.
        :type input_config: dict

        return dict
        """
        # Update the unit system.
        input_config['system']['unit_system'] = self._get_param('unitsystem')
        # Update the default loglevel.
        input_config['system']['logging']['default'] = logging.getLevelName(self._get_param('loglevel'))
        # Update the MQTT settings.
        input_config['system']['mqtt']['broker'] = self._get_param('mqttbroker')
        input_config['system']['mqtt']['port'] = self._get_param('mqttport')
        input_config['system']['mqtt']['username'] = self._get_param('mqttuser')
        input_config['system']['mqtt']['password'] = self._get_param('mqttpassword')

        return input_config

    # YAML utility methods.
    def _yaml_read(self, file_path):
        """
        Open a YAML file and return its contents.

        :param file_path:
        :return:
        """
        try:
            file_handle = open(file_path)
        except TypeError as oe:
            self._logger.critical("Cannot open config file '{}'! Received error '{}'.".
                                  format(file_path, oe))
            raise oe
        else:
            config_yaml = yaml.safe_load(file_handle)
        return config_yaml

    # def _yaml_write(self, config_dict, target_file=None):
    #     """
    #     Write out a yaml version of the config file.
    #     """
    #     return yaml.dump(config_dict)


