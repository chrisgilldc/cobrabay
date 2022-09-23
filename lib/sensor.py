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
from time import monotonic

class Sensor:
    def __init__(self,board_options):
        # Each class should implement its own board setup method.
        self._setup_sensor(board_options)
        # Create a unit registry for the object.
        self._ureg = UnitRegistry()

    # Override this class in specific implementations
    def _setup_sensor(self,board_options):
        pass

    # Override this class in specific implementations to read the
    def read(self):
        pass

class VL53L1X(Sensor):
    _i2c_address: int
    _i2c_bus: int
    from VL53L1X import VL53L1X as pimoroni_vl53l1x

    def _setup_sensor(self,board_options):
        # Set a default log level if not defined.
        try:
            self._log_level = logging.getLevelName(board_options['log_level'])
        except:
            # Default to warning.
            self._log_level = logging.WARNING

        # Import libraries needed by the VL53L1X.
        import board
        import busio

        # Create a board object we can reference.
        self._board = board

        # Create access to the I2C bus
        try:
            self._i2c = busio.I2C(board.SCL, board.SDA)
        except:
            raise

        # Check for required options in
        options = ['i2c_bus','enable_board','enable_pin']
        # Store the options.
        for item in options:
            if item not in board_options:
                raise ValueError("Required board_option '{}' missing".format(item))
        # Set the properties
        self.i2c_bus = board_options['i2c_bus']
        self.enable_board = board_options['enable_board']
        self.enable_pin = board_options['enable_pin']
        if 'i2c_address' in board_options:
            self.i2c_address = board_options['i2c_address']
        # Start ranging.
        self._sensor_obj.start_ranging()
        self._previous_reading = self._sensor_obj.get_distance()
        self._previous_timestamp = monotonic()
        self._sensor_obj.stop_ranging()

    def start_ranging(self):
        self._sensor_obj.start_ranging()

    def stop_ranging(self):
        self._sensor_obj.stop_ranging()

    def enable(self):
        self.enable_pin.value = True

    def disable(self):
        self.enable_pin.value = False

    @property
    def distance_mode(self):
        if self._distance_mode == 1:
            return 'Short'
        elif self._distance_mode == 2:
            return 'Medium'
        elif self._distance_mode == 3:
            return 'Long'

    @distance_mode.setter
    def distance_mode(self,dm):
        # Pre-checking the distance mode lets us toss an error before actually setting anything.
        if dm.lower() == 'short':
            dm = 1
        elif dm.lower() == 'medium':
            dm = 2
        elif dm.lower() == 'long':
            dm = 3
        else:
            raise ValueError("{} is not a valid distance mode".format(dm))
        self._sensor_obj.set_distance_mode(dm)
        self._distance_mode = dm

    @property
    def range(self):
        # Make sure to pace the readings properly, so we're not over-running the native readings.
        # If a request comes in before the sleep time (200ms), return the previous reading.
        if monotonic() - self._previous_timestamp < 0.2:
            return self._previous_reading
        else:
            return Quantity(self._sensor_obj.get_distance(), self._ureg.millimeter)

    # Method to find out if an address is on the I2C bus.
    def _addr_on_bus(self,i2c_address):
        while not self._i2c.try_lock():
            pass
        found_addresses = self._i2c.scan()
        print("Addresses: {}".format(found_addresses))
        self._i2c.unlock()
        if i2c_address in found_addresses:
            return True
        else:
            return False

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
        # If it's in "0xYY" format, convert it to a base 16 int.
        if isinstance(i2c_address,str):
            i2c_address = int(i2c_address,base=16)

        # If the address is already on the bus...
        if self._addr_on_bus(i2c_address):
            # Disable ourselves and see if the address goes away.
            self.disable()
            if not self._addr_on_bus(i2c_address):
                # Disabling made the board go away! That means enable pin works and there are no other boards,
                # so we're good to go!
                self.enable()
                self._i2c_address = i2c_address
            else:
                raise ValueError("Address {} still on bus even after disabling board. "
                                 "Either address or enable pin is incorrect.".format(hex(i2c_address)))
        else:
            self.disable()
            # Disable the board, check if 0x29 is clear for a reset.
            if self._addr_on_bus("0x29"):
                raise ValueError("Another board is already on the VL53L1X default 0x29 address. Cannot continue")
            self.enable()
        from VL53L1X import VL53L1X as pimoroni_vl53l1x
        print("Creating sensor object.")
        self._sensor_obj = pimoroni_vl53l1x(self._i2c_bus, 0x29)
        print("Opening sensor object.")
        self._sensor_obj.open()
        print("Changing address.")
        print("Target i2c address: {}".format(hex(i2c_address)))
        self._sensor_obj.change_address(i2c_address)
        self._sensor_obj.close()
        self._sensor_obj.open()

    @property
    def enable_board(self):
        return self._enable_board

    @enable_board.setter
    def enable_board(self,enable_board):
        self._enable_board = enable_board

    @property
    def enable_pin(self):
        return self._enable_pin

    @enable_pin.setter
    def enable_pin(self, enable_pin):
        from digitalio import DigitalInOut
        # If enable_board is set to 0, then we try this on the Pi itself.
        if self.enable_board == 0:
            # Check to see if this is just a pin number.
            if isinstance(enable_pin,int):
                pin_name = 'D' + str(enable_pin)
            else:
                pin_name = enable_pin
            try:
                enable_pin_obj = DigitalInOut(getattr(self._board,pin_name))
            except:
                raise
            else:
                self._enable_pin = enable_pin_obj
        else:
            from adafruit_aw9523 import AW9523
            # Otherwise, treat enable_board as the address of an AW9523.
            try:
                aw = AW9523(self._i2c,self.enable_board)
            except:
                raise
            # Get the pin from the AW9523.
            self._enable_pin = aw.get_pin(enable_pin)
        # Make sure this is an 'output' type pin.
        self._enable_pin.switch_to_output()

    def shutdown(self):
        # Stop from ranging
        self.stop_ranging()
        # Close the object.
        self._sensor_obj.close()

# class Synth(Sensor):
# from .synthsensor import SynthSensor
