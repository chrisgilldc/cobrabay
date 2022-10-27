####
# Cobra Bay Sensors Module
####

import logging
import weakref
from time import monotonic, sleep

import board
import busio
from adafruit_aw9523 import AW9523
from adafruit_vl53l1x import VL53L1X as af_VL53L1X
from pint import Quantity
from pint import UnitRegistry
from .TFmini_I2C import TFminiI2C


class BaseSensor:
    def __init__(self,board_options):
        # Check for the Base I2C Sensors
        required = ('i2c_bus','i2c_address')
        for item in required:
            if item not in board_options:
                raise ValueError("Required board_option '{}' missing.".format(item))
        # Create a logger
        self._name = "{}-{}".format(type(self).__name__,hex(board_options['i2c_address']))
        self._logger = logging.getLogger("CobraBay").getChild("Sensors").getChild(self._name)
        self._logger.info("Initializing sensor...")

        # Set the I2C bus and I2C Address
        self._logger.debug("Setting I2C Properties...")
        self._i2c_bus = board_options['i2c_bus']
        self._i2c_address = board_options['i2c_address']

        # Create a unit registry for the object.
        self._ureg = UnitRegistry()

        # Sensor should call this init and then extend with its own options.
        # super().__init__(board_options)

    # Override this class in specific implementations
    def _setup_sensor(self,board_options):
        pass

    # Global properties. Since all supported sensors are I2C at the moment, these can be global.
    @property
    def i2c_bus(self):
        return self._i2c_bus

    @i2c_bus.setter
    def i2c_bus(self,input):
        if input not in (1,2):
            raise ValueError("I2C Bus ID for Raspberry Pi must be 1 or 2, not {}".format(input))
        else:
            self._i2c_bus = input

class CB_VL53L1X(BaseSensor):
    _i2c_address: int
    _i2c_bus: int

    instances = weakref.WeakSet()

    def __init__(self, board_options):
        # Call super.
        super().__init__(board_options)
        # Add self to instance list.
        self._enable_pin = None
        CB_VL53L1X.instances.add(self)
        self._performance = {
            'max_range': Quantity('4000mm'),
            'min_range': Quantity('30mm')
        }

    def _setup_sensor(self, board_options):
        # Set a default log level if not defined.
        try:
            self._log_level = logging.getLevelName(board_options['log_level'])
        except KeyError:
            # Default to warning.
            self._log_level = logging.WARNING

        # Create a board object we can reference.
        self._board = board

        # Create access to the I2C bus
        try:
            self._i2c = busio.I2C(board.SCL, board.SDA)
        except:
            raise

        # Check for required options in
        options = ['i2c_bus', 'i2c_address', 'enable_board', 'enable_pin']
        # Store the options.
        for item in options:
            if item not in board_options:
                raise ValueError("Required board_option '{}' missing".format(item))
        # Set the properties
        self.enable_board = board_options['enable_board']
        self.enable_pin = board_options['enable_pin']
        self.i2c_bus = board_options['i2c_bus']
        self.i2c_address = board_options['i2c_address']
        # Enable self.
        self.enable()

        # Start ranging.
        self._sensor_obj.start_ranging()
        # Set the timing.
        self.measurement_time = Quantity(board_options['timing']).to('microseconds').magnitude
        self.distance_mode = 'long'
        self._previous_reading = self._sensor_obj.distance
        self._previous_timestamp = monotonic()
        self._sensor_obj.stop_ranging()

    def start_ranging(self):
        self._sensor_obj.start_ranging()

    def stop_ranging(self):
        self._sensor_obj.stop_ranging()

    # Enable the sensor.
    def enable(self):
        # Set the pin true to turn on the board.
        self.enable_pin.value = True
        # Wait one second to make sure the bus has stabilized.
        sleep(1)
        i2c = busio.I2C(board.SCL, board.SDA)
        self._sensor_obj = af_VL53L1X(i2c, address=0x29)
        self._sensor_obj.set_address(self._i2c_address)

    def disable(self):
        self.enable_pin.value = False

    @property
    def timing_budget(self):
        return self._sensor_obj.timing_budget

    @timing_budget.setter
    def timing_budget(self, input):
        if int(input) not in (20, 33, 50, 100, 200, 500):
            raise ValueError("Requested timing budget {} not valid. "
                             "Must be one of: 20,33,50,100,200 or 500".format(input))
        self._sensor_obj.timing_budget(int(input))

    @property
    def distance_mode(self):
        if self._sensor_obj.distance_mode == 1:
            return 'Short'
        elif self._sensor_obj.distance_mode == 2:
            return 'Long'

    @distance_mode.setter
    def distance_mode(self, dm):
        # Pre-checking the distance mode lets us toss an error before actually setting anything.
        if dm.lower() == 'short':
            dm = 1
        elif dm.lower() == 'long':
            dm = 2
        else:
            raise ValueError("{} is not a valid distance mode".format(dm))
        self._sensor_obj.distance_mode = dm

    @property
    def range(self):
        # Make sure to pace the readings properly, so we're not over-running the native readings.
        # If a request comes in before the sleep time (200ms), return the previous reading.

        if monotonic() - self._previous_timestamp < 0.2:
            return self._previous_reading
        else:
            reading = self._sensor_obj.distance
            if reading is None:
                return None
            else:
                return Quantity(self._sensor_obj.distance, self._ureg.centimeter)

    # Method to find out if an address is on the I2C bus.
    def _addr_on_bus(self, i2c_address):
        while not self._i2c.try_lock():
            pass
        found_addresses = self._i2c.scan()
        self._i2c.unlock()
        if i2c_address in found_addresses:
            return True
        else:
            return False

    @property
    def i2c_address(self):
        return self._i2c_address

    @i2c_address.setter
    # Sets the address of the board. This presumes that we start from a place of all boards being shut off.
    def i2c_address(self, i2c_address):
        # If it's in "0xYY" format, convert it to a base 16 int.
        if isinstance(i2c_address, str):
            self._i2c_address = int(i2c_address, base=16)
        else:
            self._i2c_address = i2c_address

    @property
    def enable_board(self):
        return self._enable_board

    @enable_board.setter
    def enable_board(self, enable_board):
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
            if isinstance(enable_pin, int):
                pin_name = 'D' + str(enable_pin)
            else:
                pin_name = enable_pin
            try:
                enable_pin_obj = DigitalInOut(getattr(self._board, pin_name))
            except:
                raise
            else:
                self._enable_pin = enable_pin_obj
        else:
            # Otherwise, treat enable_board as the address of an AW9523.
            # Note that reset=False is very import, otherwise creating this object will reset all other pins to off!
            try:
                aw = AW9523(self._i2c, self.enable_board, reset=False)
            except:
                raise
            # Get the pin from the AW9523.
            self._enable_pin = aw.get_pin(enable_pin)
        # Make sure this is an 'output' type pin.
        self._enable_pin.switch_to_output()

    def shutdown(self):
        # Stop from ranging
        self.stop_ranging()

class TFMini(BaseSensor):
    def __init__(self, board_options):
        super().__init__(board_options)
        self._performance = {
            'max_range': Quantity('12m'),
            'min_range': Quantity('0.3m')
        }

    def _setup_sensor(self, board_options):
        self.max_range = Quantity('12m')
        options = ['i2c_bus','i2c_address']
        for item in options:
            if item not in board_options:
                raise ValueError("Required board_option '{}' missing.".format(item))