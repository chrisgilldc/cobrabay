"""
CobraBay - Sensor Manager
"""
from __future__ import annotations

from adafruit_aw9523 import AW9523
import board
import busio
import logging
import time

import digitalio

import CobraBay.sensors
from CobraBay.datatypes import SensorResponse
from numpy import datetime64
import threading
import queue

#TODO: Try with asyncio or threading, eventually.

class CBSensorMgr:
    """
    CobraBay Sensor Manager. Creates sensor objects, polls them, keeps them in line. Also manages base I2C and
    AW9523 objects.
    """

    def __init__(self, sensor_config, i2c_config=None, generous_recovery=True, name=None, parent_logger=None,
                 log_level="WARNING", q_cbsmdata=None, q_cbsmcontrol=None):
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
        """
        # Initialize variables.
        self._sensors = {}  # Dictionary for sensor objects.
        self._latest_state = {}  # Rolling current state of the sensors.
        self._scan_speed_log = []  # List to store scan performance data.
        self._scan_avg_speed = 0
        self._i2c_bus = None
        self._ioexpanders = {}

        # self._thread: threading.Thread | None = None
        # self._thread_terminate = False

        # Save input parameters.
        self._name = name
        self._sensor_config = sensor_config
        self._i2c_config = i2c_config
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
                for addr in self._scan_aw9523s():
                    self._logger.info("Configuring AW9523 at address '{}'".format(hex(addr)))
                    self._ioexpanders[str(addr)] = AW9523(self._i2c_bus, addr, reset=True)
                    self._logger.info("Resetting all outputs on board...")
                    self._reset_aw9523(self._ioexpanders[str(addr)])

        # Pass the sensor config to the setup method to see if it works!
        self._sensors = self._create_sensor_multiple(sensor_config)

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

    def reset_i2cbus(self):
        self._logger.info("Resetting I2C bus on request.")
        self._ctrl_enable.value = False
        self._logger.info("Bus is now disabled. Waiting {}s before enablement.".format(self._wait_reset))
        time.sleep(self._wait_reset)
        self._ctrl_enable.value = True
        self._logger.info("Bus enable. Waiting {}s for ready.".format(self._wait_ready))
        mark = time.monotonic()
        while not self._ctrl_ready.value:
            if time.monotonic() - mark >= self._wait_ready:
                raise IOError("I2C Bus did not become ready in time.")
            time.sleep(0.1)
        self._logger.info("Bus now ready.")


    def sensors_activate(self):
        for sensor_id in self._sensors:
            if isinstance(self._sensors[sensor_id], CobraBay.sensors.BaseSensor):
                self._sensors[sensor_id].status = 'ranging'

    # Public Properties

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
                    sensors[sensor_id] = CobraBay.const.SENSTATE_FAULT
                else:
                    raise e
            else:
                sensors[sensor_id] = sensor_obj
        return sensors

    def _create_sensor_single(self, sensor_config):
        if sensor_config['hw_type'] == 'TFMini':
            # Create the sensor object.
            try:
                sensor_obj = CobraBay.sensors.TFMini(
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
            if self._i2c_bus is None:
                raise ValueError("Using I2C Sensor without I2C bus defined!")
            # Create an enablement pin in the appropriate place.
            # if sensor_config['enable_board'] == 0:
            #     try:
            #         target_pin = getattr(board, sensor_config['enable_pin'])
            #         enable_obj = digitalio.DigitalInOut(target_pin)
            #     except AttributeError:
            #         self._logger.error("Cannot configure sensor '{}'. Pin '{}' does not exist on the Pi.".
            #                            format(sensor_config['name'],sensor_config['enable_pin']))
            #         return
            # else:
            #     try:
            #         target_board = self._ioexpanders[str(sensor_config['enable_board'])]
            #     except KeyError:
            #         self._logger.error("Cannot configure sensor '{}', I/O board at address '{}' is not configured.".
            #                            format(sensor_config['name'],hex(sensor_config['enable_board'])))
            #         return
            #     else:
            #         enable_obj = target_board.get_pin(sensor_config['enable_pin'])
            if sensor_config['enable_board'] == 0:
                enable_board = 0
            else:
                try:
                    enable_board = self._ioexpanders[str(sensor_config['enable_board'])]
                except KeyError:
                    self._logger.error("Cannot configure sensor '{}', requested IO expander at address '{}' does not "
                                       "exist.".format(sensor_config['name'], hex(sensor_config['enable_board'])))
                    return
            self._logger.debug("Will pass I2C Bus: {} ({})".format(self._i2c_bus, type(self._i2c_bus)))
            self._logger.debug("Will pass IO Expander: {} ({})".format(enable_board, type(enable_board)))
            # Now create the actual sensor object.
            try:
                sensor_obj = CobraBay.sensors.CBVL53L1X(
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
            self.reset_i2cbus()

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
    #         if sensor_data.response_type is not CobraBay.const.SENSOR_VALUE_INR:
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
