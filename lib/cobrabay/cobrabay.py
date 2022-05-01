####
# Cobra Bay - Main
####
import gc

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
        # Set up Syslog if enabled.
        self._logger = logging.getLogger('cobrabay')


        self._logger.info('CobraBay: CobraBay Initializing...')
        mem_before = mem_free()
        gc.collect()
        mem_after = mem_free()
        self._logger.info('Available Memory: {}'.format(mem_after))
        self._logger.info('Had been {} before collection. Recovered {}'.format(mem_before,mem_after-mem_before))

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

        self._logger.info('CobraBay: Connecting to network...')
        # Create Network object.
        self._network = Network(
            system_id=config['global']['system_id'],
            bay=(self._bay),  # Pass a ref to the bay object. Multiple bays may be supported later.
            homeassistant=config['global']['homeassistant']
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
            from syslog_handler import SysLogHandler
            try:
                self.syslog = SysLogHandler(
                    address=config['global']['syslog']['host'],
                    facility=config['global']['syslog']['facility'],
                    protocol=config['global']['syslog']['protocol'])
            except Exception as e:
                self._logger.error("Could not set up Syslog logging: {}".format(e))
            else:
                self._logger.addHandler(self.syslog)

        self._logger.info('CobraBay: Creating display...')
        # Create Display object
        try:
            self._display = Display(self.config)
        except MemoryError as e:
            self._logger.error('Display: Memory error while initializing display. Have {}'.format(gc.mem_free()))
            # self._logger.error(dir(e))
            self._device_state = 'unknown'

        self._logger.info('CobraBay: Initialization complete.')

    # Command processor. This is a method because it can get called from multiple loops.
    def _process_commands(self,command_stack):
        # Might have more than one command in the stack, process each of them.
        for command in command_stack:
            if self._bay.state not in ('moving', 'docking', 'undocking'):
                if 'rescan_sensors' in command['cmd']:
                    self._sensors.rescan()
                if 'dock' in command['cmd']:
                    self.dock()
                if 'undock' in command['cmd']:
                    self.undock()
                # Don't allow a verify when we're actually doing a motion.
                if 'verify' in command['cmd'] and self._bay.state not in ('moving', 'docking', 'undocking'):
                    self.verify()
                # Don't allow a display sensor request to override an active motion
                if 'display_sensor' in command['cmd']:
                    if 'options' in command:
                        # Make sure all the options exist.
                        options = command['options']
                        print(options)
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
                            'start': time.monotonic()
                        }
            else:
                # Only allow the abort or complete commands while a motion is in action. Complete takes precedence.
                if 'complete' in command['cmd']:
                    return 'complete'
                if 'abort' in command['cmd']:
                    return 'abort'

    def _network_handler(self):
        # Always add a device state update and a memory message to the outbound message queue
        # Have the network object make any necessary reconnections.
        self._network.reconnect()
        # Queue up outbound messages for processing. By default, the Network class will not
        # send data that hasn't changed, so we can queue it up here without care.
        self._outbound_messages.append(dict(topic='device_state', message=self._device_state))
        self._outbound_messages.append(dict(topic='device_mem', message=mem_free()))
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
            # Do a network poll, this method handles all the default outbound messages and any incoming commands.
            network_data = self._network_handler()
            # Update the network components of the system state.
            system_state['signal_strength'] = network_data['signal_strength']
            system_state['mqtt_status'] = network_data['mqtt_status']
            # Should we display a given sensor during the generic display phase?
            if self._display_sensor['sensor'] is not None:
                sensor_value=self._sensors.get_sensor(self._display_sensor['sensor'])
                # If timeout has expired, blank it.
                #print("Timer: {}\nTimeout: {}".format(time.monotonic() - self._display_sensor['start'],self._display_sensor['timeout']))
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
        # Change the bay's state to docking.
        self._outbound_messages.append({'topic': 'bay_state', 'message': 'docking'})
        # Start the VL53 sensors ranging
        self._sensors.vl53('start')
        done = False
        aborted = False
        while done is False:
            # Check the network for additional commands.
            network_data = self._network_handler()
            # Check for a complete or abort command.
            if 'command' in network_data:
                if network_data['command'] == 'complete':
                    done = True
                if network_data['command'] == 'abort':
                    done = True
                    aborted = True
            try:
                sensor_data = self._sensors.sweep()
            except Exception as e:
                self._logger.error('CobraBay: Could not get sensor data. Will sleep 5m and reset.')
                self._logger.error('CobraBay: ' + e)
                time.sleep(360)
                self._network.disconnect('resetting')
                microcontroller.reset()
            # Send the collected data to the bay object to interpret
            self._bay.update(sensor_data)
            # Display the current state of the bay.
            try:
                self._display.display_dock(self._bay.position)
            except Exception as e:
                self._logger.error("Got display error during docking: {}".format(e))
            # If the bay now considers itself occupied (ie: complete), then we complete.
            if self._bay.state == 'occupied':
                self._logger.info("Received 'completion' message during docking. Finishing.")
                done = True
        # If an abort was called, do a verify.
        if aborted:
            self._logger.info("Docking aborted. Running verify to determine bay state.")
            self.verify()

    def undock(self):
        self._logger.info('CobraBay: Undock not yet implemented.')
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