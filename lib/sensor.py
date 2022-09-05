####
# Cobra Bay - Sensor
#
# Abstract class for a hardware sensor.
# Supports:
#  - VL53L1X sensor
#  - "Synthetic" sensor library for testing
####

import logging

import adafruit_aw9523
from pint import UnitRegistry, Quantity
# Imports to support the Synthetic Sensor
from .synthsensor import SynthSensor

class Sensor:
    def __init__(self,board_options):
        # Each class should implement its own board setup method.
        self._board_setup(board_options)
        # Create a unit registry for the object.
        self._ureg = UnitRegistry()

    # Override this class in specific implementations
    def _board_setup(self,board_options):
        pass

    # Override this class in specific implementations to read the
    def read(self):
        pass

class VL53L1X(Sensor):
    _i2c_address: int
    _i2c_bus: int

    def _setup_board(self,board_options):
        # Do some
        # Check for required options in
        options = ['i2c_bus','i2c_address','enable_pin','enable_board']
        # Store the options.
        for item in options:
            if item not in board_options:
                raise ValueError("Required board_option '{}' missing".format(item))
            else:
        # Import libraries needed by the VL53L1X.
        import board
        import busio
        from digitalio import DigitalInOut
        from adafruit_aw9523 import AW9523

        # Create a board object we can reference.
        self._board = board

        # Create access to the I2C bus
        try:
            self._i2c = busio.I2C(board.SCL, board.SDA)
        except:
            raise

    def enable(self):

    def disable(self):

    # Method called when creating the control pin object.
    def _create_enable_pin(self):


    def _set_address(self):


    # Properties
    @property
    def i2c_bus(self):
        return self._i2c_bus

    @i2c_bus.setter
    def i2c_bus(self,bus_id):
        if bus_id not in (1,2):
            raise ValueError("I2C Bus ID for Raspberry Pi must be 1 or 2, not {}".format(bus_id))
        else:
            self._i2c_bus = bus_id

    @property
    def i2c_address(self):
        return self._i2c_address

    @i2c_address.setter
    def i2c_address(self,i2c_address):
        if isinstance(i2c_address,str):
            self._i2c_address = int(i2c_address,base=16)
        else:
            self._i2c_address = i2c_address

    @property
    def enable_pin(self):
        return self._enable_pin

    @enable_pin.setter
    def enable_pin(self, enable_pin, enable_board):
        # If enable_board is set to 0, then we try this on the Pi itself.
        if enable_board == 0:
            pin_name = 'board.D' + enable_pin
            try:
                enable_pin_obj = exec(pin_name)
            except:
                raise
            else:
                self._enable_pin = enable_pin_obj
        else:
            # Otherwise, treat enable_board as the address of an AW9523.
            try:
                aw = adafruit_aw9523.AW9523(self._i2c,enable_board)
            except:
                raise
            # Get the pin from the AW9523.
            self._enable_pin = aw.get_pin(enable_pin)
        # Make sure this is an 'output' type pin.
        self._enable_pin.switch_to_output()

class Synth(Sensor):
