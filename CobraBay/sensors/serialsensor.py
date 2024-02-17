####
# Cobra Bay Sensor - SerialSensor
####
#
# Common class for sensors accessed via Serial (ie: Onboard or USB UART)
#

# Import the base sensor
from CobraBay.sensors import BaseSensor
from pathlib import Path


class SerialSensor(BaseSensor):
    """
    Class for all common elements of Serial-based sensors.
    """

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
            super().__init__(name=self._name, parent_logger=parent_logger, log_level=log_level)
        except ValueError:
            raise
        self._logger.info("Initializing sensor...")
        self._serial_port = None
        self._baud_rate = None
        self.serial_port = port
        self.baud_rate = baud

    ## Public Methods
    # None in this class

    ## Public Properties
    @property
    def serial_port(self):
        """
        Port for this sensor
        :return: Path
        """
        return self._serial_port

    @serial_port.setter
    def serial_port(self, target_port):
        """
        Port for this sensor. If not an absolute path will be made relative to /dev.

        :param target_port: str or Path
        :return: None
        """
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
        """
        Baud rate.

        :return: int
        """
        return self._baud_rate

    @baud_rate.setter
    def baud_rate(self, target_rate):
        """
        Baud rate.

        :param target_rate: int
        :return: None
        """
        self._baud_rate = target_rate
