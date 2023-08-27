####
# Cobra Bay Sensors Module
####

import logging
from weakref import WeakValueDictionary, WeakSet
from time import monotonic, monotonic_ns, sleep
from math import floor
import board
import busio
import csv
from adafruit_aw9523 import AW9523
from adafruit_vl53l1x import VL53L1X as af_VL53L1X
from pint import Quantity
from pint import UnitRegistry
from .tfmp import TFMP
from pathlib import Path
from pprint import pformat
import sys
import CobraBay.const
import CobraBay.exceptions
import CobraBay.util


class BaseSensor:
    def __init__(self, sensor_name, parent_logger=None, log_level="WARNING"):
        """
        Base class for Sensors.

        :param sensor_name:
        :param parent_logger: Parent logger to attach to.
        :type parent_logger: logger
        :param log_level: If no parent logger provided, log level of the new logger to create.
        :type log_level: str
        """

        # Create a unit registry for the object.
        self._ureg = UnitRegistry()

        # Set up the logger.
        if parent_logger is None:
            # If no parent detector is given this sensor is being used in a testing capacity. Create a null logger.
            self._logger = logging.getLogger(self._name)
            self._logger.setLevel(log_level)
        else:
            self._logger = parent_logger.getChild(self._name)

        # Initialize variables.
        self._previous_timestamp = monotonic()
        self._previous_reading = None
        self._requested_status = None
        self._status = None

    @property
    def range(self):
        raise NotImplementedError("Range should be overridden by specific sensor class.")

    @property
    def state(self):
        raise NotImplementedError("State should be overridden by specific sensor class.")
        
    @property
    def status(self):
        """
        Read the sensor status.  This is the requested status. It may not be the state if there have been intervening errors.
        :return: str
        """
        return self._status

    @status.setter
    def status(self, target_status):
        """
        Standard method to set a sensor status. This should generally only be called by the
        :param target_status: One of 'enable', 'disable', 'ranging'
        :type target_status: str
        :return:
        """
        if target_status not in ('disabled', 'enabled', 'ranging'):
            raise ValueError("Target status '{}' not valid".format(target_status))
        if target_status == 'disabled':
            try:
                self._disable()
            except BaseException as e:
                self._logger.error("Could not disable.")
                self._logger.exception(e)
            else:
                self._logger.debug("Status is now 'disabled'")
                self._status = 'disabled'
        elif target_status == 'enabled':
            # If returning to enabled from ranging, only need to stop ranging.
            if self._status == 'ranging':
                try:
                    self._stop_ranging()
                except BaseException as e:
                    self._logger.error("Could not stop ranging while changing to status 'enabled'")
                    self._logger.exception(e)
                else:
                    self._logger.debug("Status is now 'enabled'")
                    self._status = 'enabled'
            else:
                try:
                    self._enable()
                except BaseException as e:
                    self._logger.error("Could not enable.")
                    self._logger.exception(e)
                else:
                    self._logger.debug("Status is now 'enabled'")
                    self._status = 'enabled'
        elif target_status == 'ranging':
            # If sensor is disabled, enable before going straight to ranging.
            if self._status == 'disabled':
                try:
                    self._enable()
                except CobraBay.exceptions.SensorException as e:
                    self._logger.error("Could not perform implicit enable while changing status to ranging.")
                    self._logger.exception(e)
                    return
                else:
                    self._logger.debug("Successfully completed implicit enable to allow change to ranging")
            try:
                self._start_ranging()
            except TypeError as e:
                self._logger.warning("Could not start ranging. Sensor returned value that could not be interpreted.")
            except BaseException as e:
                self._logger.error("Could not start ranging.")
                self._logger.exception(e)
            else:
                self._logger.debug("Status is now ranging.")
                self._status = 'ranging'

    # Dummy methods for the status setter. These should be overridden by specific sensor class implementations.
    # Turn off the sensor.
    def _enable(self):
        return

    # Shut off the sensor.
    def _disable(self):
        return

    # Start actively returning readings.
    def _start_ranging(self):
        raise NotImplementedError("Start Ranging method must be implemented by cose class.")

    # Stop the sensor from ranging but leave it enabled.
    def _stop_ranging(self):
        raise NotImplementedError("Stop Ranging method must be implemented by core sensor class.")

class I2CSensor(BaseSensor):
    aw9523_boards = {}
    def __init__(self, i2c_bus, i2c_address, parent_logger=None, log_level="WARNING"):
        """

        :param i2c_bus: I2C Bus to use
        :type i2c_bus: int
        :param i2c_address: Address of the sensor.
        :type i2c_address: int or str(hex)
        :param parent_logger: Parent logger to attach to.
        :type parent_logger: logger
        :param log_level: If no parent logger provided, log level of the new logger to create.
        :type log_level: str
        """
        # Define our own name based on class name, bus and address.
        self._name = "{}-{}-{}".format(type(self).__name__, i2c_bus, hex(i2c_address))
        # Do base sensor initialization
        try:

            super().__init__(sensor_name=self._name, parent_logger=parent_logger, log_level=log_level)
        except ValueError:
            raise

        # Create a logger
        self._logger.info("Initializing sensor...")

        # Set the I2C bus and I2C Address
        self.i2c_bus = i2c_bus
        self.i2c_address = i2c_address
        self._logger.debug("Configured for I2C Bus {} and Address {}".format(self.i2c_bus, hex(self.i2c_address)))

        # How many times, in the lifetime of the sensor, have we hit a fault.
        self._lifetime_faults = 0
        # Set if the sensor hit a fault, recovered, but hasn't yet succeeded in re-reading. If it faults *again*, bomb.
        self._last_chance = False

    # Global properties.

    @property
    def name(self):
        """ Sensor Name, derived from type, bus, address. """
        return self._name

    @property
    def i2c_bus(self):
        return self._i2c_bus

    @i2c_bus.setter
    def i2c_bus(self, the_input):
        if the_input not in (1, 2):
            raise ValueError("I2C Bus ID for Raspberry Pi must be 1 or 2, not {}".format(the_input))
        else:
            self._i2c_bus = the_input

    @property
    def i2c_address(self):
        return self._i2c_address

    @i2c_address.setter
    # Stores the address of the board. Does *not* necessarily apply it to the board to update it.
    def i2c_address(self, i2c_address):
        # If it's in "0xYY" format, convert it to a base 16 int.
        if isinstance(i2c_address, str):
            self._i2c_address = int(i2c_address, base=16)
        else:
            self._i2c_address = i2c_address


class SerialSensor(BaseSensor):
    def __init__(self, port, baud, parent_logger=None, log_level="WARNING"):
        """
        :type port: str
        :type baud: int
        :type parent_logger: str
        :param parent_logger: Parent logger to attach to.
        :type parent_logger: logger
        :param log_level: If no parent logger provided, log level of the new logger to create.
        :type log_level: str
        """
        # Define our own name, based on type name and port.
        self._name = "{}-{}".format(type(self).__name__, port)
        # To base sensor initialization.
        try:
            super().__init__(sensor_name=self._name, parent_logger=parent_logger, log_level=log_level)
        except ValueError:
            raise
        self._logger.info("Initializing sensor...")
        self._serial_port = None
        self._baud_rate = None
        self.serial_port = port
        self.baud_rate = baud

    @property
    def serial_port(self):
        return self._serial_port

    @serial_port.setter
    def serial_port(self, target_port):
        port_path = Path(target_port)
        # Check if this path as given as "/dev/XXX". If not, redo with that.
        if not port_path.is_absolute():
            port_path = Path("/dev/" + target_port)
        # Make sure the path is a device we can access.
        if port_path.is_char_device():
            self._serial_port = str(port_path)
        else:
            raise ValueError("{} is not an accessible character device.".format(str(port_path)))

    @property
    def baud_rate(self):
        return self._baud_rate

    @baud_rate.setter
    def baud_rate(self, target_rate):
        self._baud_rate = target_rate

    @property
    def name(self):
        """ Sensor name, type-port """
        return self._name

class CB_VL53L1X(I2CSensor):
    _i2c_address: int
    _i2c_bus: int

    instances = WeakSet()

    def __init__(self, i2c_bus, i2c_address, enable_board, enable_pin, timing, distance_mode='long',
                 parent_logger=None, log_level="WARNING"):
        """
        :type i2c_bus: int
        :type i2c_address: hex
        :type enable_board: str
        :type enable_pin: str
        :param parent_logger: Parent logger to attach to.
        :type parent_logger: logger
        :param log_level: If no parent logger provided, log level of the new logger to create.
        :type log_level: str
        """
        try:
            super().__init__(i2c_bus=i2c_bus, i2c_address=i2c_address, parent_logger=parent_logger, log_level=log_level)
        except ValueError:
            raise

        # Create board and I2C bus objects.
        self._board = board
        # Create access to the I2C bus
        try:
            self._i2c = busio.I2C(board.SCL, board.SDA)
        except PermissionError as e:
            self._logger.warning("No access to I2C Bus.")
            raise e

        # Initialize variables.
        self._sensor_obj = None  # Sensor object from base library.
        self._ranging = False  # Ranging flag. The library doesn't actually store this!
        self._fault = False # Sensor fault state.
        self._status = 'disabled'  # Requested state of the sensor externally.
        self._distance_mode = distance_mode  # Distance mode.

        # Save the input parameters.
        self.timing_budget = timing  # Timing budget
        self.enable_board = enable_board  # Board where the enable pin is.
        self.enable_pin = enable_pin  # Pin for enabling.
        self._enable_attempt_counter = 1
        
        # Add self to instance list.
        CB_VL53L1X.instances.add(self)
        # In principle, will use this in the future.
        self._performance = {
            'max_range': Quantity('4000mm'),
            'min_range': Quantity('30mm')
        }

        # Enable the sensor.
        self.status = 'enabled'
        # Get a test reading.
        self.status = 'ranging'    # Start ranging.
        self.measurement_time = Quantity(timing).to('microseconds').magnitude
        self.distance_mode = 'long'
        test_range = self.range
        self._logger.debug("Test reading: {} ({})".format(test_range, type(test_range)))
        self._logger.debug("Setting status back to enabled, stopping ranging.")
        self.status = 'enabled'
        self._logger.debug("Initialization complete.")

    def _start_ranging(self):
        self._logger.debug("Starting ranging")
        try:
            self._sensor_obj.start_ranging()
        except AttributeError as e:
            self._logger.error("Cannot start ranging on sensor.")
            raise e
        else:
            self._ranging = True
            # Get new readings.
            try:
                self._previous_reading = Quantity(self._sensor_obj.distance, 'cm')
            except TypeError:
                if self._sensor_obj.distance is None:
                    self._previous_reading = None
                else:
                    raise
            self._previous_timestamp = monotonic()

    def _stop_ranging(self):
        self._logger.debug("Stopping ranging.")
        try:
            self._sensor_obj.stop_ranging()
        except:
            raise
        else:
            self._ranging = False

    # Enable the sensor.
    def _enable(self):
        # Shut off the sensor
        self.enable_pin.value = False
        devices_prior = CobraBay.util.scan_i2c()
        self._logger.debug("I2C devices before enable: {}".format(devices_prior))
        # Turn the sensor back on.
        self.enable_pin.value = True
        # Wait one second for the bus to stabilize
        sleep(1)
        devices_subsequent = CobraBay.util.scan_i2c()
        self._logger.debug("I2C devices after enable: {}".format(devices_subsequent))
        if len(devices_subsequent) > len(devices_prior):
            # Create the sensor at the default address.
            try:
                self._sensor_obj = af_VL53L1X(self._i2c, address=0x29)
            except ValueError:
                self._logger.error("Sensor not found at default address '0x29'. Check for configuration and hardware errors!")
            else:
                # Change the I2C address to the target address.
                self._sensor_obj.set_address(new_address=self._i2c_address)
                # Make sure fault isn't set, if we're recovering from failure.
                self._fault = False
                return
        else:
            self._logger.error("Device did not appear on I2C bus! Check configuration and for hardware errors.")

        if self._enable_attempt_counter >= 3:
            self._logger.error("Could not enable sensor after {} attempts. Marking as faulty.".format(self._enable_attempt_counter))
            self._fault = True
            raise CobraBay.exceptions.SensorException
        else:
            self._logger.warning("Could not enable sensor on attempt {}. Disabling and retrying.".format(self._enable_attempt_counter))
            self._enable_attempt_counter += 1
            self._disable()
            self._enable()

    def _disable(self):
        self.enable_pin.value = False
        # Also set the internal ranging variable to false, since by definition, when the board gets killed, we stop ranging.
        self._ranging = False

    @property
    def timing_budget(self):
        if self._sensor_obj is not None:
            return Quantity(self._sensor_obj.timing_budget, 'ms')
        elif self._timing_budget is not None:
            return Quantity(self._timing_budget, 'ms')
        else:
            return Quantity('100 ms')

    @timing_budget.setter
    def timing_budget(self, timing_input):
        if not isinstance(timing_input, Quantity):
            timing_input = Quantity(timing_input).to('ms')
        if timing_input.magnitude not in (20, 33, 50, 100, 200, 500):
            raise ValueError("Requested timing budget {} not valid. "
                             "Must be one of: 20, 33, 50, 100, 200 or 500 ms".format(input))
        # Save the timing budget.
        self._timing_budget = timing_input.magnitude
        # If object is initialized, set immediately.
        if self._sensor_obj is not None:
            self._sensor_obj.timing_budget(timing_input.magnitude)

    @property
    def distance_mode(self):
        if not self._fault:
            if self._sensor_obj.distance_mode == 1:
                return 'Short'
            elif self._sensor_obj.distance_mode == 2:
                return 'Long'
        else:
            return 'Fault'

    @distance_mode.setter
    def distance_mode(self, dm):
        if not self._fault:
            # Pre-checking the distance mode lets us toss an error before actually setting anything.
            if dm.lower() == 'short':
                dm = 1
            elif dm.lower() == 'long':
                dm = 2
            else:
                raise ValueError("{} is not a valid distance mode".format(dm))
            self._distance_mode = dm
            self._sensor_obj.distance_mode = dm

    @property
    def range(self):
        self._logger.debug("Range requsted. Sensor state is: {}".format(self.state))
        if self.state != 'ranging':
            return CobraBay.const.SENSTATE_NOTRANGING
        elif monotonic() - self._previous_timestamp < 0.2:
            # Make sure to pace the readings properly, so we're not over-running the native readings.
            # If a request comes in before the sleep time (200ms), return the previous reading.
            return self._previous_reading
        else:
            # If the sensor doesn't have data ready yet, return the previous reading.
            if not self._sensor_obj.data_ready:
                return self._previous_reading
            else:
                reading = self._recoverable_reading()
                self._sensor_obj.clear_interrupt()

            # else:
            if reading is None:
                # The Adafruit VL53L1X wraps up all invalid statuses with a 'None' return. See
                # https://github.com/adafruit/Adafruit_CircuitPython_VL53L1X/pull/8 for details.
                self._previous_reading = CobraBay.const.SENSOR_VALUE_WEAK
            elif reading <= 4:
                self._logger.debug("Reading is less than 4cm. Too close to be realiable.")
                return CobraBay.const.SENSOR_VALUE_TOOCLOSE
            else:
                self._previous_reading = Quantity(reading, 'cm')
            self._previous_timestamp = monotonic()
            return self._previous_reading

    def _recoverable_reading(self):
        '''
        Get the distance reading from the VL53L1X sensor, and attempt auto-recovery if there's an error.

        :return: float
        '''

        try:
            reading = self._sensor_obj.distance
        except OSError as e:
            # Try to recover from sensor fault.
            self._logger.critical("Attempt to read sensor threw error: {}".format(str(e)))
            self._lifetime_faults = self._lifetime_faults + 1
            self._logger.critical("Lifetime faults are now: {}".format(self._lifetime_faults))
            hex_list = []
            for address in self._i2c.scan():
                hex_list.append(hex(address))
            self._logger.debug("Current I2C bus: {}".format(hex_list))
            # Decide on the last chance.
            if self._last_chance:
                self._logger.critical("This was the last chance. No more!")
                if self._logger.isEnabledFor(logging.DEBUG):
                    self._logger.debug("I2C Bus Scan:")
                    hex_list = []
                    for address in self._i2c.scan():
                        hex_list.append(hex(address))
                    self._logger.debug("Current I2C bus: {}".format(hex_list))
                    self._logger.debug("Object Dump:")
                    self._logger.debug(pformat(dir(self._sensor_obj)))
                self._logger.critical("Cannot continue. Exiting.")
                sys.exit(1)
            else:  # Still have a last chance....
                self._last_chance = True
                hex_list = []
                for address in self._i2c.scan():
                    hex_list.append(hex(address))
                self._logger.debug("I2C bus after fault: {}".format(hex_list))
                self._logger.debug("Resetting sensor to recover...")
                # Disable the sensor.
                self._disable()
                # Re-enable the sensor. This will re-enable the sensor and put it back at its correct address.
                self._enable()
                hex_list = []
                for address in self._i2c.scan():
                    hex_list.append(hex(address))
                self._logger.debug("I2C bus after re-enabling: {}".format(hex_list))
        else:
            return reading


    # Not actually using this method, because it doesn't account for the sensor's timing budget. We wind up hitting the
    # sensor within the same timing budget window and just get the same value back five times.
    # # Method to get an average and stabilize the sensor.
    # def _read_average(self):
    #     readings = []
    #     start = monotonic()
    #     i = 0
    #     while len(readings) < 5:
    #         try:
    #             new_reading = self._sensor_obj.distance
    #         except OSError as e:
    #             self._logger.critical("Attempt to read sensor returned error: {}".format(str(e)))
    #             self._lifetime_faults += 1
    #             self._logger.critical("Lifetime faults are now: {}".format(self._lifetime_faults))
    #             hex_list = []
    #             for address in self._i2c.scan():
    #                 hex_list.append(hex(address))
    #             self._logger.critical("I2C Bus after error: {}".format(hex_list))
    #             # Do last_chance logic.
    #         else:
    #             readings.append(new_reading)
    #             i += 1
    #     self._logger.debug("Averaging readings: {}".format(readings))
    #     average = sum(readings) / 5
    #     self._logger.debug("Took {} cycles in {}s to get stable reading of {}.".
    #                        format(i, round(monotonic() - start, 2), average))
    #     return average

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
            # Check to see if the AW9523 object has already been created.
            # Use the key format "bus-addr"
            awkey = str(self.i2c_bus) + "-" + str(self.enable_board)
            if awkey not in self.__class__.aw9523_boards.keys():
                self._logger.info("Establishing access to AW9523 board on bus {}, address 0x{:x}".
                                  format(self.i2c_bus, self.enable_board))
                # Need to create the board.
                try:
                    self.__class__.aw9523_boards[awkey] = AW9523(self._i2c, self.enable_board, reset=True)
                except BaseException as e:
                    self._logger.critical("Could not access AW9523 on bus {}, address 0x{:x}".
                                          format(self.i2c_bus, self.enable_board))
                    raise e
                else:
                    CobraBay.util.aw9523_reset(self.__class__.aw9523_boards[awkey])
            # Can now create the pin
            self._enable_pin = self.__class__.aw9523_boards[awkey].get_pin(enable_pin)

            # # Otherwise, treat enable_board as the address of an AW9523.
            # # Note that reset=False is very import, otherwise creating this object will reset all other pins to off!
            # try:
            #     aw = AW9523(self._i2c, self.enable_board, reset=False)
            # except BaseException as e:
            #     self._logger.critical("Could not access AW9523 board.")
            #     raise e
            # # Get the pin from the AW9523.
            #self._enable_pin = aw.get_pin(enable_pin)
        # Make sure this is an 'output' type pin.
        self._enable_pin.switch_to_output()

    @property
    def state(self):
        """
        The current state of the sensor. This is what is actually happening, not necessarily what has been requested.
        :return: str
        """
        # If sensor is actively ranging, check for active vs. error states. These are VL53L1X specific
        self._logger.debug("Evaluating state...")
        if self._fault is True:
            # Fault while enabling.
            self._logger.debug("Fault found.")
            return CobraBay.const.SENSTATE_FAULT
        elif self.enable_pin.value is True:
            self._logger.debug("Enable pin is on.")
            if self._ranging is True:
                self._logger.debug("Sensor has been recorded as ranging.")
                return CobraBay.const.SENSTATE_RANGING
            else:
                self._logger.debug("Enabled, not ranging.")
                return CobraBay.const.SENSTATE_ENABLED
        elif self.enable_pin.value is False:
                self._logger.debug("Enable pin is off.")
                return CobraBay.const.SENSTATE_DISABLED
        else:
            raise CobraBay.exceptions.SensorException

class TFMini(SerialSensor):
    def __init__(self, port, baud, parent_logger=None, log_level="WARNING"):
        """

        :param port: Serial port
        :type port: str OR Path
        :param baud: Bitrate for the sensor.
        :type baud: int
        :param parent_logger: Parent logger to attach to.
        :type parent_logger: logger
        :param log_level: If no parent logger provided, log level of the new logger to create.
        :type log_level: str
        """
        try:
            super().__init__(port=port, baud=baud, parent_logger=parent_logger,  log_level=log_level)
        except ValueError:
            raise

        self._performance = {
            'max_range': Quantity('12m'),
            'min_range': Quantity('0.3m')
        }

        # Create the sensor object.
        self._logger.debug("Creating TFMini object on serial port {}".format(self.serial_port))
        self._sensor_obj = TFMP(self.serial_port, self.baud_rate)
        self._logger.debug("Test reading: {} ({})".format(self.range, type(self.range)))

    # TFMini is always ranging, so enable here is just a dummy method.
    @staticmethod
    def enable():
        return True

    # Likewise, we don't need to disable, do nothing.
    @staticmethod
    def disable():
        return True

    @property
    def range(self):
        # TFMini is always ranging, so no need to pace it.
        reading = self._clustered_read()  # Do a clustered read to ensure stability.
        self._logger.debug("TFmini read values: {}".format(reading))
        # Check the status to see if we got a value, or some kind of non-OK state.
        if reading.status == "OK":
            self._previous_reading = reading.distance
            self._previous_timestamp = monotonic()
            return self._previous_reading
        elif reading.status == "Weak":
            return CobraBay.const.SENSOR_VALUE_WEAK
        elif reading.status in ("Flood", "Saturation"):
            return CobraBay.const.SENSOR_VALUE_FLOOD
        else:
            raise CobraBay.exceptions.SensorException("TFMini sensor '{}' had unexpected reading '{}'".
                                                      format(self._name, reading))

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
        self._logger.debug("Took {} cycles in {}s to get stable reading of {}.".
                           format(i, round(monotonic() - start, 2), previous_read))
        return previous_read

    # State of the sensor.
    @property
    def state(self):
        """
        State of the sensor.
        :return: str
        """
        reading = self._sensor_obj.data()
        if reading.status == 'OK':
            return CobraBay.const.SENSOR_VALUE_OK
        elif reading.status == 'Weak':
            return CobraBay.const.SENSOR_VALUE_WEAK
        elif reading.status == 'Flood':
            return CobraBay.const.SENSOR_VALUE_FLOOD
        elif reading.status == 'Strong':
            return CobraBay.const.SENSOR_VALUE_STRONG
        else:
            raise CobraBay.exceptions.SensorException("TFMini sensor '{}' returned unexpected reading '{}'".
                                                      format(self._name,reading))

    @property
    def status(self):
        """
        Status of the TFMini Sensor.

        The TFMini always ranges when it's powered on, thus this status always returns "ranging"

        :return:
        """
        # The TFMini always ranges, so we can just return ranging.
        return CobraBay.const.SENSTATE_RANGING

    @status.setter
    def status(self, target_status):
        """
        Set the status of the TFMini Sensor.

        The TFMini always ranges when it's powered on, thus any input is ignored. The sensor will always range.
        :param target_status:
        :return:
        """
        pass

    @property
    def timing_budget(self):
        # The TFMini's default update rate is 100 Hz. 1s = 1000000000 ns / 100 = 10000000 ns.
        # This is static and assuming it hasn't been changed, so return it.
        return Quantity('10000000 ns')

class FileSensor(BaseSensor):
    def __init__(self, csv_file, sensor, rate, direction, unit, parent_logger=None, log_level='WARNING'):
        """

        :param csv_file: File to read
        :type csv_file: str
        :param sensor:
        :param rate:
        :param direction:
        :param unit:
        :param parent_logger: Parent logger to create a child of.
        :type parent_logger: logger
        :param log_level: If no parent logger provided, log level of the new logger to create.
        """
        try:
            super().__init__(parent_logger=parent_logger, log_level=log_level)
        except ValueError:
            raise

        # Create the sensor name, based on the file.
        self._name = 'FileSensor-' + Path(csv_file).stem + '-' + sensor
        self._logger = logging.getLogger("CobraBay").getChild("Sensors").getChild(self._name)
        self._logger.info("Initializing sensor...")
        self._logger.setLevel(log_level)
        self._source_file = Path(csv_file)
        self._logger.info("Loading file '{}'".format(self._source_file))

        try:
            with open(self._source_file) as source_file:
                reader = csv.DictReader(source_file, delimiter=",")
                self._data = list(reader)
                self._logger.info("Found data headers: {}".format(reader.fieldnames))
        except:
            raise

        self._rate = Quantity(rate)
        self._direction = direction
        self._sensor = sensor
        self._unit = unit

    def file(self):
        return self._source_file

    def name(self):
        return self._name

    @property
    def range(self):
        if self._time_mark is not None:
            motion_time = Quantity(monotonic_ns() - self._time_mark,'ns').to('ms')
            index = floor( motion_time / self._rate )
        else:
            motion_time = None
            index = 1
        try:
            value = self._data[index][self._sensor]
        except IndexError:
            return 'unknown'
        self._logger.debug("Motion time {}, Index {}, Value {}".format(motion_time, index, value))
        try:
            value = float(value)
        except ValueError:
            pass
        else:
            value = Quantity(value, self._unit)
        return value

    @property
    def state(self):
        # IF the file loaded, we're ranging, by definition.
        return CobraBay.const.SENSOR_VALUE_RANGING

    def _start_ranging(self):
        self._logger.debug("Starting ranging.")
        self._time_mark = monotonic_ns()

    def _stop_ranging(self):
        self._time_mark = None

    @property
    def timing_budget(self):
        return self._rate