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
from base64 import b64encode
from io import BytesIO

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

        # Initialize the image holding.
        self._image_buffer = BytesIO()
        self._current_image = None

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
        self._layers['error'] = self._placard('ERROR','red')

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
        self._output_image(img)

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

    # Outputs a given image to the matrix, and puts it in the current_image property to be picked up
    # and put on the MQTT stack.
    def _output_image(self,image):
        # Send to the matrix
        self._matrix.SetImage(image.convert('RGB'))

        # Put in the staging variable for pickup, base64 encoded.
        image.save(self._image_buffer, format='PNG')
        self.current = b64encode(self._image_buffer.getvalue())

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
