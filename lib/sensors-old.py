####
# Cobra Bay - Sensors
#
# Reads in defined sensors
####

import logging

import smbus
from VL53L1X import VL53L1X
from time import sleep
import board
import busio
from digitalio import DigitalInOut
from adafruit_aw9523 import AW9523
from pint import UnitRegistry, Quantity
from .nan import NaN
from .synthsensor import SynthSensor
import time
import subprocess
import sys

class Sensors:
    def __init__(self, config):
        # Grab the logger.
        self._logger = logging.getLogger('cobrabay').getChild('sensors')
        self._logger.info('Sensors: Initializing...')

        # Pint unit registry
        self._ureg = UnitRegistry()

        # I2C bus.
        self._i2c = busio.I2C(board.SCL, board.SDA)

        # Dict to hold GPIO board objects.
        self._gpio_boards = dict()

        # Dict to hold initalized sensors.
        self._sensors = dict()

        # Keep the status of sensors. If a given sensor is unavailable, we don't want to bomb the whole system out.
        self._sensor_state = {}

        # Initialize all the sensors.
        self._init_vl53l1x(config['sensors'])

        self._logger.debug("Sensors initialization complete.")

    # Initialize all VL53L1X sensors. If required, set sensor addresses.
    def _init_vl53l1x(self, sensors):
        self._logger.debug("Initial I2C State:\n{}".format(self._show_i2c()))
        self._create_vl53l1x_controls(sensors)
        # Shut off all the sensors. Turning off the enable pin also resets a sensor to the default 0x29 address.
        self._vl53l1x_shut('disable')
        self._logger.debug("After disable-all:\n{}".format(self._show_i2c()))

        # Iterate each sensor, turn it on and move it to the correct address.
        for sensor_name in sensors:
            # Localize variables to make error statements more readable.
            bus = sensors[sensor_name]['bus_id']
            sensor_addr = sensors[sensor_name]['addr']
            if sensors[sensor_name]['shut_board'] == 'pi':
                board_addr = 'pi'
            else:
                board_addr = sensors[sensor_name]['shut_board']
            self._logger.debug("For sensor {} will use address {} and board {}.".
                               format(
                                    sensor_name,
                                    hex(sensor_addr),
                                    board_addr if board_addr == 'pi' else hex(board_addr)
                               )
            )
            # Enable this sensor only.
            self._vl53l1x_shut("enable", bus_id=bus, addr=sensor_addr)
            self._logger.debug("{} should be enabled at address {}.\n{}".format(sensor_name,board_addr,self._show_i2c()))
            # Create an object.
            try:
                sensor_obj = VL53L1X(
                    i2c_bus=bus,
                    i2c_address=0x29)
            except RuntimeError:
                raise
            else:
                self._logger.debug("Sensor object created, changing address.")
                sensor_obj.open()
                self._logger.debug("Calling address change to {}".format(hex(sensor_addr)))
                sensor_obj.change_address(sensor_addr)
                self._logger.debug("I2C bus status after address change.\n{}".format(self._show_i2c()))
            # At this point, we should have a sensor object, one way or the other, so we can return it.
            self._logger.debug("Setting distance mode.")
            sensor_obj.set_distance_mode(self._distance_mode(sensors[sensor_name]['distance_mode']))
            self._logger.debug("Adding to sensors dict.")
            self._sensors[sensor_name] = {
                'type': sensors[sensor_name]['type'],
                'obj': sensor_obj,
                'ranging': sensors[sensor_name]['distance_mode']
                }

    # Method to create the VL53L1X controls.
    def _create_vl53l1x_controls(self,sensors):
        if not isinstance(sensors,dict):
            raise ValueError("Can only create sensor controls ")
        # Traverse all the sensors and create shutoff pins for them.
        for sensor_name in sensors:
            self._logger.debug("Sensor dict for {}:\n\t{}".format(sensor_name,sensors[sensor_name]))
            # Set the basic values for the this sensor.
            self._sensors[sensor_name] = {
                'type': 'vl53l1x',
                'bus_id': sensors[sensor_name]['bus_id'],
                'addr': sensors[sensor_name]['addr'],
                'shut_board': sensors[sensor_name]['shut_board'],
                'shut_pin': sensors[sensor_name]['shut_pin']
            }

            # Create a shutoff pin object.
            if sensors[sensor_name]['shut_board'] != 'pi':
                # Get the board
                try:
                    gpio_board = self._gpio_boards[sensors[sensor_name]['shut_board']]
                except KeyError:
                    # Couldn't find it, so create the board object, then use it.
                    try:
                        gpio_board = AW9523(self._i2c, address=sensors[sensor_name]['shut_board'])
                    except:
                        self._logger.debug("GPIO board for sensor {} not available. Cannot continue.".format(sensor_name))
                        return
                    self._gpio_boards[sensors[sensor_name]['shut_board']] = gpio_board
                # Alright, have the board, can create a pin.
                shutoff_pin = gpio_board.get_pin(sensors[sensor_name]['shut_pin'])
            else:
                # Shutdown pin must be directly on the board.
                pin_num = eval("board.D{}".format(sensors[sensor_name]['shut_pin']))
                shutoff_pin = DigitalInOut(pin_num)
            shutoff_pin.switch_to_output(value=False)
            self._sensors[sensor_name]['shutoff'] = shutoff_pin

    # Method to control the shutoff pins of VL53L1X sensors.
    def _vl53l1x_shut(self,command,bus_id=None,addr=None):
        if bus_id is None or addr is None:
           self._logger.debug("VL53L1X Command {}, will apply to all sensors.")
        else:
            self._logger.debug("VL53L1X Command {}, applying to Bus ID {}, Address {}".format(command, bus_id,hex(addr)))
        if command == 'enable':
            # Enabling sets pins high.
            pin_value = True
        elif command in ('disable', 'only'):
            # Disabling sets pins low. We also set low for 'only', and then set to True just for the matching pin.
            pin_value = False
        else:
            raise ValueError("{} not a valid command.".format(command))

        for sensor_name in self._sensors:
            # Is it actually a VL53L1X?
            if self._sensors[sensor_name]['type'] == 'vl53l1x':
                if bus_id is not None and addr is not None:
                    # If given a specific bus_id and address, make sure it matches.
                    if self._sensors[sensor_name]['bus_id'] == bus_id and self._sensors[sensor_name]['addr'] == addr:
                        if command == 'only':
                            self._logger.debug("Setting {} to {}".format(sensor_name,True))
                            self._sensors[sensor_name]['shutoff'].value = True
                        else:
                            self._logger.debug("Setting {} to {}".format(sensor_name,pin_value))
                            self._sensors[sensor_name]['shutoff'].value = pin_value
                    else:
                        self._logger.debug("Setting {} to {}".format(sensor_name,False))
                        self._sensors[sensor_name]['shutoff'].value = False
                else:
                    if command in ('enable','disable'):
                        self._logger.debug("Applying to all sensors, setting {} to {}".format(sensor_name, pin_value))
                        # If we weren't given a bus id and address, turn on everything.
                        self._sensors[sensor_name]['shutoff'].value = pin_value

    # Converts range mode back and forth between int and string.
    @staticmethod
    def _distance_mode(distance_mode):
        if isinstance(distance_mode,int):
            if distance_mode == 1:
                return 'short'
            elif distance_mode == 2:
                return 'medium'
            elif distance_mode == 3:
                return 'long'
            else:
                raise ValueError("Integer range mode '{}' not understood.".format(distance_mode))
        elif isinstance(distance_mode,str):
            if distance_mode.lower() == 'short':
                return 1
            elif distance_mode.lower() == 'medium':
                return 2
            elif distance_mode.lower() == 'long':
                return 3
            else:
                raise ValueError("'{}' is not a valid range mode.".format(distance_mode))
        else:
            raise TypeError("Can only convert ints and strings")

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
            # Catch these and return a NaN.
            if distance > 0:
                return Quantity(distance,self._ureg.centimeter)
            else:
                return NaN('No sensor response')
        elif self._sensors[sensor]['type'] == 'vl53l1x':
            # The VL53L1X library returns millimeters. Convert it to cm.
            measured_distance = Quantity(self._sensors[sensor]['obj'].get_distance(),self._ureg.millimeters).to('cm')
            return measured_distance
        elif self._sensors[sensor]['type'] == 'synth':
            distance = self._sensors[sensor]['obj'].distance
            dist_unit = Quantity(distance,self._ureg.centimeter)
            return dist_unit
        else:
            raise ValueError("Not a valid sensor type")

    # External method to allow a rescan of the sensors.
    def rescan(self):
        self._init_sensors(self.config['sensors'])

    def sweep(self, sensor_type=None):
        if sensor_type is None:
            sensor_type = ['all']
        sensor_data = {}
        for sensor in self._sensors:
            if self._sensors[sensor]['type'] in sensor_type or 'all' in sensor_type:
                # Get the raw sensor value.
                try:
                    reading = self._read_sensor(sensor)
                # An OSError is raised when it literally can't be read. That means it's probably missing.
                except OSError as e:
                    self._logger.debug('Sensors: Could not read sensor ' + sensor)
                    self._logger.error(e,exc_info=True)
                    raise
                # Post-processing for the HC-SR04
                if self._sensors[sensor]['type'] == 'hcsr04':
                    # Reject times when the sensor returns none or zero, because that's almost certainly a glitch. 
                    # You should never really be right up against the sensor!
                    if reading != 0 and reading is not NaN:
                        # If queue is full, remove the oldest element.
                        if  len(self._sensors[sensor]['queue']) >= self._sensors[sensor]['avg']:
                            del self._sensors[sensor]['queue'][0]
                        # Now add the new value and average.
                        self._sensors[sensor]['queue'].append(reading)
                        # Calculate the average.
                        # Add the magnitudes from all the quantities. These *should* already be in centimeters,
                        # but convert anyway to be certain.
                        sensor_magnitude_sum = sum([i.to("cm").magnitude for i in self._sensors[sensor]['queue']])
                        # Get the length of the queue.
                        sensor_queue_length = len(self._sensors[sensor]['queue'])
                        # Calculate the average.
                        avg_magnitude = sensor_magnitude_sum / sensor_queue_length
                        # Send the average back as a quantity in centimeters.
                        sensor_data[sensor] = Quantity(avg_magnitude,"cm")
                    # Now ensure wait before the next check to prevent ultrasound interference.
                    sleep(self.config['sensor_pacing'])
                else:
                    # For non-ultrasound sensors, send it directly back.
                    sensor_data[sensor] = reading
        return sensor_data

    # Method to start and stop sensors. This
    def sensor_cmd(self, action):
        for sensor in self._sensors:
            if self._sensors[sensor]['type'] == 'vl53':
                if action == 'start':
                    self._sensors[sensor]['obj'].start_ranging()
                if action == 'stop':
                    self._sensors[sensor]['obj'].stop_ranging()
                if action == 'close':
                    self._sensors[sensor]['obj'].close()
            if self._sensors[sensor]['type'] == 'hcsr04':
                if action == 'start':
                    # When starting an HCSR04, dump the queue, since values here are probably old.
                    # Arguably we should do aging on individual values and this is a quick hack. So, maybe fix later.
                    self._sensors[sensor]['queue'] = []

    # Utility function to just list all the sensors found.
    def sensor_state(self, sensor=None):
        if sensor is None:
            return self._sensor_state
        elif sensor in self._sensor_state:
            return self._sensor_state[sensor]
        else:
            raise ValueError("Sensor name not found.")

    def get_sensor(self, sensor_name):
        if sensor_name not in self._sensors.keys():
            raise ValueError("Sensor does not exist.")
        if self._sensor_state[sensor_name] == 'unavailable':
            return NaN('Sensor unavailable')
        if self._sensors[sensor_name]['type'] == 'vl53':
            self._sensors[sensor_name]['obj'].start_ranging(0)
            value = self._read_sensor(sensor_name)
            self._sensors[sensor_name]['obj'].stop_ranging()
            return value

    # For debugging, a static method to roll in i2c scan results.
    @staticmethod
    def _show_i2c():
        result = subprocess.run(["/usr/sbin/i2cdetect", "-y", "1"], stdout=subprocess.PIPE)
        return result.stdout.decode('utf-8')
