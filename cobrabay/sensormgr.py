"""
Cobra Bay - Sensor Manager
"""
from __future__ import annotations

import pprint

from adafruit_aw9523 import AW9523
import atexit
import board
import busio
import logging
import time
import digitalio
import cobrabay.sensors
from cobrabay.const import *
from cobrabay.datatypes import SensorResponse, SensorReading
from numpy import datetime64
import threading
import multiprocessing
import queue

#TODO: Try with asyncio or threading, eventually.
#TODO: Expose sensor state queue

class CBSensorMgr:
    """
    Cobra Bay Sensor Manager. Creates sensor objects, polls them, keeps them in line. Also manages base I2C and
    AW9523 objects.
    """

    def __init__(self, sensor_config, i2c_config=None, generous_recovery=True, name=None, parent_logger=None,
                 log_level="WARNING", q_cbsmdata=None, q_cbsmstatus=None, q_cbsmcontrol=None):
        """
        Create a Sensor Manager instance.

        :param sensor_config: Dictionary of sensors and their settings. Presume this is validated.
        :type sensor_config: dict
        :param i2c_config: Dictionary for I2C Config
        :type i2c_config: dict
        :param generous_recovery: In general, should when errors are encountered, log and continue or raise exceptions
        and (likely) fault? The first is default.
        :type generous_recovery: bool
        :param name: Name of the sensor manager instance. Defaults to 'CBSensorMgr'
        :type name: str
        :param parent_logger:
        :param log_level: Logging level. Any valid python logging level is allowed. Defaults to WARNING.
        :type log_level: str
        :param q_cbsmdata: Allows other threads/processes to fetch sensor readings.
        :type q_cbsmdata: queue.Queue or multiprocessing.Queue
        :param q_cbsmstatus: Allows other threads/processes to fetch sensor operating statuses.
        :type q_cbsmstatus: queue.Queue or multiprocessing.Queue
        :param q_cbsmcontrol: Takes incoming commands from parent thread/process.
        :type q_cbsmcontrol:queue.Queue or multiprocessing.Queue

        """
        # Initialize variables.
        self._sensors = {}  # Dictionary for sensor objects.
        self._latest_state = {}  # Rolling current state of the sensors.
        self._scan_speed_log = []  # List to store scan performance data.
        self._scan_avg_speed = 0
        self._wait_ready = 30
        self._wait_reset = 30
        self._i2c_bus = None
        self._i2c_available = True
        self._ioexpanders = {}

        # self._thread: threading.Thread | None = None
        # self._thread_terminate = False

        # Save input parameters.
        self._name = name
        self._sensor_config = sensor_config
        self._i2c_config = i2c_config
        self._gr = generous_recovery

        # Save the queues.
        self._q_cbsmdata = q_cbsmdata
        self._q_cbsmstatus = q_cbsmstatus
        self._q_cbsmcontrol = q_cbsmcontrol

        # Register the cleanup method.
        atexit.register(self.cleanup)

        # Set up the logger.
        if parent_logger is None:
            # If no parent detector is given this sensor is being used in a testing capacity. Create a null logger.
            self._logger = logging.getLogger(self._name)
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter(cobrabay.const.LOG_FORMAT))
            console_handler.setLevel(log_level)
            self._logger.addHandler(console_handler)
            self._logger.setLevel(log_level)
        else:
            self._logger = parent_logger.getChild(self._name)

        self._logger.debug("Received sensor config: {}".format(pprint.pformat(sensor_config)))
        self._logger.debug("Received I2C config: {}".format(pprint.pformat(i2c_config)))

        # If I2C config is given, do it.
        if self._i2c_config is not None:
            try:
                self._i2c_bus = self._create_i2c_bus(
                    i2c_bus=i2c_config['bus'],
                    pin_enable=i2c_config['enable'],
                    pin_ready=i2c_config['ready'])
            except BaseException:
                pass
            else:
                # Do a reset on the bus.
                self._reset_i2c_bus()
                # If resetting hits an error, it will set the _i2c_available to false and we skip this setup.
                if self._i2c_available:
                    for addr in self._scan_aw9523s():
                        self._logger.info("Configuring AW9523 at address '{}'".format(hex(addr)))
                        self._ioexpanders[str(addr)] = AW9523(self._i2c_bus, addr, reset=True)
                        self._logger.info("Resetting all outputs on board...")
                        self._reset_aw9523(self._ioexpanders[str(addr)])
                else:
                    self._logger.warning("Skipping IO expander setup, I2C bus is not available.")

        # Pass the sensor config to the setup method to see if it works!
        self._sensors = self._create_sensor_multiple(sensor_config)

        # self._q_cbsmdata = queue.Queue(maxsize=1)

    # Cleanup
    def cleanup(self):
        """ Shut off all sensors when exiting. """
        # Disable all sensors when shutting down.
        self._logger.debug("Disabling all sensors before deletion.")
        for sensor_id in self._sensors:
            self._logger.debug("Disabling '{}'".format(sensor_id))
            self._sensors[sensor_id].status = SENSTATE_DISABLED

    # Public Methods
    def get_sensor(self, sensor_id):
        """
        Return a given sensor object by ID. Should only be used in rare cases, usually let the manager do it's thing.

        :param sensor_id:
        :return: cobrabay.sensors.basesensor
        """
        return self._sensors[sensor_id]

    def loop(self):
        """
        Check the status of sensors.
        :return:
        """
        self._logger.debug("Beginning action loop.")

        # Check for commands in the command queue.
        while not self._q_cbsmcontrol.empty():
            self._logger.debug("Processing commands in queue...")
            # Get the command from the queue.
            try:
                command = self._q_cbsmcontrol.get_nowait()
            except queue.Empty:
                self._logger.warning("Command disappeared before it could be fetched.")
                continue
            try:
                self._logger.debug("Setting state based on command '{}'".format(command))
                self.set_sensor_state(target_state=command[0], target_sensor=command[1])
            except BaseException as e:
                self._logger.error("Could not process command '{}".format(command))
                self._logger.exception(e)
            self._q_cbsmcontrol.task_done()

        # Flush the Data and Status queues.
        self._flush_queue(self._q_cbsmdata)
        self._flush_queue(self._q_cbsmstatus)

        # Scan the sensors and collect data.
        self._logger.debug("Scanning sensors.")
        start_time = time.monotonic_ns()
        for sensor_id in self._sensors.keys():
            self._logger.debug("Checking sensor '{}'".format(sensor_id))
            if isinstance(self._sensors[sensor_id], cobrabay.sensors.BaseSensor):
                self._latest_state[sensor_id] = self._sensors[sensor_id].reading()
            elif self._sensors[sensor_id] == cobrabay.const.SENSTATE_FAULT:
                # If the sensor faulted on creation, it doesn't have a reading method, construct a fault response.
                self._latest_state[sensor_id] = SensorReading(
                    state=cobrabay.const.SENSTATE_FAULT,
                    status=cobrabay.const.SENSTATE_FAULT,
                    fault=True,
                    response_type=cobrabay.const.SENSTATE_FAULT,
                    range=cobrabay.const.GEN_UNAVAILABLE, temp=cobrabay.const.GEN_UNAVAILABLE,
                    fault_reason="Did not initialize.")
        # Calculate the run_time.
        run_time = time.monotonic_ns() - start_time
        self._scan_speed_log.append(run_time)
        self._scan_speed_log = self._scan_speed_log[:100]
        scan_data = SensorResponse(timestamp=datetime64('now','ns'), sensors=self._latest_state, scan_time = run_time)
        self._logger.debug("Enqueing scan data - {}".format(scan_data))
        # Enqueue a SensorResponse.
        self._q_cbsmdata.put(scan_data,timeout = 1)
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

    def enumerate_sensors(self):
        """
        List the configured sensors
        :return: list
        """
        return self._sensors.keys()

    def exit_tasks(self):
        """
        Things to do when shutting down the Sensor Manager.
        """
        for sensor_obj in self._sensors:
            del self._sensors[sensor_obj]

    def sensors_activate(self):
        """
        Set all sensors to ranging.
        """
        for sensor_id in self._sensors:
            if isinstance(self._sensors[sensor_id], cobrabay.sensors.BaseSensor):
                self._sensors[sensor_id].status = 'ranging'

    def set_sensor_state(self, target_state, target_sensor=None):
        """
        Set state for one or many sensors.
        :param target_state: State to set the sensor(s) to.
        :param target_sensor: Sensors to set. Defaults to all.
        :return: None
        """
        self._logger.info("{} - Starting detector state set.".format(time.monotonic()))
        if target_state in (SENSTATE_DISABLED, SENSTATE_ENABLED, SENSTATE_RANGING):
            # self._logger.debug("Traversing detectors to set status to '{}'".format(target_state))
            # Traverse the dict looking for detectors that need activation.
            for sensor in self._sensors:
                if target_sensor is None or sensor == target_sensor:
                    self._logger.debug("Sensor is of type: {}".format(type(self._sensors[sensor])))
                    if isinstance(self._sensors[sensor], str):
                        self._logger.debug("Sensor is actually string: '{}'".format(self._sensors[sensor]))
                    if self._sensors[sensor] == cobrabay.const.SENSTATE_FAULT:
                        self._logger.warning("Cannot set state of sensor '{}' before it is initialized.".
                                             format(target_sensor))
                    else:
                        self._logger.info("{} - Setting sensor {}".format(time.monotonic(), sensor))
                        self._logger.debug("Changing sensor {}".format(sensor))
                        self._sensors[sensor].status = target_state
                        self._logger.info("{} - Set complete.".format(time.monotonic()))
        else:
            raise ValueError("'{}' not a valid state for sensors.".format(target_state))

    # Public Properties
    # None defined

    # Private Methods
    def _create_sensor_multiple(self, all_configs):
        """
        Create sensor objects for a given configuration.

        :type all_configs: dict
        :return: dict
        """

        sensors = {}
        # Create detectors with the right type.
        self._logger.debug("Creating sensors...")
        self._logger.debug("Received overall sensor config: {}".format(all_configs))
        for sensor_id in all_configs:
            try:
                sensor_obj = self._create_sensor_single(all_configs[sensor_id])
            except BaseException as e:
                if self._gr:
                    self._logger.exception("Could not create object for sensor '{}'".format(sensor_id), exc_info=e)
                    sensors[sensor_id] = cobrabay.const.SENSTATE_FAULT
                else:
                    raise e
            else:
                sensors[sensor_id] = sensor_obj
        return sensors

    def _create_sensor_single(self, sensor_config):
        if sensor_config['hw_type'] == 'TFMini':
            self._logger.info("Creating TFMini '{}' sensor...".format(sensor_config['name']))
            # Create the sensor object.
            try:
                sensor_obj = cobrabay.sensors.TFMini(
                    name=sensor_config['name'],
                    port=sensor_config['port'],
                    baud=sensor_config['baud'],
                    parent_logger=self._logger,
                    # TODO: Use log level from config.
                    log_level="WARNING"
                )
            except BaseException as e:
                raise e
            else:
                return sensor_obj
        elif sensor_config['hw_type'] == 'VL53L1X':
            self._logger.info("Creating VL53L1X '{}' sensor...".format(sensor_config['name']))
            if self._i2c_bus is None:
                raise ValueError("Using I2C Sensor without I2C bus defined!")
            if self._i2c_available is False:
                raise OSError("Skipping sensor '{}', I2C bus is not available.".format(sensor_config['name']))
            if sensor_config['enable_board'] == 0:
                enable_board = 0
            else:
                try:
                    enable_board = self._ioexpanders[str(sensor_config['enable_board'])]
                except KeyError:
                    self._logger.error("Cannot configure sensor '{}', requested IO expander at address '{}' does not "
                                       "exist.".format(sensor_config['name'], hex(sensor_config['enable_board'])))
                    raise ValueError("IO expander does not exist.")
            self._logger.debug("Will pass I2C Bus: {} ({})".format(self._i2c_bus, type(self._i2c_bus)))
            self._logger.debug("Will pass IO Expander: {} ({})".format(enable_board, type(enable_board)))
            # Now create the actual sensor object.
            try:
                sensor_obj = cobrabay.sensors.CBVL53L1X(
                    name=sensor_config['name'],
                    i2c_address=sensor_config['i2c_address'],
                    i2c_bus=self._i2c_bus,
                    enable_board=enable_board,
                    enable_pin=sensor_config['enable_pin'],
                    parent_logger=self._logger,
                    # TODO: Use log level from config.
                    log_level="DEBUG"
                )
            except BaseException as e:
                raise e
            else:
                return sensor_obj
        else:
            raise TypeError(
                "Sensor has unknown hardware type '{}'. Cannot create!".format(sensor_config['hw_type']))

    def _create_i2c_bus(self, i2c_bus, pin_enable, pin_ready, pin_scl=None, pin_sda=None):
        # Create the board object.
        self._board = board

        # Create the enable and ready objects.
        enable = self._get_pinobj(pin_enable)
        self._ctrl_enable = digitalio.DigitalInOut(enable)
        self._ctrl_enable.switch_to_output()
        ready = self._get_pinobj(pin_ready)
        self._ctrl_ready = digitalio.DigitalInOut(ready)

        # If the bus doesn't start ready, reset it.
        if not ready.value:
            self._reset_i2c_bus()

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
            return busio.I2C(pin_scl, pin_sda)
        except PermissionError as e:
            self._logger.warning("No access to I2C Bus.")
            raise e
        except BaseException as e:
            self._logger.critical("Unknown exception in accessing I2C bus!")
            raise e

    @staticmethod
    def _flush_queue(q):
        """ Flush a given queue """
        while not q.empty():
            try:
                q.get(block=False)
            except queue.Empty:
                continue
            q.task_done()

    def _reset_i2c_bus(self):
        self._logger.info("Resetting I2C bus on request.")
        self._disable_i2c_bus()
        self._logger.info("Waiting {}s before enablement.".format(self._wait_reset))
        self._enable_i2c_bus()
        self._logger.info("Bus now ready.")

    def _disable_i2c_bus(self):
        if not self._ctrl_enable.value:
            self._logger.info("I2C Bus disable requested, already disabled.")
        else:
            self._logger.info("Disabling I2C Bus")
            self._ctrl_enable.value = False
            mark = time.monotonic()
            while self._ctrl_ready.value:
                if time.monotonic() - mark >= self._wait_ready:
                    self._logger.error("I2C Bus not disabled within timeout. May be stuck.")
                    self._i2c_available = True
                    return
                time.sleep(0.1)
            self._logger.info("I2C Bus reports disabled.")
            self._i2c_available = False

    def _enable_i2c_bus(self):
        if self._ctrl_enable.value:
            self._logger.info("I2C Bus enable requested, already enabled.")
        else:
            self._logger.info("Enabling I2C Bus")
            self._ctrl_enable.value = True
            mark = time.monotonic()
            while not self._ctrl_ready.value:
                if time.monotonic() - mark >= self._wait_ready:
                    self._logger.error("I2C Bus did not become ready in time. Will not set up I2C-based sensors.")
                    self._i2c_available = False
                    return
                time.sleep(0.1)
            self._logger.info("I2C Bus reports ready.")
            self._i2c_available = True

    def _scan_aw9523s(self):
        """
        Identify all AW9523s in the sensor configurations.
        :return:
        """
        aw9523_addr_list = []
        for sensor in self._sensor_config:
            try:
                aw9523_addr_list.append(self._sensor_config[sensor]['enable_board'])
            except KeyError:
                pass
        return list(set(aw9523_addr_list))

    def _get_pinobj(self, pin_id):
        if pin_id is not None:
            return getattr(self._board, pin_id)
        else:
            return None

    @staticmethod
    def _reset_aw9523(aw9523_obj):
        """
        Reset all pins on an AW9523 to outputs and turn them off.
        :param aw9523_obj: AW9523
        """
        for pin in range(15):
            pin_obj = aw9523_obj.get_pin(pin)
            pin_obj.switch_to_output()
            pin_obj.value = False

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
    #         if sensor_data.response_type is not cobrabay.const.SENSOR_RESP_INR:
    #             outbound_data[sensor_id] = sensor_data
    #             enqueue = True
    #     if enqueue:
    #         self.data.put(outbound_data)

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
