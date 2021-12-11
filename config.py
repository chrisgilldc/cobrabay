####
# CobraBay Configuration
####

config = {
    'units': 'imperial', # Set to 'imperial' for feet/inches. Otherwise defaults to metric.
    'max_detect_range': 276, # Range in inches where tracking starts.
    'speed_limit': 5, # Treat jumps in range over this rate as spurious. Either MPH or KPH, dependingon units.
    'sensor_pacing': 0.5, # Time in seconds between each sensor ping, to prevent echos.
    'sensors': {
        'center': {'type': 'vl53', 'address': 0x29, 'distance_mode': 'long', 'timing_budget': 50},
        #'sonic_test_r': {'type': 'hcsr04', 'board': 0x58, 'trigger': 1, 'echo': 2, 'timeout': 0.5 },
        'left': {'type': 'hcsr04', 'board': 'local', 'trigger': 0, 'echo': 1, 'timeout': 1 }
        }
    'network': True
}