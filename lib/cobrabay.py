####
# Cobra Bay - Main
####

import logging
from logging.config import dictConfig as logging_dictConfig
from logging.handlers import SysLogHandler
import sys
from time import monotonic, sleep

# Import the other CobraBay classes
from .bay import Bay
from .display import Display
from .network import Network
from .sensors import Sensors
from pint import UnitRegistry, Quantity

class CobraBay:
    def __init__(self, config):


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
        self._core_logger.info("Core logger message test.")
        # Create a logger for this module.
        self._logger = logging.Logger('master').getChild(__name__)
        self._logger.setLevel(logging.DEBUG)

        self._logger.info('CobraBay: CobraBay Initializing...')
        # check for all basic options.
        for option in ('global', 'sensors', 'bay'):
            if option not in config:
                self._logger.error('CobraBay: Configuration does not include required section: "' + option + '"')
                sys.exit(1)
        # Make sure at least one sensor exists.
        if len(config) == 0:
            self._logger.info('CobraBay: No sensors configured!')
            sys.exit(1)
        # Make sure sensors are assigned.
        if 'sensor' not in config['bay']['range']:
            self._logger.error('CobraBay: No range sensor assigned.')
        for index in range(len(config['bay']['lateral'])):
            if 'sensor' not in config['bay']['lateral'][index]:
                self._logger.error('CobraBay: Lateral zone ' + str(index) + ' does not have sensor assigned.')

        # Default out the Home Assistant option.
        if 'homeassistant' not in config['global']:
            config['global']['homeassistant'] = False

        # Basic checks passed. Good enough! Assign it.
        self.config = config

        # Convert inputs to Units.
        self.config['bay']['park_time'] = Quantity(self.config['bay']['park_time'])
        for option in ('dist_max', 'dist_stop'):
            self.config['bay']['range'][option] = Quantity(self.config['bay']['range'][option])
        # Lateral option distance options to convert
        for index in range(len(self.config['bay']['lateral'])):
            for option in ('intercept_range', 'dist_ideal', 'ok_spread', 'warn_spread', 'red_spread'):
                self.config['bay']['lateral'][index][option] = \
                    Quantity(self.config['bay']['lateral'][index][option])

        # Initial device state
        self._device_state = 'on'
        # Queue for outbound messages.
        self._outbound_messages = []
        # Information to display a sensor on the idle screen.
        self._display_sensor = { 'sensor': None }

        self._logger.info('CobraBay: Creating sensors...')
        # Create master sensor object to hold all necessary sensor sub-objects.
        self._sensors = Sensors(self.config)

        # Create master bay object for defined docking bay
        self._bay = Bay(self.config['bay'], self._sensors.sensor_state())
        # Run a verify to get some initial values.
        self.verify()

        self._logger.info('CobraBay: Creating display...')
        # Create Display object
        self._display = Display(self.config)

        self._logger.info('CobraBay: Connecting to network...')
        # Create Network object.
        self._network = Network(
            config = config,  # Network object needs the whole config, since parts (esp. HA discovery) needs to reference multiple parts of the config.
            bay = (self._bay),  # Pass a ref to the bay object. Multiple bays may be supported later.
        )

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
    def _process_commands(self,command_stack):
        self._logger.debug("Evaluating {} commands.".format(len(command_stack)))
        # Might have more than one command in the stack, process each of them.
        for command in command_stack:
            self._logger.debug("Considering command: {}".format(command))
            if self._bay.state not in ('docking', 'undocking'):
                if 'rescan_sensors' in command['cmd']:
                    self._sensors.rescan()
                if 'dock' in command['cmd']:
                    self.dock()
                if 'undock' in command['cmd']:
                    self.undock()
                # Don't allow a verify when we're actually doing a motion.
                if 'verify' in command['cmd']:
                    self.verify()
                if 'reset' in command['cmd']:
                    self._logger.info("Resetting bay per command.")
                    self._bay.reset()
                    print("Bay state after reset: {}".format(self._bay.state))
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
            else:
                # Only allow the abort or complete commands while a motion is in action. Complete takes precedence.
                if 'complete' in command['cmd']:
                    return 'complete'
                if 'abort' in command['cmd']:
                    return 'abort'

    def _network_handler(self):
        # Always add a device state update and a memory message to the outbound message queue
        # Queue up outbound messages for processing. By default, the Network class will not
        # send data that hasn't changed, so we can queue it up here without care.
        self._outbound_messages.append(dict(topic='device_connectivity', message=self._device_state))
        # self._outbound_messages.append(dict(topic='device_mem', message=(mem_free() / 1024)))
        self._outbound_messages.append(dict(topic='bay_state', message=self._bay.state))
        # Poll the network, send any outbound messages there for MQTT publication.
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
            # Send out the bay state. This makes sure we're ready to update this whenever we return to the operating loop.
            self._outbound_messages.append(dict(topic='bay_state', message=self._bay.state, repeat=False))
            # Do a network poll, this method handles all the default outbound messages and any incoming commands.
            network_data = self._network_handler()
            # Update the network components of the system state.
            system_state['signal_strength'] = network_data['signal_strength']
            system_state['mqtt_status'] = network_data['mqtt_status']
            # Should we display a given sensor during the generic display phase?
            if self._display_sensor['sensor'] is not None:
                sensor_value=self._sensors.get_sensor(self._display_sensor['sensor'])
                # If timeout has expired, blank it.
                if ( monotonic() - self._display_sensor['start'] ) > self._display_sensor['timeout']:
                    self._display_sensor = { 'sensor': None }
                    self._logger.info("Ending sensor display mode.")
            else:
                sensor_value=None
            try:
                self._display.display_generic(system_state,sensor_value)
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
        self._sensors.vl53('start')
        done = False
        i = 1
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
            self._outbound_messages.append(dict(topic='bay_sensors', message=sensor_data, repeat=True))

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
                self._sensors.vl53('stop')
                # Break and be done.
                break

            # Update based on bay state.
            # If bay registers a crash, oh crap!
            if self._bay.state == 'crashed':
                self._logger.error("Bay reports crash!")
                # Display crash for two minutes.
                self._hold_message('CRASHED!',120,'red')
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
    def _hold_message(self,message,hold_time=120,message_color='white'):
        mark = time.monotonic()
        while time.monotonic() - mark < hold_time:
            # Display completed for two minutes.
            system_state = {}
            system_state['signal_strength'] = 5
            system_state['mqtt_status'] = 'online'
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
        self._outbound_messages.append(dict(topic='bay_sensors', message=sensor_data, repeat=True))
        self._outbound_messages.append(dict(topic='bay_position', message=self._bay.position, repeat=True))
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