####
# Cobra Bay - Display
# 
# Displays current Bay status on a 64x32 RGB Matrix
####

import logging
from time import monotonic_ns
from datetime import datetime
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from pint import UnitRegistry, Quantity
from PIL import Image, ImageDraw, ImageFont

ureg = UnitRegistry()


class Display:
    def __init__(self, config):
        # Get a logger!
        self._logger = logging.getLogger("CobraBay").getChild("Display")
        self._logger.debug("Creating Display...")
        # Initialize the internal settings.
        self._settings = {}
        self._settings['units'] = config['global']['units']

        # Default strobe speed of 100 ms
        self._settings['strobe_speed'] = 100 * 1000000
        self._settings['matrix_width'] = config['matrix']['width']
        self._settings['matrix_height'] = config['matrix']['height']
        self._settings['mqtt_image'] = config['mqtt_image']
        self._settings['mqtt_update_interval'] = Quantity(config['mqtt_update_interval'])
        self._settings['core_font'] = 'fonts/OpenSans-Light.ttf'

        # Operating settings. These get reset on every start.
        self._running = {}
        self._running['strobe_offset'] = 0
        self._running['strobe_timer'] = monotonic_ns()

        # Layers dict.
        self._layers = {
            'lateral': {}
        }
        # Create static layers
        self._setup_layers()

        # Set up the matrix object itself.
        self._create_matrix(config['matrix'])

    # Method to set up image layers for use. This takes a command when the bay is ready so lateral zones can be prepped.
    def _setup_layers(self):
        # Initialize the layers.
        self._layers['frame_approach'] = self._frame_approach()
        self._layers['frame_lateral'] = self._frame_lateral()
        self._layers['approach'] = self._placard('APPROACH','blue')

    # Create layers for the lateral markers based on number of lateral zones. This is done at the start of each
    # dock/undock since the number of lateral zones might change.
    def setup_lateral_markers(self,lateral_count):
        # Wipe out previous layers, in case we've reduced the count, to make sure nothing lingers.
        self._layers['lateral'] = dict()

        # For convenient reference later.
        w = self._settings['matrix_width']
        h = self._settings['matrix_height']

        # Calculate the available pixels for each zones.
        avail_height = self._settings['matrix_height'] - 6  #
        pixel_lengths = self._parts(avail_height, lateral_count)
        self._logger.debug("Split {} pixels for {} lateral zones into: {}".
                           format(avail_height,lateral_count,pixel_lengths))

        status_lookup = (
            ['ok',(0,128,0,0)],
            ['warn',(255,0,0,0)],
            ['crit',(255,0,0,0)]
        )

        i = 0
        # Add in the used height of each bar to this variable. Since they're not guaranteed to be the same, we can't
        # just multiply.
        accumulated_height = 0
        while i < lateral_count:
            self._logger.debug("Processing lateral zone: {}".format(i+1))
            self._layers['lateral']['zone_' + str(i+1)] = {}
            for side in ('L','R'):
                self._layers['lateral']['zone_' + str(i + 1)][side] = {}
                for status in status_lookup:
                    # Make the image.
                    img = Image.new('RGBA', (w, h), (0,0,0,0))
                    draw = ImageDraw.Draw(img)
                    # Move the width depending on which side we're on.
                    if side == 'L':
                        line_w = 1
                    elif side == 'R':
                        line_w = w - 2  # -2, one because of the border, one because it's 0 indexed.
                    else:
                        raise ValueError("Not a valid side option, this should never happen!")
                    draw.line([(line_w,1 + accumulated_height),(line_w,1 + accumulated_height + pixel_lengths[i])],
                        fill=status[1],width=1)
                    # Put this in the right place in the lookup.
                    self._layers['lateral']['zone_' + str(i+1)][side][status[0]] = img
            # Now add the height of this bar to the accumulated height, to get the correct start for the next time.
            accumulated_height += pixel_lengths[i]
            # Increment to the next zone.
            i += 1
        print(self._layers['lateral'])

    def show_clock(self):
        w = self._settings['matrix_width']
        h = self._settings['matrix_height']
        dt_now = datetime.now().strftime("%-I:%M:%S %p")
        img = Image.new("RGB", (w, h), (0,0,0))
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype(font=self._settings['core_font'], size=self._scale_font(dt_now, w - 8, h - 4))
        draw.text((w/2,h/2),dt_now,fill="green",font=font,anchor="mm")
        self._matrix.SetImage(img)

    def show_dock(self, position, quality):
        self._logger.debug("Show Dock received position: {}".format(position))
        self._logger.debug("Show Dock received quality: {}".format(quality))

        # For easy reference.
        w = self._settings['matrix_width']
        h = self._settings['matrix_height']
        # Make a base image, black background.
        base_img = Image.new("RGBA", (w, h), (0,0,0,255))
        # Add the bottom strobe box.
        final_image = Image.alpha_composite(base_img, self._layers['frame_approach'])
        # If lateral zones exist, add the lateral frame.
        if len(self._layers['lateral']) > 0:
            final_image = Image.alpha_composite(final_image, self._layers['frame_lateral'])
            w_adjust = 8

        # Pull out the range and range quality to make the center placard.
        self._logger.debug("Creating range placard with range: {}".format(position['message']['lo']))
        range_layer = self._placard_range(position['message']['lo'],quality['message']['lo'])
        final_image = Image.alpha_composite(final_image, range_layer)

        # lateral_layer = self._lateral_status(position['message']['la'],quality['message']['la'])

        # Push the final image to the Matrix.
        self._matrix.SetImage(final_image.convert('RGB'))

        # If we want to send the image to the MQTT server, do it.
        if self._settings['mqtt_image']:
            return final_image
        else:
            return None

    # Methods to create image objects that can then be composited.
    def _frame_approach(self):
        w = self._settings['matrix_width']
        h = self._settings['matrix_height']
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle([(0, h - 3), (w - 1, h - 1)], width=1)
        return img

    def _frame_lateral(self):
        # Localize matrix width and height, just to save readability
        w = self._settings['matrix_width']
        h = self._settings['matrix_height']
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Left Rectangle
        draw.rectangle([(0, 0), (2, h-5)], width=1)
        # Right Rectangle
        draw.rectangle([(w-3, 0), (w-1, h-5)], width=1)
        return img

    # Make a placard to show range.
    def _placard_range(self,input_range,range_quality):
        if  self._settings['units'] == 'imperial':
            as_inches = input_range.to('in')
            if as_inches < 12:
                range_string = "{}\"".format(as_inches.magnitude)
            else:
                feet = int(as_inches.to(ureg.inch).magnitude // 12)
                inches = round(as_inches.to(ureg.inch).magnitude % 12,0)
                range_string = "{}'{}\"".format(feet,inches)
        else:
            as_meters = round(input_range.to('m').magnitude,2)
            range_string = "{} m".format(as_meters)
        if range_quality == 'crit':
            text_color = 'red'
        elif range_quality =='warn':
            text_color = 'yellow'
        else:
            text_color = 'white'
        # Now we can get it formatted and return it.
        self._logger.debug("Requesting placard with range string: {}".format(range_string))
        return self._placard(range_string,text_color)

    # Generalized placard creator. Make an image for arbitrary text.
    def _placard(self,text,color,w_adjust=8,h_adjust=4):
        # Localize matrix and adjust.
        w = self._settings['matrix_width']
        h = self._settings['matrix_height']
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Find the font size we can use.
        font = ImageFont.truetype(font=self._settings['core_font'],
                                  size=self._scale_font(text, w-w_adjust, h-h_adjust))
        # Make the text. Center it in the middle of the area, using the derived font size.
        draw.text((w/2, (h-4)/2), text, fill="blue", font=font, anchor="mm")
        return img


    # Utility method to find the largest font size that can fit in a space.
    def _scale_font(self, text, w, h):
        # Start at font size 1.
        fontsize = 1
        while True:
            font = ImageFont.truetype(font=self._settings['core_font'], size=fontsize)
            bbox = font.getbbox(text)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            if text_width < w and text_height < h:
                fontsize += 1
            else:
                break
        return fontsize

    # Utility method to do all the matrix creation.
    def _create_matrix(self, matrix_config):
        self._logger.info("Initializing Matrix...")
        # Create a matrix. This is hard-coded for now.
        matrix_options = RGBMatrixOptions()
        matrix_options.rows = matrix_config['height']
        matrix_options.cols = matrix_config['width']
        matrix_options.chain_length = 1
        matrix_options.parallel = 1
        matrix_options.hardware_mapping = 'adafruit-hat-pwm'
        matrix_options.disable_hardware_pulsing = True
        matrix_options.gpio_slowdown = matrix_config['gpio_slowdown']
        self._matrix = RGBMatrix(options=matrix_options)

    # Divide into roughly equal parts. Found this here:
    # https://stackoverflow.com/questions/52697875/split-number-into-rounded-numbers
    @staticmethod
    def _parts(a, b):
        q, r = divmod(a, b)
        return [q + 1] * r + [q] * (b - r)

    #
    # def _distance_display(self, canvas, range, range_pct):
    #     # If Range isn't a number, there's two options.
    #     if isinstance(range, NaN):
    #         # If the NaN reason is "Beyond range", throw up the "Approach" text
    #         if range.reason == 'Beyond range':
    #             text = "APPROACH"
    #             text_color = self._colors['darkblue']
    #         if range.reason == 'CRASH!':
    #             text = range.reason
    #             text_color = self._colors['red']
    #         # Any other NaN indicates an error.
    #         else:
    #             text = "ERROR"
    #             text_color = self._colors['red']
    #     elif range <= Quantity("1 inch"):
    #             text = "STOP!"
    #             text_color = self._colors['red']
    #     elif range < Quantity("-1 inch"):
    #             text = "BACK-UP"
    #             text_color = 0xFF0000
    #     else:
    #         # Determine what to use for range output.
    #         if self.config['global']['units'] == 'imperial':
    #             # For Imperial (ie: US) users, output as prime-notation Feet and Inches.
    #             text = self._ft_in(range)
    #         else:
    #             # For Metric (ie: Reasonable countries) users, output as decimal meters
    #             text = str(range.to("meters"))
    #         # Within 10% of range, orange
    #         if range_pct <= 0.10:
    #             text_color = self._colors['orange']
    #         # Within 20 % of range, yellow.
    #         elif range_pct <= 0.20:
    #             text_color = self._colors['yellow']
    #         else:
    #             text_color = self._colors['white']
    #     # Scale the font based on the available space and size.
    #     # text = "TESTING!"
    #     # text_color = self._colors['darkblue']
    #     selected_font = self._fit_string(text,self.matrix.width-8)
    #     # Alignment variables to determine the proper lower-left corner of the string.
    #     # Align vertically, based on canvas height with space removed for the lower strobe bar.
    #     x_start = 4 + ((canvas.width - 8)  / 2) - (self._string_width(text, selected_font) / 2)
    #     y_start = canvas.height - 4 - ((canvas.height-4)/2) + (selected_font.height/2)
    #     # x_start = 10
    #     # y_start = 15
    #     # # Add the string to the canvas, then return it.
    #     # print("Canvas size X:{}, Y:{}".format(canvas.width,canvas.height))
    #     # print("Using X:{}, Y:{}".format(x_start,y_start))
    #     graphics.DrawText(canvas,
    #                       selected_font,
    #                       x_start,
    #                       y_start,
    #                       text_color,
    #                       text)
    #     #graphics.DrawText(canvas,self.font,x_start,y_start,text_color,text)
    #     return canvas
    #
    #
    #
    # def _approach_strobe(self, canvas, range, range_pct):
    #     # Available strobing width. Cut in half since we go from both sides, take out pixels for the frames.
    #     available_width = (self.matrix.width / 2) - 1
    #
    #     # If range isn't 'None' (sensor error) or 'BR' (beyond range), then we need to figure the strobe.
    #     if not isinstance(range, NaN):
    #         # Block the distance that's been covered.
    #         bar_blocker = floor(available_width * (1-range_pct))
    #         # Only draw a blocker bar if it would have length.
    #         if bar_blocker > 0:
    #             # Left
    #             graphics.DrawLine(canvas, 1,
    #                               canvas.height - 2,
    #                               1 + bar_blocker,
    #                               canvas.height - 2,
    #                               self._colors['white'])
    #             # Right
    #             graphics.DrawLine(canvas,
    #                               canvas.width - 2,
    #                               canvas.height - 2,
    #                               canvas.width - 2 - bar_blocker,
    #                               canvas.height - 2,
    #                               self._colors['white'])
    #
    #         # Determine strober offset based on time.
    #         if monotonic_ns() - self.timer_approach_strobe >= self.config['approach_strobe_speed']:
    #             if self._approach_strobe_offset > (available_width - bar_blocker)-1:
    #                 self._approach_strobe_offset = 1
    #             else:
    #                 self._approach_strobe_offset = self._approach_strobe_offset + 1
    #             self.timer_approach_strobe = monotonic_ns()
    #
    #         # Draw dots based on the offset.
    #         graphics.DrawLine(canvas,
    #                           1 + bar_blocker + self._approach_strobe_offset,
    #                           canvas.height - 2,
    #                           1 + bar_blocker + self._approach_strobe_offset + 1,
    #                           canvas.height - 2,
    #                           self._colors['red']
    #                           )
    #         graphics.DrawLine(canvas,
    #                           canvas.width - bar_blocker - self._approach_strobe_offset,
    #                           canvas.height - 2,
    #                           canvas.width - bar_blocker - self._approach_strobe_offset-1,
    #                           canvas.height - 2,
    #                           self._colors['red']
    #                           )
    #     # Pass the Canvas back for further updates.
    #     return canvas
    #
    # def _lateral_indicators(self, lateral, lateral_num):
    #     lateral_group = Group()
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
    #                 lateral_group.append(line_left)
    #                 lateral_group.append(line_right)
    #             # If left, light left.
    #             elif lateral[index]['direction'] == 'L':
    #                 lateral_group.append(line_left)
    #             # If right, light right.
    #             elif lateral[index]['direction'] == 'R':
    #                 lateral_group.append(line_right)
    #         elif lateral[index]['status'] == 2:
    #             line_left = Line(1, bar_start, 1, bar_start+area_lengths[index]-1, 0xFFFF00)
    #             line_right = Line(self.display.width-2, bar_start, self.display.width-2,
    #                               bar_start+area_lengths[index]-1, 0xFFFF00)
    #             if lateral[index]['direction'] == 'L':
    #                 lateral_group.append(line_left)
    #             elif lateral[index]['direction'] == 'R':
    #                 lateral_group.append(line_right)
    #         elif lateral[index]['status'] == 3:
    #             line_left = Line(1, bar_start, 1, bar_start+area_lengths[index]-1, 0xFF0000)
    #             line_right = Line(self.display.width-2, bar_start, self.display.width-2,
    #                               bar_start+area_lengths[index]-1, 0xFF0000)
    #             # if things are spot on, light both sides.
    #             if lateral[index]['direction'] == 'L':
    #                 lateral_group.append(line_left)
    #             elif lateral[index]['direction'] == 'R':
    #                 lateral_group.append(line_right)
    #
    #         # Increment so the next bar starts in the correct place.
    #         bar_start = bar_start + area_lengths[index]
    #     return lateral_group
    #
    # # Display state icons, and optionally a single sensor.
    # def display_generic(self, system_state, message_color = 'white', message = None, sensor=None):
    #     canvas = self.matrix.CreateFrameCanvas()
    #     if message:
    #         font = self._fit_string(message)
    #         height = ( ( canvas.height - 5 ) / 2 ) + ( font.height / 2 )
    #         graphics.DrawText(canvas,
    #                           font,
    #                           5, height, self._colors[message_color],message)
    #     elif sensor is not None:
    #         graphics.DrawText(canvas,
    #                           self.base_font,
    #                           5,
    #                           canvas.height - 10,
    #                           self._colors['white'],
    #                           sensor
    #                           )
    #     #self._signal_bars(canvas,system_state['signal_strength'], (59, 27))
    #     self._eth_icon(canvas,True,(59,27))
    #     self._mqtt_icon(canvas,system_state['mqtt_status'], (0, 27))
    #     self.matrix.SwapOnVSync(canvas)
    #
    # # Update the display from the provided bay state.
    # def display_dock(self, bay_state, show_lateral=True):
    #     # Create a new canvas to display
    #     self._staging_canvas.Clear()
    #     # Box for the strobe.
    #     self._staging_canvas = self._strobe_box(self._staging_canvas)
    #     # Display the strobe based on range.
    #     self._staging_canvas = self._approach_strobe(self._staging_canvas, bay_state['range'], bay_state['range_pct'])
    #     # If set to show lateral, show it.
    #     if show_lateral:
    #         # Add in the lateral frame boxes
    #         self._staging_canvas = self._lateral_boxes(self._staging_canvas)
    #         self._staging_canvas = self._lateral_indicators(self._staging_canvas)
    #     # Display the distance.
    #     self._staging_canvas = self._distance_display(self._staging_canvas, bay_state['range'], bay_state['range_pct'])
    #     # Display the side indicators
    #     #master_group.append(self._side_indicators(bay_state['lateral'], bay_state['lateral_num']))
    #     # Swap in the new canvas.
    #     self.matrix.SwapOnVSync(self._staging_canvas)
    #
    # # Methods for specific graphical elements
    #
    # # Draw signal bars with an origin of X,Y
    # def _signal_bars(self, canvas, strength, origin):
    #     # If signal strength is 0, then show an X since we're probably offline.
    #     if strength < 1:
    #         graphics.DrawLine(canvas, origin[0], origin[1], origin[0] + 4, origin[1] + 4, self._colors['red'])
    #         graphics.DrawLine(canvas, origin[0], origin[1] + 4, origin[0] + 4, origin[1], self._colors['red'])
    #     else:
    #         i = 1
    #         while i <= strength:
    #             graphics.DrawLine(
    #                 canvas,
    #                 origin[0] - 1 + i,
    #                 origin[1] + 5,
    #                 origin[0] - 1 + i,
    #                 origin[1] + (5 - i),
    #                 self._colors['green'])
    #             i += 1
    #     return canvas
    #
    # # Draw the ethernet icon, for wired connections.
    # # Origin is the upper left. Icon takes 5x5 of space.
    # def _eth_icon(self, canvas, online, origin):
    #     if online:
    #         box_color = self._colors['green']
    #     else:
    #         box_color = self._colors['red']
    #     # Base 'network' line.
    #     graphics.DrawLine(canvas, origin[0], origin[1] + 4, origin[0] + 4, origin[1] + 4, self._colors['white'])
    #     # Stem
    #     graphics.DrawLine(canvas, origin[0] + 2, origin[1] + 3, origin[0] + 2, origin[1] + 3, self._colors['white'])
    #     # The System Box
    #     # Top
    #     graphics.DrawLine(canvas, origin[0] + 1, origin[1], origin[0] + 3, origin[1], box_color)
    #     # Right
    #     graphics.DrawLine(canvas, origin[0] + 3, origin[1], origin[0] + 3, origin[1] + 2, box_color)
    #     # Left
    #     graphics.DrawLine(canvas, origin[0] + 1, origin[1], origin[0] + 1, origin[1] + 2, box_color)
    #     # Bottom
    #     graphics.DrawLine(canvas, origin[0] + 1, origin[1] + 2, origin[0] + 3, origin[1] + 2, box_color)
    #     return canvas
    #
    # # Make MQTT status icon, color based on status.
    # # Origin is the upper left.
    # def _mqtt_icon(self, canvas, mqtt_status, origin):
    #     if mqtt_status:
    #         color_fg = self._colors['darkblue']
    #     else:
    #         color_fg = self._colors['red']
    #     # Left side
    #     graphics.DrawLine(canvas, origin[0], origin[1], origin[0], origin[1] + 4, color_fg)
    #     # Right side
    #     graphics.DrawLine(canvas, origin[0] + 4, origin[1], origin[0] + 4, origin[1] + 4, color_fg)
    #     # Left slant.
    #     graphics.DrawLine(canvas, origin[0], origin[1], origin[0] + 2, origin[1] + 2, color_fg)
    #     # Right slant
    #     graphics.DrawLine(canvas, origin[0] + 2, origin[1] + 2, origin[0] + 4, origin[1], color_fg)
    #
    #     # Send the canvas back
    #     return canvas
    #
    # # Graphics utility methods.
    #
    # # Box drawer.
    # def _draw_box(self, canvas, x1, y1, x2, y2, color=None):
    #     if color is None:
    #         color = graphics.Color(255, 255, 255)
    #     # Top line
    #     graphics.DrawLine(canvas, x1, y1, x2, y1, color)
    #     # Left side
    #     graphics.DrawLine(canvas, x1, y1, x1, y2, color)
    #     # Right side
    #     graphics.DrawLine(canvas, x2, y1, x2, y2, color)
    #     # Bottom
    #     graphics.DrawLine(canvas, x1, y2, x2, y2, color)
    #     # Send the canvas back.
    #     return canvas
    #
    # # Find a font size that will fit the given text in the available space.
    # def _fit_string(self, input_string, allowed_width=None):
    #     font = graphics.Font()
    #     if allowed_width is None:
    #         allowed_width = self.matrix.width
    #     for points in self._font_sizes:
    #         font.LoadFont(self._font_dir + '/' + self._base_font + '-' + str(points) + '.bdf')
    #         string_width = self._string_width(input_string, font)
    #         if string_width <= allowed_width:
    #             return font
    #     # If we fail out the bottom, return the smallest font there is.
    #     return font
    #
    # # Calculate the width of a string given a certain font.
    # @staticmethod
    # def _string_width(input_string, font):
    #     string_length = 0
    #     for char in input_string:
    #         char_width = font.CharacterWidth(ord(char))
    #         string_length = string_length + char_width
    #     return string_length
    #
    # # @ureg.check('[length]',(None))
    # @staticmethod
    # def _ft_in(length,int_places = None):
    #     # Convert to inches.
    #     as_inches = length.to(ureg.inch)
    #     feet = int(length.to(ureg.inch).magnitude // 12)
    #     inches = round(length.to(ureg.inch).magnitude % 12,int_places)
    #     return "{}'{}\"".format(feet,inches)
