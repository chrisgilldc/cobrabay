####
# Cobra Bay - Main
####

import logging
from logging.handlers import WatchedFileHandler
from time import monotonic
import atexit
import busio
import board
import os
import sys
import psutil

# Import the other CobraBay classes
from .bay import Bay
from .config import CBConfig
from .display import Display
from .detector import Lateral, Range
from .network import Network
from .systemhw import PiStatus
from . import triggers
from .version import __version__


class CobraBay:
    def __init__(self, cmd_opts=None):
        # Register the exit handler.
        atexit.register(self.system_exit)

        # Create the master logger. All modules will hang off this.
        self._master_logger = logging.getLogger("CobraBay")
        # Set the master logger to Debug, so all other messages will pass up through it.
        self._master_logger.setLevel(logging.DEBUG)
        # By default, set up console logging. This will be disabled if config file tells us to.
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        self._master_logger.addHandler(console_handler)
        # Create a "core" logger, for just this module.
        self._logger = logging.getLogger("CobraBay").getChild("Core")

        # Initial startup message.
        self._logger.info("CobraBay {} initializing...".format(__version__))

        # Create a config object.
        self._cbconfig = CBConfig(reset_sensors=True)

        # Update the logging handlers.
        self._setup_logging_handlers(self._cbconfig.log_handlers())

        # Reset our own level based on the configuration.
        self._logger.setLevel(self._cbconfig.get_loglevel("Core"))

        # Put the raw config in a variable, this is a patch.
        self.config = self._cbconfig._config

        # Create the object for checking hardware status.
        self._logger.debug("Creating Pi hardware monitor...")
        self._pistatus = PiStatus()

        # Create the network object.
        self._logger.debug("Creating network object...")
        # Create Network object.
        self._network = Network(config=self._cbconfig)
        self._logger.info('Connecting to network...')
        # Connect to the network.
        self._network.connect()

        # Queue for outbound messages.
        self._outbound_messages = []
        # Queue the startup message.
        self._outbound_messages.append({'topic_type': 'system', 'topic': 'device_connectivity', 'message': 'Online'})

        self._logger.debug("Creating detectors...")
        # Create the detectors. This is complex enough it gets its own method.
        self._detectors = self._setup_detectors()
        self._logger.debug("Have detectors: {}".format(self._detectors))

        # Create master bay object for defined docking bay
        # Master list to store all the bays.
        self._bays = {}
        self._logger.debug("Creating bays...")
        for bay_id in self._cbconfig.bay_list:
            self._logger.info("Bay ID: {}".format(bay_id))
            self._bays[bay_id] = Bay(bay_id, self._cbconfig, self._detectors)

        self._logger.info('CobraBay: Creating display...')
        self._display = Display(self._cbconfig)

        # Register the bay with the network and display.
        for bay_id in self._bays:
            self._network.register_bay(self._bays[bay_id].discovery_reg_info)
            self._display.register_bay(self._bays[bay_id].display_reg_info)

        # Collect messages from the bays.
        for bay_id in self._bays:
            self._outbound_messages = self._outbound_messages + self._bays[bay_id].mqtt_messages(verify=True)

        # Create triggers.
        self._triggers = self._setup_triggers()
        self._logger.debug("Have triggers: {}".format(self._triggers))

        # Parcel trigger objects out to the right place.
        #  - MQTT triggers go to the network module,
        #  - Range triggers go to the appropriate bay.
        self._logger.debug("Linking triggers to modules.")
        for trigger_id in self._triggers:
            self._logger.debug("{} is a {} trigger".format(trigger_id,self._triggers[trigger_id].type))
            trigger_obj = self._triggers[trigger_id]
            # Network needs to be told about triggers that talk to MQTT.
            if trigger_obj.type in ('syscommand', 'baycommand', 'mqtt_sensor'):
                self._network.register_trigger(trigger_obj)
            # Tell bays about their bay triggers.
            if trigger_obj.type in ('baycommand'):
                self._bays[trigger_obj.bay_id].register_trigger(trigger_obj)

            # elif self._triggers[trigger_id].type == 'range':
            #     # Make sure the desired bay exists!
            #     try:
            #         target_bay = self._bays[self._triggers[trigger_id].bay_id]
            #     except KeyError:
            #         self._logger.error("Trigger {} references non-existent bay {}. Cannot link.".
            #                            format(trigger_id, self._bays[self._triggers[trigger_id].bay_id] ))
            #         break
            #     target_bay.register_trigger(self._triggers[trigger_id])

        # Poll to dispatch the message queue
        self._logger.debug("Initial message queue: {}".format(self._outbound_messages))
        self._network.poll(self._outbound_messages)
        # Flush the queue.
        self._outbound_messages = []
        self._logger.info('CobraBay: Initialization complete.')

    # Common network handler, pushes data to the network and makes sure the MQTT client can poll.
    def _network_handler(self):
        # Add hardware status messages.
        self._mqtt_hw()
        # Send the outbound message queue to the network module to handle. After, we empty the message queue.
        network_data = self._network.poll(self._outbound_messages)
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
            self._logger.debug("Has trigger value: {}".format(trigger_obj.triggered))
            if trigger_obj.triggered:
                while trigger_obj.cmd_stack:
                    cmd = trigger_obj.cmd_stack.pop(0)
                    if trigger_obj.type in ('baycommand','mqtt_sensor'):
                        if cmd in ('dock','undock'):
                            # Dock or undock, enter the motion routine.
                            self._motion(trigger_obj.bay_id, cmd)
                            self._logger.debug("Returned from motion method to trigger method.")
                            break
                        elif cmd == 'abort':
                            # On an abort, call the bay's abort. This will set it ready and clean up.
                            # If we're in the _motion method, this will go back to run, if not, nothing happens.
                            self._bays[trigger_obj.bay_id].abort()
                    elif trigger_obj.type in ('syscommand'):
                        self._core_command(cmd)
            self._logger.debug("Trigger check complete.")

    # Main operating loop.
    def run(self):
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
            self._logger.debug("Returned to main loop from trigger check.")

            self._display.show(system_status, "clock")
            # Push out the image to MQTT.
            self._outbound_messages.append(
                {'topic_type': 'system',
                 'topic': 'display',
                 'message': self._display.current, 'repeat': True})

    # Start sensors and display to guide parking.
    def _motion(self, bay_id, cmd):
        # Convert command to a state. Should have planned this better, but didn't.
        if cmd == 'dock':
            direction = "Docking"
        elif cmd == 'undock':
            direction = "Undocking"
        else:
            raise ValueError("Motion command '{}' not valid.".format(cmd))

        self._logger.info('Beginning {} on bay {}.'.format(direction, bay_id))

        # Set the bay to the proper state.
        self._bays[bay_id].state = direction

        # As long as the bay is in the desired state, keep running.
        while self._bays[bay_id].state == direction:
            # Collect the MQTT messages from the bay itself.
            self._logger.debug("Collecting MQTT messages from bay.")
            bay_messages = self._bays[bay_id].mqtt_messages()
            self._logger.debug("Collected MQTT messages: {}".format(bay_messages))
            self._outbound_messages = self._outbound_messages + bay_messages
            # Collect the display data to send to the display.
            self._logger.debug("Collecting display data from bay.")
            display_data = self._bays[bay_id].display_data()
            self._logger.debug("Collected display data: {}".format(display_data))
            self._display.show_motion(direction, display_data)
            # Put the display image on the MQTT stack.
            self._outbound_messages.append(
                {'topic_type': 'system', 'topic': 'display', 'message': self._display.current, 'repeat': True})
            # Poll the network.
            self._logger.debug("Polling network.")
            self._network_handler()
            # Check for completion
            self._bays[bay_id].check_timer()
            # Check the triggers. This lets an abort be called or an underlying system command be called.
            self._trigger_check()
        self._logger.info("Bay state changed to {}. Returning to idle.".format(self._bays[bay_id].state))
        # Collect and send a final set of MQTT messages.
        self._logger.debug("Collecting MQTT messages from bay.")
        bay_messages = self._bays[bay_id].mqtt_messages()
        self._logger.debug("Collected MQTT messages: {}".format(bay_messages))
        self._outbound_messages = self._outbound_messages + bay_messages

    # Utility method to put the hardware status on the outbound message queue. This needs to be used from a few places.
    def _mqtt_hw(self):
        self._outbound_messages.append(
            {'topic_type': 'system', 'topic': 'cpu_pct', 'message': self._pistatus.status('cpu_pct'), 'repeat': False})
        self._outbound_messages.append(
            {'topic_type': 'system', 'topic': 'cpu_temp', 'message': self._pistatus.status('cpu_temp'),
             'repeat': False})
        self._outbound_messages.append(
            {'topic_type': 'system', 'topic': 'mem_info', 'message': self._pistatus.status('mem_info'),
             'repeat': False})
        self._outbound_messages.append(
            {'topic_type': 'system', 'topic': 'undervoltage', 'message': self._pistatus.status('undervoltage'),
             'repeat': False}
        )

    def undock(self):
        self._logger.info('CobraBay: Undock not yet implemented.')
        return

    def system_exit(self):
        # Wipe any previous messages. They don't matter now, we're going away!
        self._outbound_messages = []
        # Stop the ranging and close all the open sensors.
        try:
            for bay in self._bays:
                self._logger.critical("Shutting down bay {}".format(bay))
                self._bays[bay].shutdown()
            for detector in self._detectors:
                self._logger.critical("Shutting down detector: {}".format(detector))
                self._detectors[detector].shutdown()
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
        for detector_id in self.config['detectors']:
            self._logger.info("Creating detector: {}".format(detector_id))
            if self.config['detectors'][detector_id]['type'] == 'Range':
                return_dict[detector_id] = Range(self._cbconfig, detector_id)
            if self.config['detectors'][detector_id]['type'] == 'Lateral':
                return_dict[detector_id] = Lateral(self._cbconfig, detector_id)
        return return_dict

    def _setup_triggers(self):
        self._logger.debug("Creating triggers...")
        return_dict = {}
        for trigger_id in self._cbconfig.trigger_list:
            self._logger.info("Trigger ID: {}".format(trigger_id))
            trigger_config = self._cbconfig.trigger(trigger_id)
            self._logger.debug(trigger_config)
            # Create trigger object based on type.
            # All triggers except the system command handler will need a reference to the bay object.
            if trigger_config['type'] != "syscommand":
                bay_obj = self._bays[trigger_config['bay_id']]
            if trigger_config['type'] == 'mqtt_sensor':
                trigger_object = triggers.MQTTSensor(trigger_config, bay_obj)
            elif trigger_config['type'] == 'syscommand':
                trigger_object = triggers.SysCommand(trigger_config)
            elif trigger_config['type'] == 'baycommand':
                # Get the bay object reference.
                trigger_object = triggers.BayCommand(trigger_config, bay_obj)
            elif trigger_config['type'] == 'range':
                trigger_object = triggers.Range(trigger_config)
            else:
                # This case should be trapped by the config processor, but just in case, if trigger type
                # is unknown, trap and ignore.
                self._logger.error("Trigger {} has unknown type {}, cannot create.".
                                   format(trigger_id, trigger_config['type']))
                break
            return_dict[trigger_id] = trigger_object
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
