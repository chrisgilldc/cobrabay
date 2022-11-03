import board
import busio
from adafruit_vl53l1x import VL53L1X
import time
from pint import Quantity
from statistics import mean

test_time = "5 minutes"
sensor_address = 0x30
timing_budget = 200

####
# Nothing to change down here.
####

# Set up I2C Access
i2c = busio.I2C(board.SCL, board.SDA)

# Create the sensor.
sensor = VL53L1X(i2c, sensor_address)
sensor.timing_budget = timing_budget
sensor.start_ranging()

# Convert test time into seconds
test_time = Quantity(test_time).to('seconds').magnitude
test_start = time.monotonic()

readings = []

while time.monotonic() - test_start < test_time:
    reading = sensor.distance
    print("Read: {}".format(reading))
    readings.append(reading)
    time.sleep(timing_budget/1000)

print("All readings: {}".format(readings))
reading_avg = mean(readings)
reading_min = min(readings)
reading_max = max(readings)
print("Reading stats\n\tMin: {}\tMax: {}\tMean: {}".format(reading_min, reading_max, reading_avg))
