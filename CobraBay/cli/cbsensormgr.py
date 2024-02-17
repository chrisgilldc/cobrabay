####
# Cobra Bay - Sensor Manager
####

import argparse
import pathlib
import sys
import pid.base
import CobraBay
import logging
import os
import pwd
import queue
import time
from logging.handlers import WatchedFileHandler
# from collections import namedtuple
from pid import PidFile
from CobraBay.datatypes import ENVOPTIONS

## TODO: Make this a real command line invoker to be run as a system unit.

TEST_CONFIG = {
    'range':
        {
            'name': 'Range',
            'sensor_type': "TFMini",
            'port': 'serial0',
            'baud': 115200,
            'log_level': "WARNING"
        },
    'front':
        {
            'name': 'Front',
            'sensor_type': 'VL53L1X',
            'i2c_address': 0x33,
            'enable_board': 0x58,
            'enable_pin': 1,
            'log_level': "WARNING"
        },
    'middle':
        {
            'name': 'Middle',
            'sensor_type': 'VL53L1X',
            'i2c_address': 0x32,
            'enable_board': 0x58,
            'enable_pin': 2,
            'log_level': "WARNING"
        }
}


# def main():
#     cbsm = CobraBay.CBSensorMgr(
#         TEST_CONFIG, log_level="DEBUG"
#     )
#     print(cbsm._sensors)
#     cbsm.sensors_activate()
#     # start = time.monotonic()
#     print("Starting loop...")
#     while True:
#         cbsm.loop()
#         # if (time.monotonic() - start ) >= 60:
#         #     print("Getting data from queue...")
#         while len(cbsm.data) > 0:
#             print(cbsm.data.pop())
#         # start = time.monotonic()
def main():
    logger = CobraBay.util.default_logger("CBSM Tester",log_level="DEBUG")
    print(logger)
    logger.info("Starting setup...")
    cbsm = CobraBay.CBSensorMgr(
        TEST_CONFIG, log_level="DEBUG"
    )
    logger.debug("CBSM Tester has sensors: {}".format(cbsm._sensors))
    logger.debug("Activating sensors...")
    cbsm.sensors_activate()
    logger.debug("Sensors activated.")
    logger.debug("Starting thread.")
    cbsm.loop_start()
    logger.debug("Started thread.")
    while True:
        try:
            sensor_data = cbsm.data.get(block=False)
        except queue.Empty:
            continue
        else:
            logger.debug("Got sensor data: {}".format(sensor_data))

if __name__ == "__main__":
    sys.exit(main())
