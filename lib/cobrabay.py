####
# Cobra Bay - Main
####

import logging
from logging.config import dictConfig as logging_dictConfig
# from logging.handlers import SysLogHandler
import sys
from time import monotonic, sleep
import pprint
import atexit

# Import the other CobraBay classes
from .bay import Bay
from .display import Display
from .detector import Lateral, Range
from .network import Network
from .systemhw import PiStatus
from pint import Quantity

class CobraBay:
    def __init__(self, config):
        self._pp = pprint.PrettyPrinter()
        # Register the exit handler.
        atexit.register(self.system_exit)

        # Create the object for checking hardware status.
        self._pistatus = PiStatus()

        # Set up Logging.
        logging_config_dict = {
            'version': 1,
            'disable_existing_loggers': False,
            'handlers': {
                'debug_console_handler': {
                    'level': 'DEBUG',
                    'formatter': 'info',
                    'class': 'logging.StreamHandler',
                    'stream': 'ext://sys.stdout'
                }
            },
            'formatters': {
                'info': {
                    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    'datefmt': '%Y-%m-%d %H:%M:%S'
                }
            },
            'loggers': {
                '': {
                    'level': 'DEBUG',
                    'handlers': ['debug_console_handler']
                }
            }
        }
        self._core_logger = logging_dictConfig(logging_config_dict)

        # Master logger takes all log levels and runs them through the same formatter and
        self._core_logger = logging.Logger('master')
        self._core_logger.setLevel(logging.DEBUG)
        # Create a formatter
        formatter = logging.Formatter()
        # Create a basic console handler.
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        # syslog_handler = logging.handlers.SysLogHandler()
        # syslog_handler.setFormatter(formatter)
        # self._logger.addHandler(syslog_handler)
        self._core_logger.addHandler(console_handler)
        # Create a logger for this module.
        self._logger = logging.Logger('master').getChild(__name__)
        self._logger.setLevel(logging.DEBUG)

        self._logger.info('CobraBay: CobraBay Initializing...')
        # check for all basic options.
        for option in ('global', 'detectors', 'bay'):
            if option not in config:
                self._logger.error('CobraBay: Configuration does not include required section: "' + option + '"')
                sys.exit(1)

        # Basic checks passed. Good enough! Assign it.
        self.config = config

        # Initial device state
        self._device_state = 'on'
        # Queue for outbound messages.
        self._outbound_messages = []
        # Queue the startup message.
        self._outbound_messages.append({'topic': 'device_connectivity', 'message': 'online'})
        # Information to display a sensor on the idle screen.
        self._display_sensor = {'sensor': None}

        self._logger.debug("Creating network object...")
        # Create Network object.
        self._network = Network(
            # Network object needs the whole config, since parts
            # (esp. HA discovery) needs to reference multiple parts of the config.
            config=config
        )

        self._logger.debug("Creating detectors...")
        # Create the detectors
        self._detectors = self._setup_detectors()
        # Create master bay object for defined docking bay
        # Master list to store all the bays.
        self._bays = {}
        self._logger.debug("Creating bays...")
        # For testing, only one bay, hard-wire it ATM.
        self._bays[self.config['bay']['id']] = Bay(self.config['bay'], self._detectors)
        self._logger.debug("Registering bays with network handler...")

        self._logger.info('CobraBay: Creating display...')
        # Create Display object
        self._display = Display(self.config)

        self._logger.info('CobraBay: Connecting to network...')
        # Connect to the network.
        self._network.connect()

        # Check for Syslog, if so, connect.
        if 'syslog' in config['global']:
            # try:
            self._logger.info("Attempting to add Syslog handler to {} {} via {}".
                              format(config['global']['syslog']['host'],
                                     config['global']['syslog']['facility'],
                                     config['global']['syslog']['protocol']))
            from logging.handlers import SysLogHandler
            try:
                self.syslog = SysLogHandler(
                    address=config['global']['syslog']['host'],
                    facility=config['global']['syslog']['facility'])
                    # protocol=config['global']['syslog']['protocol'])
            except Exception as e:
                self._logger.error("Could not set up Syslog logging: {}".format(e))
            else:
                self._logger.addHandler(self.syslog)

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
                    # if 'rescan_sensors' in command['cmd']:
                    #     self._sensors.rescan()
                    if 'dock' in command['cmd']:
                        try:
                            self._bays[command['bay_id']].dock()
                        except ValueError:
                            self._logger.info("Bay command 'dock' was refused.")
                    if 'undock' in command['cmd']:
                        try:
                            self._bays[command['bay_id']].state('undock')
                        except ValueError:
                            self._logger.info("Bay command 'undock' was refused.")
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
        # Send the outbound message queue to the network module to handle. After, we empty the message queue.
        # print("Pending outbound messages: ")
        # self._pp.pprint(self._outbound_messages)
        network_data = self._network.poll(self._outbound_messages)
        self._outbound_messages = []
        # Check the network command queue. If there are commands, run them.
        if len(network_data['commands']) > 0:
            network_data['command'] = self._process_commands(network_data['commands'])
        return network_data

    # Main operating loop.
    def run(self):
        self._logger.info('CobraBay: Starting main operating loop.')
        # This loop runs while the system is idle. Process commands, increment various timers.
        system_state = {'signal_strength': 0, 'mqtt_status': False}
        while True:
            ## Messages from the bay.
            for bay in self._bays:
                self._outbound_messages = self._outbound_messages + self._bays[bay].mqtt_messages()
            ## Hardware messages
            # Send the hardware state out
            self._outbound_messages.append(
                {'topic': 'cpu_pct', 'message': self._pistatus.status('cpu_pct'), 'repeat': False})
            self._outbound_messages.append(
                {'topic': 'cpu_temp', 'message': self._pistatus.status('cpu_temp'), 'repeat': False})
            self._outbound_messages.append(
                {'topic': 'mem_info', 'message': self._pistatus.status('mem_info'), 'repeat': False})
            # Do a network poll, this method handles all the default outbound messages and any incoming commands.
            network_data = self._network_handler()
            # Update the network components of the system state.
            system_state['signal_strength'] = network_data['signal_strength']
            system_state['mqtt_status'] = network_data['mqtt_status']
            # Should we display a given sensor during the generic display phase?
            if self._display_sensor['sensor'] is not None:
                sensor_value = self._sensors.get_sensor(self._display_sensor['sensor'])
                # If timeout has expired, blank it.
                if (monotonic() - self._display_sensor['start']) > self._display_sensor['timeout']:
                    self._display_sensor = {'sensor': None}
                    self._logger.info("Ending sensor display mode.")
            else:
                sensor_value = None
            try:
                self._display.display_generic(system_state, sensor_value)
            except:
                pass

    # Start sensors and display to guide parking.
    def dock(self):
        self._logger.info('CobraBay: Beginning dock.')
        # Force vacant, for testing.
        self._bay.occupied = 'vacant'
        # Change the bay's state to docking.
        try:
            self._bay.state = 'docking'
        except Exception as e:
            self._logger.info("Could not start docking: {}".format(str(e)))
            return
        self._outbound_messages.append({'topic': 'bay_state', 'message': 'docking'})
        # Start the VL53 sensors ranging
        self._sensors.sensor_cmd('start')
        done = False
        while done is False:
            # Sweep the sensors. At some future point this may allow a subset of sensors. Right now it does all of them.
            sensor_data = self._sensors.sweep()
            # Send the collected data to the bay object to interpret
            self._bay.update(sensor_data)
            # Display bay positioning.
            self._display.display_dock(self._bay.position)

            # Prepare messages out to the network.
            # Current state of the bay. Probably still 'Docking'
            self._outbound_messages.append(dict(topic='bay_state', message=self._bay.state, repeat=False))
            # Is the bay occupied?
            self._outbound_messages.append(dict(topic='bay_occupied', message=self._bay.occupied, repeat=False))
            # Bay positioning
            self._outbound_messages.append(dict(topic='bay_position', message=self._bay.position, repeat=True))
            # Bay sensor readings (raw)
            self._outbound_messages.append(dict(topic='bay_raw_sensors', message=sensor_data, repeat=True))

            # Call the network handler. This will send all messages in self._outbound_messages, and return any commands
            # that need handling.
            network_data = self._network_handler()
            # Check for a complete or abort command.
            if 'command' in network_data:
                if network_data['command'] == 'complete':
                    self._logger.info("Received completion network command. Setting bay to complete.")
                    self._bay.complete()
                if network_data['command'] == 'abort':
                    self._logger.info("Recelved 'abort' network command. Resetting bay and halting.")
                    # Reset the bay.
                    self._bay.reset()
                # Stop ranging on VL53s.
                self._sensors.sensor_cmd('stop')
                # Break and be done.
                break

            # Update based on bay state.
            # If bay registers a crash, oh crap!
            if self._bay.state == 'crashed':
                self._logger.error("Bay reports crash!")
                # Display crash for two minutes.
                self._hold_message('CRASHED!', 120, 'red')
                return

            # Bay thinks it's done.
            elif self._bay.motion == 'still' and self._bay.occupied == 'occupied':
                self._logger.info("No motion and bay occupied, calling this complete.")
                # Complete the bay.
                self._bay.complete()
                break

            # if self._bay.state == 'docking':
            #     # Still docking, pass and do nothing.
            #     pass
            # elif self._bay.state == 'occupied':
            #     # Bay considers itself occupied.
            # elif self._bay.state == 'crash':
            #     # Range has hit absolute 0, which indicates an *actual* crash (we hope not!) or a sensor reading error.
            #     # Either way, we're done here.
            #     done = True
            #
            # # If the bay now considers itself occupied (ie: complete), then we complete.
            # if self._bay.state == 'occupied':
            #     self._logger.info("Received 'completion' message during docking. Finishing.")
            #     done = True
            # i += 1
        # # If an abort was called, do a verify.
        # if aborted:
        #     self._logger.info("Docking aborted. Running verify to determine bay state.")
        #     self.verify()

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

    def verify(self):
        # Sweep the sensors once.
        sensor_data = self._sensors.sweep()
        # Calculate the bay state.
        try:
            self._bay.verify(sensor_data)
        except OSError as e:
            self._logger.debug("Bay is unavailable, cannot verify.")
            return

        # Append the bay state to the outbound message queue.
        self._outbound_messages.append(dict(topic='bay_raw_sensors', message=sensor_data, repeat=True))
        self._outbound_messages.append(dict(topic='bay_sensors', message=self._bay.sensors, repeat=True))
        self._outbound_messages.append(dict(topic='bay_motion', message=self._bay.motion, repeat=True))
        self._outbound_messages.append(dict(topic='bay_alignment', message=self._bay.alignment, repeat=True))
        self._outbound_messages.append(dict(topic='bay_occupied', message=self._bay.occupied, repeat=True))
        self._outbound_messages.append(dict(topic='bay_state', message=self._bay.state, repeat=True))

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
        return_dict = {}
        for detector_name in self.config['detectors']:
            self._logger.info("Creating detector: {}".format(detector_name))
            if self.config['detectors'][detector_name]['type'] == 'Range':
                return_dict[detector_name] = Range(board_options = self.config['detectors'][detector_name]['sensor'])
                try:
                    return_dict[detector_name].timing(self.config['detectors'][detector_name]['timing'])
                except KeyError:
                    return_dict[detector_name].timing('200 ms')
            if self.config['detectors'][detector_name]['type'] == 'Lateral':
                return_dict[detector_name] = Lateral(board_options = self.config['detectors'][detector_name]['sensor'])
        return return_dict