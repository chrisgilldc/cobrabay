####
# CobraBay
####
import board
import time
#import asyncio

# Release any previous displays.
import displayio
displayio.release_displays()

# Initialize CobraBay object
import cobrabay

# Write the Cobra Bay Config. This is set up here, because it's the most obvious place.

config = {
    # Define global settings.
    'global': {
        'units': 'imperial', # Defaults to 'metric' if set to anything other than 'imperial'.
        'sensor_pacing': 5, # Time in seconds between each ultrasonic sensor ping, to prevent echos.
        'system_id': 'Bay2', # ID of the system. Will be used for MQTT client ID, as well as name in MQTT Topics.
        'homeassistant': False  # Integrate with Home Assistant?
        },
    # Define sensors to be used in the Bay definition.
    'sensors': {
        'center': {'type': 'vl53', 'address': 0x29, 'distance_mode': 'long', 'timing_budget': 50 },
        'lat_front': {'type': 'hcsr04', 'board': 0x58, 'trigger': 1, 'echo': 2, 'timeout': 0.5, 'avg': 5 },
        'lat_rear': {'type': 'hcsr04', 'board': 0x58, 'trigger': 3, 'echo': 4, 'timeout': 0.5, 'avg': 5 },
        #'center': {'type': 'synth', 'role': 'approach', 'start_value': 762, 'delta-d': 1 },
        #'lat_front': {'type': 'synth', 'role': 'side', 'start_value': 10, 'variance': 10 },
        #'lat_rear': {'type': 'synth', 'role': 'side', 'start_value': 10, 'variance': 10 }
        },
    'bay': {
        # How to range-find the vehicle
        'range': {
            'dist_max': 276, # Maximum range to report at
            'dist_stop': 10, # Distance from the range sensor where the vehicle should stop.
            'sensor': 'center' # Assigned sensor for range finding
            },
        # Lateral alignment zones to check if the vehicle is too far left or right.
        # Will be sorted by intercept range on start-up.
        'lateral': [
            { 'intercept_range': 100, # Distance at which an approaching vehicle should trigger this sensor.
               'dist_ideal': 10, # Ideal lateral distance of the vehicle from this sensor.
               'ok_spread': 1, # Within this distance of the ideal, still report it as good.
               'warn_spread': 3, # More than this distance off the ideal will throw a warning.
               'red_spread': 5, # More than this distance off the ideal will be critical
               'sensor': 'lat_front', # Assigned sensor
               'side': 'L' # Side of the bay the sensor is mounted on, 'L' or 'R'. This is relative to the range sensor.
            },
            { 'intercept_range': 50, # Distance at which an approaching vehicle should trigger this sensor.
              'dist_ideal': 10, # Ideal lateral distance of the vehicle from this sensor.
              'ok_spread': 1, # Within this distance of the ideal, still report it as good.
              'warn_spread': 3, # More than this distance off the ideal will throw a warning.
              'red_spread': 5, # More than this distance off the ideal will be critical
              'sensor': 'lat_rear', # Assigned sensor
              'side': 'L' # Side of the bay the sensor is mounted on, 'L' or 'R'. This is relative to the range sensor.
              }
            ]
    }
}

# Initialize the object.
cb = cobrabay.CobraBay(config)

print("Starting main operating loop")
# Start the main operating loop.
cb.run()
