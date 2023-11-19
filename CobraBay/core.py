####
# Cobra Bay - Main
####

import logging
from logging.handlers import WatchedFileHandler
import atexit
from pprint import pformat
import CobraBay
import sys


class CBCore:
    def __init__(self, config_obj, envoptions):
        self._network = None

        # Set the system state to initializing.
        self.system_state = 'init'

        # Register the exit handler.
        atexit.register(self.system_exit)

        # Get the master handler. This may have already been started by the command line invoker.
        self._master_logger = logging.getLogger("CobraBay")
        # Set the master logger to Debug, so all other messages will pass up through it.
        self._master_logger.setLevel(logging.DEBUG)
        # If console handler isn't already on the master logger, add it by default. Will be removed later if the
        # config tells us to.
        if not len(self._master_logger.handlers):
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG)
            self._master_logger.addHandler(console_handler)
        # Create a "core" logger, for just this module.
        self._logger = logging.getLogger("CobraBay").getChild("Core")

        self._logger.setLevel(logging.DEBUG)
        if envoptions.loglevel is not None:
            self._logger.warning("Based on command line options, setting core logger to '{}'".format(envoptions.loglevel))
            self._logger.setLevel(envoptions.loglevel)

        if not isinstance(config_obj, CobraBay.CBConfig):
            raise TypeError("CobraBay core must be passed a CobraBay Config object (CBConfig).")
        else:
            # Save the passed CBConfig object.
            self._active_config = config_obj

        # Update the logging handlers.
        self._setup_logging_handlers(**self._active_config.log_handlers())

        # Reset our own level based on the configuration.
        self._logger.setLevel(self._active_config.get_loglevel("core"))

        # Create the object for checking hardware status.
        self._logger.info("Creating Pi hardware monitor...")
        self._pistatus = CobraBay.CBPiStatus()

        # Create the network object.
        self._logger.info("Creating network object...")
        # Create Network object.
        network_config = self._active_config.network()
        self._logger.debug("Using network config:\n{}".format(pformat(network_config)))
        self._network = CobraBay.CBNetwork(**network_config, cbcore=self)
        # Register the hardware monitor with the network module.
        self._network.register_pistatus(self._pistatus)

        # # Create the outbound messages queue
        self._outbound_messages = []
        # Queue the startup message.
        self._outbound_messages.append({'topic_type': 'system', 'topic': 'device_connectivity', 'message': 'Online'})

        self._logger.info("Creating detectors...")
        # Create the detectors.
        self._detectors = self._setup_detectors()
        self._logger.debug("Detectors created: {}".format(pformat(self._detectors)))

        # Create master bay object for defined docking bay
        # Master list to store all the bays.
        self._bays = {}
        self._logger.info("Creating bays...")
        for bay_id in self._active_config.bays:
            self._logger.info("Bay ID: {}".format(bay_id))
            bay_config = self._active_config.bay(bay_id)
            self._logger.debug("Bay config:")
            self._logger.debug(pformat(bay_config))
            self._bays[bay_id] = CobraBay.CBBay(id=bay_id, system_detectors=self._detectors, cbcore=self, **bay_config)

        self._logger.info('Creating display...')
        display_config = self._active_config.display()
        self._logger.debug("Using display config:")
        self._logger.debug(pformat(display_config))
        self._display = CobraBay.CBDisplay(**display_config, cbcore=self)
        # Inform the network about the display. This is so the network can send display images. Nice to have, very
        # useful for debugging!
        self._network.display = self._display

        # Register the bay with the network and display.
        for bay_id in self._bays:
            self._network.register_bay(self._bays[bay_id])
            self._display.register_bay(self._bays[bay_id])

        # Create triggers.
        self._logger.info("Creating triggers...")
        self._setup_triggers()

        # Connect to the network.
        self._logger.info('Connecting to network...')
        self._network.connect()
        # Do an initial poll.
        self._network.poll()

        # Send initial values to MQTT, as we won't otherwise do so until we're in a running state.
        self._logger.info('Sending initial detector values...')
        for bay_id in self._bays:
            self._network.publish_bay_detectors(bay_id, publish=True)

        # We're done!
        self._logger.info('System Initialization complete.')
        self.system_state = 'running'

    # Common network handler, pushes data to the network and makes sure the MQTT client can poll.
    def _network_handler(self):
        # Send the outbound message queue to the network module to handle. After, we empty the message queue.
        network_data = self._network.poll()
        # We've pushed the message out, so reset our current outbound message queue.
        self._outbound_messages = []
        return network_data

    def _core_command(self, cmd):
        self._logger.info("Core command received: {}".format(cmd))

    # Check the system command trigger
    def _trigger_check(self):
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
            self._bays[bay_id].scan_triggers()

    # Main operating loop.
    def run(self):
        try:
            # This loop runs while the system is idle. Process commands, increment various timers.
            while True:
                # Do a network poll, this method handles all the default outbound messages and incoming status.
                network_data = self._network_handler()
                # Update the network components of the system state.
                system_status = {
                    'network': network_data['online'],
                    'mqtt': network_data['mqtt_status']}
                # Check triggers and execute actions if needed.
                self._trigger_check()
                # See if any of the bays checked to a motion state.
                for bay_id in self._bays:
                    if self._bays[bay_id].state in CobraBay.const.BAYSTATE_MOTION:
                        # Set the overall system state.
                        self.system_state = self._bays[bay_id].state
                        # Go into the motion loop.
                        self._motion(bay_id)
                        break
                self._display.show("clock", system_status=system_status)
        except BaseException as e:
            self._logger.critical("Unexpected exception encountered!")
            self._logger.exception(e)
            sys.exit(1)

    # Start sensors and display to guide parking.
    def _motion(self, bay_id):
        # Convert command to a state. Should have planned this better, but didn't.
        # if cmd == 'dock':
        #     direction = "docking"
        # elif cmd == 'undock':
        #     direction = "undocking"
        # else:
        #     raise ValueError("Motion command '{}' not valid.".format(cmd))
        #
        self._logger.info('Beginning {} on bay {}.'.format(CobraBay.const.BAYSTATE_MOTION, bay_id))

        # # Set the bay to the proper state.
        # self._bays[bay_id].state = direction
        #
        # Holding loop for undocking. While motion isn't detected, show the ready message. For docking, we go straight
        # to motion.
        if self._bays[bay_id].state == CobraBay.const.BAYSTATE_UNDOCKING:
            self._logger.debug("{} ({})".format(self._bays[bay_id].vector, type(self._bays[bay_id].vector)))
            while self._bays[bay_id].vector.direction in (CobraBay.const.DIR_STILL, CobraBay.const.GEN_UNKNOWN):
                self._display.show(mode='message',message="UNDOCK", color="orange", icons=False)
                self._network_handler()
                self._trigger_check()

        # As long as the bay is in the desired state, keep running.
        while self._bays[bay_id].state in CobraBay.const.BAYSTATE_MOTION:
            self._logger.debug("{} motion - Displaying".format(CobraBay.const.BAYSTATE_MOTION))
            # Send the bay object reference to the display method.
            self._display.show_motion(CobraBay.const.BAYSTATE_MOTION, self._bays[bay_id])
            # Poll the network.
            self._logger.debug("{} motion - Polling network.".format(CobraBay.const.BAYSTATE_MOTION))
            self._network_handler()
            # Check for completion
            self._bays[bay_id].check_timer()
            # Check the triggers. This lets an abort be called or an underlying system command be called.
            self._trigger_check()
        self._logger.info("Bay state changed to {}. Returning to idle.".format(self._bays[bay_id].state))

    def undock(self):
        self._logger.info('CobraBay: Undock not yet implemented.')
        return

    def system_exit(self, unexpected=True):
        self.system_state = 'shutdown'
        if unexpected:
            self._logger.critical("Shutting down due to unexpected error.")
        else:
            self._logger.critical("Performing requested shutdown.")
        # Wipe any previous messages. They don't matter now, we're going away!
        self._outbound_messages = []
        # Stop the ranging and close all the open sensors.
        try:
            for bay in self._bays:
                self._logger.info("Shutting down bay {}".format(bay))
                self._bays[bay].shutdown()
            for detector in self._detectors:
                self._logger.info("Disabling detector: {}".format(detector))
                self._detectors[detector].status = 'disabled'
        except AttributeError:
            # Must be exiting before bays were defined. That's okay.
            pass
        # Queue up outbound messages for shutdown.
        # Marking the system as offline *should* make everything else unavailable as well, unless availability
        # was set up incorrectly.
        self._outbound_messages.append(
            dict(
                topic_type='system',
                topic='device_connectivity',
                message='Offline',
                repeat=True
            )
        )
        # Have the display show 'offline', then grab that and send it to the MQTT broker. This will be the image
        # remaining when we go offline.
        try:
            self._display.show(system_status={'network': False, 'mqtt': False}, mode='message', message="OFFLINE",
                               icons=False)
            # Add image to the queue.
            self._outbound_messages.append(
                {'topic_type': 'system',
                 'topic': 'display',
                 'message': self._display.current, 'repeat': True})
        except AttributeError:
            pass
        # Call the network once. We'll ignore any commands we get.
        try:
            self._logger.info("Sending offline MQTT message.")
            self._network_handler()
        except AttributeError:
            pass
        self._logger.critical("Terminated.")
        if unexpected:
            sys.exit(1)
        else:
            sys.exit(0)

    # Method to set up the detectors based on the configuration.
    def _setup_detectors(self):
        return_dict = {}
        # Create detectors with the right type.
        self._logger.debug("Creating longitudinal detectors.")
        for detector_id in self._active_config.detectors_longitudinal:
            self._logger.info("Creating longitudinal detector: {}".format(detector_id))
            detector_config = self._active_config.detector(detector_id, 'longitudinal')
            self._logger.debug("Using settings: {}".format(detector_config))
            return_dict[detector_id] = CobraBay.detectors.Longitudinal(**detector_config)

        for detector_id in self._active_config.detectors_lateral:
            self._logger.info("Creating lateral detector: {}".format(detector_id))
            detector_config = self._active_config.detector(detector_id, 'lateral')
            self._logger.debug("Using settings: {}".format(detector_config))
            return_dict[detector_id] = CobraBay.detectors.Lateral(**detector_config)
        self._logger.debug("VL53LX instances: {}".format(len(CobraBay.sensors.CB_VL53L1X.instances)))
        return return_dict

    def _setup_triggers(self):
        # Set the logging level for the trigger group.
        trigger_logger = logging.getLogger("CobraBay").getChild("Trigger")
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
                self._syscmd_trigger = CobraBay.triggers.SysCommand(
                    id="syscmd",
                    topic=trigger_config['topic'],
                    log_level=trigger_config['log_level'])
                self._network.register_trigger(self._syscmd_trigger)
            else:
                if trigger_config['type'] == 'mqtt_state':
                    trigger_obj = CobraBay.triggers.MQTTSensor(
                        id=trigger_id,
                        topic=trigger_config['topic'],
                        topic_mode='full',
                        topic_prefix=None,
                        bay_obj=self._bays[trigger_config['bay']],
                        to_value=trigger_config['to_value'],
                        from_value=trigger_config['from_value'],
                        action=trigger_config['action'],
                        log_level=trigger_config['log_level']
                    )
                    # Register it with the bay based on Bay ID, and with the network
                    try:
                        self._bays[trigger_obj.bay_id].register_trigger(trigger_obj)
                    except KeyError:
                        self._logger.error("Cannot register Trigger ID '{}' with non-existent Bay ID '{}'".
                                           format(trigger_obj.id, trigger_obj.bay_id))
                    else:
                        # Register with the newtork.
                        self._network.register_trigger(trigger_obj)

                elif trigger_config['type'] == 'baycmd':
                    trigger_obj = CobraBay.triggers.BayCommand(
                        id=trigger_id,
                        topic=trigger_config['topic'],
                        bay_obj=self._bays[trigger_config['bay_id']],
                        log_level=trigger_config['log_level'])
                    try:
                        self._bays[trigger_obj.bay_id].register_trigger(trigger_obj)
                    except KeyError:
                        self._logger.error("Cannot register Bay Command trigger for non-existent Bay ID '{}'".format(trigger_obj.bay_id))
                    else:
                        # Register with the network.
                        self._network.register_trigger(trigger_obj)

                else:
                    # This case should be trapped by the config processor, but just in case, if trigger type
                    # is unknown, trap and ignore.
                    self._logger.error("Trigger {} has unknown type {}, cannot create.".
                                       format(trigger_id, trigger_config['type']))

    # Method to set up Logging handlers.
    def _setup_logging_handlers(self, file=False, console=False, file_path=None, log_format=None, syslog=False):
        # File based handler setup.
        if file:
            fh = WatchedFileHandler(file_path)
            fh.setFormatter(logging.Formatter(log_format))
            fh.setLevel(logging.DEBUG)
            # Attach to the master logger.
            self._master_logger.addHandler(fh)
            self._master_logger.info("File logging enabled. Writing to file: {}".format(file_path))

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
