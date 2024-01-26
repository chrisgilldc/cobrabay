####
# Cobra Bay - Main Executor
####

import argparse
import pathlib
import sys
import pid.base
import CobraBay
import logging
import pwd
import os
from logging.handlers import WatchedFileHandler
# from collections import namedtuple
from pid import PidFile
from CobraBay.datatypes import ENVOPTIONS

def main():
    print("CobraBay Parking System - {}".format(CobraBay.__version__))
    print("Running as '{}'".format(pwd.getpwuid(os.getuid()).pw_name))
    # Parse command line options.
    parser = argparse.ArgumentParser(
        description="CobraBay Parking System"
    )
    parser.add_argument("-b", "--base", default=".", help="Base directory, for all other paths")
    parser.add_argument("-c", "--config", default="./config.yaml", help="Config file location.")
    parser.add_argument("-cd", "--configdir", default=".", help="Directory for config files.")
    parser.add_argument("-r", "--rundir", default="/tmp", help="Run directory, for the PID file.")
    parser.add_argument("-ld", "--logdir", default=".", help="Directory to write logs to.")
    parser.add_argument("-lf", "--logfile", default="./cobrabay.log", help="Log file name to write")
    parser.add_argument("-ll", "--loglevel", help="General logging level. More fine-grained control "
                                                                      "in config file.")
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
            input_loglevel=args.loglevel
        )
    except BaseException as e:
        print(e)
        sys.exit(1)

    # Start the main operating loop.
    try:
        with PidFile('CobraBay', piddir=environment.rundir) as p:
            # Create the Master logger.
            master_logger = logging.getLogger("CobraBay")
            master_logger.setLevel(logging.DEBUG)
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG)
            master_logger.addHandler(console_handler)

            master_logger.info("Running as PID {}".format(p.pid))

            # Create a CobraBay config object.
            try:
                cbconfig = CobraBay.CBConfig(config_file=environment.configfile, environment=environment)
            except BaseException as e:
                # Relying on the config module to log details on *what* the error is.
                print("Configuration had errors. Cannot continue!")
                sys.exit(1)

            # Initialize the system
            master_logger.info("Initializing...")
            cb = CobraBay.CBCore(config_obj=cbconfig,envoptions=environment)

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
                          input_loglevel):
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

    # Run directory, for the PID file.
    try:
        rundir = pathlib.Path(input_rundir)
    except TypeError as e:
        print("Cannot make a valid path for run directory from option '{}'.".format(input_rundir))
        raise e
    else:
        if not rundir.is_absolute():
            rundir = basedir / rundir
        if not rundir.is_dir():
            raise ValueError("Run directory '{}' not a directory. Cannot continue!".format(rundir))
        print("Run directory: {}".format(rundir))

    # Config directory, to allow versioned configs.
    try:
        configdir = pathlib.Path(input_configdir)
    except TypeError as e:
        print("Cannot make a valid path for config directory from option '{}'.".format(input_configdir))
        raise e
    else:
        if not configdir.is_absolute():
            configdir = basedir / configdir
        if not configdir.is_dir():
            raise ValueError("Config directory '{}' not a directory. Cannot continue!".format(configdir))
        if configdir != basedir:
            print("Config directory: {}".format(configdir))

    try:
        configfile = pathlib.Path(input_configfile)
    except TypeError:
        configfile = None
        print("No config file specified on command line. Will search default locations.")
    else:
        # If config isn't absolute, make it relative to the base.
        if not configfile.is_absolute():
            configfile = configdir / configfile
        if not configfile.exists():
            raise ValueError("Config file '{}' does not exist. Cannot continue!".format(configfile))
        if not configfile.is_file():
            raise ValueError("Config file '{}' is not a file. Cannot continue!".format(configfile))
        print("Config file: {}".format(configfile))

    # Logging directory.
    try:
        logdir = pathlib.Path(input_logdir)
    except TypeError as e:
        print("Cannot make a valid path for log directory from option '{}'.".format(input_configdir))
        raise e
    else:
        if not logdir.is_absolute():
            logdir = basedir / logdir
        if not logdir.is_dir():
            raise ValueError("Log directory '{}' not a directory.".format(logdir))
        if logdir != basedir:
            print("Log directory: {}".format(logdir))

    # Log file
    try:
        logfile = pathlib.Path(input_logfile)
    except TypeError as e:
        print("Cannot make a valid path for run directory from option '{}'.".format(input_logdir))
        raise e
    else:
        # If config isn't absolute, make it relative to the base.
        if not logfile.is_absolute():
            logfile = logdir / logfile
        # Don't need to check if the file exists, will create on start.
        print("Log file: {}".format(logfile))

    # Log level.
    if input_loglevel is not None:
        if input_loglevel.upper() in ('DEBUG,INFO,WARNING,ERROR,CRITICAL'):
            loglevel = input_loglevel.upper()
        else:
            raise ValueError('{} is not a valid log level.'.format(input_loglevel))
    else:
        loglevel = None

    valid_environment = ENVOPTIONS(
        base=basedir,
        rundir=rundir,
        configdir=configdir,
        configfile=configfile,
        logdir=logdir,
        logfile=logfile,
        loglevel=loglevel
    )

    return valid_environment

if __name__ == "__main__":
    sys.exit(main())
