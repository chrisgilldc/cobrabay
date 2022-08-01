# Simple sensor tester.
from VL53L1X import VL53L1X
import adafruit_aw9523
import board
import busio
import time

from lib.adafruit_hcsr04 import HCSR04

aw = adafruit_aw9523.AW9523(busio.I2C(board.SCL, board.SDA))

options = {
    'vl53_bus_id': 1,
    'vl53_address': 0x29,
    'fl_trigger': 1,
    'fl_echo': 2,
    'rl_trigger': 3,
    'rl_echo': 4
}

# Create sensors!
sensors = {
    'center': VL53L1X(i2c_bus=options['vl53_bus_id'],i2c_address=options['vl53_address']),
    'front': HCSR04(trigger_pin=aw.get_pin(options['fl_trigger']),echo_pin=aw.get_pin(options['fl_echo'])),
    'rear': HCSR04(trigger_pin=aw.get_pin(options['rl_trigger']),echo_pin=aw.get_pin(options['rl_echo']))
}

sensors['center'].open()

while True:
    for sensor in sensors:
        if isinstance(sensors[sensor], VL53L1X):
            sensors[sensor].start_ranging()
            time.sleep(1)
            try:
                distance = sensors[sensor].get_distance()
            except:
                distance = "timeout"
            sensors[sensor].stop_ranging()
            distance = distance * 10

        if isinstance(sensors[sensor], HCSR04):
            try:
                distance = sensors[sensor].distance
            except RuntimeError:
                distance = "timeout"

        print("{},{},{}".format(time.time(),sensor,distance))
        time.sleep(5)