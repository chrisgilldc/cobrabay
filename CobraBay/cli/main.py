####
# Cobra Bay - Main Executor
####

import argparse
import pathlib
import sys
import CobraBay
import logging
from logging.handlers import WatchedFileHandler

from pid import PidFile

def main():
    # Parse command line options.
    parser = argparse.ArgumentParser(
        description="CobraBay Parking System"
    )
    parser.add_argument("-c", "--config", help="Config file location.")
    parser.add_argument("-r", "--run-dir", help="Run directory, for the PID file.")
    args = parser.parse_args()

    try:
        arg_config = pathlib.Path(args.config)
    except TypeError:
        arg_config = None

    # Create the Master logger.
    master_logger = logging.getLogger("CobraBay")
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    master_logger.addHandler(console_handler)

    # Create a CobraBay config object.
    try:
        cbconfig = CobraBay.CBConfig(config_file=arg_config)
    except ValueError as e:
        print(e)
        sys.exit(1)

    # Initialize the system
    cb = CobraBay.CBCore(config_obj=cbconfig)

    # Start the main operating loop.
    with PidFile('CobraBay', piddir='/tmp') as p:
        print("Pid file name: {}".format(p.pidname))
        print("Pid directory: {}".format(p.piddir))
        cb.run()


if __name__ == "__main__":
    sys.exit(main())
