"""
Cobra Bay Sensor - BaseSensor

Common base class for all sensors.
"""

import logging
from pint import UnitRegistry
from time import monotonic


class BaseSensor:
    """The common base class for all sensors."""
    _logger: logging.Logger

    def __init__(self, name, max_retries=0, parent_logger=None, log_level="WARNING"):
        """
        Base class for Sensors.

        :param name: Name of this sensor.
        :param parent_logger: Parent logger to attach to.
        :type parent_logger: logger
        :param log_level: If no parent logger provided, log level of the new logger to create.
        :type log_level: str
        """

        # Save input parameters
        self._name = name
        print("Object named: {}".format(self._name))

        # Create a unit registry
        self._ureg = UnitRegistry()

        # Set up the logger.
        if parent_logger is None:
            # If no parent detector is given this sensor is being used in a testing capacity. Create a null logger.
            self._logger = logging.getLogger(self._name)
            console_handler = logging.StreamHandler()
            console_handler.setLevel(log_level)
            self._logger.addHandler(console_handler)
            self._logger.setLevel(log_level)
        else:
            self._logger = parent_logger.getChild(self._name)
            self._logger.setLevel(log_level)

        # How many retries can the sensor have before it faults.
        self._max_retries = max_retries
        self._faults = 0

        # Initialize variables.
        self._previous_timestamp = monotonic()
        self._previous_reading = None
        self._requested_status = None
        self._status = None

    # Public Methods
    # None for this class.

    # Public Properties
    @property
    def name(self):
        """The name of the sensor."""
        return self._name

    @property
    def reading(self):
        """Current reading of the sensor."""
        raise NotImplementedError("Range should be overridden by specific sensor class.")

    @property
    def state(self):
        """Current state of the sensor."""
        raise NotImplementedError("State should be overridden by specific sensor class.")

    @property
    def status(self):
        """
        Read the sensor status.  This is the requested status. It may not be the state if there have been intervening
        errors.
        :return: str
        """
        return self._status

    @status.setter
    def status(self, target_status):
        """
        Standard method to set a sensor status.

        :param target_status: One of 'enable', 'disable', 'ranging'
        :type target_status: str
        :return: None
        """
        if target_status not in ('disabled', 'enabled', 'ranging'):
            raise ValueError("Target status '{}' not valid".format(target_status))
        if target_status == 'disabled':
            try:
                self._disable()
            except BaseException as e:
                self._logger.error("Could not disable.")
                self._logger.exception(e)
                raise e
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
                    raise e
                else:
                    self._logger.debug("Status is now 'enabled'")
                    self._status = 'enabled'
            else:
                try:
                    self._enable()
                except BaseException as e:
                    self._logger.error("Could not enable.")
                    self._logger.exception(e)
                    raise e
                else:
                    self._logger.debug("Status is now 'enabled'")
                    self._status = 'enabled'
        elif target_status == 'ranging':
            # If sensor is disabled, enable before going straight to ranging.
            if self._status == 'disabled':
                try:
                    self._enable()
                except IOError as e:
                    self._logger.error("Could not perform implicit enable while changing status to ranging.")
                    self._logger.exception(e)
                    raise e
                else:
                    self._logger.debug("Successfully completed implicit enable to allow change to ranging")
            try:
                self._start_ranging()
            except TypeError:
                self._logger.warning("Could not start ranging. Sensor returned value that could not be interpreted.")
            except BaseException as e:
                self._logger.error("Could not start ranging.")
                self._logger.exception(e)
                raise e
            else:
                self._logger.debug("Status is now ranging.")
                self._status = 'ranging'

    # Private Methods

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

    # Private Properties
    # None in this class
