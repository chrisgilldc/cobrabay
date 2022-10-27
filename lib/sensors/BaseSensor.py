#####
# Cobra Bay Sensor - Base Sensor Class used for all other sensors.
#####

import logging
from pint import UnitRegistry

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