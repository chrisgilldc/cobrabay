####
# Cobra Bay - Sensor Tester
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
# from Queue import Empty
from multiprocessing import Queue, Process
from CobraBay.util import _validate_environment

def main():
    print("CobraBay Sensor Tester - {}".format(CobraBay.__version__))
    print("Running as '{}'".format(pwd.getpwuid(os.getuid()).pw_name))
    # Parse command line options.
    parser = argparse.ArgumentParser(
        description="CobraBay Sensor Tester"
    )
    parser.add_argument("-b", "--base", default=".", help="Base directory, for all other paths")
    parser.add_argument("-c", "--config", default="./config.yaml", help="Config file location.")
    parser.add_argument("-cd", "--configdir", default=".", help="Directory for config files.")
    parser.add_argument("-r", "--rundir", default="/tmp", help="Run directory, for the PID file.")
    parser.add_argument("-ld", "--logdir", default=".", help="Directory to write logs to.")
    parser.add_argument("-lf", "--logfile", default="./cbst.log", help="Log file name to write")
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

    # Make the core config.
    coreconfig = CobraBay.config.CBCoreConfig(config_file=environment.configfile, environment=environment)
    sorted_sensors = _sort_sensors(coreconfig)
    print("Total sensors: {}".format(len(coreconfig.sensors)))
    for hw_type in sorted_sensors:
        print("\t{}: {}".format(hw_type, " ".join(sorted_sensors[hw_type])))


def _sort_sensors(config_obj):
    returndict = {}
    for sensor_name in config_obj.sensors:
        hw_type = config_obj.sensor(sensor_name)['hw_type']
        if hw_type not in returndict:
            returndict[hw_type] = [sensor_name]
        else:
            returndict[hw_type].append(sensor_name)
    return returndict

def _check_tfmini(sensor):
    pass

def _check_vl53l1x(sensor):
    pass

if __name__ == "__main__":
    sys.exit(main())