####
# Cobra Bay Display
####


import board, digitalio, displayio, framebufferio, rgbmatrix, sys, time, terminalio 
from adafruit_display_shapes.rect import Rect
from adafruit_display_shapes.line import Line
from adafruit_display_text.label import Label
from adafruit_bitmap_font import bitmap_font
from adafruit_display_text import bitmap_label
from math import floor, ceil

class Display():
    def __init__(self,config):
        # Release any existing displays. Shouldn't be necessary during normal operations.
        displayio.release_displays()
        # Set up an internal dict for storing validated and processed config
        # Pre-loaded with defaults for optional parameters.
        self.config = {
            'approach_strobe_speed': 100, # Default to 100ms
            'units': 'metric', # Default to metric, which is the native
            'range_multiplier': 1, # Since metric is default, we don't need to modify the range units, since it's natively in centimeters.
            }
        
        # Set up variables from the input configuration
        ## Maximum detection range
        try:
            self.config['max_detect_range'] = config['max_detect_range']
        except:
            print("Maximum detect range must be configured.")
            sys.exit(1)
        
        # Try to pull over values from the config array. If present, they'll overwrite the default. If not, the default stands.
        for config_value in ('speed_limit','approach_strobe_speed'):
            try:
                self.config[config_value] = config[config_value]
            except:
                pass
        
        ## Convert approach strobe speed to nanoseconds from milliseconds
        self.config['approach_strobe_speed'] = self.config['approach_strobe_speed'] * 1000000
        
        # If set to imperial units, set the appropriate range multiplier to convert
        # the HC-SR04's native cm output to inches
        try:
            if config['units'] == 'imperial':
                self.config['units'] = 'imperial'
                self.config['range_multiplier'] = 0.393701
                self.config['speed_multiplier'] = 0.022369
        except:
            self.config['units'] = 'metric'
            self.config['range_multiplier'] = 1
            self.config['speed_multiplier'] = 0.036

        ## Timer for the approach strobe
        self.timer_approach_strobe = time.monotonic_ns()
        self.approach_strobe_offset = 1
        ## Time the process started, used to simulate approaches.
        self.start_time= time.time()

        ## Create an RGB matrix. This is for a 64x32 matrix on a Metro M4 Airlift.
        matrix = rgbmatrix.RGBMatrix(
            width=64, height=32, bit_depth=1, 
            rgb_pins=[board.D2, board.D3, board.D4, board.D5, board.D6, board.D7], 
            addr_pins=[board.A0, board.A1, board.A2, board.A3], 
            clock_pin=board.A4, latch_pin=board.D10, output_enable_pin=board.D9)
            
        ## Associate the RGB matrix with a Display so that we can use displayio features 
        self.display = framebufferio.FramebufferDisplay(matrix, auto_refresh=True)
        
        ## load the fonts
        self.base_font = {
            '18': bitmap_font.load_font('fonts/Interval-Book-18.bdf'),
            '12': bitmap_font.load_font('fonts/Interval-Book-12.bdf'),
            '8': bitmap_font.load_font('fonts/Interval-Book-8.bdf'),
            }

    # Basic frame for the display
    def _Frame(self):
        frame = displayio.Group()
        # Approach frame
        frame.append(Rect(4,29,56,3,outline=0xFFFFFF))
        # Left guidance
        frame.append(Rect(0,0,3,32,outline=0xFFFFFF))
        # Right guidance
        frame.append(Rect(61,0,3,32,outline=0xFFFFFF))  
        return frame

    # Utility function to convert distance in centimeters to either Meters/Centimeters or Feet/Inches
    def _DistanceLabel(self,dist_cm,units):
        if units == 'imperial':
            # Convert cm to inches
            dist_inches = dist_cm * 0.393701
            range_feet = int(dist_inches // 12)
            range_inches = floor(dist_inches % 12)
            label = str(range_feet) + "'" + str(range_inches) + '"'
        else:
            range_meters = dist_cm / 100
            label = str(range_meters) + "m"
        return label

    def _DisplayDistance(self,center_range):
        # Positioning for labels
        label_position = ( 
            floor(self.display.width / 2), # X - Middle of the display
            floor( ( self.display.height - 4 ) / 2) ) # Y - half the height, with space removed for the approach strobe
        
        # Figure out proper coloring
        if center_range <= 30:
            range_color = 0xFF0000
        elif center_range <= 121:
            range_color = 0xFFFF00
        elif center_range > self.config['max_detect_range']:
            range_color = 0x0000FF
        else:
            range_color = 0x00FF00

        # Decide which to display.
        
        range_group = displayio.Group()
        
        if center_range >= self.config['max_detect_range']:
            approach_label = Label(
                font=self.base_font['12'],
                text="APPROACH",
                color=range_color,
                anchor_point = (0.5,0.5),
                anchored_position = label_position
                )
            range_group.append(approach_label)
        else:
            # distance label
            range_label = Label(
                font=self.base_font['18'],
                text=self._DistanceLabel(center_range,self.config['units']),
                color=range_color,
                anchor_point = (0.4,0.5),
                anchored_position = label_position
                )
            range_group.append(range_label)

        return range_group
        
    def _ApproachStrobe(self,center_range):
        approach_strobe = displayio.Group()
        # Portion of the bar to be static. Based on percent distance to parked.
        available_width = (self.display.width / 2) - 6
        # Are we in range and do we need a strobe?
        if center_range < self.config['max_detect_range']:
            # Compare tracking range to current range
            bar_blocker = floor(available_width * (1-( center_range / self.config['max_detect_range'] )))
            ## Left
            approach_strobe.append(Line(5,30,5+bar_blocker,30,0xFFFFFF))
            ## Right
            approach_strobe.append(Line(58,30,58-bar_blocker,30,0xFFFFFF))
            # Strober.
            if  time.monotonic_ns() - self.timer_approach_strobe >= self.config['approach_strobe_speed']:
                if self.approach_strobe_offset > (available_width - bar_blocker)-1:
                    self.approach_strobe_offset = 1
                else:
                    self.approach_strobe_offset = self.approach_strobe_offset + 1
                self.timer_approach_strobe = time.monotonic_ns()
                
            # Draw dots based on the offset.
            approach_strobe.append(
                Line(
                    6+bar_blocker+self.approach_strobe_offset,30,
                    6+bar_blocker+self.approach_strobe_offset+1,30,0xFF0000)
                    )
            approach_strobe.append(
                Line(
                    58-bar_blocker-self.approach_strobe_offset,30,
                    58-bar_blocker-self.approach_strobe_offset-1,30,0xFF0000)
                    )
        return approach_strobe
        
    def UpdateDisplay(self,sensor_values):
        print("New sensor values:")
        print(sensor_values)
        # Assemble the groups
        master_group = displayio.Group()
        master_group.append(self._Frame())
        master_group.append(self._ApproachStrobe(sensor_values['center']))
        master_group.append(self._DisplayDistance(sensor_values['center']))
        self.display.show(master_group)
