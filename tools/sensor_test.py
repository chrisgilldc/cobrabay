#!/usr/bin/python3

import argparse
import pathlib
import sys

parser = argparse.ArgumentParser(
    prog='sensor_test',
    description='CobraBay Sensor Tester'
)

parser.add_argument('-c', '--config', default='config.yaml', help='Location of the CobraBay config file.')
parser.add_argument('-l', '--lib', default='/home/pi/CobraBay/', help='Path to the CobraBay library directory.')
args = parser.parse_args()
print(args)
# Add the library to the python path. We're assuming this isn't installed at the system level.
sys.path.append(args.lib)
# Import and create a CobraBay config object.
from CobraBay.config import CBConfig

config = CBConfig(args.config)
