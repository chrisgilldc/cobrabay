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
from .tfmp import TFMP
from pathlib import Path


class BaseSensor:
    def __init__(self, sensor_options, required):
        self._settings = {}
        for item in required:
            if item not in sensor_options:
                raise ValueError("Required sensor_option '{}' missing.".format(item))

        # Create a unit registry for the object.
        self._ureg = UnitRegistry()

        # Initialize variables.
        self._previous_timestamp = monotonic()
        self._previous_reading = None

        # Sensor should call this init and then extend with its own options.
        # super().__init__(board_options)

    @property
    def range(self):
        raise NotImplementedError("Range should be overridden by specific sensor class.")


class I2CSensor(BaseSensor):
    def __init__(self, sensor_options):
        required = ('i2c_bus', 'i2c_address')
        try:
            super().__init__(sensor_options, required)
        except ValueError:
            raise
        # Check for the Base I2C Sensors
        # Create a logger
        self._name = "{}-{}-{}".format(type(self).__name__, sensor_options['i2c_bus'],
                                       hex(sensor_options['i2c_address']))
        self._logger = logging.getLogger("CobraBay").getChild("Sensors").getChild(self._name)
        self._logger.setLevel("WARNING")
        self._logger.info("Initializing sensor...")

        # Set the I2C bus and I2C Address
        self._logger.debug("Setting I2C Properties...")
        self.i2c_bus = sensor_options['i2c_bus']
        self.i2c_address = sensor_options['i2c_address']
        self._logger.debug("Now have I2C Bus {} and Address {}".format(self.i2c_bus, hex(self.i2c_address)))

    # Global properties. Since all supported sensors are I2C at the moment, these can be global.
    @property
    def i2c_bus(self):
        return self._i2c_bus

    @i2c_bus.setter
    def i2c_bus(self, input):
        if input not in (1, 2):
            raise ValueError("I2C Bus ID for Raspberry Pi must be 1 or 2, not {}".format(input))
        else:
            self._i2c_bus = input

    @property
    def i2c_address(self):
        return self._i2c_address

    @i2c_address.setter
    # Stores the address of the board. Does *not* necesarially apply it to the board to update it.
    def i2c_address(self, i2c_address):
        # If it's in "0xYY" format, convert it to a base 16 int.
        if isinstance(i2c_address, str):
            self._i2c_address = int(i2c_address, base=16)
        else:
            self._i2c_address = i2c_address


class SerialSensor(BaseSensor):
    def __init__(self, sensor_options):
        required = ('port', 'baud')
        try:
            super().__init__(sensor_options, required)
        except ValueError:
            raise
        # Create a logger
        self._name = "{}-{}".format(type(self).__name__, sensor_options['port'])
        self._logger = logging.getLogger("CobraBay").getChild("Sensors").getChild(self._name)
        self._logger.info("Initializing sensor...")
        self._logger.setLevel("WARNING")
        self.serial_port = sensor_options['port']
        self.baud_rate = sensor_options['baud']

    @property
    def serial_port(self):
        return self._settings['serial_port']

    @serial_port.setter
    def serial_port(self, target_port):
        port_path = Path(target_port)
        # Check if this path as given as "/dev/XXX". If not, redo with that.
        if not port_path.is_absolute():
            port_path = Path("/dev/" + target_port)
        # Make sure the path is a device we can access.
        if port_path.is_char_device():
            self._settings['serial_port'] = str(port_path)
        else:
            raise ValueError("{} is not an accessible character device.".format(str(port_path)))

    @property
    def baud_rate(self):
        return self._settings['baud_rate']

    @baud_rate.setter
    def baud_rate(self, target_rate):
        self._settings['baud_rate'] = target_rate


class CB_VL53L1X(I2CSensor):
    _i2c_address: int
    _i2c_bus: int

    instances = weakref.WeakSet()

    def __init__(self, sensor_options):
        # Call super.
        super().__init__(sensor_options)
        # Check for additional required options.
        required = ['i2c_bus', 'i2c_address', 'enable_board', 'enable_pin']
        # Store the options.
        for item in required:
            if item not in sensor_options:
                raise ValueError("Required board_option '{}' missing".format(item))

        # Define the enable pin.
        self._enable_pin = None

        # Add self to instance list.

        CB_VL53L1X.instances.add(self)
        self._performance = {
            'max_range': Quantity('4000mm'),
            'min_range': Quantity('30mm')
        }

        # Create a board object we can reference.
        self._board = board
        # Create access to the I2C bus
        try:
            self._i2c = busio.I2C(board.SCL, board.SDA)
        except ValueError:
            raise

        # Set the properties
        self.enable_board = sensor_options['enable_board']
        self.enable_pin = sensor_options['enable_pin']
        self.i2c_bus = sensor_options['i2c_bus']
        self.i2c_address = sensor_options['i2c_address']
        # Enable self.
        self.enable()

        # Start ranging.
        self._sensor_obj.start_ranging()
        # Set the timing.
        self.measurement_time = Quantity(sensor_options['timing']).to('microseconds').magnitude
        self.distance_mode = 'long'
        self._previous_reading = self._sensor_obj.distance
        self._logger.debug("Test reading: {}".format(self._previous_reading))
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
            # A "none" means the sensor had no response.
            if reading is None:
                return "No reading"
            else:
                reading = Quantity(reading, self._ureg.centimeter)
                self._previous_reading = reading
                self._previous_timestamp = monotonic()
                return self._previous_reading

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


class TFMini(SerialSensor):
    def __init__(self, sensor_options):
        super().__init__(sensor_options)
        self._performance = {
            'max_range': Quantity('12m'),
            'min_range': Quantity('0.3m')
        }

        # Create the sensor object.
        self._logger.debug("Creating TFMini object on serial port {}".format(self.serial_port))
        self._sensor_obj = TFMP(self.serial_port, self.baud_rate)
        self._logger.debug("Test reading: {}".format(self.range))

    # This sensor doesn't need an enable, do nothing.
    def enable(self):
        return True

    # Likewise, we don't need to disable, do nothing.
    def disable(self):
        return True

    @property
    def range(self):
        # TFMini is always ranging, so no need to pace it.
        reading = self._clustered_read() # Do a clustered read to ensure stability.
        self._logger.debug("TFmini read values: {}".format(reading))
        # Check the status to see if we got a value, or some kind of non-OK state.
        if reading.status == "OK":
            self._previous_reading = reading.distance
            self._previous_timestamp = monotonic()
            return self._previous_reading
        else:
            return reading.status

    # When this was tested in I2C mode, the TFMini could return unstable answers, even at rest. Unsure if
    # this is still true in serial mode, keeping this clustering method for the moment.
    def _clustered_read(self):
        stable_count = 0
        i = 0
        previous_read = self._sensor_obj.data()
        start = monotonic()
        while stable_count < 5:
            reading = self._sensor_obj.data()
            if reading.distance == previous_read.distance:
                stable_count += 1
            previous_read = reading
            i += 1
        self._logger.debug("Took {} cycles in {}s to get stable reading of {}.".format(i, round(monotonic() - start,2), previous_read))
        return previous_read
