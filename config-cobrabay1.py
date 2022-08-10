config = {
    # Define global settings.
    'global': {
        'units': 'imperial', # Defaults to 'metric' if set to anything other than 'imperial'.
        'sensor_pacing': 5, # Time in seconds between each ultrasonic sensor ping, to prevent echos.
        'system_name': 'CobraBay2', # ID of the system. Will be used for MQTT client ID, as well as name in MQTT Topics.
        'homeassistant': True,  # Integrate with Home Assistant?
        # 'syslog':
        #      {'host': 'tachyon.jumpbeacon.net',
        #       'facility': 'local7',
        #       'protocol': 'udp'}
        },
    # Define sensors to be used in the Bay definition.
    'sensors': {
        'lat_front': {
            'type': 'vl53l1x',
            'bus_id': 1,
            'addr': 0x30,
            'distance_mode': 'medium',  # Distance mode, can be 'short', 'medium', or 'long'
            'timing_budget': 50,  # Inter-measurement period, in milliseconds.
            'shut_board': 'pi',
            'shut_pin': 25
            },
        'lat_mid': {
            'type': 'vl53l1x',
            'bus_id': 1,
            'addr': 0x31,
            'distance_mode': 'medium',
            'timing_budget': 50,
            'shut_board': 0x58,
            'shut_pin': 1
            },
        'lat_rear': {
            'type': 'vl53l1x',
            'bus_id': 1,
            'addr': 0x32,
            'distance_mode': 'medium',
            'timing_budget': 50,
            'shut_board': 0x58,
            'shut_pin': 2
        },
    },
    'bay': {  # Bay definition. ONLY ONE IS SUPPORTED NOW!
        'active': True,  # Is the bay active?
        'name': 'bay2',  # Name to use for the bay in MQTT. Will be made all lower-case.
        'park_time': "2 min",  # How long until a stationary vehicle is counted as parked.
        # How to range-find the vehicle
        'range': {
            'dist_max': "276 in", # Maximum range to report at
            'dist_stop': "10 in", # Distance from the range sensor where the vehicle should stop.
            'sensor': 'center' # Assigned sensor for range finding
            },
        # Lateral alignment zones to check if the vehicle is too far left or right.
        # Will be sorted by intercept range on start-up.
        # If there aren't lateral sensors, this key still needs to exist, but it can be empty.
        'lateral': [
            # { 'intercept_range': "100 in", # Distance at which an approaching vehicle should trigger this sensor.
            #    'dist_ideal': "10 in", # Ideal lateral distance of the vehicle from this sensor.
            #    'ok_spread': "1 in", # Within this distance of the ideal, still report it as good.
            #    'warn_spread': "3 in", # More than this distance off the ideal will throw a warning.
            #    'red_spread': "5 in", # More than this distance off the ideal will be critical
            #    'sensor': 'lat_front', # Assigned sensor
            #    'side': 'L' # Side of the bay the sensor is mounted on, 'L' or 'R'. This is relative to the range sensor.
            # },
            # { 'intercept_range': "50 in", # Distance at which an approaching vehicle should trigger this sensor.
            #   'dist_ideal': "10 in", # Ideal lateral distance of the vehicle from this sensor.
            #   'ok_spread': "1 in", # Within this distance of the ideal, still report it as good.
            #   'warn_spread': "3 in", # More than this distance off the ideal will throw a warning.
            #   'red_spread': "5 in", # More than this distance off the ideal will be critical
            #   'sensor': 'lat_rear', # Assigned sensor
            #   'side': 'L' # Side of the bay the sensor is mounted on, 'L' or 'R'. This is relative to the range sensor.
            #   }
            ]
        }
    }
