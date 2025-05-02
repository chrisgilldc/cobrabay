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
import pprint

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
    parser.add_argument("-b", "--base", dest="basedir", help="Base directory, for all other paths")
    parser.add_argument("-c", "--config", dest="configfile", help="Config file location.")
    parser.add_argument("-cd", "--configdir", help="Directory for config files.")
    parser.add_argument("-r", "--rundir", help="Run directory, for the PID file.")
    parser.add_argument("-ld", "--logdir", help="Directory to write logs to.")
    parser.add_argument("-lf", "--logfile", help="Log file name to write")
    parser.add_argument("-ll", "--loglevel", help="General logging level. More fine-grained control "
                                                  "in config file.")
    parser.add_argument("-u", "--unit-system", default='metric', dest="unitsystem", help="Unit system to use. Defaults to metric. May be 'imperial'.")
    parser.add_argument("-mb", "--mqtt-broker", dest="mqttbroker", help="Set the MQTT broker.")
    parser.add_argument("-mp", "--mqtt-port", dest="mqttport", default=1883, help="Set the MQTT Port (default: 1883)")
    parser.add_argument("-mu", "--mqtt-user", dest="mqttuser", help="Set the MQTT User")


    args = parser.parse_args()

    # Run the arguments through basic validation. This just makes sure the core doesn't crash before it does full
    # validation.
    cmd_options = _validate_cmdline(args)

    # Create an envoptions tuple with the options passed.


    # try:
    #     environment = _validate_environment(
    #         input_base=args.base,
    #         input_rundir=args.rundir,
    #         input_configdir=args.configdir,
    #         input_configfile=args.config,
    #         input_logdir=args.logdir,
    #         input_logfile=args.logfile,
    #         input_loglevel=args.loglevel,
    #         input_mqttbroker=args.mqttbroker,
    #         input_mqttport=args.mqttport,
    #         input_mqttuser=args.mqttuser,
    #         input_unitsystem=args.unitsystem
    #     )
    # except BaseException as e:
    #     print(e)
    #     sys.exit(1)

    # Start the main operating loop.
    try:
        with PidFile('cobrabay', piddir=cmd_options.rundir) as p:
            # Create the Master logger.
            master_logger = logging.getLogger("cobrabay")
            master_logger.setLevel(logging.DEBUG)
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG)
            master_logger.addHandler(console_handler)
            master_logger.info("Main process running as PID {}".format(p.pid))
            master_logger.info("-----")
            master_logger.debug("Received command line options: {}".format(pprint.pformat(cmd_options)))
            # Create a Cobra Bay config object.
            #
            # try:
            #     initialconfig = cobrabay.config.CBConfig(name="initialconfig", environment=environment)
            #     minimal = initialconfig.is_minimal
            # except ValueError as ve:
            #     master_logger.critical(str(ve))
            #     sys.exit(2)
            # except BaseException as be:
            #     master_logger.critical("Unknown exception occurred loading configuration.")
            #     master_logger.critical(str(be))
            #     sys.exit(2)
            #
            # master_logger.info("Configuration loaded successfully.")
            # master_logger.debug("Active configuration at start:\n{}".format(pprint.pformat(initialconfig.active_config)))

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
            # except BaseException as be:
            #     print("Could not start system. Exiting.")
            #     print(be)
            #     sys.exit(1)

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
        loglevel=loglevel,
        mqttbroker=args.mqttbroker,
        mqttport=args.mqttport,
        mqttuser=args.mqttuser,
        mqttpassword=None,
        unitsystem=args.unitsystem
    )

if __name__ == "__main__":
    sys.exit(cbcli())