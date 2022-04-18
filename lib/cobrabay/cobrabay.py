####
# Cobra Bay - Main
####

import adafruit_logging as logging
import digitalio
import sys
import time
from gc import mem_free

# Import the other CobraBay classes
from .bay import Bay
from .display import Display
from .network import Network
from .sensors import Sensors


class CobraBay:
    def __init__(self, config):
        self._logger = logging.getLogger('cobrabay')
        self._logger.info('CobraBay: CobraBay Initializing...')
        self._logger.debug('Available memory: {}'.format(mem_free()))

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
            sys.exit(1)
        for index in range(len(config['bay']['lateral'])):
            if 'sensor' not in config['bay']['lateral'][index]:
                self._logger.error('CobraBay: Lateral zone ' + str(index) + ' does not have sensor assigned.')
                sys.exit(1)

        # Default out the Home Assistant option.
        if 'homeassistant' not in config['global']:
            config['global']['homeassistant'] = False

        # Basic checks passed. Good enough! Assign it.
        self.config = config

        # Set watchdog pin high to keep the TPL5110 from restarting the system.
        # Holding the delay pin high will prevent restart. If that ever drops, the TPL5110
        # will restart us.
        # Only set up watchdogging if a Watchdog pin is set.
        if 'watchdog_pin' in config['global']:
            watchdog_pin = digitalio.DigitalInOut(eval("board.D{}".format(config['global']['watchdog_pin'])))
            watchdog_pin.direction = digitalio.Direction.OUTPUT
            self._logger.info(f"Current Watchdog pin state: {watchdog_pin.value}")
            self._logger.info("Setting high to keep watchdog from triggering.")
            watchdog_pin.value = True
            self._logger.info("New Watchdog pin state: {}".format(watchdog_pin.value))

        # General Processing
        # All internal work is done in metric.
        # Convert dimensions from inches to cm if necessary.
        if self.config['global']['units'] == 'imperial':
            self._logger.info('CobraBay: Converting to Imperial')
            # Range distance options to convert
            for option in ('dist_max', 'dist_stop'):
                self.config['bay']['range'][option] = self.config['bay']['range'][option] * 2.54
            # Lateral option distance options to convert
            for index in range(len(self.config['bay']['lateral'])):
                for option in ('intercept_range', 'ok_spread', 'warn_spread', 'red_spread'):
                    self.config['bay']['lateral'][index][option] = self.config['bay']['lateral'][index][option] * 2.54
        else:
            # If we're defaulting to metric, make sure it's explicit set for later testing.
            self.config['units'] = 'metric'

        # Initial device state
        self._device_state = 'ready'
        # Queue for outbound messages.
        self._outbound_messages = []
        # Information to display a sensor on the idle screen.
        self._display_sensor = { 'sensor': None }

        self._logger.info('CobraBay: Creating sensors...')
        # Create master sensor object to hold all necessary sensor sub-objects.
        self._sensors = Sensors(self.config)

        # Create master bay object for defined docking bay
        self._bay = Bay(self.config['bay'], self._sensors.sensor_state())

        self._logger.info('CobraBay: Connecting to network...')
        # Create Network object.
        self._network = Network(
            system_id=config['global']['system_id'],
            bay=(self._bay),  # Pass a ref to the bay object. Multiple bays may be supported later.
            homeassistant=config['global']['homeassistant']
        )
        # Connect to the network.
        self._network.connect()

        self._logger.info('CobraBay: Creating display...')
        # Create Display object
        try:
            self._display = Display(self.config)
        except MemoryError as e:
            self._logger.error('Display: Memory error while initializing display.')
            #self._logger.error(dir(e))
            self._device_state = 'unavailable'

        self._logger.info('CobraBay: Initialization complete.')

    # Command processor. This is a method because it can get called from multiple loops.
    def _process_commands(self,command_stack):
        # Might have more than one command in the stack, process each of them.
        for command in command_stack:
            if 'rescan_sensors' in command['cmd']:
                self._sensors.rescan()
            if 'dock' in command['cmd']:
                self.dock()
            if 'undock' in command['cmd']:
                self.undock()
            if 'display_sensor' in command['cmd']:
                if 'options' in command:
                    options = command['options']
                    if isinstance(options, dict):
                        sensor = options['sensor']
                        timeout = float(options['timeout'])
                    elif isinstance(options, str):
                        sensor = options
                        timeout = float(360)
                    else:
                        return
                    if sensor not in self._sensors.sensor_state().keys():
                        return

                    # Default to 1h if larger than 1h.
                    if float(timeout) > 3600:
                        timeout = float(3600)
                    self._logger.info("Starting sensor display mode for: {}".format(sensor))
                    self._display_sensor = {
                        'sensor': sensor,
                        'timeout': timeout,
                        'start': time.monotonic()
                    }

    # Main operating loop.
    def run(self):
        self._logger.info('CobraBay: Starting main operating loop.')
        # This loop runs while the system is idle. Process commands, increment various timers.
        system_state = {'signal_strength': 0, 'mqtt_status': False}
        while True:
            # Have the network object make any necessary reconnections.
            self._network.reconnect()
            # network_data = self._network.poll(self._device_state, self._bay.state())
            # Send device and bay state outbound to MQTT.
            self._outbound_messages.append(dict(topic='device_state', message=self._device_state, only_changed=True))
            self._outbound_messages.append(dict(topic='bay_state', message=self._bay.state(), only_changed=True))

            # Poll the network, send any outbound messages there for MQTT publication.
            network_data = self._network.poll(self._outbound_messages)
            self._outbound_messages = []
            # Poll the network messages queue.
            # If there are commands passed up, process them.
            if len(network_data['commands']) > 0:
                #try:
                self._process_commands(network_data['commands'])
                # except:
                #     pass
            else:
                # No commands, so throw up the idle state.
                system_state['signal_strength'] = network_data['signal_strength']
                system_state['mqtt_status'] = network_data['mqtt_status']
            # Should we display a given sensor during the generic display phase?
            if self._display_sensor['sensor'] is not None:
                sensor_value=self._sensors.get_sensor(self._display_sensor['sensor'])
                # If timeout has expired, blank it.
                print("Timer: {}\nTimeout: {}".format(time.monotonic() - self._display_sensor['start'],self._display_sensor['timeout']))
                if ( time.monotonic() - self._display_sensor['start'] ) > self._display_sensor['timeout']:
                    self._display_sensor = { 'sensor': None }
                    self._logger.info("Ending sensor display mode.")
            else:
                sensor_value=None
            try:
                self._display.display_generic(system_state,sensor_value)
            except:
                pass

    def display_sensor(self):
        pass

    # Start sensors and display to guide parking.
    def dock(self):
        self._logger.info('CobraBay: Beginning dock.')
        # Start the VL53 sensors ranging
        self._sensors.vl53('start')
        while True:
            # Check the network for additional commands.
            self._logger.debug('CobraBay: Polling network.')
            network_data = self._network.poll(self._device_state, 'docking')
            # If we got an abort command, stop the docking!
            # Ignore all other commands, they don't make sense.
            if 'abort' in network_data['commands']:
                self._logger.info('CobraBay: Abort command, cancelling docking.')
                break
            # Check the sensors. By default, this will sweep all sensors.
            self._logger.debug('CobraBay: Sweeping sensors.')
            try:
                sensor_data = self._sensors.sweep()
            except Exception as e:
                self._logger.error('CobraBay: Could not get sensor data. Will sleep 5m and reset.')
                self._logger.error('CobraBay: ' + e)
                time.sleep(360)
                self._network.disconnect('resetting')
                microcontroller.reset()
            # Send the collected data to the bay object to interpret
            self._logger.debug('CobraBay: Getting new bay state.')
            bay_state = self._bay.update(sensor_data)
            # Display the current state of the bay.
            self._logger.debug('CobraBay: Sending bay state to display.')
            self._display.display_dock(bay_state)
        self._logger.info('CobraBay: Dock complete.')

    def undock(self):
        self._logger.info('CobraBay: Undock not yet implemented.')
        return

    # Process to stop the docking or undocking process, shut down the sensors and return to the idle state.
    def complete_dock_undock(self):
        self._logger.info('CobraBay: Beginning power down.')
        # Get all the current tasks, except ourself.
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        # Cancel all the running coroutines. This will inherently stop all the ultrasound sensors.
        for task in tasks:
            task.cancel()
        # Explicitly stop any vl53 sensors, which range on their own.
        self._sensors.vl53('stop')
        # Release the display to allow proper reinitialization later.
        displayio.release_displays()