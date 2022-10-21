####
# Cobra Bay - Config Loader
####
import board
import busio
import logging
import yaml
from pathlib import Path
from pprint import PrettyPrinter
from time import sleep

from adafruit_aw9523 import AW9523
from digitalio import DigitalInOut
from adafruit_vl53l1x import VL53L1X


class CBConfig():
    def __init__(self, config_file=None, reset_sensors=False):
        self._logger = logging.getLogger("CobraBay").getChild("Config")
        self._logger.info("Processing config...")

        # Initialize the internal config file variable
        self._config_file = None
        # Default search paths.
        search_paths = [
            Path('/etc/cobrabay/config.yaml'),
            Path.cwd().joinpath('config.yaml')
        ]
        if config_file is not None:
            search_paths.insert(0,Path(config_file))

        for path in search_paths:
            try:
                self.config_file = path
            except:
                pass
        if self._config_file is None:
            raise ValueError("Cannot find valid config file! Attempted: {}".format(search_paths))
        # Load the config file. This does validation as well!
        self.load_config(reset_sensors=reset_sensors)

    def load_config(self,reset_sensors=False):
        pp = PrettyPrinter()
        # Open the current config file and suck it into a staging variable.
        staging_yaml = self._open_yaml(self._config_file)
        # Do a formal validation here? Probably!
        # Should we reset sensors to their defined addresses and validate while loading?
        # This should probably *only* be done during startup.
        if reset_sensors:
            self._reset_sensors(staging_yaml)

        # We're good, so assign the staging to the real config.
        self._config = staging_yaml

    # Scan the configuration, reset VL53L1X sensors to their assigned addresses.
    def _reset_sensors(self,config):
        # Call the method that traverses and shuts off all defined GPIO pins and boards.
        self._gpio_shutoff(config['detectors'])
        # Things should be off, now we can bring things up at the correct address!
        for detector_name in config['detectors']:
            # Is it a single-sensor detector?
            if 'sensor' in config['detectors'][detector_name].keys():
                if config['detectors'][detector_name]['sensor']['type'] == 'VL53L1X':
                    self._set_vl53l1x_addr(
                        i2c_bus=config['detectors'][detector_name]['sensor']['i2c_bus'],
                        i2c_address=config['detectors'][detector_name]['sensor']['i2c_address'],
                        enable_board=config['detectors'][detector_name]['sensor']['enable_board'],
                        enable_pin=config['detectors'][detector_name]['sensor']['enable_pin'],
                    )

    # Set the address for a specific VL53L1X
    @staticmethod
    def _set_vl53l1x_addr(i2c_bus,i2c_address,enable_board,enable_pin):
        i2c = busio.I2C(board.SCL, board.SDA)
        # Get pins directly on the Pi.
        if enable_board == 0:
            enable_pin_name = 'D' + str(enable_pin)
            enable_pin_obj = DigitalInOut(getattr(board, enable_pin_name))
        else:
            # Get pin on a remote AW9523 board
            aw = AW9523(i2c, enable_board, reset=False)
            enable_pin_obj = aw.get_pin(enable_pin)
        # Switch to an output and turn on. This will enable the VL53L1X.
        enable_pin_obj.switch_to_output(value=True)
        # Wait 2s for the device to stabilize
        sleep(1)
        # Create a sensor object that opens up on the default address.
        sensor = VL53L1X(i2c, 0x29)
        print("Using enable pin {} to set device to address {}".format(enable_pin,i2c_address))
        # Open the object.
        sensor.set_address(i2c_address)
        del(sensor)
        del(enable_pin_obj)

    # Shuts off all GPIO pins in the detector config.
    def _gpio_shutoff(self,detectors):
        processed_boards = []
        processed_pins = []
        i2c_bus = busio.I2C(board.SCL, board.SDA)
        for detector_name in detectors:
            self._logger.debug("Checking detector: {}".format(detector_name))
            eb = detectors[detector_name]['sensor']['enable_board']
            # Board "0" is used to mark the Pi. We can't turn off *all* Pi pins, so dig in and check.
            if eb == 0:
                self._logger.debug("Detector uses GPIO pin on-board the Pi.")
                pin_number = detectors[detector_name]['sensor']['enable_pin']
                pin_name = 'D' + str(pin_number)
                pin = DigitalInOut(getattr(board, pin_name))
                pin.switch_to_output(value=False)
                pin.value = False
                processed_pins.append(pin_number)
            # Otherwise, AW9523, so check and access.
            else:
                aw_addr = detectors[detector_name]['sensor']['enable_board']
                if aw_addr in processed_boards:
                    self._logger.debug(
                        "Detector {} uses AW9523 at address {}, already processed.".format(detector_name,
                                                                                           aw_addr))
                    # If this board has already been processed, no need to do it again.
                    break
                # The AW9523 has 16 pins, 0-15, so do them all.
                aw = AW9523(i2c_bus, address=aw_addr)
                for i in range(15):
                    self._logger.debug("Shutting off {}, pin {}".format(aw_addr, i))
                    pin = aw.get_pin(i)
                    pin.switch_to_output(value=False)
                    pin.value = False
                processed_boards.append(aw_addr)
                # Nuke the AW9523 device.
                del (aw)
        # Nuke the I2C Bus object so we don't have conflicts later.
        del (i2c_bus)

    @property
    def config_file(self):
        if self._config_file is None:
            return None
        else:
            return str(self._config_file)

    @config_file.setter
    def config_file(self,input):
        # IF a string, convert to a path.
        if isinstance(input,str):
            input = Path(input)
        if not isinstance(input,Path):
            # If it's not a Path now, we can't use this.
            raise TypeError("Config file must be either a string or a Path object.")
        if not input.is_file():
            raise ValueError("Provided config file {} is not actually a file!".format(input))
        # If we haven't trapped yet, assign it.
        self._config_file = input

    # Method for opening loading a Yaml file and slurping it in.
    @staticmethod
    def _open_yaml(config_path):
        with open(config_path, 'r') as config_file_handle:
                config_yaml = yaml.safe_load(config_file_handle)
        return config_yaml

    def _validate_basic(self):
        pass

    def _validate_general(self):
        pass