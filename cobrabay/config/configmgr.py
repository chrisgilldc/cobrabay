"""
Cobrabay Configuration Manager

Instantiate one of these to handled swapping between configurations.
"""

import logging
import os
import pathlib
import cobrabay


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
        try:
            self._basedir = self._validate_basedir(self._get_envoptions().basedir)
        except TypeError:
            try:
                self._basedir = self._validate_basedir(self._cmd_options.basedir)
            except TypeError:
                self._logger.info("No base directory in environment or command line. Assuming current working directory.")
                try:
                    self._basedir = self._validate_basedir(pathlib.Path.cwd())
                except TypeError as te:
                    self._logger.critical("Could not set base directory!")
                    raise te
        self._logger.info("Base directory: {}".format(self.basedir))


        # Set the default configdir as provided. This *could* change later, maybe, but no facility is provided for that
        # now.
        try:
            self._configdir = self._validate_configdir(self._get_envoptions().configdir)
        except TypeError:
            try:
                self._configdir = self._validate_configdir(self._cmd_options.configdir)
            except TypeError:
                self._logger.info("No config directory in environment or command line. Assuming 'base/config'.")
                try:
                    self._validate_basedir(self.basedir / 'config')
                except TypeError as te:
                    self._logger.critical("Could not set config directory!")
                    raise te

        self._logger.info("Attempting to load config file: {}".format(self._cmd_options.configfile))
        # Try to get an initial configuration.
        try:
            self._active_config = self._bootstrap()
        except FileNotFoundError as fe:
            self._logger.critical("No such file or directory for initial configuration file '{}'".
                                  format(self._cmd_options.configfile))
            raise fe

        # Try to validate it.
        # if not self._active_config.validate():
        #     raise ValueError("Cannot validate initial configuration!")

    def _bootstrap(self):
        """
        Initial bootstrapping of the system. This will try to use the config file, environment and command line to get
        a valid config.
        """

        return cobrabay.config.CBConfig(
            'initial',
            configfile=self._get_configfile(),
            cmd_options=self._cmd_options,
            env_options=self._env_options,
            parent_logger=self._logger,
            log_level=self._logger.level
        )

    @property
    def active_config(self):
        """
        The currently loaded configuration
        """
        return self._active_config

    @property
    def basedir(self):
        """
        The base directory path for the system. Relative paths are all relative to this.
        This cannot be changed once the system starts.
        """
        return self._basedir

    @property
    def system_name(self):
        """
        Convenience property to get the system_name as defined by the current active configuration.
        """
        return self._active_config.config['system']['system_name']

    @property
    def unit_system(self):
        """
        Convenience property to get the unit_system as defined by the current active configuration.
        """
        return self._active_config.config['system']['unit_system']


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
            basedir=os.getenv("CB_BASEDIR"),
            rundir=None,
            configdir=os.getenv("CB_CONFIGDIR"),
            configfile=None,
            logdir=os.getenv("CB_LOGDIR"),
            logfile=None,
            loglevel=os.getenv("CB_LOGLEVEL"),
            mqttbroker=os.getenv("CB_MQTTBROKER"),
            mqttport=os.getenv("CB_MQTTPORT"),
            mqttuser=os.getenv("CB_MQTTUSER"),
            mqttpassword=os.getenv("CB_MQTTPASSWORD"),
            unitsystem=os.getenv("CB_UNITSYSTEM")
        )

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