"""
Cobra Bay configuration management
Marshmallow style.
"""
import copy
import logging
from marshmallow import ValidationError
import os
import pathlib
import platform
import yaml
from pprint import pformat
from datetime import datetime

from cobrabay.datatypes import CBValidation, ENVOPTIONS_EMPTY
import cobrabay.const
from cobrabay.config.schema import CBSchema

class CBConfigMgr:
    """
    Cobrabay Configuration Manager

    Can handle multiple configurations, load, save and validate them.
    """

    def __init__(self, cbcore, cmd_options=None, parent_logger=None, log_level="WARNING"):
        """
        Initialize.

        :param cbcore: Reference to the Cobrabay Core object.
        :type cbcore: cobrabay.CBCore
        """
        if parent_logger is None:
            # If no parent detector is given this sensor is being used in a testing capacity. Create a null logger.
            self._logger = logging.getLogger("ConfigMgr")
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter(cobrabay.const.LOG_FORMAT))
            console_handler.setLevel(log_level)
            self._logger.addHandler(console_handler)
            self._logger.setLevel(log_level)
        else:
            self._logger = parent_logger.getChild("ConfigMgr")

        self._initial_config = None
        self._active_config = None
        self._cbcore = cbcore
        self._cmd_options = cmd_options
        # Get the options from the environment and save them.
        self._env_options = self._get_envoptions()

        # Set our base directory. This cannot be changed later.
        self._basedir = self._validate_basedir()
        # Set the default configdir as provided. This *could* change later, maybe, but no facility is provided for that
        # now.
        self._configdir = self._validate_configdir(self.cmd_options.configdir)

        self._logger.info("Attempting to load config file: {}".format(self._cmd_options.configfile))
        # Try to get an initial configuration.
        try:
            self._active_config = self._bootstrap()
        except FileNotFoundError as fe:
            self._logger.critical("No such file or directory for initial configuration file '{}'".
                                  format(self._cmd_options.configfile))
            raise fe

        self._logger.info("Initial config. Will attempt to validate...")
        self._logger.info(pformat(self._active_config.config))

        # Try to validate it.
        valid = self._active_config.validate()

    def _bootstrap(self):
        """
        Initial bootstrapping of the system. This will try to use the config file, environment and command line to get
        a valid config.
        """

        return CBConfig(
            'initial',
            configfile=self._get_configfile(),
            cmd_options=self._cmd_options, 
            env_options=self._env_options,
            parent_logger=self._logger,
            log_level=self._logger.level
        )

    @property
    def basedir(self):
        """
        The base directory path for the system. Relative paths are all relative to this.
        This cannot be changed once the system starts.
        """
        return self._basedir

    @property
    def cmd_options(self):
        """
        The command line set at startup.
        """
        return self._cmd_options

    @property
    def env_options(self):
        """
        The environment variables set at startup.
        """
        return self._env_options

    def add_cfgobj(self, cfgobj):
        """
        Add a new configuration object to manage. This is intended to be added during initialization.
        """
        pass

    def _get_configfile(self):
        """
        Get the full path to the configuration file, based on command line and environment options.

        return Path
        """

        if self._cmd_options.configfile is not None:
            configfile = pathlib.Path(self._cmd_options.configfile)
        elif self._env_options.basedir is not None:
            configfile = pathlib.Path(self._env_options.configfile)
        else:
            configfile = 'config.yaml'

        if not configfile.is_absolute():
            configfile = self._configdir / configfile

        return configfile

    @staticmethod
    def _get_envoptions():
        """
        Get the environment variables, if set.
        """
        return cobrabay.datatypes.ENVOPTIONS(
            basedir=None,
            rundir=None,
            configdir=None,
            configfile=None,
            logdir=None,
            logfile=None,
            loglevel=None,
            mqttbroker=os.getenv("CB_MQTTBROKER"),
            mqttport=os.getenv("CB_MQTTPORT"),
            mqttuser=os.getenv("CB_MQTTUSER"),
            mqttpassword=os.getenv("CB_MQTTPASSWORD"),
            unitsystem=os.getenv("CB_UNITSYSTEM")
        )

    def _validate_basedir(self):
        """
        Validate the base directory.
        """

        # Find the base path.
        try:
            basedir = pathlib.Path(self.cmd_options.basedir)
        except TypeError as e:
            self._logger.error(
                "Cannot make a valid path for base directory from option '{}'.".format(self.cmd_options.basedir))
            raise e
        else:
            # Make the base absolute.
            basedir = basedir.absolute()
            if not basedir.is_dir():
                raise TypeError("Base directory '{}' is not a directory.".format(basedir))
            self._logger.info("Base directory: {}".format(basedir))

        return basedir

    def _validate_configdir(self, configdir):
        """
        Validate the configuration directory.
        If the provided directory is *not* absolute, it will try to prefix the system base directory.
        """

        try:
            configdir = pathlib.Path(configdir)
        except TypeError as e:
            print("Cannot make a valid path for config directory from '{}'.".format(configdir))
            raise e
        else:
            if not configdir.is_absolute():
                configdir = self._cmd_options.basedir / configdir
            if not configdir.is_dir():
                raise ValueError("Config directory '{}' not a directory.".format(configdir))
            if configdir != self._cmd_options.basedir:
                self._logger.info("Config directory: {}".format(configdir))

        return configdir

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

        # Load the config from the YAML.
        self._config = self._yaml_read(self.configfile)

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

    @property
    def config(self):
        """
        The Active Config is the combination of the config file, the environment and any config settings from MQTT.
        """
        working_config = self._config

        # Overlay dict.
        overlay = {
            'system': {
                'unit_system': self._get_param('unitsystem'),
                'mqtt': {
                    'broker': self._get_param('mqttbroker'),
                    'port': self._get_param('mqttport'),
                    'username': self._get_param('mqttuser'),
                    'password': self._get_param('mqttpassword')
                },
                'logging':{
                    'default': logging.getLevelName(self._get_param('loglevel'))
                }
            }
        }

        return working_config | overlay

    def base_config(self):
        return self._config

    @config.setter
    def config(self, the_config):
        """
        Update some or all of the config.
        """

    def network(self):
        """ Get network settings from the config."""
        the_return = {
            'unit_system': self.active_config['system']['unit_system'],
            'system_name': self.active_config['system']['system_name'],
            'interface': self.active_config['system']['interface'],
            **self.active_config['system']['mqtt'],
            'log_level': self.get_loglevel(item_id='network'),
            'mqtt_log_level': self.active_config['system']['logging']['mqtt']}
        return the_return

    def get_loglevel(self, item_id, item_type=None):
        """
        Get the log level for a specific item.
        """
        # If a loglevel was set at the command line, that overrides everything else, return it.
        if self._environment.loglevel is not None:
            return self._environment.loglevel
        if item_type == 'sensor':
            try:
                return self.active_config['system']['logging']['sensor'][item_id]
            except KeyError:
                # If no specific level, use the general detectors level.
                return self.active_config['system']['logging']['sensors']
        elif item_type == 'bay':
            try:
                return self.active_config['system']['logging']['bay'][item_id]
            except KeyError:
                # If no specific level, use the general bay level.
                return self.active_config['system']['logging']['bays']
        elif item_type == 'trigger':
            try:
                return self.active_config['system']['logging']['trigger'][item_id]
            except KeyError:
                # If no specific level, use the general detectors level.
                return self.active_config['system']['logging']['triggers']
        else:
            return self.active_config['system']['logging'][item_id]

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


    # Validate!
    def validate(self):
        """
        Validate the config
        """
        try:
            CBSchema().load(self.config)
        except ValidationError as err:
            self._logger.error("Could not validate.")
            self._logger.error(err.messages)
            return False
        return True

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


