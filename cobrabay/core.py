"""
Cobra Bay Core
"""

import copy
# import queue
import sys
import signal
import logging
import time
from logging.handlers import WatchedFileHandler

import cobrabay

class CBCore:
    """
    Cobra Bay Core object. Only one is needed. Handles interaction among other modules and shutdown.
    """
    def __init__(self, cmd_options=cobrabay.datatypes.ENVOPTIONS_EMPTY, q_cbsmdata=None, q_cbsmcontrol=None):
        """
        Cobra Bay Core Class Initializer.

        :param cmd_options: Command line options as passed. Includes defaults.
        :type cmd_options: cobrabay.datatypes.ENVOPTIONS
        :param q_cbsmdata: Data passing queue. Currently, does nothing, for later expansion.
        :type q_cbsmdata: Queue
        :param q_cbsmcontrol: Control queue. Currently, does nothing, for later expansion.
        :type q_cbsmcontrol: Queue
        """
        # Initialize variables
        self.system_state='init' # System state is initializing.
        self._bays = {}
        self._network = None
        self._pistatus = None
        self._sensor_latest_data = {}
        self.sensor_log = []
        self._sensormgr = None
        # Network data dict. This collects data from subscriptions as well as interface and MQTT status.
        # At start, we assume interface is down, and MQTT by definition can't be connected.
        self._net_data = {
            'interface': (time.monotonic(), False),
            'mqtt': (time.monotonic(), False)
        }
        self._triggers = None
        self._exit_code = -1

        # Get the master handler. This may have already been started by the command line invoker.
        self._master_logger = logging.getLogger("cobrabay")
        # Set the master logger to Debug, so all other messages will pass up through it.
        self._master_logger.setLevel(logging.DEBUG)
        # If console handler isn't already on the master logger, add it by default. Will be removed later if the
        # config tells us to.
        if not len(self._master_logger.handlers):
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG)
            self._master_logger.addHandler(console_handler)
        # Create a "core" logger, for just this module.
        self._logger = logging.getLogger("cobrabay").getChild("Core")

        self._logger.setLevel(logging.DEBUG)
        if cmd_options.loglevel is not None:
            self._logger.info(
                "Based on command line option, setting core logger to '{}'".format(cmd_options.loglevel))
            self._logger.setLevel(cmd_options.loglevel)

        # Register the signal handlers.
        self._setup_signal_handlers()

        # Create configuration manager.
        self._configmgr = cobrabay.config.CBConfigMgr(self, cmd_options=cmd_options, parent_logger=self._logger, log_level=cmd_options.loglevel)

        # Call the system setup method.
        self._setup_system()

    # Public Methods

    # Main operating loop.
    def run(self):
        """
        Main operating loop.
        """

        # Start the run loop.
        try:
            # Main run loop. Keep running as long as the exit code isn't set.
            while self._exit_code < 0:
                # New style....
                # Poll all the main objects to get them to update.
                self._pistatus.update()
                # Update the local sensor variable.
                # self._sensor_update()
                # Call Bay update to have them update their data state.
                for bay_id in self._bays:
                    self._bays[bay_id].update()
                # Poll the network
                self._logger.debug("Polling network.")
                self._network.poll()
                # Check triggers and execute actions if needed.
                # self._trigger_check()
                # See if any of the bays checked to a motion state.
                self._logger.debug("Updating bays.")
                for bay_id in self._bays:
                    if self._bays[bay_id].state in cobrabay.const.BAYSTATE_MOTION:
                        # Set the overall system state.
                        self.system_state = self._bays[bay_id].state
                        # Go into the motion loop.
                        self._motion(bay_id)
                        break
                self._logger.debug("Updating idle display.")
                self._display.show("clock")
        except BaseException as e:
            # Exit due to failure.
            self._logger.critical("Unexpected exception encountered!")
            self._logger.exception(e)
            self.system_exit(1)
        else:
            # We should only get here if we caught some kind of signal and set an exit code. Clean up and do it.
            self.system_exit(self._exit_code)

    def system_exit(self, exit_code=1):
        """
        Perform system shutdown. Clean up sensors, send status to MQTT.
        :param exit_code: Exit code to send when terminating. This should follow BASH conventions.
        """
        # Set system state to offline. Network module will pull this and send it to MQTT.
        self.system_state = 'offline'
        # Shut off the sensors.
        # This must be done first, otherwise the I2C bus will get cut out from underneath the sensors.
        # Set all sensors to disable. This won't actually disable the TFMini, but meh.
        try:
            self._sensormgr.set_sensor_state(cobrabay.const.SENSTATE_DISABLED)
        except AttributeError:
            # If the sensor manager wasn't initialized, this failsed. But that's okay.
            pass
        self._logger.critical("Terminated.")
        sys.exit(exit_code)

    # Public Properties

    @property
    def configured_sensors(self):
        """
        Return a list of configured sensor IDs.

        :return:
        """
        return self._active_config.sensors

    @property
    def sensor_latest_data(self):
        """Latest data from the sensor manager."""
        return self._sensor_latest_data

    @property
    def net_data(self):
        """ Data from subscribed topics in the Network Module. """
        return self._net_data

    def set_net_data(self, id, payload):
        """ Set new payload value for a subscribed topic. Wrap it in a timestamp."""
        self._net_data[id] = (time.monotonic(), payload)

    # Private methods

    def _core_command(self, cmd):
        """ Core command handlers. Not yet implemented."""
        #TODO: Fully implement core command handler.
        self._logger.info("Core command received: {}".format(cmd))
        self._logger.info("Core command handling not yet implemented. Nothing to do.")

    def _motion(self, bay_id):
        self._logger.info('Beginning {} on bay {}.'.format(self._bays[bay_id].state, bay_id))

        # If the bay is in UNDOCKING, show 'UNDOCKING' on the display until there is motion. If there is no motion by
        # the undock timeout, return to READY.
        if self._bays[bay_id].state == cobrabay.const.BAYSTATE_UNDOCKING:
            self._logger.debug("{} ({})".format(self._bays[bay_id].vector, type(self._bays[bay_id].vector)))
            while (self._bays[bay_id].vector.direction in (cobrabay.const.DIR_STILL, cobrabay.const.GEN_UNKNOWN) and
                   self._bays[bay_id].state == cobrabay.const.BAYSTATE_UNDOCKING):
                # Update local sensor variable.
                self._sensor_update()
                # Update bays with sensor data.
                for bay_id in self._bays:
                    try:
                        self._bays[bay_id].update()
                    except IndexError as e:
                        self._logger.error("Bay {} threw index error. Trace details...".format(bay_id))
                        self._logger.exception(e)
                        self._logger.debug("Sensor log at time of exception: {}".format(self.sensor_log))
                self._display.show(mode='message', message="UNDOCK", color="orange", icons=False)
                # Timeout and go back to ready if the vehicle hasn't moved by the timeout.
                # Kids are probably running around.
                #self._bays[bay_id].check_timer()
                # If the bay state has returned to ready, break.
                # Check the network
                self._network_handler()
                # Check triggers for changes.
                self._trigger_check()

        # As long as the bay is in the desired state, keep running.
        while self._bays[bay_id].state in cobrabay.const.BAYSTATE_MOTION:
            self._logger.debug("{} motion - Displaying".format(cobrabay.const.BAYSTATE_MOTION))
            # Send the bay object reference to the display method.
            #TODO: Redo how the display gets its data.
            self._display.show_motion(cobrabay.const.BAYSTATE_MOTION, self._bays[bay_id])
            # Update local sensor variable.
            self._logger.debug("{} motion - Updating local sensor values.".format(cobrabay.const.BAYSTATE_MOTION))
            self._sensor_update()
            # Update bays with sensor data.
            for bay_id in self._bays:
                self._bays[bay_id].update()
            # Poll the network.
            self._logger.debug("{} motion - Polling network.".format(cobrabay.const.BAYSTATE_MOTION))
            self._network_handler()
            # Check for completion
            #self._bays[bay_id].check_timer()
            # Check the triggers. This lets an abort be called or an underlying system command be called.
            self._trigger_check()
        self._logger.info("Bay state changed to {}. Returning to idle.".format(self._bays[bay_id].state))

    def _network_handler(self):
        """ Common network handlers. Pushes data to the network, polls the MQTT connection and handles inbound
        messages. """
        # Send the outbound message queue to the network module to handle. After, we empty the message queue.
        network_data = self._network.poll()
        # We've pushed the message out, so reset our current outbound message queue.
        self._outbound_messages = []
        return network_data

    def _sensor_update(self):
        """
        Update local latest sensor variable from the data queue.
        :return:
        """
        # Loop the sensors.
        #TODO: Make this conditional on execution mode (single/async/threaded/process)
        self._sensormgr.loop()
        # Pull the sensor data into the latest data holding variable. This should ease threading.
        if self._q_cbsmdata.empty():
            self._logger.debug("No data available in sensor queue.")
        else:
            latest_data = self._q_cbsmdata.get_nowait()
            self._logger.debug("Fetched sensor data from queue: {}".format(latest_data))
            self._q_cbsmdata.task_done()
            # latest_status = self._q_cbsmstatus.get_nowait()
            # self._q_cbsmstatus.task_done()
            if len(self.sensor_log) > 0:
                if latest_data.timestamp != self.sensor_log[0].timestamp:
                    # If timestamps are different, sensor manager has updated the data, and it's new to fetch.
                    self._sensor_log_add(latest_data)
                else:
                    self._logger.debug("No change to latest sensor data, nothing to update.")
                    return
            else:
                # If there's no data in the log, we're at startup and go ahead and add.
                self._sensor_log_add(latest_data)

    def _sensor_log_add(self, sensor_response):
        """
        Add a SensorResponse from the sensor manager to the log.

        :param sensor_response: Sensor Response record to add
        :type sensor_response: namedtuple
        :return:
        """
        self.sensor_log = [copy.deepcopy(sensor_response)] + self.sensor_log[0:99]
        self._logger.debug("Sensor log now has {} entries.".format(len(self.sensor_log)))
        if len(self.sensor_log) == 0:
            # If we're just starting to get data, we can pull the data over directly.
            self._logger.debug("No data marked as latest, considering all data in sensor log as latest.")
            self._sensor_latest_data = self.sensor_log[0].sensors
        # Pull out the most recent data and put it in the sensor_most_recent dict.
        for sensor_id in self.sensor_log[0].sensors:
            # Don't update when waiting for an interrupt.
            if self.sensor_log[0].sensors[sensor_id].response_type == cobrabay.const.SENSOR_RESP_INR:
                self._logger.debug("Sensor '{}' is waiting for interrupt. Keeping previous latest value.".format(sensor_id))
            else:
                self._sensor_latest_data[sensor_id] = self.sensor_log[0].sensors[sensor_id]
                self._logger.debug("Adding to sensor data as latest. Latest data now has: {}".format(
                    self._sensor_latest_data))

    def _trigger_check(self):
        """
        Check the system command trigger, tell the bays to check their attached triggers.
        :return:
        """
        # We pass the caller name explicitly. There's inspect-fu that could be done, but that
        # may have portability issues.
        self._logger.debug("Checking System Command trigger.")
        if self._syscmd_trigger.triggered:
            self._logger.debug("System command handler is triggered.")
            while self._syscmd_trigger.cmd_stack:
                cmd = self._syscmd_trigger.cmd_stack.pop(0)
                self._logger.debug("Sending command '{}' to core processor.".format(cmd))
                self._core_command(cmd)
        # Tell the bays to check their triggers.
        for bay_id in self._bays:
            self._logger.debug("Commanding trigger scan for bay '{}'".format(bay_id))
            self._bays[bay_id].triggers_check()

    def _setup_logging_handlers(self, file=False, console=False, log_file=None, log_format=None, syslog=False):
        """ Setup logging handlers."""
        # File based handler setup.
        if file:
            fh = WatchedFileHandler(log_file)
            fh.setFormatter(logging.Formatter(log_format))
            fh.setLevel(logging.DEBUG)
            # Attach to the master logger.
            self._master_logger.addHandler(fh)
            self._master_logger.info("File logging enabled. Writing to file: {}".format(log_file))

        if syslog:
            raise NotImplemented("Syslog logging not yet implemented")

        # Deal with the Console logger.

        # Send a last message through the temporary console handler.
        if not console:
            self._logger.info("Disabling general console logging. Will only log Critical events to the console.")
        else:
            self._logger.info("Console logging enabled. Passing logging to console.")

        # Remove all existing console handlers so a new one can be created.
        for handler in self._master_logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                self._master_logger.removeHandler(handler)

        # Create a new handler.
        ch = logging.StreamHandler()
        # Set format.
        ch.setFormatter(logging.Formatter(log_format))
        # Set logging level.
        if console:
            ch.setLevel(logging.DEBUG)
        else:
            ch.setLevel(logging.CRITICAL)
        self._master_logger.addHandler(ch)

    def _setup_sensors(self):
        """
        Setup sensors. OLD.
        :return:
        """
        return_dict = {}
        # Create the correct sensors.
        self._logger.debug("Creating sensors.")
        for sensor_id  in self._active_config.sensors:
            self._logger.debug("Creating sensor: {}".format(sensor_id))
            sensor_config = self._active_config.sensor(sensor_id)
            self._logger.debug("Using settings: {}".format(sensor_config))
            # Create the correct type of sensor object based on defined type.
            if sensor_config['hw_type'] == 'VL53L1X':
                # return_dict[sensor_id] = cobrabay.sensors.CBVL53L1X(
                #     name=sensor_config['name'], i2c_address=sensor_config['hw_settings']['i2c_address'],
                #     i2c_bus=sensor_config['hw_settings']['i2c_bus'],
                #     enable_board=sensor_config['hw_settings']['enable_board'],
                #     enable_pin=sensor_config['hw_settings']['enable_pin'],
                #     timing=sensor_config['hw_settings']['timing'], always_range=sensor_config['always_range'],
                #     distance_mode=sensor_config['hw_settings']['distance_mode'],
                #     parent_logger=self._logger,
                #     log_level=sensor_config['log_level'])
                return_dict[sensor_id] = cobrabay.sensors.CBVL53L1X(name=sensor_config['name'],
                                                                    **sensor_config['hw_settings'])
            elif sensor_config['hw_type'] == 'TFMini':
                return_dict[sensor_id] = cobrabay.sensors.TFMini(name=sensor_config['name'],
                                                                 **sensor_config['hw_settings'])

            else:
                self._logger.error("Sensor '{}' has unknown type '{}'. Cannot configure!".
                                   format(sensor_id, sensor_config['hw_type']))
        # self._logger.debug("VL53LX instances: {}".format(len(cobrabay.sensors.CBVL53L1X.instances)))
        return return_dict

    def _setup_signal_handlers(self):
        """
        Sets up POSIX signal handlers.
        :return:
        """
        self._logger.info("Registering signal handlers.")
        # Reload configuration.
        # signal.signal(signal.SIGHUP, self._reload_config)
        # Terminate cleanly.
        # Default quit
        signal.signal(signal.SIGTERM, self._signal_handler)
        # Quit and dump core. Not going to do that, so
        signal.signal(signal.SIGQUIT, self._signal_handler)

        # All other signals are some form of error.
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGILL, self._signal_handler)
        signal.signal(signal.SIGTRAP, self._signal_handler)
        signal.signal(signal.SIGABRT, self._signal_handler)
        signal.signal(signal.SIGBUS, self._signal_handler)
        signal.signal(signal.SIGFPE, self._signal_handler)
        # signal.signal(signal.SIGKILL, receiveSignal)
        signal.signal(signal.SIGUSR1, self._signal_handler)
        signal.signal(signal.SIGSEGV, self._signal_handler)
        signal.signal(signal.SIGUSR2, self._signal_handler)
        signal.signal(signal.SIGPIPE, self._signal_handler)
        signal.signal(signal.SIGALRM, self._signal_handler)

    def _setup_display(self):
        """
        Set up the Display Object
        """
        # Create the display.
        self._logger.info("Core got availability topic: {}".format(self._network.availability_topic))
        self._display = cobrabay.CBDisplay(
            availability_topic=self._network.availability_topic,
            client_id=self._network.client_id,
            device_info=self._network.device_info,
            mqtt_settings=self._network.mqtt_settings,
            system_name=self._network.system_name,
            width=self._configmgr.active_config.config['display']['width'],
            height=self._configmgr.active_config.config['display']['height'],
            gpio_slowdown=self._configmgr.active_config.config['display']['gpio_slowdown'],
            cbcore=self,
            font=self._configmgr.active_config.config['display']['font'],
            font_size_clock=self._configmgr.active_config.config['display']['font_size_clock'],
            font_size_range=self._configmgr.active_config.config['display']['font_size_range'],
            #bottom_box=self._configmgr.active_config.config['display']['bottom_box'],
            #strobe_speed=self._configmgr.active_config.config['display']['strobe_speed'],
            icons=self._configmgr.active_config.config['display']['icons'],
            unit_system=self._configmgr.unit_system,
            log_level=self._configmgr.active_config.get_loglevel('display')
        )


    def _setup_network(self):
        """
        Set up the Network Object
        """

        # Create the network object.
        self._logger.info("Configuring Network...")
        # Create Network object.
        self._network = cobrabay.CBNetwork(
            unit_system=self._configmgr.unit_system,
            system_name=self._configmgr.system_name,
            interface=self._configmgr.active_config.config['system']['interface'],
            broker=self._configmgr.active_config.config['system']['mqtt']['broker'],
            port=self._configmgr.active_config.config['system']['mqtt']['port'],
            username=self._configmgr.active_config.config['system']['mqtt']['username'],
            password=self._configmgr.active_config.config['system']['mqtt']['password'],
            base=self._configmgr.active_config.config['system']['mqtt']['base'],
            ha_discover=self._configmgr.active_config.config['system']['ha']['discover'],
            ha_pd_send=self._configmgr.active_config.config['system']['ha']['pd_send'],
            ha_base=self._configmgr.active_config.config['system']['ha']['base'],
            ha_suggested_area=self._configmgr.active_config.config['system']['ha']['suggested_area'],
            cbcore=self,
            log_level=self._configmgr.active_config.get_loglevel('network'))

        # Add net data entries for all the icons and all the subscriptions, so we have *something*
        # even before MQTT data is received.
        for icon in self._configmgr.active_config.config['display']['icons']:
             self._net_data[icon] = (None,None)
        self._net_data['ev-charging'] = (None, None)
        #TODO: fix this up for subscriptions.

        # for sub in self._active_config.network()['subscriptions']:
        #     self._net_data[sub['id']] = (None,None)
        self._logger.debug("Net data at startup: {}".format(self._net_data))

        # # Create the outbound messages queue
        self._outbound_messages = []
        # Queue the startup message.
        self._outbound_messages.append({'topic_type': 'system', 'topic': 'device_connectivity', 'message': 'Online'})


    def _setup_util(self, config_obj):
        """
        Setup miscellaneous utility items - PI hardware monitor
        """

    def _setup_system(self):
        """
        Main system setup operations. Create all necessary objects based on the current active configuration in the
        configuration manager.
        """

        # Set the system state to init. This is redundant on startup but needed if reinitializing.
        self.system_state = 'init'
        self._logger.info("Setting up system.")

        if not isinstance(self._configmgr.active_config, cobrabay.config.CBConfig):
            raise TypeError("Cobra Bay core must be passed a Cobra Bay Config object (CBConfig).")

        # Update the logging handlers.
        self._setup_logging_handlers(
            file=self._configmgr.active_config.config['system']['logging']['file'],
            console=self._configmgr.active_config.config['system']['logging']['console'],
            log_file=self._configmgr.active_config.config['system']['logging']['log_file'],
            log_format=self._configmgr.active_config.config['system']['logging']['log_format'],
            )

        # Reset our own level based on the configuration.
        self._logger.setLevel(self._configmgr.active_config.get_loglevel("core"))

        # Create the network object.
        self._logger.info("Creating network object...")
        self._setup_network()

        # Create the object for checking hardware status.
        self._logger.info("Creating Pi hardware monitor...")
        self._pistatus = cobrabay.CBPiStatus(
            availability_topic=self._network.availability_topic,
            client_id=self._network.client_id,
            device_info=self._network.device_info,
            mqtt_settings=self._network.mqtt_settings,
            system_name=self._configmgr.system_name,
            unit_system=self._configmgr.unit_system
        )

        # Create the display so we can show a startup message!
        self._setup_display()

        # Register the hardware monitor with the network module.
        # self._network.register_pistatus(self._pistatus)
        # Register the display with the network module.
        self._network.display = self._display

        # self._logger.info("Creating sensor manager...")
        # # Create the Sensor Manager
        # sensor_config = self._active_config.sensors_config()
        # self._logger.debug("Using Sensor config:\n{}".format(pformat(sensor_config)))
        # self._logger.debug("Using I2C config:\n{}".format(pformat(self._active_config.i2c_config())))
        # # Create the queues needed for the sensor manager.
        # self._q_cbsmdata = queue.Queue(maxsize=1)
        # self._q_cbsmstatus = queue.Queue(maxsize=1)
        # self._q_cbsmcontrol = queue.Queue(maxsize=1)
        # self._sensormgr = cobrabay.CBSensorMgr(sensor_config=sensor_config, i2c_config=self._active_config.i2c_config(),
        #                                        log_level=self._active_config.get_loglevel('sensors'),
        #                                        q_cbsmdata=self._q_cbsmdata, q_cbsmstatus=self._q_cbsmstatus,
        #                                        q_cbsmcontrol=self._q_cbsmcontrol)
        # # Register the sensor manager with the network handler, now that it exists.
        # self._logger.debug("Registering sensor manager with the network module.")
        # self._network.register_sensormgr(self._sensormgr)
        # # Activate the sensors.
        # #TODO: Convert to using the command queue to be threading safe.
        # self._q_cbsmcontrol.put(
        #     (cobrabay.const.SENSTATE_RANGING,None)
        # )
        # #self._sensormgr.set_sensor_state(target_state=cobrabay.const.SENSTATE_RANGING)
        # # Loop once and get initial latest data.
        # #TODO: Add config option for threading vs. not and make conditional.
        # self._sensormgr.loop()
        #
        # # Initial sensor update.
        # self._sensor_update()
        # self._sensor_latest_data = self._q_cbsmdata.get_nowait()
        # self._logger.debug("Initial data from sensor manager: {}".format(self._sensor_latest_data))

        # Create master bay object for defined docking bay
        # Master list to store all the bays.
        # self._bays = {}
        # self._logger.info("Creating bays...")
        # for bay_id in self._active_config.bays:
        #     self._logger.info("Bay ID: {}".format(bay_id))
        #     bay_config = self._active_config.bay(bay_id)
        #     self._logger.debug("Bay config:")
        #     self._logger.debug(pformat(bay_config))
        #     self._bays[bay_id] = cobrabay.CBBay(bay_id=bay_id, cbcore=self, q_cbsmcontrol=self._q_cbsmcontrol, **bay_config)
        #
        # self._logger.info('Creating display...')
        # display_config = self._active_config.display()
        # self._logger.debug("Using display config:")
        # self._logger.debug(pformat(display_config))
        # self._display = cobrabay.CBDisplay(**display_config, cbcore=self)


        # # Register the bay with the network and display.
        # for bay_id in self._bays:
        #     self._network.register_bay(self._bays[bay_id])
        #     self._display.register_bay(self._bays[bay_id])
        #
        # # Create triggers.
        # self._logger.info("Creating triggers...")
        # self._setup_triggers()

        # Connect to the network.
        self._logger.info('Connecting to network...')
        self._network.connect()
        # Do an initial poll.
        self._network.poll()

        # Send initial values to MQTT, as we won't otherwise do so until we're in a running state.
        #TODO: Rework initial sending of sensor values.
        #self._logger.info('Sending initial detector values...')
        #for bay_id in self._bays:
        #    self._network.publish_bay_detectors(bay_id, publish=True)

        # We're done!
        self._logger.info('System Initialization complete.')
        self.system_state = 'running'

    def _setup_triggers(self):
        """ Setup triggers based on the configuration. """
        # Set the logging level for the trigger group.
        trigger_logger = logging.getLogger("cobrabay").getChild("Trigger")
        trigger_logger.setLevel("DEBUG")

        self._logger.debug("Creating triggers...")
        self._logger.info("Trigger list: {}".format(self._active_config.triggers))
        for trigger_id in self._active_config.triggers:
            self._logger.debug("Trigger ID: {}".format(trigger_id))
            trigger_config = self._active_config.trigger(trigger_id)
            self._logger.debug("Has config: {}".format(trigger_config))
            # Create trigger object based on type.
            if trigger_config['type'] == "syscmd":
                # Create the system command trigger. We should only do this once!
                self._syscmd_trigger = cobrabay.triggers.SysCommand(
                    trigger_id="syscmd",
                    topic=trigger_config['topic'],
                    log_level=trigger_config['log_level'])
                self._network.register_trigger(self._syscmd_trigger)
            else:
                if trigger_config['type'] == 'mqtt_state':
                    try:
                        bay_obj = self._bays[trigger_config['bay']]
                    except KeyError:
                        self._logger.error("Trigger '{}' references non-existent bay '{}'. Cannot setup!".
                                           format(trigger_id, trigger_config['bay']))
                    else:
                        trigger_obj = cobrabay.triggers.MQTTSensor(
                            trigger_id=trigger_id,
                            topic=trigger_config['topic'],
                            topic_mode='full',
                            # topic_prefix=None, Don't pass a topic_prefix, not needed here.
                            bay_obj=self._bays[trigger_config['bay']],
                            payload_to_value=trigger_config['payload_to_value'],
                            payload_from_value=trigger_config['payload_from_value'],
                            action=trigger_config['action'],
                            log_level=trigger_config['log_level']
                        )
                        # Register it with the bay based on Bay ID, and with the network
                        try:
                            self._bays[trigger_obj.bay_id].trigger_register(trigger_obj)
                        except KeyError:
                            self._logger.error("Cannot register Trigger ID '{}' with non-existent Bay ID '{}'".
                                               format(trigger_obj.id, trigger_obj.bay_id))
                        else:
                            # Register with the newtork.
                            self._network.register_trigger(trigger_obj)

                elif trigger_config['type'] == 'baycmd':
                    trigger_obj = cobrabay.triggers.BayCommand(
                        trigger_id=trigger_id,
                        topic=trigger_config['topic'],
                        bay_obj=self._bays[trigger_config['bay_id']],
                        log_level=trigger_config['log_level'])
                    try:
                        self._bays[trigger_obj.bay_id].trigger_register(trigger_obj)
                    except KeyError:
                        self._logger.error("Cannot register Bay Command trigger for non-existent Bay ID '{}'".format(
                            trigger_obj.bay_id))
                    else:
                        # Register with the network.
                        self._network.register_trigger(trigger_obj)

                else:
                    # This case should be trapped by the config processor, but just in case, if trigger type
                    # is unknown, trap and ignore.
                    self._logger.error("Trigger {} has unknown type {}, cannot create.".
                                       format(trigger_id, trigger_config['type']))

    def _signal_handler(self, signalNumber=None, frame=None):
        """Catch incoming signals and perform the correct actions.

        :param signalNumber: Signal Number
        :param frame: F
        :return:
        """

        self._logger.info(f"Caught signal {signalNumber}")
        if signalNumber == 1:
            self._logger.critical("SIGHUP for reload not yet supported. Will do nothing.")
        elif signalNumber == 2:
            self._logger.critical("Keyboard interrupt received! Performing clean shutdown and exit.")
            # self.system_exit(exit_code=0)
            self._exit_code = 0
        elif signalNumber in (3, 15):
            self._logger.critical("Performing clean shutdown and exit.")
            self._exit_code = 0
        else:
            self._logger.critical("Unexpected signal received. Cleaning up and exiting.")
            self._exit_code = signalNumber+128
