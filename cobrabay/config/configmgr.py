"""
Cobrabay Configuration Manager

Instantiate one of these to handled swapping between configurations.
"""

import logging
import os
import pathlib
from marshmallow import ValidationError
from cobrabay.config import CBConfig
import cobrabay.const
from cobrabay.datatypes import ENVOPTIONS, ENVOPTIONS_EMPTY

class CBConfigMgr:
    """
    Cobrabay Configuration Manager

    Can handle multiple configurations, load, save and validate them.
    """

    def __init__(self, cbcore, cmd_options=ENVOPTIONS_EMPTY, parent_logger=None, log_level="WARNING"):
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
        self._active_config_name = None
        self._configs = {}
        self._cbcore = cbcore
        self._cmd_options = cmd_options

        # CMD and ENV debugging
        self._logger.debug("Received command line options: {}".format(cmd_options))
        self._logger.debug("Have environment: {}".format(self._get_envoptions()))

        # Set our base directory. This cannot be changed later.
        self._basedir = self._find_basedir()

        # Set the config directory.
        self._configdir = self._find_configdir()

        # Try to get an initial configuration.
        # try:
        #     self._active_config = self._bootstrap()
        # except FileNotFoundError as fe:
        #     self._logger.critical("No such file or directory for initial configuration file '{}'".
        #                           format(self._cmd_options.configfile))
        #     raise fe
        # except ValidationError as ve:
        #     self._logger.critical("Initial configuration file does not validate! Cannot continue.")
        #     self._logger.critical("Error encountered '{}'".format(ve))

        # Try to validate it.
        # if not self._active_config.validate():
        #     raise ValueError("Cannot validate initial configuration!")

    def load_config(self, config_file=None, config_name=None):
        """
        Load and validate a config to make it available.
        """
        if config_file is None:
            target_file = self._get_configfile()
        else:
            target_file = config_file

        try:
            config_obj = CBConfig(
                config_name,
                configfile=target_file,
                cmd_options=self._cmd_options,
                env_options=self._get_envoptions(),
                parent_logger=self._logger
                # log_level=logging.getLevelName(self._logger.level)
            )
        except ValidationError as ve:
            self._logger.error("File in '{}' is not valid.".format(config_file))
            self._logger.error(ve)
            return False
        else:
            self._configs[config_name] = {
                'name': config_name,
                'path': config_file,
                'obj': config_obj
            }
            return True

    def activate_config(self, config_name):
        """
        Activate a loaded config.
        """
        if not config_name in self._configs:
            raise ValueError("'{}' is not a loaded configuration!".format(config_name))
        self._active_config_name = config_name

    @property
    def active_config(self):
        """
        The currently loaded configuration
        """
        if self._active_config_name is None:
            raise ValueError("Cannot return active config as active config has not yet been set.")
        return self._configs[self._active_config_name]['obj']

    @property
    def active_config_name(self):
        """
        Return the name of the currently active configuration.
        """
        return self._active_config_name

    def configs(self):
        """List available configurations"""
        return self._configs.keys()

    # def _bootstrap(self):
    #     """
    #     Initial bootstrapping of the system. This will try to use the config file, environment and command line to get
    #     a valid config.
    #     """
    #     self._logger.debug("Attempting to instantiate initial config.")
    #     return CBConfig(
    #         'initial',
    #         configfile=self._get_configfile(),
    #         cmd_options=self._cmd_options,
    #         env_options=self._get_envoptions(),
    #         parent_logger=self._logger,
    #         log_level=logging.getLevelName(self._logger.level)
    #     )

    @property
    def basedir(self):
        """
        The base directory path for the system. Relative paths are all relative to this.
        This cannot be changed once the system starts.
        """
        return self._basedir

    @property
    def configdir(self):
        """
        The directory for configuration files
        """
        return self._configdir

    @property
    def system_name(self):
        """
        Convenience property to get the system_name as defined by the current active configuration.
        """
        return self.active_config.config['system']['system_name']

    @property
    def unit_system(self):
        """
        Convenience property to get the unit_system as defined by the current active configuration.
        """
        return self.active_config.config['system']['unit_system']

    @property
    def cmd_options(self):
        """
        The command line set at startup.
        """
        return self._cmd_options

    # @property
    # def env_options(self):
    #     """
    #     The environment variables set at startup.
    #     """
    #     return self._env_options

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
            self._logger.info("Using config file from command line '{}'".format(configfile))
        elif self._get_envoptions().configfile is not None:
            configfile = pathlib.Path(self._get_envoptions().configfile)
            self._logger.info("Using config file from environment line '{}'".format(configfile))
        else:
            configfile = pathlib.Path('config.yaml')
            self._logger.info("Config file not specified, defaulting to 'config.yaml'")

        if not configfile.is_absolute():
            self._logger.info("Config file is not an absolute path. Assuming it's in the config directory.")
            configfile = self._configdir / configfile

        return configfile

    @staticmethod
    def _get_envoptions():
        """
        Get the environment variables, if set.
        """
        return cobrabay.datatypes.ENVOPTIONS(
            basedir=os.getenv("CB_BASEDIR"),
            rundir=os.getenv("CB_RUNDIR"),
            configdir=os.getenv("CB_CONFIGDIR"),
            configfile=os.getenv("CB_CONFIGFILE"),
            logdir=os.getenv("CB_LOGDIR"),
            logfile=None,
            loglevel=os.getenv("CB_LOGLEVEL"),
            mqttbroker=os.getenv("CB_MQTTBROKER"),
            mqttport=os.getenv("CB_MQTTPORT"),
            mqttuser=os.getenv("CB_MQTTUSER"),
            mqttpassword=os.getenv("CB_MQTTPASSWORD"),
            unitsystem=os.getenv("CB_UNITSYSTEM")
        )

    def _find_basedir(self):
        """
        Find a valid basedir to use from command line, environment, or cwd.
        """
        if self._cmd_options.basedir is not None:
            try:
                basedir = self._validate_basedir(self._cmd_options.basedir)
            except TypeError:
                self._logger.warning("Base directory set in command line but not valid. Setting is '{}'".
                                     format(self._cmd_options.basedir))
            else:
                self._logger.info("Set base directory to '{}' from command line.".format(basedir))
                return basedir

        if self._get_envoptions().basedir is not None:
            try:
                basedir = self._validate_basedir(self._get_envoptions().basedir)
            except TypeError:
                self._logger.warning("Environment variable for base directory set but not valid. Setting is '{}'".
                                     format(self._get_envoptions().basedir))
            else:
                self._logger.info("Set base directory to '{}' from environment.".format(basedir))
                return basedir

        # No base directory from environment or command line, so default it to CWD.
        try:
            basedir = self._validate_basedir(pathlib.Path.cwd())
        except TypeError as te:
            self._logger.critical("Could not set base directory!")
            raise te
        self._logger.info("Set base directory to '{}' as default".format(basedir))
        return basedir

    def _find_configdir(self):
        """
        Find a valid configdir to use from command line, environment, or cwd.
        """
        if self._cmd_options.configdir is not None:
            try:
                configdir = self._validate_configdir(self._cmd_options.configdir)
            except TypeError:
                self._logger.warning("Config directory set in command line but not valid. Setting is '{}'".
                                     format(self._cmd_options.configdir))
            else:
                self._logger.info("Config dir set to '{}' from command line.".format(configdir))
                return configdir

        if self._get_envoptions().configdir is not None:
            try:
                configdir = self._validate_configdir(self._get_envoptions().configdir)
            except TypeError:
                self._logger.warning("Environment variable for config directory set but not valid. Setting is '{}'".
                                     format(self._get_envoptions().configdir))
            else:
                self._logger.info("Config dir set to '{}' from environment.".format(configdir))
                return configdir

        try:
            configdir = self._validate_configdir(pathlib.Path.cwd() / 'config')
        except ValueError:
            self._logger.warning("Separate config directory does not exist. Defaulting config directory to base directory")
            return self.basedir
        else:
            self._logger.info("Config dir defaulted to \'{}\'".format(configdir))
            return configdir



    def _validate_basedir(self, basedir):
        """
        Validate the base directory.
        """

        # Find the base path.
        try:
            basedir = pathlib.Path(basedir)
        except TypeError as e:
            self._logger.error(
                "Cannot make a valid path for base directory from option '{}'.".format(self._cmd_options.basedir))
            raise e
        else:
            # Make the base absolute.
            basedir = basedir.absolute()
            if not basedir.is_dir():
                raise TypeError("Base directory '{}' is not a directory.".format(basedir))
        return basedir

    def _validate_configdir(self, configdir):
        """
        Validate the configuration directory.
        If the provided directory is *not* absolute, it will try to prefix the system base directory.
        """

        try:
            configdir = pathlib.Path(configdir)
        except TypeError as e:
            self._logger.error("Cannot make a valid path for config directory from '{}'.".format(configdir))
            raise e
        else:
            if not configdir.is_absolute():
                configdir = self.basedir / configdir
            if not configdir.is_dir():
                raise ValueError("Config directory '{}' not a directory.".format(configdir))
        return configdir