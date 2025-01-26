####
# Cobra Bay Sensor - I2CSensor
####
#
# Common class for sensors accessed via I2C
#

# Import the base sensor.
from cobrabay.sensors import BaseSensor
import board
import busio

class I2CSensor(BaseSensor):
    """
    Class for common elements of all I2C-based Sensors.
    """
    aw9523_boards = {}

    def __init__(self, name, i2c_address, i2c_bus, max_retries=0, parent_logger=None, log_level="WARNING"):
        """

        :param name: Name of the sensor
        :type name: str
        :param i2c_address: Address of the sensor.
        :type i2c_address: int or str(hex)
        :param i2c_bus: Instantiated object for the I2C Bus.
        :type i2c_bus: busio.I2C
        :param max_retries: How many times to try resetting a sensor before declaring it in fault.
        :type max_retries: int
        :param parent_logger: Parent logger to attach to.
        :type parent_logger: logger
        :param log_level: If no parent logger provided, log level of the new logger to create.
        :type log_level: str
        """
        # Define our own name based on class name, bus and address.
        id = "{}-{}-{}".format(type(self).__name__, i2c_bus, hex(i2c_address))
        # Do base sensor initialization

        try:
            super().__init__(name=name, id=id, max_retries=max_retries, parent_logger=parent_logger, log_level=log_level)
        except ValueError:
            raise

        # Log that we're initializing.
        self._logger.info("Initializing sensor...")

        # Set the I2C bus and I2C Address
        self.i2c_bus = i2c_bus
        self.i2c_address = i2c_address
        self._logger.debug("Configured for I2C device '{}' and Address '{}'".
                           format(self.i2c_bus._i2c._i2c_bus._device.name,hex(self.i2c_address)))

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
        if isinstance(the_input,busio.I2C):
            self._i2c_bus = the_input
        else:
            raise ValueError("I2C Bus must be a busio.I2C object. Instead is '{}'".format(type(the_input)))

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
    # None in this class

    ## Private Properties
    # None in this class
