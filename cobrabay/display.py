####
# Cobra Bay - Display
# 
# Displays current Bay status on a 64x32 RGB Matrix
####

import board
from displayio import release_displays, Group
from framebufferio import FramebufferDisplay
from rgbmatrix import RGBMatrix
from time import monotonic_ns
from adafruit_display_shapes.rect import Rect
from adafruit_display_shapes.line import Line
# from adafruit_display_text.label import Label
from adafruit_display_text.bitmap_label import Label
from adafruit_bitmap_font import bitmap_font
import adafruit_logging as logging
from math import floor
# from unit import Unit
from unit import NaN
from gc import mem_free, collect


class Display:
    def __init__(self, config):
        self._logger = logging.getLogger('cobrabay')
        self._logger.debug("Memory at display init: {}".format(mem_free()))
        # Release any existing displays. Shouldn't be necessary during normal operations.

        release_displays()
        # Set up an internal dict for storing validated and processed config
        # Pre-set some standard config options. Some of these may get overridden by other options.
        self.config = {
            'global': {
                'units': 'metric'  # Default to metric, which is the native for all the sensors.
            },
            'approach_strobe_speed': 100,  # Default to 100ms
            'output_multiplier': 1,  # Metric is default, no multiplier needed by default.
            'input_multiplier': 1  # Metric is default, no multiplier needed by default.
            }
            
        # Merge in the provided values with the defaults.
        self.config.update(config)

        # Convert approach strobe speed to nanoseconds from milliseconds
        self.config['approach_strobe_speed'] = self.config['approach_strobe_speed'] * 1000000
        
        # Timer for the approach strobe
        self.timer_approach_strobe = monotonic_ns()
        self.approach_strobe_offset = 1

        self._logger.info("Creating matrix...")
        collect()
        # Create an RGB matrix. This is for a 64x32 matrix on a Metro M4 Airlift.
        #try:
        matrix = RGBMatrix(
            width=64, height=32, bit_depth=1,
            rgb_pins=[board.D2, board.D3, board.D4, board.D5, board.D6, board.D7],
            addr_pins=[board.A0, board.A1, board.A2, board.A3],
            clock_pin=board.A4, latch_pin=board.D10, output_enable_pin=board.D9)
        # except MemoryError:
        #     raise

        self._logger.info("Attaching matrix to framebuffer")
        # Associate the RGB matrix with a Display so that we can use displayio features 
        self.display = FramebufferDisplay(matrix, auto_refresh=True)

        self._logger.debug("Memory before loading base font: {}".format(mem_free()))
        # load the font
        self.base_font = bitmap_font.load_font('fonts/Interval-Book-18.bdf')
        self._logger.debug("Memory after loading base font: {}".format(mem_free()))

        self.small_font = bitmap_font.load_font('fonts/Interval-Book-12.bdf')
        self._logger.debug("Memory after loading small font: {}".format(mem_free()))

    # Basic frame for the display
    @staticmethod
    def _frame():
        frame = Group()
        # Approach frame
        frame.append(Rect(4, 29, 56, 3, outline=0xFFFFFF))
        # Left guidance
        frame.append(Rect(0, 0, 3, 32, outline=0xFFFFFF))
        # Right guidance
        frame.append(Rect(61, 0, 3, 32, outline=0xFFFFFF))
        return frame

    def _distance_display(self, range, range_pct):
        # Create the distance IO group.
        range_group = Group()

        # print("Display input:\n\tRange: {}\n\tRange Pct: {}".format(range,range_pct))

        # Positioning for labels
        label_position = ( 
            floor(self.display.width / 2),  # X - Middle of the display
            floor((self.display.height - 4) / 2))  # Y - half the height, with space removed for the approach strobe

        # Default label setup. Logic will override these properties if needed.
        approach_label = Label(
                font=self.base_font,
                color=0x00FF00,
                anchor_point=(0.4, 0.5),
                anchored_position=label_position
                )

        # If Range isn't a number, there's two options.
        if isinstance(range, NaN):
            # If the NaN reason is "Beyond range", throw up the "Approach" text
            if range.reason == 'Beyond range':
                approach_label.color = 0x0000FF  # Blue
                approach_label.text = "CLOSE"
                approach_label.anchor_point = (0.5, 0.5)  # Anchor in the center
                #approach_label.font = self.small_font
            # Any other NaN indicates an error.
            else:
                approach_label.text = "ERROR"
                approach_label.color = 0xFF0000
                approach_label.anchor_point = (0.5, 0.5)
        elif range.value <= 1:
            if range.value < 0 and abs(range.value) > 2:
                approach_label.text="BACK-UP"
                approach_label.color = 0xFF0000
            else:
                approach_label.text = "STOP!"
                approach_label.color = 0xFF0000
        else:
            # Determine what to use for range output.
            if self.config['global']['units'] == 'imperial':
                # For Imperial (ie: US) users, output as prime-notation Feet and Inches.
                approach_label.text = range.asftin('prime')
            else:
                # For Metric (ie: Reasonable countries) users, output as decimal meters
                approach_label.text = str(range.convert("m"))
            # If under 20% of total distance, color the text differently.
            # Within 10% of range, orange
            if range_pct <= 0.10:
                approach_label.color = 0xFF9933
            # Within 20 % of range, yellow.
            elif range_pct <= 0.20:
                approach_label.color = 0xFFFF00
        range_group.append(approach_label)

        return range_group
        
    def _approach_strobe(self, range, range_pct):
        approach_strobe = Group()
        # Available strobing width. Cut in half since we go from both sides, take out pixes for the frames.
        available_width = (self.display.width / 2) - 6
        # If range isn't 'None' (sensor error) or 'BR' (beyond range), then we need to figure the strobe.
        if not isinstance(range, NaN):
            # Block the distance that's been covered.
            bar_blocker = floor(available_width * (1-range_pct))
            # Left
            approach_strobe.append(Line(5, 30, 5+bar_blocker, 30, 0xFFFFFF))
            # Right
            approach_strobe.append(Line(58, 30, 58-bar_blocker, 30, 0xFFFFFF))
            # Strober.
            if monotonic_ns() - self.timer_approach_strobe >= self.config['approach_strobe_speed']:
                if self.approach_strobe_offset > (available_width - bar_blocker)-1:
                    self.approach_strobe_offset = 1
                else:
                    self.approach_strobe_offset = self.approach_strobe_offset + 1
                self.timer_approach_strobe = monotonic_ns()
                
            # Draw dots based on the offset.
            approach_strobe.append(
                Line(
                    6+bar_blocker+self.approach_strobe_offset, 30,
                    6+bar_blocker+self.approach_strobe_offset+1, 30, 0xFF0000)
                    )
            approach_strobe.append(
                Line(
                    58-bar_blocker-self.approach_strobe_offset, 30,
                    58-bar_blocker-self.approach_strobe_offset-1, 30, 0xFF0000)
                    )
        return approach_strobe

    def _side_indicators(self, lateral, lateral_num):
        si_group = Group()
        
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
            if isinstance(lateral[index], str):
                if lateral[index] == 'BR':
                    pass  # Append to both left and right.
            # Show Green if we're in the 'spot on' or 'acceptable' deviance statuses.
            elif lateral[index]['status'] <= 1:
                line_left = Line(1, bar_start, 1, bar_start+area_lengths[index]-1, 0x00FF00)
                line_right = Line(self.display.width-2, bar_start, self.display.width-2,
                                  bar_start+area_lengths[index]-1, 0x00FF00)
                # if things are spot on, light both sides.
                if lateral[index]['direction'] is None:
                    si_group.append(line_left)
                    si_group.append(line_right)
                # If left, light left.
                elif lateral[index]['direction'] is 'L':
                    si_group.append(line_left)
                # If right, light right.
                elif lateral[index]['direction'] is 'R':
                    si_group.append(line_right)
            elif lateral[index]['status'] == 2:
                line_left = Line(1, bar_start, 1, bar_start+area_lengths[index]-1, 0xFFFF00)
                line_right = Line(self.display.width-2, bar_start, self.display.width-2,
                                  bar_start+area_lengths[index]-1, 0xFFFF00)
                if lateral[index]['direction'] is 'L':
                    si_group.append(line_left)
                elif lateral[index]['direction'] is 'R':
                    si_group.append(line_right)
            elif lateral[index]['status'] == 3:
                line_left = Line(1, bar_start, 1, bar_start+area_lengths[index]-1, 0xFF0000)
                line_right = Line(self.display.width-2, bar_start, self.display.width-2,
                                  bar_start+area_lengths[index]-1, 0xFF0000)
                # if things are spot on, light both sides.
                if lateral[index]['direction'] is 'L':
                    si_group.append(line_left)
                elif lateral[index]['direction'] is 'R':
                    si_group.append(line_right)

            # Increment so the next bar starts in the correct place.
            bar_start = bar_start + area_lengths[index]
        return si_group   

    # Draw signal bars with an origin of X,Y
    @staticmethod
    def _signal_bars(strength, origin):
        signalbar_group = Group()
        
        # Draw a background box.
        # signalbar_group.append(Rect(origin[0],origin[1],5,5,fill=0xFFFFFF))
        
        # Draw the bars.
        i = 1
        while i <= strength:
            bar = Line(origin[0]-1+i, origin[1]+5, origin[0]-1+i, origin[1]+(5-i), 0x00FF00)
            signalbar_group.append(bar)
            i += 1
        
        return signalbar_group

    # Show the MQTT connection status icon.
    @staticmethod
    def _mqtt_icon(mqtt_status, origin):
        mqttstatus_group = Group()
        if mqtt_status:
            # color_fill = 0xFFFFFF
            color_fg = 0x00008B
        else:
            # color_fill = 0x000000
            color_fg = 0xFF0000
        # Add the background box.    
        # mqttstatus_group.append(Rect(origin[0],origin[1],5,5,fill=color_fill))
        # Draw the letter M.
        # Left side.
        mqttstatus_group.append(Line(origin[0], origin[1], origin[0], origin[1]+4, color_fg))
        # Right side
        mqttstatus_group.append(Line(origin[0]+4, origin[1], origin[0]+4, origin[1]+4, color_fg))
        # Left slant.
        mqttstatus_group.append(Line(origin[0], origin[1], origin[0]+2, origin[1]+2, color_fg))
        # Right slant
        mqttstatus_group.append(Line(origin[0]+2, origin[1]+2, origin[0]+4, origin[1], color_fg))
        
        # Return it.
        return mqttstatus_group

    # Display state icons, and optionally a single sensor.
    def display_generic(self, system_state, sensor=None):
        master_group = Group()
        if sensor is not None:
            master_group.append(
                Label(
                    font=self.base_font,
                    color=0xFFFFFF,
                    anchor_point=(0.4, 0.5),
                    anchored_position=(floor(self.display.width / 2), floor((self.display.height - 4) / 2))
                    # text=self._distance_label(sensor)
                )
            )
        master_group.append(self._signal_bars(system_state['signal_strength'], (59, 27)))
        master_group.append(self._mqtt_icon(system_state['mqtt_status'], (0, 27)))
        self.display.show(master_group)

    # Update the display from the provided bay state.
    def display_dock(self, bay_state):
        self._logger.debug("Display,1 - Start,{}".format(mem_free()))
        # Display group for the output.
        master_group = Group()
        self._logger.debug("Display,2 - Group Creation,{}".format(mem_free()))
        # Frame is always constant, so we add this right away.
        master_group.append(self._frame())
        self._logger.debug("Display,3 - Frame Created,{}".format(mem_free()))
        # Display the strobe based on range. 
        master_group.append(self._approach_strobe(bay_state['range'], bay_state['range_pct']))
        self._logger.debug("Display,4 - Strobe Created,{}".format(mem_free()))
        # Display the distance.
        master_group.append(self._distance_display(bay_state['range'], bay_state['range_pct']))
        self._logger.debug("Display,3 - Distance Created,{}".format(mem_free()))
        # Display the side indicators
        master_group.append(self._side_indicators(bay_state['lateral'], bay_state['lateral_num']))
        self._logger.debug("Display,4 - Side indicators created,{}".format(mem_free()))
        self.display.show(master_group)
        self._logger.debug("Display,5 - Send to display,{}".format(mem_free()))