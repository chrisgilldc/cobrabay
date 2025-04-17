"""
Cobrabay Command Line executor
"""

import argparse
import pathlib
import sys
import pid.base
import cobrabay
import logging
import os
import pwd
import socket
# from logging.handlers import WatchedFileHandler
# from collections import namedtuple
from pid import PidFile
from cobrabay.datatypes import ENVOPTIONS
# from Queue import Empty
from multiprocessing import Queue  # , Process


def cbcli():
    """
    Main Cobra Bay CLI Invoker
    """
    print("cobrabay Parking System - {}".format(cobrabay.__version__))
    print("User: {}\tHost: {}\tIP: {}".format(pwd.getpwuid(os.getuid()).pw_name, socket.getfqdn(),
                                               socket.gethostbyname(socket.gethostname())))
    # Parse command line options.
    parser = argparse.ArgumentParser(
        description="Cobra Bay Parking System"
    )
    parser.add_argument("-b", "--base", default=".", help="Base directory, for all other paths")
    parser.add_argument("-c", "--config", help="Config file location.")
    parser.add_argument("-cd", "--configdir", help="Directory for config files.")
    parser.add_argument("-r", "--rundir", help="Run directory, for the PID file.")
    parser.add_argument("-ld", "--logdir", help="Directory to write logs to.")
    parser.add_argument("-lf", "--logfile", help="Log file name to write")
    parser.add_argument("-ll", "--loglevel", help="General logging level. More fine-grained control "
                                                  "in config file.")
    parser.add_argument("-mb", "--mqtt-broker", dest="mqttbroker", help="Set the MQTT broker.")
    parser.add_argument("-mp", "--mqtt-port", dest="mqttport", default=1883, help="Set the MQTT Port (default: 1883)")
    parser.add_argument("-mu", "--mqtt-user", dest="mqttuser", help="Set the MQTT User")


    args = parser.parse_args()

    # Validate the environment options.

    try:
        environment = _validate_environment(
            input_base=args.base,
            input_rundir=args.rundir,
            input_configdir=args.configdir,
            input_configfile=args.config,
            input_logdir=args.logdir,
            input_logfile=args.logfile,
            input_loglevel=args.loglevel,
            input_mqttbroker=args.mqttbroker,
            input_mqttport=args.mqttport,
            input_mqttuser=args.mqttuser
        )
    except BaseException as e:
        print(e)
        sys.exit(1)

    # Start the main operating loop.
    try:
        with PidFile('cobrabay', piddir=environment.rundir) as p:
            # Create the Master logger.
            master_logger = logging.getLogger("cobrabay")
            master_logger.setLevel(logging.DEBUG)
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG)
            master_logger.addHandler(console_handler)
            master_logger.info("Main process running as PID {}".format(p.pid))

            # Create a Cobra Bay config object.
            try:
                coreconfig = cobrabay.config.CBCoreConfig(config_file=environment.configfile, environment=environment)
            except BaseException as e:
                # Relying on the config module to log details on *what* the error is.
                print("Configuration had errors. Cannot continue!")
                sys.exit(1)

            # Initialize the system
            master_logger.info("Initializing...")
            # Create the queues.
            # Data flow.
            q_cbsmdata = Queue()
            # Control
            q_cbsmcontrol = Queue()

            # Create the core system core, which will run in the main process.
            cb = cobrabay.CBCore(config_obj=coreconfig, envoptions=environment, q_cbsmdata=q_cbsmdata,
                                 q_cbsmcontrol=q_cbsmcontrol)

            # Start the Sensor Manager process.
            # cbsm_process = Process(target=cobrabay.sensormgr.CBSensorMgr, args=(sensorconfig, q_cbsmdata=q_cbsmdata, q_cbsmcontrol=q_cbsmcontrol))
            # cbsm_process.start()

            # Start.
            master_logger.info("Initialization complete. Operation start.")
            cb.run()
    except pid.base.PidFileAlreadyLockedError:
        print("Cannot start, already running!")


def _validate_environment(input_base,
                          input_rundir,
                          input_configdir,
                          input_configfile,
                          input_logdir,
                          input_logfile,
                          input_loglevel,
                          input_mqttbroker,
                          input_mqttport,
                          input_mqttuser):
    """
    Validate the provided command line arguments and check for environment variables.
    """

    # Set base from environment, if set.
    if os.getenv("CB_BASE"):
        input_base = os.getenv("CB_BASE")
        print("Setting base path from environment CB_BASE: {}".format(input_base))

    # Check the base directory.
    try:
        base = pathlib.Path(input_base)
    except TypeError as e:
        print("Cannot make a valid path for base directory from option '{}'.".format(input_base))
        raise e
    else:
        # Make the base absolute.
        basedir = base.absolute()
        if not basedir.is_dir():
            raise TypeError("Base directory '{}' is not a directory.".format(basedir))
        print("Base directory: {}".format(basedir))

    # Set run from environment, if set.
    if not input_rundir:
        if os.getenv("CB_RUNDIR"):
            rundir = os.getenv("CB_RUNDIR")
            print("Setting run directory path from environment CB_RUNDIR: {}".format(rundir))
        else:
            rundir = "/tmp"
    else:
        rundir = input_rundir

    # Run directory, for the PID file.
    try:
        rundir = pathlib.Path(rundir)
    except TypeError as e:
        print("Cannot make a valid path for run directory from option '{}'.".format(rundir))
        raise e
    else:
        if not rundir.is_absolute():
            rundir = basedir / rundir
        if not rundir.is_dir():
            raise ValueError("Run directory '{}' not a directory. Cannot continue!".format(rundir))
        print("Run directory: {}".format(rundir))

    # Set config dir from environment, if set.
    if not input_configdir:
        if os.getenv("CB_CONFIGDIR"):
            configdir = os.getenv("CB_CONFIGDIR")
            print("Setting config directory from environment CB_CONFIGFILE: {}".format(input_configdir))
        else:
            print("Config directory not provided. Defaulting to current directory.")
            configdir = "."
    else:
        configdir = input_configdir

    # Config directory, to allow versioned configs.
    try:
        configdir = pathlib.Path(configdir)
    except TypeError as e:
        print("Cannot make a valid path for config directory from option '{}'.".format(configdir))
        raise e
    else:
        if not configdir.is_absolute():
            configdir = basedir / configdir
        if not configdir.is_dir():
            raise ValueError("Config directory '{}' not a directory. Cannot continue!".format(configdir))
        if configdir != basedir:
            print("Config directory: {}".format(configdir))

    # If input
    # Set config file from environment, if set.
    if not input_configfile:
        if os.getenv("CB_CONFIGFILE"):
            configfile = os.getenv("CB_CONFIGFILE")
            print("Setting config file from environment CB_CONFIGFILE: {}".format(configfile))
        else:
            print("Config file not provided. Defaulting to 'config.yaml'")
            configfile = "./config.yaml"
    else:
        configfile = input_configfile

    try:
        configfile = pathlib.Path(configfile)
    except TypeError:
        configfile = None
        print("No config file specified on command line. Will search default locations.")
    else:
        # If config isn't absolute, make it relative to the base.
        if not configfile.is_absolute():
            configfile = configdir / configfile
        # if not configfile.exists():
        #     raise ValueError("Config file '{}' does not exist. Cannot continue!".format(configfile))
        # if not configfile.is_file():
        #     raise ValueError("Config file '{}' is not a file. Cannot continue!".format(configfile))
        print("Config file: {}".format(configfile))

    # Set log dir from environment, if set.
    if not input_logdir:
        if os.getenv("CB_LOGDIR"):
            logdir = os.getenv("CB_LOGDIR")
            print("Setting log director from environment CB_LOGDIR: {}".format(logdir))
        else:
           print("Logging directory not provided. Defaulting to current directory.")
           logdir = "."
    else:
        logdir = input_logdir

    # Logging directory.
    try:
        logdir = pathlib.Path(logdir)
    except TypeError as e:
        print("Cannot make a valid path for log directory from option '{}'.".format(logdir))
        raise e
    else:
        if not logdir.is_absolute():
            logdir = basedir / logdir
        if not logdir.is_dir():
            raise ValueError("Log directory '{}' not a directory.".format(logdir))
        if logdir != basedir:
            print("Log directory: {}".format(logdir))

    # Set logfile from environment, if set.
    if not input_logfile:
        if os.getenv("CB_LOGFILE"):
            logfile = os.getenv("CB_LOGFILE")
            print("Setting log file from environment CB_LOGFILE: {}".format(logfile))
        else:
            print("No log file name specified. Defaulting to 'cobrabay.log'")
            logfile = 'cobrabay.log'
    else:
        logfile = input_logfile

    # Log file
    try:
        logfile = pathlib.Path(logfile)
    except TypeError as e:
        print("Cannot make a valid path for log file from option '{}'.".format(logfile))
        raise e
    else:
        # If config isn't absolute, make it relative to the base.
        if not logfile.is_absolute():
            logfile = logdir / logfile
        # Don't need to check if the file exists, will create on start.
        print("Log file: {}".format(logfile))

    if not input_loglevel:
        if os.getenv("CB_LOGLEVEL"):
            loglevel = os.getenv("CB_LOGLEVEL")
            print("Setting system log level to '{}'".format(loglevel))
        else:
            print("No system log level provided. Defaulting to 'WARNING'")
            loglevel = "WARNING"
    else:
        loglevel = input_loglevel

    if loglevel.upper() in 'DEBUG,INFO,WARNING,ERROR,CRITICAL':
        loglevel = loglevel.upper()
    else:
        raise ValueError('{} is not a valid log level. Must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL'.format(input_loglevel))

    # MQTT Port
    # Set MQTT Port  from environment, if set.
    if input_mqttport:
        mqttport = input_mqttport
    elif os.getenv("CB_MQTTPORT"):
        mqttport = os.getenv("CB_MQTTPORT")
        print("Setting MQTT Port from environment CB_MQTTPORT: {}".format(input_mqttport))
    else:
        mqttport = None

    # MQTT Broker
    # Set MQTT broker  from environment, if set.
    if input_mqttbroker:
        mqttbroker = input_mqttbroker
    elif os.getenv("CB_MQTTBROKER"):
        mqttbroker = os.getenv("CB_MQTTBROKER")
        print("Setting MQTT Broker from environment CB_MQTTBROKER: {}".format(mqttbroker))
    else:
        mqttbroker = None

    # MQTT User
    # Set MQTT Port  from environment, if set.
    if input_mqttuser:
        mqttuser = input_mqttuser
        print("Using MQTT user: {}".format(mqttuser))
    elif os.getenv("CB_MQTTUSER"):
        mqttuser = os.getenv("CB_MQTTUSER")
        print("Setting MQTT USER from environment CB_MQTTUSER: {}".format(mqttuser))
    else:
        mqttuser = None

    # Set MQTT Password from environment, if set.
    if os.getenv("CB_MQTTPASSWORD"):
        mqttpassword = os.getenv("CB_MQTTPASSWORD")
        print("Setting MQTT Password from environment CB_MQTTPASSWORD")
    else:
        mqttpassword = None

    valid_environment = ENVOPTIONS(
        base=basedir,
        rundir=rundir,
        configdir=configdir,
        configfile=configfile,
        logdir=logdir,
        logfile=logfile,
        loglevel=loglevel,
        mqttbroker=mqttbroker,
        mqttport=mqttport,
        mqttuser=mqttuser,
        mqttpassword=mqttpassword
    )

    return valid_environment

if __name__ == "__main__":
    sys.exit(cbcli())