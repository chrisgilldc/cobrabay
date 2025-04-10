####
# Cobra Bay Sensor - VL53L1X
####
#
# VL53L1X range sensor, accessed via I2C. All sensors of this type default to address 0x28. When using multiple, they
# must be enabled one at a time and configured to their correct address.
import board
import busio
import digitalio
# The I2CSensor class
from cobrabay.sensors import I2CSensor
# Required Cobra Bay datatypes
from cobrabay.datatypes import SensorReading
import cobrabay.util
# Import WeakSet so we can track other instances.
from weakref import WeakSet
# Core sensor library.
import adafruit_vl53l1x
# IO Expander
import adafruit_aw9523
# General libraries
from pint import Quantity
from time import monotonic, monotonic_ns, sleep
from numpy import datetime64


class CBVL53L1X(I2CSensor):
    _i2c_address: int
    _i2c_bus: int

    instances = WeakSet()

    def __init__(self, name, i2c_address, enable_board, enable_pin, i2c_bus,
                 timing=200, always_range=False, distance_mode='long', max_retries=0,
                 parent_logger=None, log_level="WARNING"):
        """
        :param name: Name of this sensor.
        :type name: str
        :type i2c_address: int
        :param enable_board: Board to use for enabling the sensor.
        :type enable_board: int or adafruit_aw9523.AW9523
        :param enable_pin: Pin to turn the sensor on and off.
        :type enable_pin: int or str
        :param i2c_bus: I2C bus object
        :type i2c_bus: busio.I2C
        :param timing: Initial timing of the sensor.
        :type timing: int or Quantity('ms')
        :param max_retries: Maximum number of retries before the sensor is marked as in fault.
        :type max_retries: int
        :param parent_logger: Parent logger to attach to.
        :type parent_logger: logger
        :param log_level: If no parent logger provided, log level of the new logger to create.
        :type log_level: str
        """

        try:
            super().__init__(name=name, i2c_address=i2c_address, i2c_bus=i2c_bus, max_retries=max_retries,
                             parent_logger=parent_logger, log_level=log_level)
        except ValueError:
            raise

        # Initialize variables.
        self._sensor_obj = None  # Sensor object from base library.
        self._ranging = False  # Ranging flag. The library doesn't actually store this!
        self._fault = False  # Sensor fault state.
        self._status = 'disabled'  # Requested state of the sensor externally.
        self._board = board

        # Save the input parameters.
        self.timing_budget = timing  # Timing budget
        self._distance_mode = distance_mode  # Distance mode.
        self.enable_board = enable_board
        self.enable_pin = enable_pin  # Pin for enabling.
        self._logger.debug("Saved enable pin: {}".format(self._enable_pin._pin))
        self._enable_attempt_counter = 1

        # Add self to instance list.
        CBVL53L1X.instances.add(self)

        # In principle, will use this in the future.
        # self._performance = {
        #     'max_range': Quantity('4000mm'),
        #     'min_range': Quantity('30mm')
        # }

        # Enable the sensor.
        self.status = 'enabled'
        # Get a test reading.
        self.status = 'ranging'  # Start ranging.
        self.distance_mode = 'long'
        test_range = self.reading(wait=True)
        self._logger.debug("Test reading: {} ({})".format(test_range, type(test_range)))
        if not always_range:
            self._logger.debug("Setting status back to enabled, stopping ranging.")
            self.status = 'enabled'
        else:
            self._logger.info("Sensor set to always range. Keeping in ranging state.")
        self._logger.debug("Initialization complete.")

    # Public Methods
    @property
    def data_ready(self):
        """Interrupt status for data readiness of the sensor."""
        try:
            return self._sensor_obj.data_ready
        except OSError:
            self._logger.warning("Received exception when checking interrupt.")
            return False

    @property
    def clear_interrupt(self):
        """ Clear the interrupt on the sensor"""
        attempts = 0
        while True:
            try:
                self._sensor_obj.clear_interrupt
            except OSError as e:
                if attempts > 5:
                    self._logger.critical("Could not clear interrupt after 5 attempts")
                    raise e
                else:
                    attempts += 1
            else:
                return

    def reading(self, wait=False):
        """
        Get the current range reading of the sensor.

        :param wait: Wait for interrupt to return. Will be up to self.timing_budget milliseconds.
        :return: SensorResponse(response_type, reading)
        """
        self._logger.debug("Range requested. Sensor state is: {}".format(self.state))
        self._logger.debug("Pin is type: {}".format(type(self._enable_pin)))
        if self.state != cobrabay.const.SENSTATE_RANGING:
            return cobrabay.datatypes.SensorReading(
                state=self.state,
                status=self.status,
                fault=self._fault,
                response_type=cobrabay.const.SENSOR_RESP_NOTRANGING,
                range=None,
                temp=None,
                fault_reason=None
            )
        start = monotonic_ns()
        # Check the interrupt to see if the sensor has new data.
        while not self.data_ready:
            if wait:
                # Wait one millisecond.
                sleep(0.001)
            else:
                # If waiting for the sensor, return Interrupt Not Ready immediately.
                return cobrabay.datatypes.SensorReading(
                    state=self.state,
                    status=self.status,
                    fault=self._fault,
                    response_type=cobrabay.const.SENSOR_RESP_INR,
                    range=None,
                    temp=None,
                    fault_reason=None
                )
        # We get here once the interrupt is ready.
        # Fetch the data.
        attempts = 0
        sensor_response = None
        while sensor_response is None:
            try:
                sensor_response = self._sensor_obj.distance
            except OSError as oe:
                if attempts > 3:
                    self._logger.error("Sensor reading resulted in error over '{}' attempts. Marking faulted.".format(attempts))
                    self._fault=True
                    self._lifetime_faults += 1
                    response_type=cobrabay.const.SENSTATE_FAULT
                    range=None
                    fault_reason=oe
                else:
                    attempts += 1
            except BaseException as e:
                self._logger.error("Unknown exception encountered while reading sensor.")
                self._logger.exception(e)
                raise

        if sensor_response is None:
            # The Adafruit VL53L1X wraps up all invalid statuses with a 'None' return. See
            # https://github.com/adafruit/Adafruit_CircuitPython_VL53L1X/pull/8 for details.
            response_type=cobrabay.const.SENSOR_RESP_NOTRANGING
            range = None
            fault_reason = None
        # Check for minimum and maximum ranges.
        elif sensor_response <= 4:
            response_type = cobrabay.const.SENSOR_RESP_TOOCLOSE
            range=None
            fault_reason=None
        else:
            response_type=cobrabay.const.SENSOR_RESP_OK
            range=Quantity(sensor_response, 'cm')
            fault_reason=None
        # Clear the interrupt.
        self.clear_interrupt
        # Return.
        return SensorReading(
            state=self.state,
            status=self.status,
            fault=self._fault,
            response_type=response_type,
            range=range, temp=None, fault_reason=fault_reason
        )

    # Public Properties
    @property
    def distance_mode(self):
        """
        Distance mode of the sensor.

        :return:
        """
        if not self._fault:
            if self._sensor_obj.distance_mode == 1:
                return 'Short'
            elif self._sensor_obj.distance_mode == 2:
                return 'Long'
        else:
            return 'Fault'

    @distance_mode.setter
    def distance_mode(self, target_mode):
        """
        Distance mode of the sensor. May be 'short' or 'long'

        :param target_mode: str
        :return:
        """
        if not self._fault:
            # Pre-checking the distance mode lets us toss an error before actually setting anything.
            if target_mode.lower() == 'short':
                target_mode = 1
            elif target_mode.lower() == 'long':
                target_mode = 2
            else:
                raise ValueError("{} is not a valid distance mode".format(target_mode))
            self._distance_mode = target_mode
            self._sensor_obj.distance_mode = target_mode

    @property
    def enable_board(self):
        """
        Address of the board used to enable and disable the sensor. 0 for Pi onboard GPIO pins, otherwise the hex
        address with the address of an AW9523.

        :return: int
        """
        return self._enable_board

    @enable_board.setter
    def enable_board(self, enable_board):
        self._enable_board = enable_board

    @property
    def enable_pin(self):
        """
        Pin used to enable and disable this sensor. If using a pin on the pi
        :return:
        """
        return self._enable_pin

    @enable_pin.setter
    def enable_pin(self, enable_pin):
        # If enable_board is set to 0, then we try this on the Pi itself.
        if self.enable_board == 0:
            # Check to see if this is just a pin number.
            if isinstance(enable_pin, int):
                pin_name = 'D' + str(enable_pin)
            else:
                pin_name = enable_pin
            try:
                enable_pin_obj = digitalio.DigitalInOut(getattr(self._board, pin_name))
            except:
                raise
            else:
                self._enable_pin = enable_pin_obj
        elif isinstance(self.enable_board, adafruit_aw9523.AW9523):
            self._enable_pin = self.enable_board.get_pin(enable_pin)

        # else:
        #     # Check to see if the AW9523 object has already been created.
        #     # Use the key format "bus-addr"
        #     awkey = str(self.i2c_bus) + "-" + str(self.enable_board)
        #     if awkey not in self.__class__.aw9523_boards.keys():
        #         self._logger.info("Establishing access to AW9523 board on bus {}, address 0x{:x}".
        #                           format(self.i2c_bus, self.enable_board))
        #         # Need to create the board.
        #         try:
        #             self.__class__.aw9523_boards[awkey] = AW9523(self._i2c_bus, self.enable_board, reset=True)
        #         except BaseException as e:
        #             self._logger.critical("Could not access AW9523 on bus {}, address 0x{:x}".
        #                                   format(self.i2c_bus, self.enable_board))
        #             raise e
        #         else:
        #             self._logger.debug("Waiting 1s for I2C bus to settle.")
        #             sleep(1)
        #             self._logger.debug("Setting all to outputs with value off.")
        #             try:
        #                 cobrabay.util.aw9523_reset(self.__class__.aw9523_boards[awkey])
        #             except OSError as e:
        #                 self._logger.error("Error while resetting pins on AW9523 board on bus '{}', address "
        #                                    "'0x{:x}'. Base error was: '{} - {}'".
        #                                    format(self.i2c_bus, self.enable_board, e.__class__.__name__, str(e)))
        #                 self._logger.critical("Cannot continue!")
        #                 raise SystemExit
        #
        #     # Can now create the pin
        #     self._enable_pin = self.__class__.aw9523_boards[awkey].get_pin(enable_pin)

        # Make sure this is an 'output' type pin.
        self._enable_pin.switch_to_output()

    @property
    def enable_value(self):
        """
        Get the enablement value of the sensor.
        This property uses a protected read of the pin to guard against I/O Errors.
        """
        attempt_count = 0
        while True:
            try:
                actual_value = self.enable_pin.value
            except OSError as e:
                if attempt_count > 5:
                    raise e
                else:
                    attempt_count += 1
            else:
                return actual_value

    @enable_value.setter
    def enable_value(self, tgt_value):
        """
        Set the enablement value of the sensor.
        This setter uses a protected write of the pin to guard against I/O Errors.

        :param tgt_value: Value to set the enable pin to.
        :type tgt_value: bool
        """
        attempt_count = 0
        while True:
            try:
                self.enable_pin.value = tgt_value
            except OSError as e:
                if attempt_count > 5:
                    raise e
                else:
                    attempt_count += 1
            else:
                return True

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
            return cobrabay.const.SENSTATE_FAULT
        elif self.enable_value is True:
            self._logger.debug("Enable pin is on.")
            if self._ranging is True:
                self._logger.debug("Sensor has been recorded as ranging.")
                return cobrabay.const.SENSTATE_RANGING
            else:
                self._logger.debug("Enabled, not ranging.")
                return cobrabay.const.SENSTATE_ENABLED
        elif self.enable_value is False:
            self._logger.debug("Enable pin is off.")
            return cobrabay.const.SENSTATE_DISABLED
        else:
            self._logger.critical("Unknown sensor fault state '{}', Enable pin '{}'".
                                  format(self._fault, self.enable_value))
            return cobrabay.const.SENSTATE_FAULT

    @property
    def timing_budget(self):
        """ Timing budget for the sensor, in milliseconds. """
        if self._sensor_obj is not None:
            return Quantity(self._sensor_obj.timing_budget, 'ms')
        elif self._timing_budget is not None:
            return Quantity(self._timing_budget, 'ms')
        else:
            return Quantity('100 ms')

    @timing_budget.setter
    def timing_budget(self, timing_input):
        """ Set the timing budget for the sensor, in milliseconds
        The VL53L1X only supports 20, 33, 50, 100, 200 or 500ms as options. See documentation for more details.

        :param self:
        :type timing_input: int or Quantity('ms')
        """

        if not isinstance(timing_input, Quantity):
            timing_input = Quantity(timing_input)
        if timing_input.magnitude not in (20, 33, 50, 100, 200, 500):
            raise ValueError("Requested timing budget {} not valid. "
                             "Must be one of: 20, 33, 50, 100, 200 or 500 ms".format(input))
        # Save the timing budget.
        self._timing_budget = timing_input.magnitude
        # If object is initialized, set immediately.
        if self._sensor_obj is not None:
            self._sensor_obj.timing_budget(timing_input.magnitude)

    ## Private Methods
    # def __del__(self):
    #     """Destructor, disables the sensor when the object is destroyed."""
    #     self._logger.debug("Disabling sensor on object deletion.")
    #     self._logger.debug("Enable pin object: {}".format(self._enable_pin))
    #     self.status = 'disabled'

    def _disable(self):
        """
        Disable the sensor

        :param self:
        """

        # Don't bother to stop ranging, it's inherent in disabling the pin.
        # self._sensor_obj.stop_ranging()
        self.enable_value = False
        # Also set the internal ranging variable to false, since by definition, when the board gets killed,
        # we stop ranging.
        self._ranging = False

    def _enable(self):
        """ Enable the sensor. This puts the sensor on the I2C Bus, ready to range, but not ranging yet. """

        self.enable_value = False
        devices_prior = cobrabay.util.scan_i2c()
        self._logger.debug("I2C devices before enable: {}".format(devices_prior))
        # Turn the sensor back on.
        self.enable_value = True
        # Wait one second for the bus to stabilize
        sleep(1)
        devices_subsequent = cobrabay.util.scan_i2c()
        self._logger.debug("I2C devices after enable: {}".format(devices_subsequent))
        if len(devices_subsequent) > len(devices_prior):
            # Create the sensor at the default address.
            try:
                self._sensor_obj = adafruit_vl53l1x.VL53L1X(self.i2c_bus, address=0x29)
            except ValueError:
                self._logger.error("Sensor not found at default address '0x29'. Check configuration!")
            except OSError as e:
                self._logger.error("Sensor not responsive! Marking sensor as in fault. Base error was: '{} - {}'"
                                   .format(e.__class__.__name__, str(e)))
                self._fault = True
            else:
                # Change the I2C address to the target address.
                self._sensor_obj.set_address(new_address=self.i2c_address)
                # Make sure fault isn't set, if we're recovering from failure.
                self._fault = False
                return
        else:
            self._logger.error("Device did not appear on I2C bus! Check configuration and for hardware errors.")

        if self._enable_attempt_counter >= 3:
            self._logger.error("Could not enable sensor after {} attempts. Marking as faulty.".
                               format(self._enable_attempt_counter))
            self._fault = True
            raise IOError("Could not enable sensor.")
        else:
            self._logger.warning("Could not enable sensor on attempt {}. Disabling and retrying.".
                                 format(self._enable_attempt_counter))
            self._enable_attempt_counter += 1
            self._disable()
            self._enable()

    def _start_ranging(self):
        """ Start ranging on the sensor. """

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
        """ Stop ranging on the sensor while remaining enabled. """
        self._logger.debug("Stopping ranging.")
        try:
            self._sensor_obj.stop_ranging()
        except:
            raise
        else:
            self._ranging = False

    ## Private Properties
