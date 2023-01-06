####
# Cobra Bay - Main
####

import logging
from logging.handlers import SysLogHandler
from logging.handlers import WatchedFileHandler
import sys
from time import monotonic
import atexit
import busio
import board

# Import the other CobraBay classes
from .bay import Bay
from .config import CBConfig
from .display import Display
from .detector import Lateral, Range
from .network import Network
from .systemhw import PiStatus
from .version import __version__


class CobraBay:
    def __init__(self, cmd_opts=None):
        # Register the exit handler.
        # atexit.register(self.system_exit)

        # Create the master logger. All modules will hang off this.
        self._master_logger = logging.getLogger("CobraBay")
        # Set the master logger to Debug, so all other messages will pass up through it.
        self._master_logger.setLevel(logging.DEBUG)
        # By default, set up console logging. This will be disabled if config file tells us to.
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        # basic_formatter =
        # console_handler.setFormatter(basic_formatter)
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
        # self._triggers = {}
        # self._logger.debug("Creating triggers...")
        # for trigger_id in self._cbconfig.trigger_list:
        #    self._logger.info("Trigger ID: {}".format(trigger_id))
        #    self._triggers[trigger_id]

        # Poll to dispatch the message queue
        self._logger.debug("Initial message queue: {}".format(self._outbound_messages))
        self._network.poll(self._outbound_messages)
        # Flush the queue.
        self._outbound_messages = []
        self._logger.info('CobraBay: Initialization complete.')

    # Command processor.
    def _process_commands(self, command_stack):
        self._logger.debug("Evaluating {} commands.".format(len(command_stack)))
        # Might have more than one command in the stack, process each of them.
        for command in command_stack:
            self._logger.debug("Considering command: {}".format(command))
            if command['type'] == 'bay':
                # Some commands can only run when we're *not* actively docking or undocking.
                if self._bays[command['bay_id']] not in ('docking', 'undocking'):
                    if 'dock' in command['cmd']:
                        self._logger.debug("Got dock command for Bay ID {}".format(command['bay_id']))
                        self._logger.debug("Available bays: {}".format(self._bays.keys()))
                        # try:
                        self._dock(command['bay_id'])
                        # except ValueError:
                        #     self._logger.info("Bay command 'dock' was refused.")
                    if 'undock' in command['cmd']:
                        try:
                            self._undock(command['bay_id'])
                        except ValueError:
                            self._logger.info("Bay command 'undock' was refused.")
                        except KeyError:
                            self._logger.info("Receved command 'dock' for unknown bay '{}'".format(command['bay_id']))
                    # Don't allow a verify when we're actually doing a motion.
                    if 'verify' in command['cmd']:
                        self._bays[command['bay_id']].verify()
                    if 'abort' in command['cmd']:
                        self._bays[command['bay_id']].abort()
                    # if 'reset' in command['cmd']:
                    #     self._logger.info("Resetting bay per command.")
                    #     self._bay.reset()
                    #     print("Bay state after reset: {}".format(self._bay.state))
            if command['type'] == 'device':
                # Don't allow a display sensor request to override an active motion
                if 'display_sensor' in command['cmd']:
                    if 'options' in command:
                        # Make sure all the options exist.
                        options = command['options']
                        try:
                            sensor = options['sensor']

                        except:
                            self._logger.info("Got 'display_sensor' command but incorrect options: {}".
                                              format(command['options']))
                            return
                        try:
                            timeout = float(options['timeout'])
                        except KeyError:
                            timeout = float(360)

                        # Make sure the sensor really exists.
                        if sensor not in self._sensors.sensor_state().keys():
                            self._logger.info(
                                "Got 'display_sensor' command but sensor {} does not exist.".format(sensor))
                            return

                        # Default to 1h if larger than 1h.
                        if float(timeout) > 3600:
                            timeout = float(3600)
                        self._logger.info("Starting sensor display mode for: {}".format(sensor))
                        self._display_sensor = {
                            'sensor': sensor,
                            'timeout': timeout,
                            'start': monotonic()
                        }

    def _network_handler(self):
        # Add hardware status messages.
        self._mqtt_hw()
        # Send the outbound message queue to the network module to handle. After, we empty the message queue.
        network_data = self._network.poll(self._outbound_messages)
        self._outbound_messages = []
        # Check the network command queue. If there are commands, run them.
        if len(network_data['commands']) > 0:
            network_data['command'] = self._process_commands(network_data['commands'])
        return network_data

    # Main operating loop.
    def run(self):
        # This loop runs while the system is idle. Process commands, increment various timers.
        while True:
            ## Messages from the bay.
            for bay in self._bays:
                # Monitor and check for a state change into docking or undocking.
                self._bays[bay].monitor()
                if self._bays[bay].state == 'Docking':
                    self._logger.info("Entering docking mode due to movement.")
                    self._dock(bay)
                    break  ## Exit this cycle
                # Since undocking isn't fully developed, don't do this right now. But it's in here as a stud.
                # elif self._bays[bay].state == 'Undocking':
                #     self._logger.info("Entering undocking mode due to movement.")
                #     self._undock()
                self._outbound_messages = self._outbound_messages + self._bays[bay].mqtt_messages()
            # Do a network poll, this method handles all the default outbound messages and any incoming commands.
            network_data = self._network_handler()
            # Update the network components of the system state.
            # system_state['online'] = network_data['online']
            # system_state['mqtt_status'] = network_data['mqtt_status']

            self._display.show("clock")
            # Push out the image to MQTT.
            self._outbound_messages.append(
                {'topic_type': 'system',
                 'topic': 'display',
                 'message': self._display.current, 'repeat': True})
            # Have the bay monitor range, for movement.

    # Start sensors and display to guide parking.
    def _dock(self, bay_id):
        self._logger.info('Beginning dock.')
        # Wipe the post_action dict.
        self._post_action = {}

        # Set up the displays lateral layers.
        # self._logger.info('Creating lateral layers.')
        # self._display.setup_lateral_markers(self._bays[bay_id].lateral_count)

        # Put the bay into docking mode. The command handler will catch ValueErrors (when the bay isn't ready to dock)
        # and KeyErrors (when the bay_id) is bad
        self._logger.debug("Putting bay in dock mode.")
        self._bays[bay_id].state = 'Docking'

        # As long as the bay still thinks it's docking, keep displaying!
        while self._bays[bay_id].state == "Docking":
            # Collect the MQTT messasges from the bay itself.
            self._logger.debug("Collecting MQTT messages from bay.")
            bay_messages = self._bays[bay_id].mqtt_messages()
            self._logger.debug("Collected MQTT messages: {}".format(bay_messages))
            self._outbound_messages = self._outbound_messages + bay_messages
            # Collect the display data to send to the display.
            self._logger.debug("Collecting display data from bay.")
            display_data = self._bays[bay_id].display_data()
            self._logger.debug("Collected display data: {}".format(display_data))
            self._display.show_dock(display_data)
            # Put the display image on the MQTT stack.
            self._outbound_messages.append(
                {'topic_type': 'system', 'topic': 'display', 'message': self._display.current, 'repeat': True})
            # Poll the network.
            self._logger.debug("Polling network.")
            self._network_handler()
            # Check for completion
            self._bays[bay_id].check_timer()

        self._post_action['time'] = monotonic()

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

    # Display a message for a given amount of time.
    def _hold_message(self, message, hold_time=120, message_color='white'):
        mark = time.monotonic()
        while time.monotonic() - mark < hold_time:
            # Display completed for two minutes.
            system_state = {'signal_strength': 5, 'mqtt_status': 'online'}
            self._display.display_generic(system_state, message=message, message_color=message_color)
        return

    # def verify(self):
    #     # Sweep the sensors once.
    #     sensor_data = self._sensors.sweep()
    #     # Calculate the bay state.
    #     try:
    #         self._bay.verify(sensor_data)
    #     except OSError as e:
    #         self._logger.debug("Bay is unavailable, cannot verify.")
    #         return
    #
    #     # Append the bay state to the outbound message queue.
    #     self._outbound_messages.append(dict(typetopic='bay_raw_sensors', message=sensor_data, repeat=True))
    #     self._outbound_messages.append(dict(topic='bay_sensors', message=self._bay.sensors, repeat=True))
    #     self._outbound_messages.append(dict(topic='bay_motion', message=self._bay.motion, repeat=True))
    #     self._outbound_messages.append(dict(topic='bay_alignment', message=self._bay.alignment, repeat=True))
    #     self._outbound_messages.append(dict(topic='bay_occupied', message=self._bay.occupied, repeat=True))
    #     self._outbound_messages.append(dict(topic='bay_state', message=self._bay.state, repeat=True))

    # Process to stop the docking or undocking process, shut down the sensors and return to the idle state.
    # def complete_dock_undock(self):
    #     self._logger.info('CobraBay: Beginning power down.')
    #     # Get all the current tasks, except ourself.
    #     tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    #     # Cancel all the running coroutines. This will inherently stop all the ultrasound sensors.
    #     for task in tasks:
    #         task.cancel()
    #     # Explicitly stop any vl53 sensors, which range on their own.
    #     self._sensors.vl53('stop')
    #     # Release the display to allow proper reinitialization later.
    #     displayio.release_displays()

    def system_exit(self):
        # Wipe any previous messages. They don't matter now, we're going away!
        self._outbound_messages = []
        # Stop the ranging and close all the open sensors.
        for bay in self._bays:
            self._bays[bay].shutdown()
        # Queue up outbound messages for shutdown.
        self._outbound_messages.append(
            dict(
                topic='device_connectivity',
                message='offline',
                repeat=True
            )
        )
        # self._outbound_messages.append(
        #     dict(
        #         topic='bay_state',
        #         message='unavailable',
        #         repeat=True
        #     )
        # )
        # self._outbound_messages.append(
        #     dict(
        #         topic='bay_occupied',
        #         message='unavailable',
        #         repeat=True
        #     )
        # )
        # Call the network once. We'll ignore any commands we get.
        self._network_handler()

    # Method to set up the detectors based on the configuration.
    def _setup_detectors(self):
        i2c_bus = busio.I2C(board.SCL, board.SDA)
        return_dict = {}
        for detector_id in self.config['detectors']:
            self._logger.info("Creating detector: {}".format(detector_id))
            if self.config['detectors'][detector_id]['type'] == 'Range':
                return_dict[detector_id] = Range(self._cbconfig, detector_id)
                # This probably isn't needed anymore, let's try it without.
                # try:
                #     return_dict[detector_id].timing(self.config['detectors'][detector_id]['timing'])
                # except KeyError:
                #     return_dict[detector_id].timing('200 ms')
            if self.config['detectors'][detector_id]['type'] == 'Lateral':
                return_dict[detector_id] = Lateral(self._cbconfig, detector_id)
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
