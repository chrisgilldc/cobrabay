#!/usr/bin/python3

import board
import busio
from digitalio import DigitalInOut
from adafruit_aw9523 import AW9523
from VL53L1X import VL53L1X
import time
from io import StringIO
import sys
import subprocess

def show_i2c():
	result = subprocess.run(["/usr/sbin/i2cdetect","-y","1"],stdout=subprocess.PIPE)
	return result.stdout.decode('utf-8')

print("Initial I2C State:\n")
print(show_i2c())

# Set up the i2c bus
i2c = busio.I2C(board.SCL, board.SDA)

# Board 1 is directly on the Pi.
board1_pin = DigitalInOut(board.D25)
# Boards on the AW9523
gpio_board = AW9523(i2c)
board2_pin = gpio_board.get_pin(2)
board3_pin = gpio_board.get_pin(3)
board4_pin = gpio_board.get_pin(1)

# Set the pins to output
#board1_pin.switch_to_output(value=False)
board1_pin.switch_to_output(value=False)
board2_pin.switch_to_output(value=False)
#board3_pin.switch_to_output(value=False)

print("All boards have pins created and shut off. New I2C bus scan:")
print(show_i2c())

tgt_addr = [0x30, 0x31, 0x32, 0x33]
pins = [board1_pin, board2_pin, board3_pin, board4_pin]

i=0
while i < len(tgt_addr):
	print("Enabling board {}".format(i+1))
	print("Existing value: {}".format(pins[i].value))
	pins[i].value = True
	print("New value: {}".format(pins[i].value))
	print("I2C Scan after board enable:")
	print(show_i2c())
	sensor = VL53L1X(i2c_bus=1, i2c_address=0x29)
	sensor.open()
	sensor.change_address(tgt_addr[i])
#	sensor.close()

	print("Sensor readdressed. I2C Scan below.")
#  Pausing for 5s.")
	print(show_i2c())
	#time.sleep(2)
	#sensor.start_ranging()
	#range = sensor.get_distance()
	#print("Reading range: {} mm".format(range))
#	time.sleep(5)
#	pins[i].value = False
#	print("Sensor shut off.")
	input("Press enter to continue...")
	i += 1

# Re-enable all pins
for pin in pins:
	pin.value = True
