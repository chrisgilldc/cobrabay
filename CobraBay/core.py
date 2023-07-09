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
    def __init__(self, config_obj):
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

        # Initial startup message.
        self._logger.info("CobraBay {} initializing...".format(CobraBay.__version__))

        if not isinstance(config_obj,CobraBay.CBConfig):
            raise TypeError("CobraBay core must be passed a CobraBay Config object (CBConfig).")
        else:
            # Save the passed CBConfig object.
            self._cbconfig = config_obj

        # Update the logging handlers.
        self._setup_logging_handlers(self._cbconfig.log_handlers())

        # Reset our own level based on the configuration.
        self._logger.setLevel(self._cbconfig.get_loglevel("core"))

        # Create the object for checking hardware status.
        self._logger.debug("Creating Pi hardware monitor...")
        self._pistatus = CobraBay.CBPiStatus()

        # Create the network object.
        self._logger.debug("Creating network object...")
        # Create Network object.
        network_config = self._cbconfig.network()
        self._logger.debug("Using network config:")
        self._logger.debug(pformat(network_config))
        self._network = CobraBay.CBNetwork(**network_config, cbcore=self)
        self._network.register_pistatus(self._pistatus)

        # Queue for outbound messages.
        self._outbound_messages = []
        # Queue the startup message.
        self._outbound_messages.append({'topic_type': 'system', 'topic': 'device_connectivity', 'message': 'Online'})

        self._logger.debug("Creating detectors...")
        # Create the detectors.
        self._detectors = self._setup_detectors()
        self._logger.debug("Have detectors: {}".format(self._detectors))

        # Create master bay object for defined docking bay
        # Master list to store all the bays.
        self._bays = {}
        self._logger.info("Creating bays...")
        for bay_id in self._cbconfig.bay_list:
            self._logger.info("Bay ID: {}".format(bay_id))
            bay_config = self._cbconfig.bay(bay_id)
            self._logger.debug("Bay config:")
            self._logger.debug(pformat(bay_config))
            self._bays[bay_id] = CobraBay.CBBay(**bay_config, system_detectors=self._detectors, cbcore=self)

        self._logger.info('Creating display...')
        display_config = self._cbconfig.display()
        self._logger.debug("Using display config:")
        self._logger.debug(pformat(display_config))
        self._display = CobraBay.CBDisplay(**display_config, cbcore=self)
        # Inform the network about the display. This is so the network can send display images. Nice to have, very
        # useful for debugging!
        self._network.display = self._display

        # Register the bay with the network and display.
        for bay_id in self._bays:
            self._network.register_bay(self._bays[bay_id])
            self._display.register_bay(self._bays[bay_id].display_reg_info)

        # # Collect messages from the bays.
        # for bay_id in self._bays:
        #     self._outbound_messages = self._outbound_messages + self._bays[bay_id].mqtt_messages(verify=True)

        # Create triggers.
        self._logger.debug("About to setup triggers.")
        self._triggers = self._setup_triggers()
        self._logger.debug("Done calling setup_triggers.")
        self._logger.debug("Have triggers: {}".format(self._triggers))

        # Parcel trigger objects out to the right place.
        #  - MQTT triggers go to the network module,
        #  - Range triggers go to the appropriate bay.
        self._logger.debug("Linking triggers to modules.")
        for trigger_id in self._triggers:
            trigger_obj = self._triggers[trigger_id]
            # Network needs to be told about triggers that talk to MQTT.
            if isinstance(trigger_obj, CobraBay.triggers.MQTTTrigger):
                self._logger.debug("Registering Trigger {} with Network module.".format(trigger_id))
                self._network.register_trigger(trigger_obj)
            # Tell bays about their bay triggers.
            #if trigger_obj.type in ('baycommand'):
            #    self._bays[trigger_obj.bay_id].register_trigger(trigger_obj)

            # elif self._triggers[trigger_id].type == 'range':
            #     # Make sure the desired bay exists!
            #     try:
            #         target_bay = self._bays[self._triggers[trigger_id].bay_id]
            #     except KeyError:
            #         self._logger.error("Trigger {} references non-existent bay {}. Cannot link.".
            #                            format(trigger_id, self._bays[self._triggers[trigger_id].bay_id] ))
            #         break
            #     target_bay.register_trigger(self._triggers[trigger_id])

        # Connect to the network.
        self._logger.info('Connecting to network...')
        self._network.connect()
        # Do an initial poll.
        self._network.poll()
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

    # Method for checking the triggers and acting appropriately.
    def _trigger_check(self):
        # We pass the caller name explicitly. There's inspect-fu that could be done, but that
        # may have portability issues.
        for trigger_id in self._triggers.keys():
            self._logger.debug("Checking trigger: {}".format(trigger_id))
            trigger_obj = self._triggers[trigger_id]
            # Disabling range triggers for the moment.
            # Range objects need to be checked explicitly. So call it!
            # if trigger_obj.type == 'range':
            #     trigger_obj.check()
            # self._logger.debug("Has trigger value: {}".format(trigger_obj.triggered))
            if trigger_obj.triggered:
                while trigger_obj.cmd_stack:
                    # Pop the command from the object.
                    cmd = trigger_obj.cmd_stack.pop(0)
                    # Route it appropriately.
                    if isinstance(trigger_obj,CobraBay.triggers.SysCommand):
                        self._core_command(cmd)
                    else:
                        if cmd in ('dock','undock'):
                            # Dock or undock, enter the motion routine.
                            self._motion(trigger_obj.bay_id, cmd)
                            self._logger.debug("Returned from motion method to trigger method.")
                            break
                        elif cmd == 'abort':
                            # On an abort, call the bay's abort. This will set it ready and clean up.
                            # If we're in the _motion method, this will go back to run, if not, nothing happens.
                            self._bays[trigger_obj.bay_id].abort()
            self._logger.debug("Trigger check complete.")

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
                    'mqtt': network_data['mqtt_status'] }

                # Check triggers and execute actions if needed.
                self._trigger_check()

                self._display.show(system_status, "clock")
        except BaseException as e:
            self._logger.critical("Unexpected exception encountered!")
            self._logger.exception(e)
            sys.exit(1)

    # Start sensors and display to guide parking.
    def _motion(self, bay_id, cmd):
        # Convert command to a state. Should have planned this better, but didn't.
        if cmd == 'dock':
            direction = "docking"
        elif cmd == 'undock':
            direction = "undocking"
        else:
            raise ValueError("Motion command '{}' not valid.".format(cmd))

        self._logger.info('Beginning {} on bay {}.'.format(direction, bay_id))

        # Set the bay to the proper state.
        self._bays[bay_id].state = direction

        # As long as the bay is in the desired state, keep running.
        while self._bays[bay_id].state == direction:
            self._logger.debug("{} motion - Displaying".format(cmd))
            # Send the bay object reference to the display method.
            self._display.show_motion(direction, self._bays[bay_id])
            # Poll the network.
            self._logger.debug("{} motion - Polling network.".format(cmd))
            self._network_handler()
            # Check for completion
            self._bays[bay_id].check_timer()
            # Check the triggers. This lets an abort be called or an underlying system command be called.
            self._trigger_check()
        self._logger.info("Bay state changed to {}. Returning to idle.".format(self._bays[bay_id].state))
        # Collect and send a final set of MQTT messages.
        # self._logger.debug("Collecting MQTT messages from bay.")
        # bay_messages = self._bays[bay_id].mqtt_messages()
        # self._logger.debug("Collected MQTT messages: {}".format(bay_messages))
        # self._outbound_messages = self._outbound_messages + bay_messages

    def undock(self):
        self._logger.info('CobraBay: Undock not yet implemented.')
        return

    def system_exit(self):
        self.system_state = 'shutdown'
        # Wipe any previous messages. They don't matter now, we're going away!
        self._outbound_messages = []
        # Stop the ranging and close all the open sensors.
        try:
            for bay in self._bays:
                self._logger.critical("Shutting down bay {}".format(bay))
                self._bays[bay].shutdown()
            for detector in self._detectors:
                self._logger.critical("Disabling detector: {}".format(detector))
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
            self._display.show(system_status={ 'network': False, 'mqtt': False }, mode='message', message="OFFLINE", icons=False)
            # Add image to the queue.
            self._outbound_messages.append(
                {'topic_type': 'system',
                 'topic': 'display',
                 'message': self._display.current, 'repeat': True})
        except AttributeError:
            pass
        # Call the network once. We'll ignore any commands we get.
        self._logger.critical("Sending offline MQTT message.")
        self._network_handler()

    # Method to set up the detectors based on the configuration.
    def _setup_detectors(self):
        return_dict = {}
        # Create detectors with the right type.
        self._logger.debug("Creating longitudinal detectors.")
        for detector_id in self._cbconfig.detectors_longitudinal:
            self._logger.info("Creating longitudinal detector: {}".format(detector_id))
            detector_config = self._cbconfig.detector(detector_id,'longitudinal')
            self._logger.debug("Using settings: {}".format(detector_config))
            return_dict[detector_id] = CobraBay.detectors.Range(**detector_config)

        for detector_id in self._cbconfig.detectors_lateral:
            self._logger.info("Creating lateral detector: {}".format(detector_id))
            detector_config = self._cbconfig.detector(detector_id,'lateral')
            self._logger.debug("Using settings: {}".format(detector_config))
            return_dict[detector_id] = CobraBay.detectors.Lateral(**detector_config)
        self._logger.debug("VL53LX instances: {}".format(len(CobraBay.sensors.CB_VL53L1X.instances)))
        return return_dict

    def _setup_triggers(self):
        self._logger.debug("Creating triggers...")
        return_dict = {}
        self._logger.info("Trigger list: {}".format(self._cbconfig.trigger_list))
        for trigger_id in self._cbconfig.trigger_list:
            self._logger.info("Trigger ID: {}".format(trigger_id))
            trigger_config = self._cbconfig.trigger(trigger_id)
            self._logger.debug(trigger_config)
            # Create trigger object based on type.
            # All triggers except the system command handler will need a reference to the bay object.
            if trigger_config['type'] == "syscommand":
                return_dict[trigger_id] = CobraBay.triggers.SysCommand(
                    id="sys_cmd",
                    name="System Command Handler",
                    topic=trigger_config['topic'],
                    log_level=trigger_config['log_level'])
            else:
                if trigger_config['type'] == 'mqtt_sensor':
                    return_dict[trigger_id] = CobraBay.triggers.MQTTSensor(
                        id = trigger_config['id'],
                        name = trigger_config['name'],
                        topic = trigger_config['topic'],
                        topic_mode = 'full',
                        bay_obj = self._bays[trigger_config['bay_id']],
                        change_type = trigger_config['change_type'],
                        trigger_value = trigger_config['trigger_value'],
                        when_triggered = trigger_config['when_triggered'],
                        log_level = trigger_config['log_level']
                    )
                elif trigger_config['type'] == 'baycommand':
                    # Get the bay object reference.
                    return_dict[trigger_id] = CobraBay.triggers.BayCommand(
                        id = trigger_config['id'],
                        name = trigger_config['name'],
                        topic = trigger_config['topic'],
                        bay_obj = self._bays[trigger_config['bay_id']],
                        log_level = trigger_config['log_level'])
                # elif trigger_config['type'] == 'range':
                #     # Range triggers also need the detector object.
                #     return_dict[trigger_id] = CobraBay.triggers.Range(trigger_config, bay_obj,
                #                                              self._detectors[trigger_config['detector']])
                else:
                    # This case should be trapped by the config processor, but just in case, if trigger type
                    # is unknown, trap and ignore.
                    self._logger.error("Trigger {} has unknown type {}, cannot create.".
                                       format(trigger_id, trigger_config['type']))
        return return_dict

    # Method to set up Logging handlers.
    def _setup_logging_handlers(self, handler_config):
        # File based handler setup.
        if handler_config['file']:
            fh = WatchedFileHandler(handler_config['file_path'])
            fh.setFormatter(handler_config['format'])
            fh.setLevel(logging.DEBUG)
            # Attach to the master logger.
            self._master_logger.addHandler(fh)
            self._master_logger.info("File logging enabled.")

        if handler_config['syslog']:
            raise NotImplemented("Syslog logging not yet implemented")

        # Console handling. If disabling, send a message here.
        if not handler_config['console']:
            self._master_logger.info("Disabling console logging.")

        # Remove all console handlers.
        for handler in self._master_logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                self._master_logger.removeHandler(handler)

        # Add the new console handler.
        if handler_config['console']:
            # Replace the console handler with a new one with the formatter.
            ch = logging.StreamHandler()
            ch.setFormatter(handler_config['format'])
            ch.setLevel(logging.DEBUG)
            self._master_logger.addHandler(ch)
