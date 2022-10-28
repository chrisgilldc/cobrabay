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
from PIL import Image, ImageDraw, ImageFont, ImageColor
from base64 import b64encode
from io import BytesIO
import math

ureg = UnitRegistry()


class Display:
    def __init__(self, config):
        # Get a logger!
        self._logger = logging.getLogger("CobraBay").getChild("Display")
        self._logger.setLevel(config.get_loglevel('display'))
        self._logger.info("Display initializing...")
        # Initialize the internal settings.
        self._settings = config.display()
        self._logger.info("Now have settings: {}".format(self._settings))

        # Operating settings. These get reset on every start.
        self._running = {}
        self._running['strobe_offset'] = 0
        self._running['strobe_timer'] = monotonic_ns()

        self._current_image = None

        # Layers dict.
        self._layers = {
            'lateral': {}
        }

        # Create static layers
        self._setup_layers()

        # Set up the matrix object itself.
        self._create_matrix(self._settings['matrix_width'], self._settings['matrix_height'], self._settings['gpio_slowdown'])

    # Method to set up image layers for use. This takes a command when the bay is ready so lateral zones can be prepped.
    def _setup_layers(self):
        # Initialize the layers.
        self._layers['frame_approach'] = self._frame_approach()
        self._layers['frame_lateral'] = self._frame_lateral()
        self._layers['approach'] = self._placard('APPROACH','blue')
        self._layers['error'] = self._placard('ERROR','red')

    # Create layers for the lateral markers based on number of lateral zones. This is done at the start of each
    # dock/undock since the number of lateral zones might change.
    def setup_lateral_markers(self,lateral_count):
        if lateral_count == 0:
            return

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

    # General purpose message displayer
    def show(self,mode,message=None,color="white"):
        if mode == 'clock':
            string = datetime.now().strftime("%-I:%M %p")
            # Clock is always in green.
            color = "green"
        elif mode == 'message':
            if message is None:
                raise ValueError("Show requires a message when used in Message mode.")
            string = message
        else:
            raise ValueError("Show did not get a valid mode.")
        # Make a base layer.
        base_img = Image.new("RGBA", (self._settings['matrix_width'], self._settings['matrix_height']), (0,0,0,255))
        placard = self._placard(string, color, w_adjust=0, h_adjust=0)
        final_image = Image.alpha_composite(base_img, placard)
        self._output_image(final_image)

    # Specific displayer for docking.
    def show_dock(self, display_data):
        self._logger.debug("Show Dock received data: {}".format(display_data))
        # For easy reference.
        w = self._settings['matrix_width']
        h = self._settings['matrix_height']
        # Make a base image, black background.
        base_image = Image.new("RGBA", (w, h), (0,0,0,255))
        ## Center area, the range number.
        # Pull out the range and range quality to make the center placard.
        self._logger.debug("Creating range placard with range: {}".format(display_data['range']))
        range_layer = self._placard_range(display_data['range'], display_data['range_quality'])
        final_image = Image.alpha_composite(base_image, range_layer)

        ## Bottom strobe box.
        # Frame is a pre-baked box.
        final_image = Image.alpha_composite(final_image, self._layers['frame_approach'])
        # Strober calculate the blocking box and the strobe bugs.
        final_image = Image.alpha_composite(final_image, self._strober(display_data))

        # If lateral zones exist, add the lateral frame.
        if len(self._layers['lateral']) > 0:
            final_image = Image.alpha_composite(final_image, self._layers['frame_lateral'])
            w_adjust = 8

        self._output_image(final_image)

    def _strober(self, display_data):
        w = self._settings['matrix_width']
        h = self._settings['matrix_height']
        img = Image.new("RGBA", (w, h), (0,0,0,0))
        draw = ImageDraw.Draw(img)
        # Calculate where the blockers need to be.
        available_width = (w-2)/2
        blocker_width = math.floor(available_width * (1-display_data['range_pct']))
        self._logger.debug("Strober blocker width: {}".format(blocker_width))
        # Because of rounding, we can wind up with an entirely closed bar if we're not fully parked.
        # Thus, fudge the space unless we're okay.

        if display_data['range_quality'] != 'ok' and blocker_width > 28:
            blocker_width = 28
        # Draw the blockers.
        draw.line([(1, h-2),(blocker_width+1, h-2)], fill="white")
        draw.line([(w-blocker_width-2, h-2), (w-2, h-2)], fill="white")
        # If we're fully parked the line is full and there's nowhere for the bugs, so don't bother.
        if blocker_width < 30:
            left_strobe_start = blocker_width+2+self._running['strobe_offset']
            left_strobe_stop = left_strobe_start + 3
            if left_strobe_stop > (w/2)-1:
                left_strobe_stop = (w/2)-1
            draw.line([(left_strobe_start, h-2),(left_strobe_stop,h-2)], fill="red")
            right_strobe_start = w - 2 - blocker_width - self._running['strobe_offset']
            right_strobe_stop = right_strobe_start - 3
            if right_strobe_stop < (w/2)+1:
                right_strobe_stop = (w/2)+1
            draw.line([(right_strobe_start, h - 2), (right_strobe_stop, h - 2)], fill="red")

        # If time is up, move the strobe bug forward.
        if monotonic_ns() > self._running['strobe_timer'] + self._settings['strobe_speed']:
            self._running['strobe_offset'] += 1
            self._running['strobe_timer'] = monotonic_ns()
            # Don't let the offset push the bugs out to infinity.
            if self._running['strobe_offset'] > (w/2) - blocker_width:
                self._running['strobe_offset'] = 0
        return img

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
            if as_inches.magnitude < 12:
                range_string = "{}\"".format(round(as_inches.magnitude,1))
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
        self._logger.debug("Requesting placard with range string {} in color {}".format(range_string, text_color))
        return self._placard(range_string, text_color)

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
        draw.text((w/2, (h-4)/2), text, fill=ImageColor.getrgb(color), font=font, anchor="mm")
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
    def _create_matrix(self, width, height, gpio_slowdown):
        self._logger.info("Initializing Matrix...")
        # Create a matrix. This is hard-coded for now.
        matrix_options = RGBMatrixOptions()
        matrix_options.cols = width
        matrix_options.rows = height
        matrix_options.chain_length = 1
        matrix_options.parallel = 1
        matrix_options.hardware_mapping = 'adafruit-hat-pwm'
        matrix_options.disable_hardware_pulsing = True
        matrix_options.gpio_slowdown = gpio_slowdown
        self._matrix = RGBMatrix(options=matrix_options)

    # Outputs a given image to the matrix, and puts it in the current_image property to be picked up
    # and put on the MQTT stack.
    def _output_image(self,image):
        # Send to the matrix
        self._matrix.SetImage(image.convert('RGB'))

        image_buffer = BytesIO()
        # Put in the staging variable for pickup, base64 encoded.
        image.save(image_buffer, format='PNG')
        self.current = b64encode(image_buffer.getvalue())

        # For debugging, write to a file in tmp.
        image.save("/tmp/cobrabay-display.png", format='PNG')

    @property
    def current(self):
        return self._current_image

    @current.setter
    def current(self,image):
        self._current_image = image

    # Divide into roughly equal parts. Found this here:
    # https://stackoverflow.com/questions/52697875/split-number-into-rounded-numbers
    @staticmethod
    def _parts(a, b):
        q, r = divmod(a, b)
        return [q + 1] * r + [q] * (b - r)
