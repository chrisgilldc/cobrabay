####
# Cobra Bay - Display
# 
# Displays current Bay status on a 64x32 RGB Matrix
####

import logging
from time import monotonic_ns
from math import floor
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
from .nan import NaN
from pint import UnitRegistry, Quantity

ureg = UnitRegistry()

class Display:
    def __init__(self, config):
        # self._logger = logging.getLogger('cobrabay').getChild("display")
        self._logger = logging.getLogger('display-test')
        console_handler = logging.StreamHandler()
        self._logger.addHandler(console_handler)

        # Set up an internal dict for storing validated and processed config
        # Pre-set some standard config options. Some of these may get overridden by other options.
        self.config = {
            'global': {
                'units': 'metric'  # Default to metric, which is the native for all the sensors.
            },
            'approach_strobe_speed': 100,  # Default to 100ms
            }
            
        # Merge in the provided values with the defaults.
        self.config.update(config)

        # Convert approach strobe speed to nanoseconds from milliseconds
        self.config['approach_strobe_speed'] = self.config['approach_strobe_speed'] * 1000000
        
        # Timer for the approach strobe
        self.timer_approach_strobe = monotonic_ns()
        # Initialize the approach strobe offset. This needs to get kept from cycle to cycle.
        self._approach_strobe_offset = 0
        
        self._logger.info("Creating matrix...")
        # Create a matrix. This is hard-coded for now.
        matrix_options = RGBMatrixOptions()
        matrix_options.rows = 32
        matrix_options.cols = 64
        matrix_options.chain_length = 1
        matrix_options.parallel = 1
        matrix_options.hardware_mapping = 'adafruit-hat-pwm'
        matrix_options.disable_hardware_pulsing = True
        matrix_options.gpio_slowdown = 4
        self.matrix = RGBMatrix(options=matrix_options)

        # load the fonts
        self._font_dir = 'fonts'
        self._base_font = 'Interval-Book'
        self._font_sizes = [18,12,8]
        self.font = graphics.Font()
        self.font.LoadFont('fonts/Interval-Book-12.bdf')

        # Convenient dict for colors.
        self._colors = {
            'black': graphics.Color(0, 0, 0),
            'white': graphics.Color(255, 255, 255),
            'green': graphics.Color(0, 255, 0),
            'red': graphics.Color(255, 0, 0),
            'darkblue': graphics.Color(0, 0, 139),
            'orange': graphics.Color(255,153, 51),
            'yellow': graphics.Color(255,255, 0)
        }

        self._staging_canvas = self.matrix.CreateFrameCanvas()

    # Basic frame for the display
    def _frame(self,canvas):
        # Left approach box
        self._draw_box(canvas, 0, 0, 2, canvas.height-5, self._colors['white'])
        # Right approach box
        self._draw_box(canvas, canvas.width-3, 0, canvas.width-1, canvas.height-5, self._colors['white'])
        # Approach strobe box
        self._draw_box(canvas, 0, canvas.height-3, canvas.width-1, canvas.height-1, self._colors['white'])
        # Return the canvas for additional additions.
        return canvas

    # Utility method to make drawing boxes easier.
    def _draw_box(self, canvas, x1, y1, x2, y2, color=None):
        if color is None:
            color = graphics.Color(255, 255, 255)
        # Top line
        graphics.DrawLine(canvas, x1, y1, x2, y1, color)
        # Left side
        graphics.DrawLine(canvas, x1, y1, x1, y2, color)
        # Right side
        graphics.DrawLine(canvas, x2, y1, x2, y2, color)
        # Bottom
        graphics.DrawLine(canvas, x1, y2, x2, y2, color)
        # Send the canvas back.
        return canvas

    def _distance_display(self, canvas, range, range_pct):
        print("Range value: {}".format(range))
        # If Range isn't a number, there's two options.
        if isinstance(range, NaN):
            # If the NaN reason is "Beyond range", throw up the "Approach" text
            if range.reason == 'Beyond range':
                text = "APPROACH"
                text_color = self._colors['darkblue']
            # Any other NaN indicates an error.
            else:
                text = "ERROR"
                text_color = self._colors['red']
        elif range <= Quantity("1 inch"):
                text = "STOP!"
                text_color = self._colors['red']
        elif range < Quantity("-1 inch"):
                text = "BACK-UP"
                text_color = 0xFF0000
        else:
            # Determine what to use for range output.
            if self.config['global']['units'] == 'imperial':
                # For Imperial (ie: US) users, output as prime-notation Feet and Inches.
                text = self._ft_in(range)
            else:
                # For Metric (ie: Reasonable countries) users, output as decimal meters
                text = str(range.to("meters"))
            # Within 10% of range, orange
            if range_pct <= 0.10:
                print("Should be text color orange")
                text_color = self._colors['orange']
            # Within 20 % of range, yellow.
            elif range_pct <= 0.20:
                print("Should be text color yellow.")
                text_color = self._colors['yellow']
            else:
                print("Should be text color white")
                text_color = self._colors['white']
        print("Text color variable: {}".format(text_color))
        # Scale the font based on the available space and size.
        # text = "TESTING!"
        # text_color = self._colors['darkblue']
        selected_font = self._fit_string(text,self.matrix.width-8)
        # Alignment variables to determine the proper lower-left corner of the string.
        # Align vertically, based on canvas height with space removed for the lower strobe bar.
        x_start = 4 + ((canvas.width - 8)  / 2) - (self._string_width(text, selected_font) / 2)
        y_start = canvas.height - 4 - ((canvas.height-4)/2) + (selected_font.height/2)
        # x_start = 10
        # y_start = 15
        # # Add the string to the canvas, then return it.
        # print("Canvas size X:{}, Y:{}".format(canvas.width,canvas.height))
        # print("Using X:{}, Y:{}".format(x_start,y_start))
        graphics.DrawText(canvas,
                          selected_font,
                          x_start,
                          y_start,
                          text_color,
                          text)
        #graphics.DrawText(canvas,self.font,x_start,y_start,text_color,text)
        return canvas

    # Find a font size that will fit the given text in the available space.
    # Returns a font so it can be used downstream.
    def _fit_string(self,input_string,allowed_width=None):
        font = graphics.Font()
        if allowed_width is None:
            allowed_width = self.matrix.width
        for points in self._font_sizes:
            font.LoadFont(self._font_dir + '/' + self._base_font + '-' + str(points) + '.bdf')
            string_width = self._string_width(input_string,font)
            if string_width <= allowed_width:
                return font
        # If we fail out the bottom, return the smallest font there is.
        return font

    # Calculate the width of a string given a certain font.
    @staticmethod
    def _string_width(input_string, font):
        string_length = 0
        for char in input_string:
            char_width = font.CharacterWidth(ord(char))
            string_length = string_length + char_width
        return string_length

    # @ureg.check('[length]',(None))
    @staticmethod
    def _ft_in(length,int_places = None):
        # Convert to inches.
        as_inches = length.to(ureg.inch)
        feet = int(length.to(ureg.inch).magnitude // 12)
        inches = round(length.to(ureg.inch).magnitude % 12,int_places)
        return "{}'{}\"".format(feet,inches)

    def _approach_strobe(self, canvas, range, range_pct):
        # Available strobing width. Cut in half since we go from both sides, take out pixels for the frames.
        available_width = (self.matrix.width / 2) - 1

        # If range isn't 'None' (sensor error) or 'BR' (beyond range), then we need to figure the strobe.
        if not isinstance(range, NaN):
            # Block the distance that's been covered.
            bar_blocker = floor(available_width * (1-range_pct))
            # Only draw a blocker bar if it would have length.
            if bar_blocker > 0:
                # Left
                graphics.DrawLine(canvas, 1,
                                  canvas.height - 2,
                                  1 + bar_blocker,
                                  canvas.height - 2,
                                  self._colors['white'])
                # Right
                graphics.DrawLine(canvas,
                                  canvas.width - 2,
                                  canvas.height - 2,
                                  canvas.width - 2 - bar_blocker,
                                  canvas.height - 2,
                                  self._colors['white'])

            # Determine strober offset based on time.
            if monotonic_ns() - self.timer_approach_strobe >= self.config['approach_strobe_speed']:
                if self._approach_strobe_offset > (available_width - bar_blocker)-1:
                    self._approach_strobe_offset = 1
                else:
                    self._approach_strobe_offset = self._approach_strobe_offset + 1
                self.timer_approach_strobe = monotonic_ns()

            # Draw dots based on the offset.
            graphics.DrawLine(canvas,
                              1 + bar_blocker + self._approach_strobe_offset,
                              canvas.height - 2,
                              1 + bar_blocker + self._approach_strobe_offset + 1,
                              canvas.height - 2,
                              self._colors['red']
                              )
            graphics.DrawLine(canvas,
                              canvas.width - bar_blocker - self._approach_strobe_offset,
                              canvas.height - 2,
                              canvas.width - bar_blocker - self._approach_strobe_offset-1,
                              canvas.height - 2,
                              self._colors['red']
                              )
        # Pass the Canvas back for further updates.
        return canvas

    # def _side_indicators(self, lateral, lateral_num):
    #     si_group = Group()
    #
    #     # Assign out the available vertical pixels in a round-robin fashion so each area gets a fair shake.
    #     area_lengths = [0] * lateral_num
    #     available_height = self.display.height-2
    #     candidate_area = 0
    #     while available_height > 0:
    #         area_lengths[candidate_area] += 1
    #         available_height -= 1
    #         candidate_area += 1
    #         if candidate_area > len(area_lengths) - 1:
    #             candidate_area = 0
    #
    #     # Start position of the bar, from the top.
    #     bar_start = 1
    #     # Go through each lateral detection zone. These should be ordered from rear to front.
    #     for index in range(len(lateral)):
    #         # If it returned the string 'BR', the vehicle has yet to cross this sensor's line of sight, so do nothing.
    #         if isinstance(lateral[index], str):
    #             if lateral[index] == 'BR':
    #                 pass  # Append to both left and right.
    #         # Show Green if we're in the 'spot on' or 'acceptable' deviance statuses.
    #         elif lateral[index]['status'] <= 1:
    #             line_left = Line(1, bar_start, 1, bar_start+area_lengths[index]-1, 0x00FF00)
    #             line_right = Line(self.display.width-2, bar_start, self.display.width-2,
    #                               bar_start+area_lengths[index]-1, 0x00FF00)
    #             # if things are spot on, light both sides.
    #             if lateral[index]['direction'] is None:
    #                 si_group.append(line_left)
    #                 si_group.append(line_right)
    #             # If left, light left.
    #             elif lateral[index]['direction'] == 'L':
    #                 si_group.append(line_left)
    #             # If right, light right.
    #             elif lateral[index]['direction'] == 'R':
    #                 si_group.append(line_right)
    #         elif lateral[index]['status'] == 2:
    #             line_left = Line(1, bar_start, 1, bar_start+area_lengths[index]-1, 0xFFFF00)
    #             line_right = Line(self.display.width-2, bar_start, self.display.width-2,
    #                               bar_start+area_lengths[index]-1, 0xFFFF00)
    #             if lateral[index]['direction'] == 'L':
    #                 si_group.append(line_left)
    #             elif lateral[index]['direction'] == 'R':
    #                 si_group.append(line_right)
    #         elif lateral[index]['status'] == 3:
    #             line_left = Line(1, bar_start, 1, bar_start+area_lengths[index]-1, 0xFF0000)
    #             line_right = Line(self.display.width-2, bar_start, self.display.width-2,
    #                               bar_start+area_lengths[index]-1, 0xFF0000)
    #             # if things are spot on, light both sides.
    #             if lateral[index]['direction'] == 'L':
    #                 si_group.append(line_left)
    #             elif lateral[index]['direction'] == 'R':
    #                 si_group.append(line_right)
    #
    #         # Increment so the next bar starts in the correct place.
    #         bar_start = bar_start + area_lengths[index]
    #     return si_group

    # Draw signal bars with an origin of X,Y
    def _signal_bars(self, canvas, strength, origin):
        # If signal strength is 0, then show an X since we're probably offline.
        if strength < 1:
            graphics.DrawLine(canvas, origin[0], origin[1], origin[0] + 4, origin[1] + 4, self._colors['red'])
            graphics.DrawLine(canvas, origin[0], origin[1] + 4, origin[0] + 4, origin[1], self._colors['red'])
        else:
            i = 1
            while i <= strength:
                graphics.DrawLine(
                    canvas,
                    origin[0]-1+i,
                    origin[1]+5,
                    origin[0]-1+i,
                    origin[1]+(5-i),
                    self._colors['green'])
                i += 1
        return canvas

    # Draw the ethernet icon, for wired connections.
    # Origin is the upper left. Icon takes 5x5 of space.
    def _eth_icon(self,canvas,online,origin):
        if online:
            box_color = self._colors['green']
        else:
            box_color = self._colors['red']
        # Base 'network' line.
        graphics.DrawLine(canvas,origin[0],origin[1]+4,origin[0]+4,origin[1]+4,self._colors['white'])
        # Stem
        graphics.DrawLine(canvas,origin[0]+2,origin[1]+3,origin[0]+2,origin[1]+3,self._colors['white'])
        # The System Box
        # Top
        graphics.DrawLine(canvas, origin[0] + 1, origin[1], origin[0] + 3,origin[1], box_color)
        # Right
        graphics.DrawLine(canvas, origin[0] + 3, origin[1], origin[0] + 3, origin[1] + 2, box_color)
        # Left
        graphics.DrawLine(canvas, origin[0] + 1, origin[1], origin[0] + 1, origin[1] + 2, box_color)
        # Bottom
        graphics.DrawLine(canvas, origin[0] + 1, origin[1] + 2, origin[0] + 3, origin[1] + 2, box_color)
        return canvas

    # Show the MQTT connection status icon.
    # Origin is the upper left.
    def _mqtt_icon(self, canvas, mqtt_status, origin):
        if mqtt_status:
            color_fg = self._colors['darkblue']
        else:
            color_fg = self._colors['red']
        # Left side
        graphics.DrawLine(canvas, origin[0], origin[1], origin[0], origin[1]+4, color_fg)
        # Right side
        graphics.DrawLine(canvas, origin[0]+4, origin[1], origin[0]+4, origin[1]+4, color_fg)
        # Left slant.
        graphics.DrawLine(canvas, origin[0], origin[1], origin[0]+2, origin[1]+2, color_fg)
        # Right slant
        graphics.DrawLine(canvas, origin[0]+2, origin[1]+2, origin[0]+4, origin[1], color_fg)

        # Send the canvas back
        return canvas

    # Display state icons, and optionally a single sensor.
    def display_generic(self, system_state, sensor=None):
        canvas = self.matrix.CreateFrameCanvas()
        if sensor is not None:
            graphics.DrawText(canvas,
                              self.base_font,
                              5,
                              canvas.height - 10,
                              self._colors['white'],
                              sensor
                              )
        #self._signal_bars(canvas,system_state['signal_strength'], (59, 27))
        self._eth_icon(canvas,True,(59,27))
        self._mqtt_icon(canvas,system_state['mqtt_status'], (0, 27))
        self.matrix.SwapOnVSync(canvas)

    # Update the display from the provided bay state.
    def display_dock(self, bay_state):
        # Create a new canvas to display
        self._staging_canvas.Clear()
        # Frame is always constant, so we add this right away.
        # Display the Frame
        #self._staging_canvas = self._frame(self._staging_canvas)
        # Display the strobe based on range. 
        # self._staging_canvas = self._approach_strobe(self._staging_canvas, bay_state['range'], bay_state['range_pct'])
        # Display the distance.
        self._staging_canvas = self._distance_display(self._staging_canvas, bay_state['range'], bay_state['range_pct'])
        # Display the side indicators
        #master_group.append(self._side_indicators(bay_state['lateral'], bay_state['lateral_num']))
        # Swap in the new canvas.
        self.matrix.SwapOnVSync(self._staging_canvas)
