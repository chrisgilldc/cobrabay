####
# Cobra Bay - Sensors
#
# Reads in defined sensors
####

import board
import digitalio
import sys
import time
import terminalio
from adafruit_hcsr04 import HCSR04
from adafruit_aw9523 import AW9523
from adafruit_vl53l1x import VL53L1X
from .synthsensor import SynthSensor
import adafruit_logging as logging


class Sensors:
    def __init__(self, config):
        # Grab the logger.
        self._logger = logging.getLogger('sensors')
        self._logger.info('Sensors: Initializing...')

        # Boards with GPIO pins. Always has 'local' as the native board.
        # Can add additional boards (ie: AW9523) during initialization.
        self.gpio_boards = {'local': board}

        # General config.
        self.config = {
            'sensor_pacing': 0.5
        }

        # Try to pull over values from the config array.
        # If present, they'll overwrite the default. If not, the default stands.
        for config_value in ('sensor_pacing'):
            try:
                self.config[config_value] = config[config_value]
            except:
                pass

        # Keep the status of sensors. If a given sensor is unavailable, we don't want to bomb the whole system out.
        self._sensor_state = {}

        # Initialize all the sensors.
        howmany = self._init_sensors(config['sensors'])
        self._logger.info('Sensors: Processed ' + str(howmany) + ' sensors.')
        self._logger.info('Sensors: Initialization complete.')

    # To initialize multiple sensors in a go. Takes a dict of sensor definitions.
    def _init_sensors(self, sensors):
        i = 0
        self._sensors = {}
        for sensor in sensors:
            self._logger.info('Sensors: Trying setup for ' + sensor)
            try:
                sensor_obj = self._create_sensor(sensors[sensor])
            except Exception as e:
                self._logger.error('Sensors: Could not initialize ' + sensor + ', marking unavailable')
                self._logger.error('Sensors: ' + str(e))
                self._sensor_state[sensor] = 'unavailable'
            else:
                # if sensor_obj is not None:
                self._sensors[sensor] = {
                    'type': sensors[sensor]['type'],
                    'obj': sensor_obj}
                # For ultrasound sensors, add in the averaging rate and initialize buffer.
                if self._sensors[sensor]['type'] == 'hcsr04':
                    self._sensors[sensor]['avg'] = sensors[sensor]['avg']
                    self._sensors[sensor]['queue'] = []

                # Test the sensor and make sure we can get a result. 
                # Value doesn't matter, just get *something*

                try:
                    result = self._read_sensor(sensor)
                except Exception as e:
                    self._logger.error('Sensors: Read test of sensor ' + sensor + ' failed, marking unavailable')
                    self._logger.error('Sensors: ' + str(e))
                    self._sensor_state[sensor] = 'unavailable'
                else:
                    self._logger.debug('Sensors: Read test of sensor ' + sensor + ' got: ' + str(result))
                    # Finally, set the sensor as available.
                    if result is not None:
                        self._sensor_state[sensor] = 'available'
                    else:
                        self._sensor_state[sensor] = 'unavailable'
            i += 1
        return i

    def _create_sensor(self, options):
        # VL53L1X sensor.
        if options['type'] == 'vl53':
            # Create the sensor
            try:
                new_sensor = VL53L1X(board.I2C(), address=options['address'])
            except Exception as e:
                raise OSError("VL53L1X sensor not available at address '" + str(options['address']) + "'. Ignoring.")
            # Set the defaults.
            new_sensor.distance_mode = 2
            new_sensor.timing_budget = 50
            if 'distance_mode' in options:
                if options['distance_mode'] == 'short':
                    new_sensor.distance_mode = 1
            if 'timing_budget' in options:
                if options['timing_budget'] in (15, 20, 33, 50, 100, 200, 500):
                    new_sensor.timing_budget = options['timing_budget']
                else:
                    self._logger.debug('Sensors: Requested timing budget ' + str(
                        options['timing_budget']) + ' not supported. Keeping default of 50ms.')

            new_sensor.start_ranging()

            return new_sensor

        # The HC-SR04 sensor, or US-100 in HC-SR04 compatibility mode
        elif options['type'] == 'hcsr04':

            # Confirm trigger, echo and board are set. These are *required*.
            for parameter in ('board', 'trigger', 'echo'):
                if parameter not in options:
                    raise ValueError("Parameter " + parameter + " not defined for HC-SR04 sensor.")
                # Set a custom timeout if necessary
                if 'timeout' not in options:
                    timeout = 0.1
                else:
                    timeout = options['timeout']

            # Make sure the GPIO board has been initialized.
            # This is already seeded with 'local', so that *always* works.
            # Since we only support AW9523 expansion boards(currently), 
            # then any missing board must be an AW9523.
            if options['board'] not in self.gpio_boards:
                try:
                    self.gpio_boards[options['board']] = AW9523(board.I2C(), address=options['board'])
                except Exception as e:
                    raise OSError("AW9523 not available at address '" + str(options['board']) + "'. Skipping.")

            # Create HCSR04 object with the correct pin syntax.
            # Pins on the AW9523
            if options['board'] in (0x58, 0x59, 0x5A, 0x5B):
                new_sensor = HCSR04(
                    trigger_pin=self.gpio_boards[options['board']].get_pin(options['trigger']),
                    echo_pin=self.gpio_boards[options['board']].get_pin(options['echo']),
                    timeout=timeout)
            # 'Local' GPIO, directly on the board.
            elif options['board'] == 'local':
                # Use the exec call to convert the inbound pin number to the actual pin objects
                tp = eval("board.D{}".format(options['trigger']))
                ep = eval("board.D{}".format(options['echo']))
                new_sensor = HCSR04(trigger_pin=tp, echo_pin=ep, timeout=timeout)
            else:
                raise OSError("GPIO board '" + options['board'] + "' not valid!")

            # No errors to this point, return the sensor.
            return new_sensor

        # Synthetic sensors, IE: fake numbers to allow for testing.
        elif options['type'] == 'synth':
            return SynthSensor(options)
        else:
            raise ValueError("Not a valid sensor type")

    # Provides a uniform interface to access different types of sensors.
    def _read_sensor(self, sensor):
        if self._sensors[sensor]['type'] == 'hcsr04':
            try:
                distance = self._sensors[sensor]['obj'].distance
            except RuntimeError:
                # Catch timeouts and return None if it times out.
                return None
            except OSError:
                raise
            # Sensor can be wonky and return 0, even when it doesn't strictly timeout.
            # Catch these and return None instead.
            if distance > 0:
                return distance
            else:
                return None
        if self._sensors[sensor]['type'] in ('vl53', 'synth'):
            distance = self._sensors[sensor]['obj'].distance
            return distance

    # External method to allow a rescan of the sensors.
    def rescan(self):
        self._init_sensors(self.config['sensors'])


    def vl53(self, action):
        if action not in ('start', 'stop'):
            self._logger.error('Sensors: Requested invalid action for VL53 sensor. Must be either "start" or "stop".')
            raise ValueError("Must be 'start' or 'stop'.")
        else:
            for sensor in self._sensors:
                if self._sensors[sensor]['type'] == 'vl53':
                    if action == 'start':
                        self._sensors[sensor]['obj'].start_ranging()
                    if action == 'stop':
                        self._sensors[sensor]['obj'].stop_ranging()

    def sweep(self, sensor_type=['all']):
        sensor_data = {}
        for sensor in self._sensors:
            if self._sensors[sensor]['type'] in sensor_type or 'all' in sensor_type:
                # Get the raw sensor value.
                try:
                    value = self._read_sensor(sensor)
                # An OSError is raised when it literally can't be read. That means it's probably missing.
                except OSError as e:
                    self._logger.debug('Sensors: Could not read sensor ' + sensor)
                    self._logger.debug('Sensors: ' + str(e))
                    raise
                # Post-processing for the HC-SR04
                if self._sensors[sensor]['type'] == 'hcsr04':
                    # Reject times when the sensor returns none or zero, because that's almost certainly a glitch. 
                    # You should never really be right up against the sensor!
                    if value != 0 and value is not None:
                        # If queue is full, remove the oldest element.
                        if len(self._sensors[sensor]['queue']) >= self._sensors[sensor]['avg']:
                            del self._sensors[sensor]['queue'][0]
                        # Now add the new value and average.
                        self._sensors[sensor]['queue'].append(value)
                        # Calculate the average
                        avg_value = sum(self._sensors[sensor]['queue']) / self._sensors[sensor]['avg']
                        # Send the average back.
                        sensor_data[sensor] = avg_value
                    # Now ensure wait before the next check to prevent ultrasound interference.
                    time.sleep(self.config['sensor_pacing'])
                else:
                    # For non-ultrasound sensors, send it directly back.
                    sensor_data[sensor] = value

                # Only return non-none values
                if value is not None:
                    sensor_data[sensor] = value
        return sensor_data

    # Utility function to just list all the sensors found.
    def sensor_state(self, sensor=None):
        if sensor is None:
            return self._sensor_state
        elif sensor in self._sensor_state:
            return self._sensor_state[sensor]
        else:
            raise ValueError("Sensor name not found.")

    def get_sensor(self,sensor_name):
        print("Get sensor for: {}".format(sensor_name))
        if sensor_name not in self._sensors.keys():
            print("Sensor name does not exist.")
            return None
        if self._sensor_state[sensor_name] == 'unavailable':
            print("Sensor not available!")
            return 'unavailable'
        if self._sensors[sensor_name]['type'] == 'vl53':
            print("Sensor type VL53")
            self._sensors[sensor_name]['obj'].start_ranging()
            value = self._read_sensor(sensor_name)
            self._sensors[sensor_name]['obj'].stop_ranging()
            return value
        return None
