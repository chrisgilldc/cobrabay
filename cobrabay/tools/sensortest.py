"""
Cobrabay Sensor Tester
"""

import argparse
import pathlib
import sys
import pid.base
import cobrabay
import logging
import os
import pwd
import queue
import socket
from pid import PidFile
from cobrabay.datatypes import ENVOPTIONS
import pprint

def sensortestcli():
    """
    Sensor Test Command Line Invoker
    """
    print("Cobrabay Sensor Tester - {}".format(cobrabay.__version__))

    # Parse command line options.
    parser = argparse.ArgumentParser(
        description="Cobra Sensor Tester"
    )
    parser.add_argument("-b", "--base", default=".", help="Base directory, for all other paths")
    parser.add_argument("-c", "--config", default="./config.yaml", help="Config file location.")
    parser.add_argument("-cd", "--configdir", default=".", help="Directory for config files.")
    parser.add_argument("-r", "--rundir", default="/tmp", help="Run directory, for the PID file.")
    parser.add_argument("-ld", "--logdir", default=".", help="Directory to write logs to.")
    parser.add_argument("-lf", "--logfile", default="./cobrabay.log", help="Log file name to write")
    parser.add_argument("-ll", "--loglevel", help="General logging level. More fine-grained control "
                                                  "in config file.")
    parser.add_argument("-i", "--iterations", help="How many times to iterate the sensors. Defaults to continuous.")
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
        with (PidFile('cobrabay', piddir=environment.rundir) as p):
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
            # Sensor Data
            q_cbsmdata = queue.Queue(maxsize=1)
            # Sensor Status
            q_cbsmstatus = queue.Queue(maxsize=1)
            # Control
            q_cbsmcontrol = queue.Queue(maxsize=1)

            # Create the sensor manager.
            cbsm = cobrabay.sensormgr.CBSensorMgr(
                coreconfig.sensors_config(),
                i2c_config=coreconfig.i2c_config(),
                name="cbsm_test",
                q_cbsmdata=q_cbsmdata,
                q_cbsmstatus=q_cbsmstatus,
                q_cbsmcontrol=q_cbsmcontrol)

            reading_accumulator = {}

            # Start.
            master_logger.info("Queueing ranging command....")
            # Send the start command.
            q_cbsmcontrol.put((cobrabay.const.SENSTATE_RANGING, None))
            master_logger.info("Starting sensing...")
            while True:
                try:
                    cbsm.loop()
                    if not q_cbsmdata.empty():
                        readings = q_cbsmdata.get()
                        q_cbsmdata.task_done()
                        for sensor in readings.sensors:
                            # Make a dict for this sensor if not seen before.
                            if sensor not in reading_accumulator:
                                reading_accumulator[sensor] = {}

                            # Count response types
                            if readings.sensors[sensor].response_type not in reading_accumulator[sensor]:
                                reading_accumulator[sensor]['response_type'][readings.sensors[sensor].response_type] = 1
                            else:
                                reading_accumulator[sensor]['response_type'][readings.sensors[sensor].response_type] += 1

                            # Add  to the list of real readings.
                            if readings.sensors[sensor].response_type == 'ok':
                                if 'readings' not in reading_accumulator[sensor]:
                                    reading_accumulator[sensor]['readings'] = [readings.sensors[sensor].range]
                                else:
                                    reading_accumulator[sensor]['readings'].append(readings.sensors[sensor].range)

                except KeyboardInterrupt:
                    break
    except pid.base.PidFileAlreadyLockedError:
        print("Cannot start, a Cobrabay instance is already running!")
    pprint.pprint(reading_accumulator)

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
    sys.exit(sensortestcli())
