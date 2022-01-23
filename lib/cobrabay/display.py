####
# Cobra Bay - Display
# 
# Displays current Bay status on a 64x32 RGB Matrix
####

# Experimental asyncio support so we can keep updating the display while sensors update.
import asyncio

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
        # Pre-set some standard config options. Some of these may get overridden by other options.
        self.config = {
            'global': {
                'units': 'metric' # Default to metric, which is the native for all the sensors.
            },
            'approach_strobe_speed': 100, # Default to 100ms
            'output_multiplier': 1, # Since metric is default, we don't need to modify the range units, since it's natively in centimeters.
            'input_multiplier': 1 # Provided values default to metric, but will be changed to convert inches to cm if needed.
            }
            
        # Merge in the provided values with the defaults.
        self.config.update(config)
        
        # Set unit multiplier if required.
        if self.config['global']['units'] == 'imperial':
            self.config['output_multiplier'] = 0.393701 # 1cm = 0.393701 inches, so we use this as the multiplier for display if in imperial mode.
            self.config['input_multiplier'] = 2.54 # 1in = 2.54cm

        ## Convert approach strobe speed to nanoseconds from milliseconds
        self.config['approach_strobe_speed'] = self.config['approach_strobe_speed'] * 1000000
        
        ## Timer for the approach strobe
        self.timer_approach_strobe = time.monotonic_ns()
        self.approach_strobe_offset = 1

        ## Create an RGB matrix. This is for a 64x32 matrix on a Metro M4 Airlift.
        matrix = rgbmatrix.RGBMatrix(
            width=64, height=32, bit_depth=1, 
            rgb_pins=[board.D2, board.D3, board.D4, board.D5, board.D6, board.D7], 
            addr_pins=[board.A0, board.A1, board.A2, board.A3], 
            clock_pin=board.A4, latch_pin=board.D10, output_enable_pin=board.D9)
            
        ## Associate the RGB matrix with a Display so that we can use displayio features 
        self.display = framebufferio.FramebufferDisplay(matrix, auto_refresh=True)

        ## load the font
        self.base_font = bitmap_font.load_font('fonts/Interval-Book-18.bdf')
 
    # Basic frame for the display
    def _Frame(self):
        frame = displayio.Group()
        # Approach frame
        frame.append(Rect(4,29,56,3,outline=0xFFFFFF))
        #frame.append(Rect(4,29,43,3,outline=0xFFFFFF))
        # Left guidance
        frame.append(Rect(0,0,3,32,outline=0xFFFFFF))
        # Right guidance
        frame.append(Rect(61,0,3,32,outline=0xFFFFFF))
        return frame

    # Utility function to convert distance in centimeters to either Meters or Feet/Inches
    def _DistanceLabel(self,dist_cm):
        if self.config['global']['units'] == 'imperial':
            # Convert cm to inches
            dist_inches = dist_cm * self.config['output_multiplier']
            range_feet = int(dist_inches // 12)
            range_inches = floor(dist_inches % 12)
            label = str(range_feet) + "'" + str(range_inches) + '"'
        else:
            range_meters = round(dist_cm / 100,1)
            label = str(range_meters) + "m"
        return label

    def _DisplayDistance(self):
        # Create the distance IO group.
        range_group = displayio.Group()

       # Positioning for labels
        label_position = ( 
            floor(self.display.width / 2), # X - Middle of the display
            floor( ( self.display.height - 4 ) / 2) ) # Y - half the height, with space removed for the approach strobe

        # Trap cases where there isn't a self.sensors[self.config['bay']['range']['sensor']]
        if self.config['bay']['range']['sensor'] not in self.sensor_values:
            approach_label = Label(
                font=self.base_font,
                text="ERROR",
                color=0xFF0000,
                anchor_point = (0.5,0.5),
                anchored_position = label_position
                )
            range_group.append(approach_label)
            return range_group
            
        # Didn't trap, proceed.
        
        # Adjust the provided range down by the parking distance. This will let us display the distance to the stopping point, not the sensor!
        stop_range = self.sensor_values[self.config['bay']['range']['sensor']] - self.config['bay']['range']['dist_stop']
        
        # Don't let range be negative. May be more logic later to do additional warnings.
        if stop_range < 0:
            stop_range = 0
        
        # Figure out distance-based values.
        if stop_range <= 30:
            range_color = 0xFF0000
            range_text = self._DistanceLabel(stop_range)
            anchor = (0.4,0.5)
        elif stop_range <= 121:
            range_color = 0xFFFF00
            range_text = self._DistanceLabel(stop_range)
            anchor = (0.4,0.5)
        elif stop_range > self.config['bay']['range']['dist_max']:
            range_color = 0x0000FF
            range_text = "APPROACH"
            anchor = (0.5,0.5)
        else:
            range_color = 0x00FF00
            range_text = self._DistanceLabel(stop_range)
            anchor = (0.4,0.5)

        # Build the approach label, add it to the group and return it.
        approach_label = Label(
            font=self.base_font,
            text=range_text,
            color=range_color,
            anchor_point = anchor,
            anchored_position = label_position
            )
        range_group.append(approach_label)

        return range_group
        
    def _ApproachStrobe(self,):
        approach_strobe = displayio.Group()
        # Portion of the bar to be static. Based on percent distance to parked.
        available_width = (self.display.width / 2) - 6
        # Are we in range and do we need a strobe?
        if self.sensor_values[self.config['bay']['range']['sensor']] < self.config['bay']['range']['dist_max']:
            # Compare tracking range to current range
            bar_blocker = floor(available_width * (1-( self.sensor_values[self.config['bay']['range']['sensor']] / self.config['bay']['range']['dist_max'] )))
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

    def _SideIndicators(self):
        si_group = displayio.Group()
        vert_start = 30 # Where on the display to start.
        # Go through each lateral detection zone. These should be ordered from rear to front.
        
        for index in range(len(self.config['bay']['lateral'])):
            # If the main range sensor says the vehicle is close enough, start paying attention to this sensor.
            if self.sensor_values[self.config['bay']['range']['sensor']] <= self.config['bay']['lateral'][index]['intercept_range']:
                # Get the distance of the vehicle from the lateral sensor.
                try:
                    lat_position = self.sensor_values[self.config['bay']['lateral'][index]['sensor']]
                    print("Got lateral position: " + str(lat_position))
                except KeyError:
                    # If the sensor isn't reporting, we change it to a None and mark it as a non-reporting cycle
                    lat_position = None
                    self.lateral_status[index]['cycles'] += 1
                else:
                    # Set the cycles for this sensor back to zero.
                    self.lateral_status[index]['cycles'] = 0
                    # Determine the deviance side and magnitude based on this sensor report.
                    position_deviance = lat_position - self.config['bay']['lateral'][index]['dist_ideal']
                    print("Position deviance: " + str(position_deviance))
                    if position_deviance == 0:
                        deviance_side = None
                    # Deviance away from the sensor.
                    elif position_deviance > 0:
                        if self.config['bay']['lateral'][index]['side'] == 'P':
                            deviance_side = 'P'
                        else:
                            deviance_side = 'D'
                    # Deviance towards the sensor.
                    elif position_deviance < 0:
                        if self.config['bay']['lateral'][index]['side'] == 'D':
                            deviance_side = 'D'
                        else:
                            deviance_side = 'P'
                    print("Deviance side: " + str(deviance_side))

                    # How big is the deviance and how is it displayed.
                    # Within the 'dead zone', no report is given, it's treated as being spot on.
                    if abs(position_deviance) <= self.config['bay']['lateral'][index]['ok_spread']:
                        self.lateral_status[index]['deviance_side'] = 0
                    # Between the dead zone and the warning zone, we show white, an indicator but nothing serious.
                    elif self.config['bay']['lateral'][index]['ok_spread'] < abs(position_deviance) < self.config['bay']['lateral'][index]['warn_spread']:
                        self.lateral_status[index]['deviance_side'] = 1
                    # Way off, huge warning.
                    elif abs(position_deviance) >= self.config['bay']['lateral'][index]['red_spread']:
                        self.lateral_status[index]['deviance_side'] = 3
                    # Notably off, warn yellow.
                    elif abs(position_deviance) >= self.config['bay']['lateral'][index]['warn_spread']:
                        self.lateral_status[index]['deviance_side'] = 2
                        
                    print("Lateral status: " + str(self.lateral_status[index]['deviance_side']))

            else:
                # Remove the length of this indicator so it doesn't get used.
                vert_start = vert_start - self.config['bay']['lateral'][index]['indicator_length']


        return si_group   

    async def UpdateDisplay(self,sensor_values):
        self.sensor_values.update(sensor_values)
        master_group = displayio.Group()
        master_group.append(self._Frame())
        master_group.append(self._SideIndicators())
        #master_group.append(self._ApproachStrobe())
        master_group.append(self._DisplayDistance())
        self.display.show(master_group)
        await asyncio.sleep(0)
