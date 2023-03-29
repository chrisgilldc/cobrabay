####
# Cobra Bay - Sensor Testing Tool
####

import argparse
import pathlib
import sys
import CobraBay
import logging

from pid import PidFile, PidFileAlreadyRunningError, PidFileAlreadyLockedError

def main():
    # Parse command line options.
    parser = argparse.ArgumentParser(
        description="CobraBay Sensor Tester"
    )
    parser.add_argument("-c", "--config", help="Config file location.")
    parser.add_argument("-r", "--run-dir", help="Run directory, for the PID file.")
    parser.add_argument("-n", default=1, help="Number of test readings to take.")
    parser.add_argument("-s", default="all", help="Sensors to test.")
    args = parser.parse_args()

    # Check for an active CobraBay instance.
    if args.run_dir:
        pid_lock = PidFile('CobraBay', piddir=args.run_dir)
    else:
        # Default the pid file to /tmp
        pid_lock = PidFile('CobraBay', piddir="/tmp")

    try:
        pid_lock.check()
    except PidFileAlreadyRunningError:
        print("Cannot run sensor test while CobraBay is active. CobraBay running as PID {}".format(pid_lock.pid))
        sys.exit(1)
    except PidFileAlreadyLockedError:
        print("CobraBay lock exists but appears not to be running. May be stale. "
              "Check directory '{}', clear and retry.".format(pid_lock.piddir))

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
        cbconfig = CobraBay.CBConfig(config_file=arg_config, reset_sensors=True)
    except ValueError as e:
        print(e)
        sys.exit(1)

    # Start the main operating loop.
    with PidFile('CobraBay', piddir='/tmp') as p:
        # Load the various sensors.
        sensors = load_sensors(cbconfig)
        print("Loaded sensors: {}".format(list(sensors.keys())))
        if args.s == 'all':
            test_sensors = sensors.keys()
        else:
            if args.s not in sensors.keys():
                print("Requested test sensors '{}' not in configured sensors.")
                sys.exit(1)
            else:
                test_sensors = [ args.s ]

        for sensor in sensors:
            sensors[sensor].start_ranging()

        i = 1
        while i <= int(args.n):
            print("Test cycle: {}".format(i))
            for sensor in test_sensors:
                print("{} - {}".format(sensor, sensors[sensor].range))
            i += 1


# Method to load just the sensors out of a given CobraBay Config.
def load_sensors(cbconfig):
    sensors = {}
    for detector_id in cbconfig.detector_list:
        detector_config = cbconfig.detector(detector_id)
        if detector_config['sensor']['type'] == 'VL53L1X':
            # Create the sensor object using provided settings.
            sensor_obj = CobraBay.sensors.CB_VL53L1X(detector_config['sensor'])
        elif detector_config['sensor']['type'] == 'TFMini':
            sensor_obj = CobraBay.sensors.TFMini(detector_config['sensor'])
        else:
            continue
        sensors[detector_id] = sensor_obj
    return sensors


if __name__ == "__main__":
    sys.exit(main())
