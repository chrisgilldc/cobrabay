####
# Cobra Bay - Display
# 
# Displays current Bay status on a 64x32 RGB Matrix
####

# Experimental asyncio support so we can keep updating the display while sensors update.
#import asyncio

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
        try: 
            matrix = rgbmatrix.RGBMatrix(
                width=64, height=32, bit_depth=1, 
                rgb_pins=[board.D2, board.D3, board.D4, board.D5, board.D6, board.D7], 
                addr_pins=[board.A0, board.A1, board.A2, board.A3], 
                clock_pin=board.A4, latch_pin=board.D10, output_enable_pin=board.D9)
        except MemoryError:
            raise

        ## Associate the RGB matrix with a Display so that we can use displayio features 
        self.display = framebufferio.FramebufferDisplay(matrix, auto_refresh=True)

        ## load the font
        self.base_font = bitmap_font.load_font('fonts/Interval-Book-18.bdf')
        
        ## Load a smaller font for longer text
        self.small_font = bitmap_font.load_font('fonts/Interval-book-12.bdf')
        
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

    def _DisplayDistance(self,range,range_pct):
        # Create the distance IO group.
        range_group = displayio.Group()

       # Positioning for labels
        label_position = ( 
            floor(self.display.width / 2), # X - Middle of the display
            floor( ( self.display.height - 4 ) / 2) ) # Y - half the height, with space removed for the approach strobe

        # Default label setup. Logic will override these properties if needed.
        approach_label = Label(
                font = self.base_font,
                color = 0x00FF00,
                anchor_point = (0.4,0.5),
                anchored_position = label_position
                )

        # First find cases where the sensor returned None. This indicates an error.
        if range is None :
            approach_label.text = "ERROR"
            approach_label.color = 0xFF0000
            approach_label.anchor_point = (0.5,0.5)
        # If vehicle is beyond range, range will read as 'BR' and range_pct is None (because you can't have a percentage of a string)
        elif range_pct is None and range is 'BR':
            approach_label.color = 0x0000FF # Blue
            approach_label.font = self.small_font # Smaller font to fit the text
            approach_label.text = "APPROACH"
            approach_label.anchor_point = (0.5,0.5) # Anchor in the center
        ## Within 10% of range, red!
        elif range_pct <= 0.10:
            approach_label.color = 0xFF0000
            approach_label.text = self._DistanceLabel(range)
        ## Within 20 % of range, yellow.
        elif range_pct <= 0.20:
            approach_label.color = 0xFFFF00
            approach_label.text = self._DistanceLabel(range)
        ## Range readings in the remaining 80%
        else:
            approach_label.text = self._DistanceLabel(range)

        range_group.append(approach_label)

        return range_group
        
    def _ApproachStrobe(self,range,range_pct):
        approach_strobe = displayio.Group()
        # Available strobing width. Cut in half since we go from both sides, take out pixes for the frames.
        available_width = (self.display.width / 2) - 6
        # If range isn't 'None' (sensor error) or 'BR' (beyond range), then we need to figure the strobe.
        if range not in (None,'BR'):
            # Block the distnace that's been covered.
            bar_blocker = floor(available_width * (1-range_pct))
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

    def _SideIndicators(self,lateral,lateral_num):
        si_group = displayio.Group()
        
        # Assign out the available vertical pixels in a round-robin fashion so each area gets a fair shake.
        area_lengths = [0] * lateral_num
        available_height = self.display.height-2
        candidate_area = 0
        while available_height > 0:
            area_lengths[candidate_area] += 1
            available_height -= 1
            candidate_area += 1
            if candidate_area > len(area_lengths) - 1:
                candidate_area = 0
        
        # Start position of the bar, from the top.
        bar_start = 1
        # Go through each lateral detection zone. These should be ordered from rear to front.
        for index in range(len(lateral)):
            # If it returned the string 'BR', the vehicle has yet to cross this sensor's line of sight, so do nothing.
            if isinstance(lateral[index],str):
                if lateral[index] == 'BR':
                    pass # Append to both left and right.
            # Show Green if we're in the 'spot on' or 'acceptable' deviance statuses.
            elif lateral[index]['status'] <= 1:
                    line_left = Line(1,bar_start,1,bar_start+area_lengths[index]-1,0x00FF00)
                    line_right = Line(self.display.width-2,bar_start,self.display.width-2,bar_start+area_lengths[index]-1,0x00FF00)
                    # if things are spot on, light both sides.
                    if lateral[index]['direction'] is None:
                        si_group.append(line_left)
                        si_group.append(line_right)
                    elif lateral[index]['direction'] is 'L':
                        si_group.append(line_left)
                    elif lateral[index]['direction'] is 'R':
                        si_group.append(line_right)
            elif lateral[index]['status'] == 2:
                    line_left = Line(1,bar_start,1,bar_start+area_lengths[index]-1,0xFFFF00)
                    line_right = Line(self.display.width-2,bar_start,self.display.width-2,bar_start+area_lengths[index]-1,0xFFFF00)
                    # if things are spot on, light both sides.
                    if lateral[index]['direction'] is 'L':
                        si_group.append(line_left)
                    elif lateral[index]['direction'] is 'R':
                        si_group.append(line_right)
            elif lateral[index]['status'] == 3:
                    line_left = Line(1,bar_start,1,bar_start+area_lengths[index]-1,0xFF0000)
                    line_right = Line(self.display.width-2,bar_start,self.display.width-2,bar_start+area_lengths[index]-1,0xFF0000)
                    # if things are spot on, light both sides.
                    if lateral[index]['direction'] is 'L':
                        si_group.append(line_left)
                    elif lateral[index]['direction'] is 'R':
                        si_group.append(line_right)

            # Increment so the next bar starts in the correct place.
            bar_start = bar_start + area_lengths[index]
        return si_group   

    # Draw signal bars with an origin of X,Y
    def _SignalBars(self,strength,origin):
        signalbar_group = displayio.Group()
        
        # Draw a background box.
        #signalbar_group.append(Rect(origin[0],origin[1],5,5,fill=0xFFFFFF))
        
        # Draw the bars.
        i = 1
        while i <= strength:
            bar = Line(origin[0]-1+i,origin[1]+5,origin[0]-1+i,origin[1]+(5-i),0x00FF00)
            signalbar_group.append(bar)
            i += 1
        
        return(signalbar_group)
        
    def _MQTTIcon(self,mqtt_status,origin):
        mqttstatus_group = displayio.Group()
        if mqtt_status:
            color_fill = 0xFFFFFF
            color_fg = 0x00008B
        else:
            color_fill = 0x000000
            color_fg = 0xFF0000
        # Add the background box.    
        #mqttstatus_group.append(Rect(origin[0],origin[1],5,5,fill=color_fill))
        # Draw the letter M.
        ## Left side.
        mqttstatus_group.append(Line(origin[0],origin[1],origin[0],origin[1]+4,color_fg))
        ## Right downstroke
        mqttstatus_group.append(Line(origin[0]+4,origin[1],origin[0]+4,origin[1]+4,color_fg))
        ## Left slant.
        mqttstatus_group.append(Line(origin[0],origin[1],origin[0]+2,origin[1]+2,color_fg))
        ## Right slant
        mqttstatus_group.append(Line(origin[0]+2,origin[1]+2,origin[0]+4,origin[1],color_fg))
        
        # Return it.
        return mqttstatus_group
        
        
    def DisplayIdle(self,system_state):
        master_group = displayio.Group()
        master_group.append(self._SignalBars(system_state['signal_strength'],(59,27)))
        master_group.append(self._MQTTIcon(system_state['mqtt_status'],(0,27)))
        self.display.show(master_group)

    # Update the display from the provided bay state.
    def DisplayDock(self,bay_state):
        # Display group for the output.
        master_group = displayio.Group()
        # Frame is always contstant, so we add this right away.
        master_group.append(self._Frame())
        # Display the strobe based on range. 
        master_group.append(self._ApproachStrobe(bay_state['range'],bay_state['range_pct']))
        # Display the distance.
        master_group.append(self._DisplayDistance(bay_state['range'],bay_state['range_pct']))
        # Display the side indicators
        master_group.append(self._SideIndicators(bay_state['lateral'],bay_state['lateral_num']))
        self.display.show(master_group)
