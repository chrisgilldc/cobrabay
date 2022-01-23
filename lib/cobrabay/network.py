####
# Cobra Bay - Network
#
# Connects to the network to report bay status and take basic start/stop commands.
####

import board
import busio
from digitalio import DigitalInOut
#import adafruit_requests as requests
import adafruit_esp32spi.adafruit_esp32spi_socket as socket
from asafruit_esp32spi import adafruit_esp32spi

class Network:
    def __init__(self,config):
        try:
            from secrets import secrets
        except ImportError:
            print("Wifi secrets are kept in secrets.py, please add them there!")
            raise
        
        # Set up the on-board ESP32 pins. These are correct for the M4 Airlift. Check library reference for others.
        esp32_cs = DigitalInOut(board.ESP_CS)
        esp32_ready = DigitalInOut(board.ESP_BUSY)
        esp32_reset = DigitalInOut(board.ESP_RESET)
        
        # Create ESP object
        spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
        self.esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)
        
        if self.esp.status == adafruit_esp32spi.WL_IDLE_STATUS:
            print("ESP32 found and in idle mode")
            print("Firmware version", esp.firmware_version)
            print("MAC address:",[hes(i) for i in esp.MAC_address])
            
        # List available APs
        for ap in esp.scan_networks():
            print("\t%s\t\tRSSI: %d" % (str(ap["ssid"], "utf-8"), ap["rssi"]))