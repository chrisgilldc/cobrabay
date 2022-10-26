####
# Cobra Bay - Main
####

import logging
from logging.config import dictConfig as logging_dictConfig
# from logging.handlers import SysLogHandler
import sys
from time import monotonic
import atexit
import busio
import board
from digitalio import DigitalInOut
from adafruit_aw9523 import AW9523
from io import BytesIO
from pprint import PrettyPrinter

# Import the other CobraBay classes
from .bay import Bay
from .config import CBConfig
from .display import Display
from .detector import Lateral, Range
from .network import Network
from .systemhw import PiStatus

class CobraBay:
    def __init__(self, cmd_opts=None):
        # Register the exit handler.
        # atexit.register(self.system_exit)

        # Create a config object.
        self._cbconfig = CBConfig(reset_sensors=True)

        config = self._cbconfig._config

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

        # Basic checks passed. Good enough! Assign it.
        self.config = config

        # Create the network object.
        self._logger.debug("Creating network object...")
        # Create Network object.
        self._network = Network(
            # Network gets the general config.
            config=self.config['global']
        )
        self._logger.info('CobraBay: Connecting to network...')
        # Connect to the network.
        self._network.connect()

        # Queue for outbound messages.
        self._outbound_messages = []
        # Queue the startup message.
        self._outbound_messages.append({'topic_type': 'system', 'topic': 'device_connectivity', 'message': 'online'})

        self._logger.debug("Creating detectors...")
        # Create the detectors
        self._detectors = self._setup_detectors()
        # Create master bay object for defined docking bay
        # Master list to store all the bays.
        self._bays = {}
        self._logger.debug("Creating bays...")
        # For testing, only one bay, hard-wire it ATM.
        self._bays[self.config['bay']['id']] = Bay(self.config['bay'], self._detectors)
        self._logger.debug("Sending bay discovery info to Network handler.")
        self._logger.debug(self._bays[self.config['bay']['id']].discovery_info())
        self._network.register_bay(self._bays[self.config['bay']['id']].discovery_info())

        self._logger.info('CobraBay: Creating display...')
        # Create Display object
        display_config = self.config['display']
        display_config['global'] = self.config['global']
        self._display = Display(display_config)



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
                    if 'dock' in command['cmd']:
                        self._logger.debug("Got dock command for Bay ID {}".format(command['bay_id']))
                        self._logger.debug("Available bays: {}".format(self._bays.keys()))
                        try:
                            self._dock(command['bay_id'])
                        except ValueError:
                            self._logger.info("Bay command 'dock' was refused.")
                        # except KeyError:
                        #     self._logger.info("Receved command 'dock' for unknown bay '{}'".format(command['bay_id']))
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
        self._logger.info('CobraBay: Starting main operating loop.')
        # This loop runs while the system is idle. Process commands, increment various timers.
        system_state = {'signal_strength': 0, 'mqtt_status': False}
        while True:
            ## Messages from the bay.
            for bay in self._bays:
                self._outbound_messages = self._outbound_messages + self._bays[bay].mqtt_messages()
            ## Hardware messages

            # Do a network poll, this method handles all the default outbound messages and any incoming commands.
            network_data = self._network_handler()
            # Update the network components of the system state.
            system_state['online'] = network_data['online']
            system_state['mqtt_status'] = network_data['mqtt_status']

            self._display.show_clock()
            # Push out the image to MQTT.
            self._outbound_messages.append(
                {'topic_type': 'system',
                 'topic': 'display',
                 'message': self._display.current, 'repeat': True})


    # Start sensors and display to guide parking.
    def _dock(self,bay_id):
        self._logger.info('Beginning dock.')

        # Set up the displays lateral layers.
        self._logger.info('Creating lateral layers.')
        self._display.setup_lateral_markers(self._bays[bay_id].lateral_count)

        # Put the bay into docking mode. The command handler will catch ValueErrors (when the bay isn't ready to dock)
        # and KeyErrors (when the bay_id) is bad
        self._logger.debug("Putting bay in dock mode.")
        self._bays[bay_id].dock()
        # Create a buffer to store the image, if/when we get it.
        image_buffer = BytesIO()

        # As long as the bay still thinks it's docking, keep displaying!
        while self._bays[bay_id].state == "docking":
            self._logger.debug("Collecting bay messages.")
            # Collect the MQTT mesasges from the bay itself.
            bay_messages = self._bays[bay_id].mqtt_messages()
            # Use the message data to send to the display.
            self._logger.debug("Sending bay data to display.")
            outbound_image = self._display.show_dock(position=bay_messages[1], quality=bay_messages[2])
            self._logger.debug("Display processing returned type: {}".format(type(outbound_image)))
            if outbound_image is not None:
                # Write to the image buffer as a PNG.
                outbound_image.save(image_buffer, format="PNG")
                # Send a base64 encoded version to MQTT.
                self._outbound_messages.append(
                    {'topic_type': 'bay', 'topic': 'bay_display', 'message': b64encode(image_buffer.getvalue()),
                     'repeat': True, 'topic_mappings': {'bay_id': bay_id} }
                )

            # Put the bay messages on the MQTT stack to go out.
            self._logger.debug("Collecting outbound MQTT messages.")
            self._outbound_messages = self._outbound_messages + bay_messages

            # Poll the network.
            self._logger.debug("Polling network.")
            network_data = self._network_handler()

    # Utility method to put the hardware status on the outbound message queue. This needs to be used from a few places.
    def _mqtt_hw(self):
        self._outbound_messages.append(
            {'topic_type': 'system', 'topic': 'cpu_pct', 'message': self._pistatus.status('cpu_pct'), 'repeat': False})
        self._outbound_messages.append(
            {'topic_type': 'system', 'topic': 'cpu_temp', 'message': self._pistatus.status('cpu_temp'), 'repeat': False})
        self._outbound_messages.append(
            {'topic_type': 'system', 'topic': 'mem_info', 'message': self._pistatus.status('mem_info'), 'repeat': False})

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
        self._outbound_messages.append(dict(typetopic='bay_raw_sensors', message=sensor_data, repeat=True))
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
        i2c_bus = busio.I2C(board.SCL, board.SDA)
        return_dict = {}
        for detector_id in self.config['detectors']:
            self._logger.info("Creating detector: {}".format(detector_id))
            if self.config['detectors'][detector_id]['type'] == 'Range':
                return_dict[detector_id] = \
                    Range(detector_id,
                          self.config['detectors'][detector_id]['name'],
                          board_options = self.config['detectors'][detector_id]['sensor'])
                # This probably isn't needed anymore, let's try it without.
                # try:
                #     return_dict[detector_id].timing(self.config['detectors'][detector_id]['timing'])
                # except KeyError:
                #     return_dict[detector_id].timing('200 ms')
            if self.config['detectors'][detector_id]['type'] == 'Lateral':
                return_dict[detector_id] = \
                    Lateral(detector_id,
                            self.config['detectors'][detector_id]['name'],
                            board_options = self.config['detectors'][detector_id]['sensor'])
        return return_dict
