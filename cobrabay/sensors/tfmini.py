####
# Cobra Bay Sensor - TFMini+
####
#
# TFMini+ in Serial mode. I2C mode was tested and tended to overwhelm the bus, so no go.
# Note that this sensor always ranges as long as it's powered, so

# The SerialSensor class
from cobrabay.sensors import SerialSensor
# Required Cobra Bay datatypes
from cobrabay.datatypes import SensorResponse, SensorReading, TFMPData
# General libraries
from pint import Quantity
from time import monotonic
from .tfmp import TFMP
import cobrabay.const
from numpy import datetime64

class TFMini(SerialSensor):
    def __init__(self, name, port, baud, error_margin=None, parent_logger=None, clustering=1, log_level="WARNING"):
        """
        Sensor for TFMini

        :param name: Name of this sensor. Should be unique.
        :type name: str
        :param port: Serial port
        :type port: str OR Path
        :param error_margin: Known variability for the sensor reading-to-reading.
        :type error_margin: Quantity
        :param baud: Bitrate for the sensor.
        :type baud: int
        :param parent_logger: Parent logger to attach to.
        :type parent_logger: logger
        :param clustering: Should we cluster read, and if so how many to cluster?
        :type clustering: int
        :param log_level: If no parent logger provided, log level of the new logger to create.
        :type log_level: str
        """
        try:
            super().__init__(name=name, port=port, baud=baud, parent_logger=parent_logger, log_level=log_level)
        except ValueError:
            raise

        self._performance = {
            'max_range': Quantity('12m'),
            'min_range': Quantity('0.3m')
        }

        self._fault = False # Currently don't fault out the TFMinin.

        if error_margin is None:
            self._error_margin = Quantity("2cm")
        else:
            self._error_margin = error_margin

        # Cluster reading setting.
        self._clustering = clustering

        # Create the sensor object.
        self._logger.debug("Creating TFMini object on serial port {}".format(self.serial_port))
        self._sensor_obj = TFMP(self.serial_port, self.baud_rate)
        self._logger.debug("Test reading: {} ({})".format(self.reading, type(self.reading)))

    # Public Methods

    def data_ready(self):
        """Interrupt status for the sensor. Since the TFMini has no interrupt, always return true."""
        return True

    # TFMini is always ranging, so enable here is just a dummy method.
    @staticmethod
    def enable():
        """
        Enable the sensor. Because the TFMini always ranges when powered, this always returns True.
        :return:
        """
        return True

    # Likewise, we don't need to disable, do nothing.
    @staticmethod
    def disable():
        """
        Disable the sensor. Because the TFMini always ranges when powered, this does nothing.
        """
        pass

    def reading(self):
        """Reading from the sensor."""
        #TODO: Determine source of frequent (every few second) checksum errors.
        # "OSError: Sensor checksum error"
        try:
            reading = self._clustered_read(self._clustering)
        except BaseException as e:
            self._logger.error("Reading received exception - '{}: {}'".format(type(e).__name__, e))
            self._state = cobrabay.const.SENSTATE_DISABLED
            return SensorReading(
                state=self.state,
                status=self.status,
                fault=self._fault,
                response_type=cobrabay.const.SENSTATE_FAULT,
                range=None,
                temp=None,
                fault_reason=e
            )
        else:

            # self._state = cobrabay.const.SENSTATE_RANGING
            self._logger.debug("TFmini read values: {}".format(reading))
            # Check the status to see if we got a value, or some kind of non-OK state.
            if reading.status == "OK":
                return SensorReading(
                    state=self.state,
                    status=self.status,
                    fault=self._fault,
                    response_type=cobrabay.const.SENSOR_RESP_OK,
                    range=reading.distance,
                    temp=reading.temperature,
                    fault_reason=None
                )
            elif reading.status == "Weak":
                return SensorReading(
                    state=self.state,
                    status=self.status,
                    fault=self._fault,
                    response_type=cobrabay.const.SENSOR_RESP_WEAK,
                    range=None,
                    temp=None,
                    fault_reason=None
                )
            elif reading.status in ("Flood", "Saturation"):
                return SensorReading(
                    state=self.state,
                    status=self.status,
                    fault=self._fault,
                    response_type=cobrabay.const.SENSOR_RESP_FLOOD,
                    range=None,
                    temp=None,
                    fault_reason=None
                )
            elif reading.status == 'Strong':
                return SensorReading(
                    state=self.state,
                    status=self.status,
                    fault=self._fault,
                    response_type=cobrabay.const.SENSOR_RESP_STRONG,
                    range=None,
                    temp=None,
                    fault_reason=None
                )
            else:
                return SensorReading(
                    state=self.state,
                    status=self.status,
                    fault=self._fault,
                    response_type=cobrabay.const.SENSTATE_FAULT,
                    range=None,
                    temp=None,
                    fault_reason="Unknown reading '{}'".format(reading)
                )

    # The clustered read method requires the sensor to be returning a consistent result to return.
    # Passing '1' will require two consecutive reads of the same value.
    def _clustered_read(self, reading_count):
        stable_count = 0
        i = 0
        previous_read = self._sensor_obj.data()
        start = monotonic()
        while stable_count < reading_count:
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
        return cobrabay.const.SENSTATE_RANGING

    @property
    def status(self):
        """
        Status of the TFMini Sensor.

        The TFMini always ranges when it's powered on, thus this status always returns "ranging"

        :return:
        """
        # The TFMini always ranges, so we can just return ranging.
        return cobrabay.const.SENSTATE_RANGING

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
