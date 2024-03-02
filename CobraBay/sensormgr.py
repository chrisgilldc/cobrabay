"""
CobraBay - Sensor Manager
"""
from __future__ import annotations

import logging
import time
import CobraBay.sensors
from CobraBay.datatypes import SensorResponse
from numpy import datetime64
import threading
import queue

##TODO: Remove threading, convert to run as a standalone server and use IPC.

class CBSensorMgr:
    """
    CobraBay Sensor Manager. Creates sensor objects, polls them, keeps them in line.
    """

    def __init__(self, sensor_config, generous_recovery=True, name=None, parent_logger=None,
                 log_level="WARNING", q_cbsmdata=None, q_cbsmcontrol=None):
        """
        Create a Sensor Manager instance.

        :param sensor_config: Dictionary of sensors and their settings. Presume this is validated.
        :type sensor_config: dict
        :param generous_recovery: In general, should when errors are encountered, log and continue or raise exceptions
        and (likely) fault? The first is default.
        :type generous_recovery: bool
        :param name: Name of the sensor manager instance. Defaults to 'CBSensorMgr'
        :type name: str
        :param parent_logger:
        :param log_level: Logging level. Any valid python logging level is allowed. Defaults to WARNING.
        :type log_level: str
        """
        # Initialize variables.
        self._sensors = {}  # Dictionary for sensor objects.
        self._latest_state = {}  # Rolling current state of the sensors.
        self._scan_speed_log = []  # List to store scan performance data.
        self._scan_avg_speed = 0

        self._thread: threading.Thread | None = None
        self._thread_terminate = False

        # Save input parameters.
        self._name = name
        self._gr = generous_recovery

        # Set up the logger.
        if parent_logger is None:
            # If no parent detector is given this sensor is being used in a testing capacity. Create a null logger.
            self._logger = logging.getLogger(self._name)
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter(CobraBay.const.LOG_FORMAT))
            console_handler.setLevel(log_level)
            self._logger.addHandler(console_handler)
            self._logger.setLevel(log_level)
        else:
            self._logger = parent_logger.getChild(self._name)

        # Pass the sensor config to the setup method to see if it works!
        self._sensors = self._sensor_create_multiple(sensor_config)

        # Queue to share data with threads.
        # Old way of doing it.
        # self.data = deque(maxlen=len(self._sensors))
        self.data = queue.Queue(maxsize=1)

    # Public Methods
    def loop(self):
        """
        Check the status of sensors.
        :return:
        """
        # If data is still in the queue from the previous loop, junk it.
        self._logger.debug("Beginning sensor scan loop.")
        try:
            self._logger.debug("Queue still has data. Flushing.")
            while self.data.full():
                self.data.get(block=False)
                self.data.task_done()
        except queue.Empty:
            pass
        self._logger.debug("Scanning sensors.")
        start_time = time.monotonic_ns()
        for sensor_id in self._sensors.keys():
            self._logger.debug("Checking sensor '{}'".format(sensor_id))
            if isinstance(self._sensors[sensor_id], CobraBay.sensors.BaseSensor):
                self._latest_state[sensor_id] = self._sensors[sensor_id].reading()
            elif self._sensors[sensor_id] == CobraBay.const.SENSTATE_FAULT:
                # If the sensor faulted on creation, it doesn't have a reading method, construct a fault response.
                self._latest_state[sensor_id] = SensorResponse(timestamp=datetime64('now'),
                                                               response_type=CobraBay.const.SENSTATE_FAULT,
                                                               reading=None, fault_reason="Did not initialize.")
        # Calculate the run_time.
        run_time = time.monotonic_ns() - start_time
        self._scan_speed_log.append(run_time)
        self._scan_speed_log = self._scan_speed_log[:100]
        self._logger.debug("Enqueing scan data.")
        self.data.put(self._latest_state, timeout=1)
        self._logger.debug("Loop complete.")

    def loop_forever(self):
        """
        Read the sensors in a loop continuously.

        :raises OSError: if an unrecoverable error is encountered with a sensor.
        """

        run = True

        while run:
            if self._thread_terminate:
                self._logger.info("Thread termination requested.")
                break

            try:
                self.loop()
            except OSError as e:
                self._logger.error("Encountered unrecoverable sensor error '{}'".format(e))
                raise e

    def loop_start(self):
        """
        Set a thread running to read the sensors forever.

        :return: bool
        """

        if self._thread is not None:
            return False

        self._logger.debug("Starting sensor loop thread.")
        self._thread_terminate = False
        self._thread = threading.Thread(target=self._thread_main, name=f"cbsensormgr-{self._name}")
        self._thread.daemon = True
        self._thread.start()

        return True

    def loop_stop(self):
        """
        Stop the thread started with loop_start.

        :return: bool
        """
        self._logger.debug("Stopping sensor loop thread.")

        self._thread_terminate = True

        if threading.current_thread() != self._thread:
            self._thread.join()
            self._thread = None

        return True

    def exit_tasks(self):
        """
        Things to do when shutting down the Sensor Manager.
        """
        for sensor_obj in self._sensors:
            del self._sensors[sensor_obj]

    def sensors_activate(self):
        for sensor_id in self._sensors:
            if isinstance(self._sensors[sensor_id], CobraBay.sensors.BaseSensor):
                self._sensors[sensor_id].status = 'ranging'

    # Public Properties

    # Private Methods
    # def _enqueue_data(self):
    #     """
    #     Assemble data to enqueue.
    #
    #     :return: None
    #     """
    #     outbound_data = {}
    #     enqueue = False
    #     for sensor_id in self._sensors:
    #         sensor_data = self._data_internal[sensor_id]
    #         if sensor_data.response_type is not CobraBay.const.SENSOR_VALUE_INR:
    #             outbound_data[sensor_id] = sensor_data
    #             enqueue = True
    #     if enqueue:
    #         self.data.put(outbound_data)

    def _sensor_create_multiple(self, sensor_config):
        """
        Create sensor objects for a given configuration.
        :return: dict
        """
        sensors = {}
        # Create detectors with the right type.
        self._logger.debug("Creating sensors...")
        self._logger.debug("Received overall sensor config: {}".format(sensor_config))
        for sensor_id in sensor_config:
            try:
                sensor_obj = self._sensor_create_single(sensor_config[sensor_id])
            except BaseException as e:
                if self._gr:
                    self._logger.warning("Could not create object for sensor '{}'".format(sensor_id))
                    sensors[sensor_id] = CobraBay.const.SENSTATE_FAULT
                else:
                    raise e
            else:
                sensors[sensor_id] = sensor_obj
        return sensors

    def _sensor_create_single(self, sensor_config):
        if sensor_config['sensor_type'] == 'TFMini':
            # Create the sensor object.
            try:
                sensor_obj = CobraBay.sensors.TFMini(
                    port=sensor_config['port'],
                    baud=sensor_config['baud'],
                    parent_logger=self._logger,
                    log_level=sensor_config['log_level']
                )
            except BaseException as e:
                raise e
            else:
                return sensor_obj
        elif sensor_config['sensor_type'] == 'VL53L1X':
            try:
                sensor_obj = CobraBay.sensors.CBVL53L1X(
                    i2c_address=sensor_config['i2c_address'],
                    enable_board=sensor_config['enable_board'],
                    enable_pin=sensor_config['enable_pin'],
                    parent_logger=self._logger,
                    log_level="WARNING"
                )
            except BaseException as e:
                raise e
            else:
                return sensor_obj
        else:
            raise TypeError("Sensor has unknown type '{}'. Cannot create!".format(sensor_config['sensor_type']))

    def _thread_main(self) -> None:
        self.loop_forever()

    # Private Properties
    @property
    def _name(self):
        return self.__name

    @_name.setter
    def _name(self, the_input):
        if the_input is None:
            self.__name = 'CBSensorMgr'
        else:
            self.__name = the_input
