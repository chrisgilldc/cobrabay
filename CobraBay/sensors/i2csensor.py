####
# Cobra Bay Sensor - I2CSensor
####
#
# Common class for sensors accessed via I2C
#

# Import the base sensor.
from CobraBay.sensors import BaseSensor
import board
import busio

class I2CSensor(BaseSensor):
    """
    Class for common elements of all I2C-based Sensors.
    """
    aw9523_boards = {}

    def __init__(self, i2c_address, max_retries=0, i2c_bus=1, pin_scl=None, pin_sda=None, parent_logger=None, log_level="WARNING"):
        """

        :param i2c_address: Address of the sensor.
        :type i2c_address: int or str(hex)
        :param i2c_bus: I2C bus on the Pi to use. If you wish to specify SCL and SDA pins, set this to None.
        :type i2c_bus: int
        :param pin_scl: I2C Clock pin. Will be ignored if i2c_bus is anything other than None.
        :type pin_scl: int
        :param pin_sda: I2C Data pin. Will be ignored if i2c_bus is anything other than None.
        :type pin_sda: int
        :param parent_logger: Parent logger to attach to.
        :type parent_logger: logger
        :param log_level: If no parent logger provided, log level of the new logger to create.
        :type log_level: str
        """
        # Define our own name based on class name, bus and address.
        self._name = "{}-{}-{}".format(type(self).__name__, i2c_bus, hex(i2c_address))
        # Do base sensor initialization

        try:
            super().__init__(name=self._name, max_retries=max_retries, parent_logger=parent_logger, log_level=log_level)
        except ValueError:
            raise

        # Log that we're initializing.
        self._logger.info("Initializing sensor...")

        # Set the I2C bus and I2C Address
        self.i2c_bus = i2c_bus
        self.i2c_address = i2c_address
        self._logger.debug("Configured for I2C Bus {} and Address {}".format(self.i2c_bus, hex(self.i2c_address)))

        # Create the I2C Object.
        self._create_i2c_obj(i2c_bus, pin_scl, pin_sda)

        # How many times, in the lifetime of the sensor, have we hit a fault.
        self._lifetime_faults = 0
        # Set if the sensor hit a fault, recovered, but hasn't yet succeeded in re-reading. If it faults *again*, bomb.
        self._last_chance = False

    ## Public Methods
    # None in this class.

    ## Public Properties
    @property
    def i2c_bus(self):
        """
        I2C Bus. Should almost always be 1.
        :return: int
        """
        return self._i2c_bus

    @i2c_bus.setter
    def i2c_bus(self, the_input):
        """
        I2C Bus to use. Should almost always be 1.
        :param the_input: int
        :return: None
        """
        if the_input not in (1, 2):
            raise ValueError("I2C Bus ID for Raspberry Pi must be 1 or 2, not {}".format(the_input))
        else:
            self._i2c_bus = the_input

    @property
    def i2c_address(self):
        """
        I2C Address of the sensor.
        :return:
        """
        return self._i2c_address

    @i2c_address.setter
    # Stores the address of the board. Does *not* necessarily apply it to the board to update it.
    def i2c_address(self, i2c_address):
        """
        I2C address of the sensor. This *only* changes the address the we're trying to read, it does not try to change
        the address the sensor is actually configured for.
        :param i2c_address: int or str
        :return: None
        """
        # If it's in "0xYY" format, convert it to a base 16 int.
        if isinstance(i2c_address, str):
            self._i2c_address = int(i2c_address, base=16)
        else:
            self._i2c_address = i2c_address

    ## Private Methods
    def _create_i2c_obj(self, i2c_bus, pin_scl, pin_sda):
        # Create the board object.
        self._board = board

        # Determine what to do for I2C creation.
        if i2c_bus is not None:
            self._logger.debug("I2C Bus set to {}. Determining correct pins.".format(i2c_bus))
            if i2c_bus == 1:
                pin_scl = self._board.SCL
                pin_sda = self._board.SDA
            elif i2c_bus == 0:
                pin_scl = self._board.SCL0
                pin_sda = self._board.SDA0
            self._logger.debug("Selected SCL pin '{}', SDA pin '{}'".format(pin_scl, pin_sda))
        else:
            self._logger.debug("Pins set directly. Using SCL pin '{}', SDA pin '{}'".format(pin_scl, pin_sda))
        try:
            self._i2c = busio.I2C(pin_scl, pin_sda)
        except PermissionError as e:
            self._logger.warning("No access to I2C Bus.")
            raise e
        except BaseException as e:
            self._logger.critical("Unknown exception in accessing I2C bus!")
            raise e

    ## Private Properties
    # None in this class
