####
# Cobra Bay - The Bay!
####

import copy
import time

import pint.errors
from pint import UnitRegistry, Quantity
from time import monotonic
from math import floor
from numpy import datetime64, timedelta64
from numpy import int32 as np_int32
import logging
from pprint import pformat
from operator import attrgetter
from CobraBay.const import *
from CobraBay.datatypes import Intercept, Vector


class CBBay:
    def __init__(self, id,
                 name,
                 depth,
                 longitudinal,
                 lateral,
                 cbcore,
                 q_cbsmcontrol,
                 timeouts,
                 triggers=None,
                 report_adjusted=True,
                 log_level="WARNING"):
        """
        :param id: ID for the bay. Cannot have spaces.
        :type id: str
        :param name: Long "friendly" name for the Bay, used in MQTT messages
        :type name: str
        :param depth: Absolute distance of the bay, from the range sensor to the end. Must be a linear Quantity.
        :type depth: Quantity(Distance)
        :param longitudinal: Detectors which are arranged as longitudinal.
        :type longitudinal: dict
        :param lateral: Detectors which are arranged as lateral.
        :type lateral: dict
        :param cbcore: Object reference to the CobraBay core.
        :type cbcore: CobraBay.core.CBCore
        :param q_cbsmcontrol: Sensor Manager control queue.
        :type q_cbsmcontrol: Queue
        :param timeouts: Dict with timeouts for 'dock','undock' and 'postroll' times.
        :type time_dock: dict
        :param triggers: Dictionary of Triggers for this bay. Can be modified later with register_trigger.
        :type triggers: dict
        :param log_level: Log level for the bay, must be a Logging level.
        :type log_level: str
        """
        # Must set ID before we can create the logger.
        self.id = id
        self._logger = logging.getLogger("CobraBay").getChild(self.id)
        self._logger.setLevel(log_level.upper())
        self._logger.info("Initializing bay: {}".format(id))

        # Save the parameters.
        self._cbcore = cbcore
        self._config = {'long': longitudinal, 'lat': lateral}
        self._config_merged = self._merge_config()
        self.depth_abs = depth
        self._name = name
        self._q_cbsmcontrol = q_cbsmcontrol
        self._timeouts = timeouts
        if triggers is None:
            self._triggers = {}
        else:
            self._triggers = triggers
        self._report_adjusted = report_adjusted

        # Debug output....
        self._logger.debug("Have Longitudinal config: {}".format(longitudinal))
        self._logger.debug("Have lateral config: {}".format(lateral))

        # Make a list of configured sensor names from the configuration.
        self._configured_sensors = {'long': [], 'lat': []}
        self._logger.debug("Compiling configured sensors.")
        for sensor in longitudinal['sensors']:
            self._logger.debug("Considering in longitudinal configuration: {}".format(sensor))
            self._configured_sensors['long'].append(sensor['name'])
        for sensor in lateral['sensors']:
            self._logger.debug("Considering in lateral configuration: {}".format(sensor))
            self._configured_sensors['lat'].append(sensor['name'])
        self._logger.info("Configured longitudinal sensors: {}".format(self._configured_sensors['long']))
        self._logger.info("Configured lateral sensors: {}".format(self._configured_sensors['lat']))

        # Select a longitudinal detector to be the main range detector.
        # Only one supported currently.
        self._selected_range = self._select_range(longitudinal)
        self._logger.debug("Longitudinal detector '{}' selected for ranging".format(self._selected_range))
        # Sort the lateral detectors by intercept.
        self.lateral_sorted = self._sort_lateral(lateral['sensors'])

        # Initialize variables.
        self._motion_timeout = None
        self._occupancy = None
        self._occupancy_score = None
        self._position = {}
        self._previous = {}
        self._previous_scan_ts = 0
        self._quality_ranges = {}
        self._sensor_info = {
            'state': {},
            'status': {},
            'reading': {},
            'quality': {},
            'motion': {},
            'vector': {},
            'intercepted': {}
        }
        self._state = None
        self._trigger_registry = {}

        # Create a unit registry.
        self._ureg = UnitRegistry

        # Calculate ranges for sensors.
        self._calculate_quality_ranges(longitudinal=longitudinal, lateral=lateral)

        # Set the occupancy score. This is set statically, so it doesn't change if/when sensors die.
        self._occupancy_score = self._calculate_occupancy_score()
        self._logger.info("Calculated occupancy score of '{}'".format(self._occupancy_score))

        # Activate detectors.
        # self._logger.info("Activating detectors...")
        # self._detector_state(SENSTATE_RANGING)
        # self._logger.info("Detectors activated.")

        # Motion timer for the current motion.
        self._current_motion = {
            'mark': time.monotonic() + 5
        }

        # Set our initial state.
        # self._scan_detectors()

        self._logger.info("Bay '{}' initialization complete.".format(self.id))

        self.state = BAYSTATE_READY

    ## Public Methods

    # Abort gets called when we want to cancel a docking.
    def abort(self):
        self.state = "ready"

    def check_timer(self):
        # TODO: Fix this so it works.
        self._logger.debug("Evaluating for timer expiration.")
        # Update the dock timer.
        self._logger.debug("Selected range sensor is: {} ({})".format(self._selected_range,
                                                                      type(self._selected_range)))
        self._logger.debug("Sensor info has data: {}".format(self._sensor_info))
        if self._sensor_info['motion'][self._selected_range]:
            # If motion is detected, update the time mark to the current time.
            self._logger.debug("Motion found, resetting dock timer.")
            self._current_motion['mark'] = time.monotonic()
        else:
            # Report the timer every 15s, to the info log level.
            time_elapsed = Quantity(time.monotonic() - self._current_motion['mark'], 's')
            if floor(time_elapsed.magnitude) % 15 == 0:
                self._logger.debug("Motion timer at {} seconds vs allowed {}s".
                                   format(floor(time_elapsed.magnitude), self._active_timeout))
            # No motion, check for completion
            if time_elapsed >= self._active_timeout:
                self._logger.info("Dock timer has expired, returning to ready")
                # Set self back to ready.
                self.state = 'ready'

    def shutdown(self):
        self._logger.critical("Beginning shutdown...")
        self._logger.critical("Shutting off detectors...")
        self._q_cbsmcontrol.put((SENSTATE_DISABLED, None))
        self._logger.critical("Shutdown complete. Exiting.")

    def trigger_register(self, trigger_obj):
        self._logger.debug("Registering trigger ID '{}'".format(trigger_obj.id))
        self._triggers[trigger_obj.id] = trigger_obj

    def trigger_deregister(self, trigger_id):
        self._logger.debug("Deregistering Trigger ID '{}'".format(trigger_id))
        del self._triggers[trigger_id]

    def triggers_check(self):
        for trigger_id in self._triggers:
            if self._triggers[trigger_id].triggered:
                self._logger.debug("Trigger '{}' is active.".format(trigger_id))
                self._logger.debug("Trigger has command stack - {}".format(self._triggers[trigger_id].cmd_stack))
                while self._triggers[trigger_id].cmd_stack:
                    # Pop the command from the object.
                    cmd = self._triggers[trigger_id].cmd_stack.pop(0)
                    self._logger.debug("Next command on stack. '{}' ({})".format(cmd, type(cmd)))
                    # Bay commands will trigger a motion or an abort.
                    # For nomenclature reasons, change the imperative form to the descriptive
                    if cmd.lower() == BAYCMD_DOCK:
                        self._logger.debug("Setting bay state to 'DOCKING'")
                        self.state = BAYSTATE_DOCKING
                        break
                    elif cmd.lower() == BAYCMD_UNDOCK:
                        self._logger.debug("Setting bay state to 'UNDOCKING'")
                        self.state = BAYSTATE_UNDOCKING
                        break
                    elif cmd.lower() == BAYCMD_ABORT:
                        self._logger.debug("Aborting bay motions.")
                        self.abort()
                    elif cmd.lower() == BAYSTATE_VERIFY:
                        self._logger.debug("Scanning sensors, calculating occupancy and sending to MQTT broker.")
                        self.state = BAYSTATE_VERIFY
                    else:
                        self._logger.debug("'{}' has no associated action as a bay command.".format(cmd))

    def update(self):
        """Read in sensor values and update all derived values."""

        # If the data hasn't changed, don't update.
        if len(self._cbcore.sensor_log) > 0:
            # if self._cbcore.sensor_latest_data.timestamp == self._sensor_log[0].timestamp:
            #     self._logger.debug("No change to latest sensor data, nothing to update.")
            #     return
            # else:
            #     # Proceed with update.
            #     self._logger.debug("Adding latest sensor data to log.")
            #     self._sensor_log = [copy.deepcopy(self._cbcore.sensor_latest_data)] + self._sensor_log[0:9]
            #     self._logger.debug("Sensor log now has '{}' entries.".format(len(self._sensor_log)))
            #     self._logger.debug("Latest entry is: {}".format(self._sensor_log[0]))

            # Update all the Longitudinal sensors.
            for sensor_id in self._configured_sensors['long']:
                self._logger.debug("Updating values for '{}' (Long)".format(sensor_id))
                # State
                self._sensor_info['status'][sensor_id] = self._cbcore.sensor_log[0].sensors[sensor_id].response_type

                # Reading
                if self._cbcore.sensor_log[0].sensors[sensor_id].response_type == SENSOR_RESP_OK:
                    # If the sensor actually reported a value, go with it.
                    self._sensor_info['reading'][sensor_id] = (
                            self._cbcore.sensor_log[0].sensors[sensor_id].range - self._config_merged[sensor_id][
                        'zero_point']
                    )
                elif self._cbcore.sensor_log[0].sensors[sensor_id].response_type == SENSOR_RESP_INR:
                    # This means we're waiting for the interrupt. Continue to use the most recent value.
                    self._sensor_info['reading'][sensor_id] = self._most_recent_reading(sensor_id)
                else:
                    self._sensor_info['reading'][sensor_id] = GEN_UNKNOWN

                # Quality
                self._sensor_info['quality'][sensor_id] = self._sensor_quality_long(sensor_id)

                # Motion
                self._sensor_info['motion'][sensor_id] = self._sensor_motion(sensor_id)

            # Update the Lateral sensors.
            for sensor_id in self._configured_sensors['lat']:
                self._logger.debug("Updating values for '{}' (Lat)".format(sensor_id))

                # Update the readings.
                if self._cbcore.sensor_log[0].sensors[sensor_id].response_type == SENSOR_RESP_OK:
                    # If the sensor actually reported a value, update it with the offset and store.
                    self._sensor_info['reading'][sensor_id] = (
                            self._cbcore.sensor_log[0].sensors[sensor_id].range - self._config_merged[sensor_id][
                        'zero_point']
                    )
                elif self._cbcore.sensor_log[0].sensors[sensor_id].response_type == SENSOR_RESP_INR:
                    # This means we're waiting for the interrupt. Continue to use the most recent value.
                    self._sensor_info['reading'][sensor_id] = self._most_recent_reading(sensor_id)
                else:
                    self._sensor_info['reading'][sensor_id] = GEN_UNKNOWN

                # Intercept status.
                self._sensor_info['intercepted'][sensor_id] = self._sensor_intercepted(sensor_id)

                # Quality
                self._sensor_info['quality'][sensor_id] = self._sensor_quality_lat(sensor_id)

        # If bay is in a motion state, check the timer for expiration.
        if self.state in BAYSTATE_MOTION:
            self.check_timer()

    ## Public Properties

    @property
    def active(self):
        """
        Activeness state of the bay. IE: Is it doing something? This is a useful shorthand
        :return: bool
        """
        if self._state in (BAYSTATE_DOCKING, BAYSTATE_UNDOCKING, BAYSTATE_VERIFY, BAYSTATE_POSTROLL):
            return True
        else:
            return False

    @property
    def configured_sensors(self):
        return self._configured_sensors

    @property
    def depth_abs(self):
        """
        Absolute distance from the range sensor to the end of the bay.

        :return: float
        """
        return self._depth_abs

    @depth_abs.setter
    def depth_abs(self, the_input):
        """
        Set the absolute depth.

        :param the_input:
        :return:
        """
        self._depth_abs = Quantity(the_input).to('cm')

    # @property
    # def discovery_reg_info(self):
    #     # For discovery, the detector hierarchy doesn't matter, so we can flatten it.
    #     return_dict = {
    #         'id': self.id,
    #         'bay_name': self.bay_name,
    #         'detectors': []
    #     }
    #     for item in self._sensors:
    #         detector = {
    #             'detector_id': item,
    #             'name': self._sensors[item].name,
    #             'type': self._sensors[item].detector_type
    #         }
    #         return_dict['detectors'].append(detector)
    #     return return_dict

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, input):
        self._id = input.replace(" ", "_").lower()

    # @property
    # def range(self):
    #     '''
    #     The selected range object for this bay.
    #
    #     :return: detectors.Range
    #     '''
    #     return self._sensors[self._selected_range]
    @property
    def config_merged(self):
        """ The complete configuration for sensors, including defaults."""
        return self._config_merged

    @property
    def motion_timer(self):
        '''
        Reports time left on the current motion in M:S format. If no active motion, returns 'Inactive'.

        :return: str
        '''
        if self._active_timeout is not None:
            remaining_time = self._active_timeout - Quantity(time.monotonic() - self._current_motion['mark'], 's')
            # This catches the case were we're reporting a negative value to Home Assistant, which it reports in strange
            # ways. Instead, just clamp it to zero. This is *likely* due to not checking often enough, but this fix is
            # good enough for now.
            if remaining_time < 0:
                return Quantity("0s")
            else:
                return remaining_time
        else:
            # Return 0s if no active motion. This is because HA doesn't like it if we switch to a string representation.
            return Quantity("0s")

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, name):
        self._name = name

    @property
    def occupied(self):
        """
        Occupancy state of the bay, determined based on what the sensors can hit.
        If positively occupied or not, returns that, otherwise 'unknown'.

        :returns: bay occupancy state
        :rtype: bool
        """
        # TODO: Rework all this logic. Should probably be a rolling monitor of values?

        self._logger.debug("Checking for occupancy.")
        # Status variable for occupancy. Start at unknown.
        occ = GEN_UNKNOWN

        # Must be actively ranging to determine occupancy. Check for that, return unknown otherwise.
        if self._selected_range not in self._sensor_info['status']:
            self._logger.info("Cannot calculate occupancy, selected longitudinal sensor does not have a known status. "
                              "This is fine on startup.")
            self._logger.info("Current sensor_info: {}".format(self._sensor_info))
            return GEN_UNKNOWN

        if self._sensor_info['status'][self._selected_range] != SENSOR_RESP_OK:
            self._logger.debug("Selected longitudinal sensor not ranging. Occupancy 'unknown'")
            return GEN_UNKNOWN

        range_quality = self._sensor_info['quality'][self._selected_range]
        if range_quality in (SENSOR_QUALITY_NOOBJ, SENSOR_QUALITY_DOOROPEN, SENSOR_QUALITY_BEYOND):
            # Cases where there's no vehicle longitudinally means we jump straight to unoccupied.
            self._logger.debug("Longitudinal quality is '{}', not occupied.".format(range_quality))
            occ = "false"
        elif range_quality in (SENSOR_QUALITY_EMERG, SENSOR_QUALITY_BACKUP, SENSOR_QUALITY_PARK,
                               SENSOR_QUALITY_FINAL, SENSOR_QUALITY_BASE, SENSOR_QUALITY_OK):
            self._logger.debug("Matched longitudinal quality: {}".format(range_quality))
            # If the detector is giving us any of the 'close enough' qualities, there's something being found that
            # could be a vehicle. Check the lateral sensors to be sure that's what it is, rather than somebody blocking
            # the sensors or whatnot
            occ_score = 1
            for sensor_id in self._configured_sensors['lat']:
                self._logger.debug("Checking quality for lateral sensor '{}'.".format(sensor_id))
                if self._sensor_info['quality'][sensor_id] in (SENSOR_QUALITY_OK, SENSOR_QUALITY_WARN,
                                                               SENSOR_QUALITY_CRIT):
                    # No matter how badly parked the vehicle is, it's still *there*
                    occ_score += 1
            self._logger.debug("Achieved lateral score {} of {}".format(occ_score, self._occupancy_score))
            if occ_score >= self._occupancy_score:
                # All sensors have found something more or less in the right place, so yes, we're occupied!
                occ = 'true'
            else:
                occ = 'false'
        else:
            self._logger.warning(
                "Occupancy cannot be calculated, longitudinal sensor had quality '{}'".format(range_quality))
            occ = 'error'
        if occ != self._occupancy:
            self._logger.info("Occupancy has changed from '{}' to '{}'".format(self._occupancy, occ))
        self._occupancy = occ
        return occ

    @property
    def range_pct(self):
        '''
        Percentage of distance covered from the garage door to the stop point.
        :return: float
        '''
        # TODO: Fix range references.
        # If it's not a Quantity, just return zero.
        self._logger.debug("Calculating range percentage")
        self._logger.debug("Range value: {} ({})".format(self.range.value, type(self.range.value)))
        self._logger.debug("Adjusted depth: {}".format(self.depth))
        if isinstance(self.range.value, Quantity):
            range_pct = self.range.value.to('cm') / self.depth.to('cm')
            # Singe this is dimensionless, just take the value and make it a Python scalar.
            range_pct = range_pct.magnitude
            return range_pct
        else:
            return 0

    @property
    def selected_range(self):
        """ The range sensor selected to be controlling for longitudinal readings."""
        return self._selected_range

    @property
    def sensor_info(self):
        return self._sensor_info

    @property
    def state(self):
        """
        Operating state of the bay.
        See const.py 'BAYSTATE_*' for valid values.

        :returns Bay state
        :rtype: String
        """
        return self._state

    @state.setter
    def state(self, m_input):
        """
        Change the operating state of the bay.

        :param m_input:
        :return: None
        """
        # Trap invalid bay states.
        self._logger.debug("input: {}, {} {}".format(m_input, BAYSTATE_VERIFY, BAYSTATE_VERIFY == m_input))
        if m_input not in (BAYSTATE_READY, BAYSTATE_NOTREADY, BAYSTATE_DOCKING, BAYSTATE_UNDOCKING, BAYSTATE_VERIFY,
                           GEN_UNAVAILABLE):
            raise ValueError("{} is not a valid bay state.".format(m_input))
        self._logger.debug("Old state: {}, new state: {}".format(self._state, m_input))
        if m_input == self._state:
            self._logger.debug("Requested state {} is also current state. No action.".format(m_input))
            return
        # When requested to enter a motion state, DOCKING or UNDOCKING.
        if m_input in SYSSTATE_MOTION and self.state not in SYSSTATE_MOTION:
            self._logger.info("Entering state: {} (Previously '{}')".format(m_input, self.state))
            self._current_motion['mark'] = monotonic()
            # self._sensor_log = []  # Reset the sensor log to flush stale data.
            self._logger.info("Start time: {}".format(self._current_motion['mark']))
            self._logger.info("Setting all sensors to ranging.")
            # TODO: Convert to queue command.
            self._q_cbsmcontrol.put((SENSTATE_RANGING, None))
        # When requesting to leave a motion state.
        elif m_input not in SYSSTATE_MOTION and self.state in SYSSTATE_MOTION:
            self._logger.info("Entering state: {} (Previously '{}')".format(m_input, self.state))
            # Reset some variables.
            # Make the mark none to be sure there's not a stale value in here.
            self._current_motion['mark'] = None
            # self._sensor_log = []
        # Now store the state.
        self._state = m_input

    @property
    def vector(self):
        """
        The vector from the bay's selected range detector.

        :return:
        :rtype: namedtuple
        """
        # When performing a verify, always report no motion, since we're not collecting enough data, any
        # values will be noise.
        # TODO: Rework vector calculation. Need to bring this inboard since detectors are gone.
        # return Vector(speed=Quantity('0kph'), direction='still')
        # Return variable for unknown movement.
        vector_unknown = Vector(speed=GEN_UNKNOWN, direction=GEN_UNKNOWN)

        # Have to have at least two elements.
        if len(self._cbcore.sensor_log) < 2:
            self._logger.debug("Vector - Not enough sensor readings to calculate vector.")
            return vector_unknown

        # If we haven't had a motion reading recently enough, vector can't be determined.
        # 100ms is 100000000ns, will make this static.
        timediff = (datetime64('now', 'ns') - self._cbcore.sensor_log[0].timestamp).astype(np_int32)
        self._logger.debug("Vector - Time difference is '{}' ({})".format(timediff, type(timediff)))

        if timediff < timedelta64(750000000, 'ns').astype(np_int32):
            # TODO: Make this interval be based on the actual sensor timing interval. OR, can keep, good enough?
            self._logger.info("Vector - Most recent longitudinal reading over 750ms ago, can't determine vector.")
            return vector_unknown

        # If we haven't returned yet, we can calculate.
        i = 1
        while i <= len(self._cbcore.sensor_log):
            # Find the element in the log where the selected range sense returned a Quantity, and is either
            # 250ms (0.25s) ago OR is the last reading (good enough)
            if ((((self._cbcore.sensor_log[0].timestamp - self._cbcore.sensor_log[i].timestamp).astype(np_int32)
                  >= 250000000) or i == len(self._cbcore.sensor_log))
                    and type(self._cbcore.sensor_log[i].sensors[self._selected_range].range) is Quantity):
                self._logger.debug("Vector - Comparing to reading {}".format(i))
                # TODO: Account for a dead zone so tiny changes don't result in a motion.
                # FIXME: Returns unknown sometimes, don't know why.
                spread_time = (self._cbcore.sensor_log[0].timestamp - self._cbcore.sensor_log[i].timestamp).astype(
                    np_int32)
                self._logger.debug("Vector - Sensor reading time spread is {}".format(spread_time))
                try:
                    spread_distance = (self._cbcore.sensor_log[0].sensors[self._selected_range].range
                                   - self._cbcore.sensor_log[i].sensors[self._selected_range].range)
                except pint.errors.DimensionalityError:
                    self._logger.warning("Dimensionality error when evaluating vector. SensorReading 0 had selected "
                                         "range {} ({}) while {} had selected range {} ({})".format(
                        self._cbcore.sensor_log[0].sensors[self._selected_range].range,
                        type(self._cbcore.sensor_log[0].sensors[self._selected_range].range),
                        i, self._cbcore.sensor_log[i].sensors[self._selected_range].range,
                        type(self._cbcore.sensor_log[i].sensors[self._selected_range].range)
                    ))
                    return vector_unknown
                self._logger.debug("Vector - Sensor reading distance spread is {}".format(spread_distance))
                speed = abs(spread_distance) / Quantity(spread_time, "ns")
                if spread_distance == 0:
                    direction = DIR_STILL
                elif spread_distance > 0:
                    direction = DIR_REV
                elif spread_distance < 0:
                    direction = DIR_FWD
                else:
                    self._logger.warning(
                        "Vector - Direction spread has unhandleable value '{}'".format(spread_distance))
                    return vector_unknown
                # Convert the value.
                self._logger.debug("Vector - Raw speed is '{}'".format(speed))
                speed = speed.to("kph")
                self._logger.debug("Vector - Converted speed '{}'".format(speed))
                return Vector(speed=speed, direction=direction)
            # Increment
            i += 1

    ## Private Methods

    def _merge_config(self):
        merged_config = {}
        for sensor_config in self._config['long']['sensors']:
            merged = {**self._config['long']['defaults'], **sensor_config}
            merged_config[merged['name']] = merged
        for sensor_config in self._config['lat']['sensors']:
            merged = {**self._config['lat']['defaults'], **sensor_config}
            merged_config[merged['name']] = merged
        self._logger.debug("Merged sensor config by name: {}".format(merged_config))
        return merged_config

    def _most_recent_reading(self, sensor_id):
        """Get the most recent reading from the sensor log for a given sensor_id"""
        # TODO: Make this more robust or with more options to deal with edge cases.
        for entry in self._cbcore.sensor_log:
            try:
                if entry.sensors[sensor_id].response_type == SENSOR_RESP_OK:
                    return entry.sensors[sensor_id].range
                elif entry.sensors[sensor_id].response_type == SENSOR_RESP_INR:
                    continue
            except KeyError:
                pass

    # Old _make_range implementation...

    # def _make_range_buckets(self, longitudinal, lateral):
    #     ''' Calculate ranges for each sensor.'''
    #     # Output dictionary.
    #     configured_detectors = {}
    #     self._logger.debug("Bay Longitudinal settings: {}".format(longitudinal))
    #     self._logger.debug("Bay Lateral settings: {}".format(lateral))
    #
    #     for sensor_config in longitudinal['sensors']:
    #         # Merge the sensor config and defaults.
    #         sensor_config = {**longitudinal['defaults'], **sensor_config}
    #         self._logger.debug("Calculating ranges for sensor config: {}".format(sensor_config))
    #         bay_depth = (self.depth_abs - sensor_config['zero_point'])
    #         long_ranges = {
    #             'zero': sensor_config['zero_point'],
    #             'park_min': sensor_config['zero_point'] - sensor_config['spread_park'],
    #             'park_max': sensor_config['zero_point'] + sensor_config['spread_park'],
    #             'base': (bay_depth * sensor_config['pct_crit']) + sensor_config['spread_park'],
    #             'final': (bay_depth * sensor_config['pct_warn']) + sensor_config['spread_park']
    #         }
    #         self._logger.debug("Calculated ranges for longitudinal sensor '{}': {}".format(sensor_config['name'],
    #                                                                                        pformat(long_ranges)))
    #         self._ranges['long'][sensor_config['name']] = long_ranges
    #
    #     for sensor_config in lateral['sensors']:
    #         sensor_config = {**lateral['defaults'], **sensor_config}
    #         self._logger.debug("Calculating ranges for sensor config: {}".format(sensor_config))
    #         lat_ranges = {
    #             'zero': sensor_config['zero_point'],
    #             'warn_min': sensor_config['zero_point'] - sensor_config['spread_warn'],
    #             'ok_min': sensor_config['zero_point'] - sensor_config['spread_ok'],
    #             'ok_max': sensor_config['zero_point'] + sensor_config['spread_ok'],
    #             'warn_max': sensor_config['zero_point'] + sensor_config['spread_warn']
    #         }
    #         self._logger.debug(
    #             "Calculated ranges for lateral sensor '{}': {}".format(sensor_config['name'], pformat(lat_ranges)))
    #         self._ranges['lat'][sensor_config['name']] = lat_ranges

    def _calculate_quality_ranges(self, longitudinal, lateral):
        ''' Calculate ranges for each sensor.'''
        # Output dictionary.
        configured_detectors = {}
        self._logger.debug("Bay Longitudinal settings: {}".format(longitudinal))
        self._logger.debug("Bay Lateral settings: {}".format(lateral))

        for sensor_config in longitudinal['sensors']:
            # Merge the sensor config and defaults.
            sensor_config = {**longitudinal['defaults'], **sensor_config}
            self._logger.info("Calculating quality ranges for '{}'.".format(sensor_config['name']))
            # Create the sub-dict
            self._quality_ranges[sensor_config['name']] = {}
            self._logger.debug("Total bay depth: {}".format(self.depth_abs))
            self._logger.debug("Zero Point: {}".format(sensor_config['zero_point']))
            # Adjusted distance of the bay. Distance from the offset point to the end of the bay
            adjusted_depth = self.depth_abs - sensor_config['zero_point']
            self._logger.debug("Adjusted depth: {}".format(adjusted_depth))
            self._logger.debug("Critical multiplier: {}".format(sensor_config['pct_crit']))
            self._logger.debug("Warn multiplier: {}".format(sensor_config['pct_warn']))
            # Crit and Warn are as a percentage of the *adjusted* distance.
            crit_distance = sensor_config['zero_point'] + (adjusted_depth * sensor_config['pct_crit'])
            self._logger.debug("Critical distance: {}".format(crit_distance))
            warn_distance = sensor_config['zero_point'] + (adjusted_depth * sensor_config['pct_warn'])
            self._logger.debug("Warning distance: {}".format(warn_distance))

            # TODO: Actually implement error_margins.
            error_margin = 0

            # Set the quality ranges.
            ## Okay is the Offset, +/- the error margin.
            self._quality_ranges[sensor_config['name']][SENSOR_QUALITY_EMERG] = \
                [Quantity("0 in"), Quantity("2 in")]
            self._quality_ranges[sensor_config['name']][SENSOR_QUALITY_BACKUP] = \
                [Quantity("2 in"), sensor_config['zero_point'] - error_margin]
            self._quality_ranges[sensor_config['name']][SENSOR_QUALITY_PARK] = \
                [sensor_config['zero_point'] - error_margin, sensor_config['zero_point'] + error_margin]
            self._quality_ranges[sensor_config['name']][SENSOR_QUALITY_FINAL] = \
                [self._quality_ranges[sensor_config['name']][SENSOR_QUALITY_PARK][1], crit_distance]
            self._quality_ranges[sensor_config['name']][SENSOR_QUALITY_BASE] = [crit_distance, warn_distance]
            self._quality_ranges[sensor_config['name']][SENSOR_QUALITY_OK] = [warn_distance, self.depth_abs]
            # End of Beyond has to have *an* end. One light year is probably fine as an arbitrarily large value.
            self._quality_ranges[sensor_config['name']][SENSOR_QUALITY_BEYOND] = [self.depth_abs, Quantity('1ly')]
            self._logger.debug("Calculated quality ranges --")
            self._logger.debug(pformat(self._quality_ranges[sensor_config['name']]))

        for sensor_config in lateral['sensors']:
            # Merge the defaults with the specific sensor.
            sensor_config = {**lateral['defaults'], **sensor_config}
            self._logger.debug("Calculating ranges for sensor config: {}".format(sensor_config))
            self._logger.info("Calculating quality ranges for '{}'.".format(sensor_config['name']))
            # Create the sub-dict
            self._quality_ranges[sensor_config['name']] = {}

            # TODO: Actually implement error_margins.
            error_margin = 0

            # Set the quality ranges.
            self._quality_ranges[sensor_config['name']][SENSOR_QUALITY_OK] = \
                [sensor_config['zero_point'] - sensor_config['spread_ok'],
                 sensor_config['zero_point'] + sensor_config['spread_ok']
                 ]
            self._quality_ranges[sensor_config['name']][SENSOR_QUALITY_WARN] = \
                [sensor_config['zero_point'] - sensor_config['spread_warn'],
                 sensor_config['zero_point'] + sensor_config['spread_warn']
                 ]
            # This hard-wires a critical range that should always match.
            self._quality_ranges[sensor_config['name']][SENSOR_QUALITY_CRIT] = \
                [Quantity('-1 km'), Quantity('1 km')]

            self._logger.debug("Calculated quality ranges --")
            self._logger.debug(pformat(self._quality_ranges[sensor_config['name']]))

    # def _quality(self, sensor_id):
    #     # Pull the current value for evaluation.
    #
    #     self._logger.debug("Evaluating longitudinal raw value '{}' for quality".
    #                        format(self._sensor_info['reading'][sensor_id]))
    #     self._logger.debug("Available qualities: {}".format(self._qualities.keys()))
    #     for quality in self._qualities:
    #         self._logger.debug("Checking quality '{}'".format(quality))
    #         try:
    #             if self._qualities[quality][0] <= self._sensor_info['reading'][sensor_id]) < self._qualities[quality][1]:
    #                 self._logger.debug("In quality range '{}' ({} <= X < {})".format(quality,
    #                                                                                  self._qualities[quality][0],
    #                                                                                  self._qualities[quality][1]))
    #                 return quality
    #         except ValueError:
    #             self._logger.error("Received ValueError when finding quality. Range start {} ({}), end {} ({}), read "
    #                                "value {}".format(
    #                 self._qualities[quality][0],type(self._qualities[quality][0]),
    #                 self._qualities[quality][1],type(self._qualities[quality][1]),
    #                 self._sensor_info['reading'][sensor_id])
    #             ))

    def _sensor_intercepted(self, sensor_id):
        self._logger.debug("Lateral Intercept - Checking interception status for '{}'".format(sensor_id))

        intercept = next(item for item in self.lateral_sorted if item.sensor_id == sensor_id)
        self._logger.debug("Lateral Intercept - Using intercept {}".format(intercept))
        try:
            if self._sensor_info['reading'][self.selected_range] <= intercept.intercept:
                self._logger.info("Lateral Intercept - Lateral '{}' is intercepted.".format(sensor_id))
                return True
            else:
                self._logger.info("Lateral Intercept - Lateral '{}' is not intercepted.".format(sensor_id))
                return False
        except ValueError as e:
            self._logger.warning("Lateral Intercept - Selected range threw ValueError exception with '{}' ({})".
                                 format(self._sensor_info['reading'][self.selected_range],
                                        type(self._sensor_info['reading'][self.selected_range])))
            self._logger.exception(e)
            return False

    def _sensor_motion(self, sensor_id):
        """
        Calculate motion for a given Sensor ID
        :param sensor_id: Longitudinal sensor to calculate motion for.
        :return:
        """
        self._logger.info("Calculating motion for sensor '{}'.".format(sensor_id))
        # Make sure this is for a longitudinal sensor.
        if sensor_id not in self._configured_sensors['long']:
            raise ValueError("Sensor ID '{}' is not a configure Longitudinal sensor. Cannot compute motion.".
                             format(sensor_id))
        # TODO: Finish the motion logic.
        filtered_log = []
        self._logger.debug("Sensor log: {} ({})".format(self._cbcore.sensor_log, type(self._cbcore.sensor_log)))
        for response in self._cbcore.sensor_log:
            if response.sensors[sensor_id].response_type == SENSOR_RESP_OK:
                filtered_log.append(response)
        self._logger.debug("Filtered history has {} entries, of {} available".format(len(filtered_log),
                                                                                     len(self._cbcore.sensor_log)))

        # Can't compute motion from fewer than two values.
        if len(filtered_log) < 2:
            return GEN_UNKNOWN
        # Calculate the time difference in seconds.
        timediff = (filtered_log[0].timestamp - filtered_log[-1].timestamp)
        self._logger.debug("Timediff is: {} ({})".format(timediff, type(timediff)))

        # Only take entries at least 250ms apart.
        if timediff < TIME_MOTION_EVAL:
            self._logger.debug(
                "First and last readings are {} ns apart. Less than 250ms, can't calculate.".format(timediff))
            return GEN_UNKNOWN

        self._logger.debug("First log: {}".format(filtered_log[0]))
        self._logger.debug("Last log: {}".format(filtered_log[-1]))

        net_dist = filtered_log[-1].sensors[sensor_id].range - filtered_log[0].sensors[sensor_id].range
        net_time = filtered_log[0].timestamp - filtered_log[-1].timestamp
        self._logger.info("Traveled '{}' in '{}'".format(net_dist, net_time))

    def _sensor_quality_lat(self, sensor_id):
        """
        Determine quality for lateral sensors.

        :param sensor_id:
        :return:
        """
        sensor_reading = self._most_recent_reading(sensor_id)
        self._logger.debug(
            "Evaluating lateral raw value '{}' for quality".format(sensor_reading))
        self._logger.debug("Sensor quality definitions: {}".format(self._quality_ranges[sensor_id]))
        # Is this a longitudinal or lateral sensor? We can tell by which sensor list it's on.
        quality_ranges = (SENSOR_QUALITY_OK, SENSOR_QUALITY_WARN, SENSOR_QUALITY_CRIT)

        # Is the sensor intercepted? If not, nothing else to do.
        if not self._sensor_info['intercepted'][sensor_id]:
            return SENSOR_QUALITY_NOTINTERCEPTED

        for quality in quality_ranges:
            self._logger.debug("Checking quality '{}'".format(quality))
            try:
                if (self._quality_ranges[sensor_id][quality][0] <=
                        sensor_reading < self._quality_ranges[sensor_id][quality][1]):
                    self._logger.debug("In quality range '{}' ({} <= {} < {})".
                                       format(quality,
                                              self._quality_ranges[sensor_id][quality][0],
                                              sensor_reading,
                                              self._quality_ranges[sensor_id][quality][1]))
                    return quality
            except ValueError:
                self._logger.error(
                    "Received ValueError when finding quality. Range start {} ({}), end {} ({}), read "
                    "value {}".format(
                        self._quality_ranges[sensor_id][quality][0], type(self._quality_ranges[sensor_id][quality][0]),
                        self._quality_ranges[sensor_id][quality][1], type(self._quality_ranges[sensor_id][quality][1]),
                        self._sensor_info['reading'][sensor_id]
                    ))

        self._logger.debug("Did not otherwise match quality, marking 'unknown'")
        # In case of a strange failure, return Unknown.
        return GEN_UNKNOWN

    def _sensor_quality_long(self, sensor_id):
        """
        Determine quality for longitudinal sensors.

        :param sensor_id:
        :return:
        """
        sensor_reading = self._most_recent_reading(sensor_id)
        self._logger.debug(
            "Evaluating longitudinal raw value '{}' for quality".format(sensor_reading))
        self._logger.debug("Available qualities: {}".format(self._quality_ranges[sensor_id].keys()))
        quality_ranges = (SENSOR_QUALITY_EMERG, SENSOR_QUALITY_BACKUP, SENSOR_QUALITY_PARK, SENSOR_QUALITY_FINAL,
                          SENSOR_QUALITY_BASE, SENSOR_QUALITY_OK, SENSOR_QUALITY_BEYOND)

        for quality in quality_ranges:
            self._logger.debug("Checking quality '{}'".format(quality))
            try:
                if (self._quality_ranges[sensor_id][quality][0] <=
                        sensor_reading < self._quality_ranges[sensor_id][quality][1]):
                    self._logger.debug("In quality range '{}' ({} <= {} < {})".
                                       format(quality,
                                              self._quality_ranges[sensor_id][quality][0],
                                              self._sensor_info['reading'][sensor_id],
                                              self._quality_ranges[sensor_id][quality][1]))
                    return quality
            except ValueError:
                self._logger.error(
                    "Received ValueError when finding quality. Range start {} ({}), end {} ({}), read "
                    "value {}".format(
                        self._quality_ranges[sensor_id][quality][0], type(self._quality_ranges[sensor_id][quality][0]),
                        self._quality_ranges[sensor_id][quality][1], type(self._quality_ranges[sensor_id][quality][1]),
                        self._sensor_info['reading'][sensor_id]
                    ))
        # If we get here, quality is unknown.
        return GEN_UNKNOWN

    def _select_range(self, longitudinal):
        """
        Select a primary longitudinal sensor to use for range from among those presented.

        :param longitudinal:
        :return: str
        """
        self._logger.debug("Sensors considered for selection: {}".format(longitudinal['sensors']))
        if len(longitudinal['sensors']) == 0:
            raise ValueError("No longitudinal sensors defined. Cannot select a range!")
        elif len(longitudinal['sensors']) > 1:
            raise ValueError("Cannot select a range! More than one longitudinal sensors not currently supported.")
        else:
            return longitudinal['sensors'][0]['name']

    def _sort_lateral(self, lateral_sensors):
        """
        Sort the lateral detectors by distance.

        :param lateral_sensors: List of lateral sensor definition dicts.
        :type lateral_sensors: list
        :return:
        """

        self._logger.debug("Creating sorted intercepts from laterals: {}".format(lateral_sensors))
        lateral_sorted = []
        # Create named tuples and put it in the list.
        for item in lateral_sensors:
            # Make a named tuple out of the detector's config.
            this_sensor = Intercept(item['name'], item['intercept'])
            lateral_sorted.append(this_sensor)
        lateral_sorted = sorted(lateral_sorted, key=attrgetter('intercept'))
        self._logger.debug("Lateral sensors sorted to order: {}".format(lateral_sorted))
        return lateral_sorted

    ## Private Properties
    @property
    def _active_timeout(self):
        ''' Utility method to determine which timeout to use.'''
        if self.state == BAYSTATE_DOCKING:
            return self._timeouts['dock']
        elif self.state == BAYSTATE_UNDOCKING:
            return self._timeouts['undock']
        elif self._state == BAYSTATE_POSTROLL:
            return self._timeouts['post-roll']
        else:
            return None

    def _calculate_occupancy_score(self):
        """Calculate the target occupancy score based on available sensors."""
        max_score = len(self.lateral_sorted)
        score = floor(max_score * (2 / 3)) + 1  # Add 1 for the longitudinal sensor.
        return score
