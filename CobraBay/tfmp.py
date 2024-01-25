#
# TFMini Plus Python Library
# Reworked from Bud Ryerson's TFMini-Plus_python library (https://github.com/budryerson/TFMini-Plus_python/)
#

import importlib
import time
import pint
import serial
from CobraBay.datatypes import TFMP_data

class TFMP:
    ####
    # Class Constants
    ####

    # Buffer sizes
    TFMP_FRAME_SIZE = 9  # Size of one data frame = 9 bytes
    TFMP_COMMAND_MAX = 8  # Longest command = 8 bytes
    TFMP_REPLY_SIZE = 8  # Longest command reply = 8 bytes

    # Timeout Limits for various functions
    TFMP_MAX_READS = 20  # readData() sets SERIAL error
    MAX_BYTES_BEFORE_HEADER = 20  # getData() sets HEADER error
    MAX_ATTEMPTS_TO_MEASURE = 20

    TFMP_DEFAULT_ADDRESS = 0x10  # default I2C slave address
    # as hexadecimal integer
    #
    # System Error Status Condition
    TFMP_READY = 0  # no error
    TFMP_SERIAL = 1  # serial timeout
    TFMP_HEADER = 2  # no header found
    TFMP_CHECKSUM = 3  # checksum doesn't match
    TFMP_TIMEOUT = 4  # I2C timeout
    TFMP_PASS = 5  # reply from some system commands
    TFMP_FAIL = 6  # "
    TFMP_I2CREAD = 7
    TFMP_I2CWRITE = 8
    TFMP_I2CLENGTH = 9
    TFMP_WEAK = 10  # Signal Strength ≤ 100
    TFMP_STRONG = 11  # Signal Strength saturation
    TFMP_FLOOD = 12  # Ambient Light saturation
    TFMP_MEASURE = 13

    # Command Codes
    GET_FIRMWARE_VERSION = 0x00010407  # returns 3 byte firmware version
    TRIGGER_DETECTION = 0x00040400  # frame rate must be set to zero
    # returns a 9 byte data frame
    SOFT_RESET = 0x00020405  # returns a 1 byte pass/fail (0/1)
    HARD_RESET = 0x00100405  # "
    SAVE_SETTINGS = 0x00110405  # This must follow every command
    # that modifies volatile parameters.
    # Returns a 1 byte pass/fail (0/1)

    SET_FRAME_RATE = 0x00030606  # Each of these commands return
    SET_BAUD_RATE = 0x00060808  # an echo of the command
    STANDARD_FORMAT_CM = 0x01050505  # "
    PIXHAWK_FORMAT = 0x02050505  # "
    STANDARD_FORMAT_MM = 0x06050505  # "
    ENABLE_OUTPUT = 0x01070505  # "
    DISABLE_OUTPUT = 0x00070505  # "
    SET_I2C_ADDRESS = 0x100B0505  # "

    SET_SERIAL_MODE = 0x000A0500  # default is Serial (UART)
    SET_I2C_MODE = 0x010A0500  # set device as I2C slave

    I2C_FORMAT_CM = 0x01000500  # returns a 9 byte data frame
    I2C_FORMAT_MM = 0x06000500  # "
    #
    # UART Serial baud rate in Hex.
    BAUD_9600 = 0x002580
    BAUD_14400 = 0x003840
    BAUD_19200 = 0x004B00
    BAUD_56000 = 0x00DAC0
    BAUD_115200 = 0x01C200
    BAUD_460800 = 0x070800
    BAUD_921600 = 0x0E1000

    # Framerate
    FRAME_0 = 0x0000  # internal measurement rate
    FRAME_1 = 0x0001  # expressed in hexadecimal
    FRAME_2 = 0x0002
    FRAME_5 = 0x0005  # set to 0x0003 in prior version
    FRAME_10 = 0x000A
    FRAME_20 = 0x0014
    FRAME_25 = 0x0019
    FRAME_50 = 0x0032
    FRAME_100 = 0x0064
    FRAME_125 = 0x007D
    FRAME_200 = 0x00C8
    FRAME_250 = 0x00FA
    FRAME_500 = 0x01F4
    FRAME_1000 = 0x03E8

    def __init__(self,serial_port="/dev/serial0", baud_rate=115200, unit_system='metric'):
        # Initialize variables.
        self._data_stream = None
        # Store the inputs as internal variables.
        self._serial_port = serial_port
        self._baud_rate = baud_rate
        # If pint is installed, use Quantities
        try:
            importlib.import_module("pint")
        except ImportError:
            # Don't use pint, will return raw numbers.
            self._use_pint = False
        else:
            self._use_pint = True
            # Default us to metric.
            self.unit_system = unit_system
        # Open the port.
        self._open()
        # Great, good to go!

    # Core data fetcher.
    def data(self):
        frames = self._read_frames(self.TFMP_FRAME_SIZE)

        # Convert up the values from the raw bytes.
        dist = (frames[3] * 256) + frames[2]
        flux = (frames[5] * 256) + frames[4]
        temp = (frames[7] * 256) + frames[6]
        temp = (temp >> 3) - 256

        # Check for unusual states and flag those.
        if dist == 65535 or flux < 100:
            status = "Weak"
        elif dist == 65534 or flux == 65535:
            status = "Saturation"
        elif dist == 65532:
            status = "Flood"
        else:
            status = "OK"

        # If we're using pint Quantities, wrap as quantities.
        if self._use_pint:
            if status == "OK":
                dist = pint.Quantity(dist,"cm").to(self._unit_length)
            temp = pint.Quantity(temp, "celsius").to(self._unit_temp)
        return_data = TFMP_data(status, dist, flux, temp)
        return return_data

    # Core command sender. This will send commands and process returns. Commands are then exposed through public
    # methods.
    def _send_cmd(self, command, parameter):
        # Create command data four-byte array
        # Consists of reply length, command length, command data, and one-byte parameter.
        command_data = bytearray(command.to_bytes(self.TFMP_COMMAND_MAX, byteorder='little'))
        print("Initial command data: {}".format(command_data))
        # Pull out the first two bytes to use later.
        reply_length = command_data[0]
        command_length = command_data[1]
        print("Reply length: {}".format(reply_length))
        print("Command length: {}".format(command_length))
        command_data[0] = 0x5A     # Add the header at the beginning

        # A couple commands have multi-byte parameters, so adjust for that if need be.
        if  command == self.SET_FRAME_RATE:
            command_data[3:2] = parameter.to_bytes(2, byteorder='little')
        elif command == self.SET_BAUD_RATE:
            command_data[3:3] = parameter.to_bytes(3, byteorder='little')

        # Calculate a checksum value for everything.
        checksum = 0
        for i in range(command_length - 1):
            checksum += command_data[i]
        # Add the checksum in the final slot in the command
        command_data[command_length - 1] = (checksum & 0xFF)


        # Send the command
        print("Sending Command: b{}".format(command_data))
        # Flush out the serial buffers.
        self._data_stream.reset_input_buffer()
        self._data_stream.reset_output_buffer()
        # Send the command out.
        self._data_stream.write(command_data)

        # If no reply is expected, return true and done.
        if reply_length == 0:
            return True

        # Get reply.
        try:
            reply = self._read_frames_cmd(reply_length)
        except IOError:
            # Failed checksum raises IO error, pass it on.
            raise

        # Properly interpret the results.
        if command == self.GET_FIRMWARE_VERSION:
            return "{}.{}.{}".format(reply[5],reply[4],reply[3])
        else:
            if command in (self.SOFT_RESET, self.HARD_RESET, self.SAVE_SETTINGS):
                if reply[3] == 1:
                    return False
                else:
                    return True


    # Current unit system.
    @property
    def unit_system(self):
        return self._unit_system

    # Change unit system.
    @unit_system.setter
    def unit_system(self, input):
        if input.lower() not in ('metric', 'imperial'):
            raise ValueError("Unit system must be 'metric' or 'imperial'")
        else:
            if input == 'metric':
                self._unit_system = 'metric'
                self._unit_temp = 'celsius'
                self._unit_length = 'cm'
            elif input == 'imperial':
                self._unit_system = 'imperial'
                self._unit_temp = 'fahrenheit'
                self._unit_length = 'in'

    # Open the serial port. If it hasn't been configured yet, set it up.
    def _open(self):
        # If the serial port hasn't been set up yet, create it and open it.
        if self._data_stream is None:
            self._data_stream = serial.Serial(
                self._serial_port,
                self._baud_rate,
                bytesize=8,
                parity=serial.PARITY_NONE,
                stopbits=1)
        else:
            # Otherwise, just open it again.
            self._data_stream.open()

    def _close(self):
        self._data_stream.close()

    # Method to read frames from the serial port. Used by both the data method and the command method.
    def _read_frames(self, length, timeout = 1000):
        #print("Reading TFMP frames...")
        serial_timeout = time.time() + timeout
        #  Flush all but last frame of data from the serial buffer.
        #print("Resetting serial input buffer...")
        ts = time.monotonic_ns()
        while self._data_stream.inWaiting() > self.TFMP_FRAME_SIZE:
            self._data_stream.reset_input_buffer()
        end = time.monotonic_ns() - ts
        #print("Serial input buffer reset in {}ms...".format(end/1000000))
        # Reads data byte by byte from the serial buffer checking for the two header bytes.
        frames = bytearray(length)  # 'frame' data buffer
        while (frames[0] != 0x59) or (frames[1] != 0x59):
            if self._data_stream.inWaiting():
                #  Read 1 byte into the 'frame' plus one position.
                next_byte = self._data_stream.read()[0]
                #print("{}".format(hex(next_byte)), end=" ")
                # frames.append(self._data_stream.read()[0])
                frames.append(next_byte)
                #  Shift entire length of 'frame' one byte left.
                frames = frames[1:]
            #  If no HEADER or serial data not available
            #  after more than one second...
            if time.time() > serial_timeout:
                raise serial.SerialTimeoutException("Sensor did not return header or serial data within one second.")
        #print("")
        # If we haven't raised an exception, checksum the data.
        if not self._checksum(frames):
            raise IOError("Sensor checksum error")
        else:
            return frames

    def _read_frames_cmd(self, length, timeout = 1000):
        '''
        Method to read frames for a command response.

        :param length:
        :param timeout:
        :return:
        '''
        serial_timeout = time.time() + timeout
        #  Flush all but last frame of data from the serial buffer.
        while self._data_stream.inWaiting() > self.TFMP_FRAME_SIZE:
            self._data_stream.read()
        # Reads data byte by byte from the serial buffer checking for the two header bytes.
        frames = bytearray(length)  # 'frame' data buffer
        # Command replies should be '0x5A <RESPONSE LENGTH>'
        print("Reading stream for reply header: 0x51 {}".format(length))
        while (frames[0] != 0x5A) or (frames[1] != length):
            if self._data_stream.inWaiting():
                #  Read 1 byte into the 'frame' plus one position.
                frames.append(self._data_stream.read()[0])
                #  Shift entire length of 'frame' one byte left.
                frames = frames[1:]
                frame_string = ", ".join(hex(b) for b in frames)
                print("Have frames: {}".format(frame_string))
            #  If no HEADER or serial data not available after timeout interval.
            if time.time() > serial_timeout:
                print("\n")
                raise serial.SerialTimeoutException("Sensor did not return header or serial data within one second.")
        print("\nComplete. Have byte array:\n{}\nChecksumming data.".format(frames))

        # If we haven't raised an exception, checksum the data.
        if not self._checksum(frames):
            raise IOError("Sensor checksum error")
        else:
            return frames

    # Destructor.
    def __del__(self):
        if self._data_stream is not None:
            self._data_stream.close()

    # Utility method to calculate checksums.
    @staticmethod
    def _checksum(frames):
        # Checksum starts at 0.
        chksum = 0
        #  Add together all bytes but the last.
        for i in range(len(frames) - 1):
            chksum += frames[i]
        #   If the low order byte does not equal the last byte...
        if (chksum & 0xFF) == frames[len(frames) - 1]:
            return True
        else:
            return False