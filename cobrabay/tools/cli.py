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
from multiprocessing import Queue # , Process
import pprint


def cbcli():
    """
    Main Cobra Bay CLI Invoker
    """
    print("cobrabay Parking System - {}".format(cobrabay.__version__))
    print("User: {}\tHost: {}\tIP: {}".format(pwd.getpwuid(os.getuid()).pw_name, socket.getfqdn(), socket.gethostbyname(socket.gethostname())))
    # Parse command line options.
    parser = argparse.ArgumentParser(
        description="Cobra Bay Parking System"
    )
    parser.add_argument("-b", "--base", dest="basedir", default=".", help="Base directory, for all other paths")
    parser.add_argument("-c", "--config", dest="configfile", default="./config.yaml", help="Config file location.")
    parser.add_argument("-cd", "--configdir", default=".", help="Directory for config files.")
    parser.add_argument("-cv", "--config-validate", action="store_true", help="Validate configuration and exit.")
    parser.add_argument("-r", "--rundir", default="/tmp", help="Run directory, for the PID file.")
    parser.add_argument("-ld", "--logdir", default=".", help="Directory to write logs to.")
    parser.add_argument("-lf", "--logfile", default="./cobrabay.log", help="Log file name to write")
    parser.add_argument("-ll", "--loglevel", help="General logging level. More fine-grained control "
                                                  "in config file.")
    args = parser.parse_args()

    # Run the arguments through basic validation. This just makes sure the core doesn't crash before it does full
    # validation.
    cmd_options = _validate_cmdline(args)

    # Create the Master logger.
    master_logger = logging.getLogger("cobrabay")
    master_logger.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    master_logger.addHandler(console_handler)

    # If validation mode is selected, try to create a config, validate it, then exit.
    if args.config_validate:
        validation_config = cobrabay.config.CBConfig("Validation", args.configfile, cmd_options=cmd_options, parent_logger=master_logger)
        sys.exit(0)

    # Start the main operating loop.
    try:
        with PidFile('cobrabay', piddir=cmd_options.rundir) as p:
            master_logger.info("Main process running as PID {}".format(p.pid))
            master_logger.debug("Received command line options: {}".format(pprint.pformat(cmd_options)))
            # Initialize the system
            master_logger.info("Initializing...")
            # Create the queues.
            # Data flow.
            q_cbsmdata = Queue()
            # Control
            q_cbsmcontrol = Queue()

            #Create the core system core, which will run in the main process.
            # try:
            cb = cobrabay.CBCore(cmd_options=cmd_options,
                                 q_cbsmdata=q_cbsmdata,
                                 q_cbsmcontrol=q_cbsmcontrol)

            # Start the Sensor Manager process.
            # cbsm_process = Process(target=cobrabay.sensormgr.CBSensorMgr, args=(sensorconfig, q_cbsmdata=q_cbsmdata, q_cbsmcontrol=q_cbsmcontrol))
            # cbsm_process.start()
            

            # Start.
            master_logger.info("Initialization complete. Operation start.")
            cb.run()
    except pid.base.PidFileAlreadyLockedError:
        print("Cannot start, already running!")

def _validate_cmdline(args):
    """
    Simple validation of the command line.
    This checks *only* options that would bomb the system prior to full validation of the configuration.
    """

    # Have to validate the log level, otherwise the logger can't be configured.

    if args.loglevel is not None:
        if args.loglevel.upper() in 'DEBUG,INFO,WARNING,ERROR,CRITICAL':
            loglevel = args.loglevel.upper()
        else:
            print("'{}' is not a valid log level. Must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL".format(
                    args.loglevel))
            sys.exit(2)
    else:
        loglevel = None

    return ENVOPTIONS(
        basedir=args.basedir,
        rundir=args.rundir,
        configdir=args.configdir,
        configfile=args.configfile,
        logdir=args.logdir,
        logfile=args.logfile,
        loglevel=loglevel
    )

if __name__ == "__main__":
    sys.exit(cbcli())
