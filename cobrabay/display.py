####
# Cobra Bay - Display
#
# Displays statuses on an RGB Matrix
####

import logging
from base64 import b64encode
from datetime import datetime
from io import BytesIO
from pint import UnitRegistry, Quantity
from PIL import Image, ImageDraw, ImageFont, ImageColor
from rgbmatrix import RGBMatrix, RGBMatrixOptions
import rgbmultitool
from rgbmultitool import graphics
from time import monotonic_ns
from cobrabay.const import *

# Class definition
class CBDisplay:
    def __init__(self,
                 width,
                 height,
                 gpio_slowdown,
                 cbcore,
                 font,
                 font_size_clock=None,
                 font_size_range=None,
                 bottom_box=None,
                 strobe_speed=None,
                 icons=None,
                 unit_system="metric",
                 log_level="WARNING"):
        """
        Cobrabay Display Object

        :param width: Pixel width of the display.
        :type width: int
        :param height: Pixel height of the display.
        :type height: int
        :param gpio_slowdown: GPIO pacing to prevent flicker.
        :type gpio_slowdown: int
        :param font: Path to the font to use for text. Must be a TTF.
        :type font: Path
        :param font_size_clock: Font size to use for the clock. If not provided will be auto-scaled, which takes time.
        :type font_size_clock: int
        :param font_size_range: Font size to use for range display. If not provided will be auto-scaled, which takes time.
        :type font_size_clock: int
        :param cbcore: Reference to the Core object.
        :param bottom_box: For motions, bottom box to use. May be 'off', 'strobe', or 'progress'
        :type bottom_box: str
        :param strobe_speed: If strobe bottom box is used, how fast should it move?
        :type strobe_speed: Quantity(ms),
        :param icons: Dict defining which icons to turn on and off.
        :type icons: dict
        :param unit_system: Unit system to display in. May be 'imperial' or 'metric'
        :type unit_system: str
        :param log_level: Logging level for the display sub-logger. Defaults to 'Warning'
        :type log_level: str
        """

        # Set up our logger.
        self._logger = logging.getLogger("cobrabay").getChild("Display")
        self._logger.setLevel(log_level.upper())
        self._logger.info("Display initializing...")
        self._logger.info("Display unit system: {}".format(unit_system))

        # Save parameters
        self._matrix_width = width
        self._matrix_height = height
        self.unit_system = unit_system  # Set the unit system.
        self._cbcore = cbcore  # Save the core reference.
        self._font = font  # Save the font.
        self._logger.debug("Font: {}".format(self._font))
        self._logger.debug("Font type: {}".format(type(self._font)))
        self._logger.debug("Font properties: {}".format(dir(self._font)))

        self._icons = icons
        self._logger.info("Icon settings: {}".format(self._icons))

        # Default the bottom box appropriately.
        if bottom_box is None:
            bottom_box = 'strobe'
            self._logger.info("No bottom box specified. Defaulting to strobe.")
        self._bottom_box = bottom_box
        # Default the strobe speed if necessary.
        if self._bottom_box == 'strobe' and strobe_speed is None:
            self._logger.info("Using strobe and no speed specified. Defaulting to 200ms")
            self._strobe_speed = Quantity('200ms')
        else:
            self._strobe_speed = strobe_speed

        # Find font sizes if necessary.
        if font_size_clock is None:
            self._logger.warning("No clock font size provided. Auto-calculating, this may take a while...")
            self._font_size_clock = self._find_font_size_clock(width=(self._matrix_width - 6),
                                                               height=(self._matrix_height - 6))
            self._logger.warning("Determined clock font size to be '{}'. Recommend putting this in the config!".
                                 format(self._font_size_clock))
        else:
            self._font_size_clock = font_size_clock
        # Can't calculate the font size for the range now, so just save the flag.
        self._font_size_range = font_size_range

        # Initialize instance variables.
        self._current_image = None
        # Operating settings. These get reset on every start.
        self._running = {'strobe_offset': 0, 'strobe_timer': monotonic_ns()}
        # Layers dict.
        self._layers = {'lateral': {}}

        # Report the matrix size.
        self._logger.info("Matrix is {}x{}".format(self._matrix_width, self._matrix_height))

        # Create prepared layers.
        self._setup_layers()

        # Set up the matrix object itself.
        self._logger.info("Initializing matrix...")
        self._matrix = self._create_matrix(self._matrix_width, self._matrix_height, gpio_slowdown)
        self._logger.info("Display initialization complete.")

    ## Public Methods
    def register_bay(self, bay_obj):
        '''
        Register a bay with the display. This pre-creates all the needed images for display.

        :param bay_obj: The bay object being registered.
        :type bay_obj: CBBay
        :return:
        '''
        self._logger.debug("Registering bay ID {} to display".format(bay_obj.id))
        self._logger.debug("Setting up for laterals: {}".format(bay_obj.lateral_sorted))
        # Initialize a dict for this bay.
        self._layers[bay_obj.id] = {}

        # Determine the proper range font size for this bay.
        if self._font_size_range is None:
            self._logger.warning("Range font size not pre-set. Auto-scaling, this may take some time")
            self._font_size_range = self._find_font_size_range(bay_obj.depth, bay_obj.depth - bay_obj.depth_abs)
            self._logger.warning("Found range font size: {}".format(self._font_size_range))
        else:
            self._logger.info("Using range font size '{}'".format(self._font_size_range))

        # If no lateral detectors are defined, do nothing else.
        if len(bay_obj.lateral_sorted) == 0:
            return

        # Calculate the available pixels for each zone.
        avail_height = self._matrix_height - 6  #
        pixel_lengths = self._parts(avail_height, len(bay_obj.lateral_sorted))
        self._logger.debug("Split {} pixels for {} lateral zones into: {}".
                           format(avail_height, len(bay_obj.lateral_sorted), pixel_lengths))

        # Eventually replace this with the _status_color method.
        status_lookup = (
            {'status': SENSOR_QUALITY_OK, 'border': (0, 128, 0, 255), 'fill': (0, 128, 0, 255)},
            {'status': SENSOR_QUALITY_WARN, 'border': (255, 255, 0, 255), 'fill': (255, 255, 0, 255)},
            {'status': SENSOR_QUALITY_CRIT, 'border': (255, 0, 0, 255), 'fill': (255, 0, 0, 255)},
            {'status': SENSOR_QUALITY_NOOBJ, 'border': (255, 255, 255, 255), 'fill': (0, 0, 0, 0)}
        )

        i = 0
        # Add in the used height of each bar to this variable. Since they're not guaranteed to be the same, we can't
        # just multiply.
        accumulated_height = 0
        for intercept in bay_obj.lateral_sorted:
            sensor_id = intercept.sensor_id
            self._logger.debug("Processing lateral zone: {}".format(sensor_id))
            self._layers[bay_obj.id][sensor_id] = {}
            for side in ('L', 'R'):
                self._layers[bay_obj.id][sensor_id][side] = {}
                if side == 'L':
                    line_w = 0
                    nointercept_x = 1
                elif side == 'R':
                    line_w = self._matrix_width - 3
                    nointercept_x = self._matrix_width - 2
                else:
                    raise ValueError("Not a valid side option, this should never happen!")

                # Make an image for the 'fault' status.
                img = Image.new('RGBA', (self._matrix_width, self._matrix_height), (0, 0, 0, 0))
                # Make a striped box for fault.
                img = self._rectangle_striped(
                    img,
                    (line_w, 1 + accumulated_height),
                    (line_w + 2, 1 + accumulated_height + pixel_lengths[i]),
                    pricolor='red',
                    seccolor='yellow'
                )
                self._layers[bay_obj.id][sensor_id][side]['fault'] = img
                del (img)

                # Make an image for no_object
                img = Image.new('RGBA', (self._matrix_width, self._matrix_height), (0, 0, 0, 0))
                # Draw white lines up the section.
                draw = ImageDraw.Draw(img)
                draw.line(
                    [nointercept_x, 1 + accumulated_height, nointercept_x, 1 + accumulated_height + pixel_lengths[i]],
                    fill='white', width=1)
                self._layers[bay_obj.id][sensor_id][side][SENSOR_QUALITY_NOTINTERCEPTED] = img
                del (img)

                for item in status_lookup:
                    self._logger.debug("Creating layer for side {}, status {} with border {}, fill {}."
                                       .format(side, item['status'], item['border'], item['fill']))
                    # Make the image.
                    img = Image.new('RGBA', (self._matrix_width, self._matrix_height), (0, 0, 0, 0))
                    draw = ImageDraw.Draw(img)
                    # Draw the rectangle
                    draw.rectangle(
                        [line_w, 1 + accumulated_height, line_w + 2, 1 + accumulated_height + pixel_lengths[i]],
                        fill=item['fill'],
                        outline=item['border'],
                        width=1)
                    # Put this in the right place in the lookup.
                    self._layers[bay_obj.id][sensor_id][side][item['status']] = img
                    # Write for debugging
                    # img.save("/tmp/cobrabay-{}-{}-{}.png".format(lateral,side,status[0]), format='PNG')
                    del (draw)
                    del (img)

            # Now add the height of this bar to the accumulated height, to get the correct start for the next time.
            accumulated_height += pixel_lengths[i]
            # Increment to the next zone.
            i += 1
        self._logger.debug("Created laterals for {}: {}".format(bay_obj.id, self._layers[bay_obj.id]))

    def show(self, mode, message=None, color="white", icons=True):
        """
        Show a general-purpose message on the display.

        :param mode: One of 'clock' to show clock or 'message' to show the string.
        :type mode: str
        :param message: For 'message' mode, the string to display.
        :type message: str
        :param color: For 'message' mode, the color the text should be. Defaults to white.
        :type color: str
        :param icons: Should the status icons (ie: network connection) be displayed. Defaults true.
        :type icons: bool
        :return:
        """

        # By default, font_size should auto-scale, so make it none.
        font_size = None

        if mode == 'clock':
            string = datetime.now().strftime("%-I:%M")
            # Clock is always in green.
            color = "green"
            font_size = self._font_size_clock
        elif mode == 'message':
            if message is None:
                raise ValueError("Show requires a message when used in Message mode.")
            string = message
        else:
            raise ValueError("Show mode '{}' is not valid. Must be 'clock' or 'message'.".format(mode))

        placard_h = 0

        # Make a base layer.
        img = Image.new("RGBA", (self._matrix_width, self._matrix_height), (0, 0, 0, 255))
        # If enabled, put status icons at the bottom of the display.
        if icons:
            for icon_name in self._icons:
                if self._icons[icon_name]:
                    # If enabled, draw it based on whichever icon it is.
                    if icon_name == 'network':
                        # If data is available in the data, draw it.
                        network_icon = graphics.icon_network(self._cbcore.net_data['interface'][1], self._cbcore.net_data['mqtt'][1])
                        img.paste(network_icon,
                                  (self._matrix_width - network_icon.width, self._matrix_height - network_icon.height))
                        # Adjust available placard height so we don't stomp over the icons.
                        if placard_h < 6:
                            placard_h = 6
                        # Otherwise draw the unavailable version.
                    elif icon_name == 'ev-battery':
                        self._logger.debug("EV Battery data value: {}".format(self._cbcore.net_data['ev-battery'][1]))
                        charge_value = self._cbcore.net_data['ev-battery'][1]
                        battery_icon = graphics.icon_battery(charge_value, 12, 6)
                        img.paste(battery_icon,
                                  (int(self._matrix_width/2 - battery_icon.width/2), self._matrix_height - battery_icon.height))
                        # Move the placard height up.
                        if placard_h < 7:
                            placard_h = 7
                    elif icon_name == 'ev-plug':
                        # If ev-plug is None, don't display it, there's no data.
                        if (self._cbcore.net_data['ev-plug'][1] is not None or
                                self._cbcore.net_data['ev-charging'][1] is not None):
                            self._logger.debug("EV Plug data value: {}".format(self._cbcore.net_data['ev-plug'][1]))
                            plug_icon = graphics.icon_evplug(
                                plugged_in=self._cbcore.net_data['ev-plug'][1],
                                charging=self._cbcore.net_data['ev-charging'][1])
                            img.paste(plug_icon,
                                      (0,self._matrix_height - plug_icon.height))
                    elif icon_name == 'garage-door':
                        pass
                    elif icon_name == 'sensors':
                        pass
                    elif icon_name == 'mini-vehicle':
                        pass
        else:
            placard_h = 0

        # Placard with the text.
        placard = self._placard(string, color, font_size=font_size, w_adjust=0, h_adjust=placard_h)
        img = Image.alpha_composite(img, placard)
        # Send it to the display!
        self.current = img

    def show_motion(self, direction, bay_obj):
        #TODO: Maybe remove direction, not sure we need that anymore.
        """Show motion placard based on bay object's sensor info.

        :param bay_obj: Bay object to display.
        :type bay_obj: CBBay
        """
        self._logger.debug("Show Motion received bay '{}'".format(bay_obj.name))

        # Don't do motion display if the bay isn't in a motion state.
        if bay_obj.state not in ('docking', 'undocking'):
            self._logger.error("Asked to show motion for bay that isn't performing a motion. Will not do!")
            return

        self._logger.debug("Bay has sensor info: {}".format(bay_obj.sensor_info))

        # For easy reference.
        w = self._matrix_width
        h = self._matrix_height
        # Make a base image, black background.
        final_image = Image.new("RGBA", (self._matrix_width, self._matrix_height), (0, 0, 0, 255))

        ## Center area, the range number.
        self._logger.debug("Compositing range placard...")

        # Get the range value from the bay.
        range_reading = bay_obj.sensor_info['reading'][bay_obj.selected_range]
        range_quality = bay_obj.sensor_info['quality'][bay_obj.selected_range]

        range_layer = self._placard_range(
            range_reading,
            range_quality,
            bay_obj.state
        )
        final_image = Image.alpha_composite(final_image, range_layer)

        # ## Bottom strobe box.
        self._logger.debug("Compositing strobe...")
        try:
            if self._bottom_box.lower() == 'strobe':
                final_image = Image.alpha_composite(final_image,
                                                    self._strobe(
                                                        range_quality=range_quality,
                                                        range_pct=bay_obj.range_pct))
            elif self._bottom_box.lower() == 'progress':
                self._logger.debug("Compositing in progress for bottom box.")
                final_image = Image.alpha_composite(final_image,
                                                    self._progress_bar(range_pct=bay_obj.range_pct))
        except AttributeError:
            self._logger.debug("Bottom box disabled.")
            pass

        self._logger.debug("Compositing laterals.")
        for intercept in bay_obj.lateral_sorted:
            self._logger.debug("Lateral: {}".format(intercept.sensor_id))
            sensor_quality = bay_obj.sensor_info['quality'][intercept.sensor_id]
            sensor_reading = bay_obj.sensor_info['reading'][intercept.sensor_id]

            if sensor_quality in (SENSOR_QUALITY_NOTINTERCEPTED, SENSOR_QUALITY_NOOBJ):
                # No intercept shows on both sides.
                combined_layers = Image.alpha_composite(
                    self._layers[bay_obj.id][intercept.sensor_id]['L'][sensor_quality],
                    self._layers[bay_obj.id][intercept.sensor_id]['R'][sensor_quality]
                )
                final_image = Image.alpha_composite(final_image, combined_layers)
            elif sensor_quality in (SENSOR_QUALITY_OK, SENSOR_QUALITY_WARN, SENSOR_QUALITY_CRIT):
                self._logger.debug("Bay's merged config is: {}".format(bay_obj.config_merged))
                # Pick which side the vehicle is offset towards.
                try:
                    if sensor_reading == 0:
                        skew = ('L', 'R')  # In the rare case the value is exactly zero, show both sides.
                    elif bay_obj.config_merged[intercept.sensor_id]['side'] == 'R' and sensor_reading > 0:
                        skew = ('R')
                    elif bay_obj.config_merged[intercept.sensor_id]['side'] == 'R' and sensor_reading < 0:
                        skew = ('L')
                    elif bay_obj.config_merged[intercept.sensor_id]['side'] == 'L' and sensor_reading > 0:
                        skew = ('L')
                    elif bay_obj.config_merged[intercept.sensor_id]['side'] == 'L' and sensor_reading < 0:
                        skew = ('R')
                except TypeError:
                    self._logger.warning("Sensor reading had unexpected value '{}' and type '{}'".
                                         format(sensor_reading, type(sensor_reading)))
                else:
                    self._logger.debug(
                        "Compositing in lateral indicator layer for {} {} {}".format(bay_obj.config_merged[intercept.sensor_id]['name'], skew, sensor_quality))
                    for item in skew:
                        selected_layer = self._layers[bay_obj.id][intercept.sensor_id][item][sensor_quality]
                        final_image = Image.alpha_composite(final_image, selected_layer)
            else:
                combined_layers = Image.alpha_composite(
                    self._layers[bay_obj.id][intercept.sensor_id]['L']['fault'],
                    self._layers[bay_obj.id][intercept.sensor_id]['R']['fault']
                )
                final_image = Image.alpha_composite(final_image, combined_layers)
        self._logger.debug("Returning final image.")
        self.current = final_image

    ## Public Properties
    @property
    def current(self):
        """
        Base64 encoded current version of what's on the display.

        :return:
        """
        return self._current_image

    @current.setter
    def current(self, image):
        """
        Take an image, send it to the display, and save it as a Base64 encoded version for pickup by MQTT.

        :param image: Image to output.
        :type image: Image
        :return:
        """

        # Send to the matrix
        self._matrix.SetImage(image.convert('RGB'))
        # Convert to Base64 and save.
        image_buffer = BytesIO()
        # Put in the staging variable for pickup, base64 encoded.
        image.save(image_buffer, format='PNG')
        self._current_image = b64encode(image_buffer.getvalue())

    @property
    def unit_system(self):
        """
        The current unit system of the display.
        :return:
        """
        return self._unit_system

    @unit_system.setter
    def unit_system(self, the_input):
        """
        Set the unit system

        :param the_input:
        :return:
        """
        if the_input.lower() not in ('imperial', 'metric'):
            raise ValueError("Unit system must be one of 'imperial' or 'metric'. Instead got '{}' ({})".
                             format(the_input, type(the_input)))
        self._unit_system = the_input.lower()

    ## Private Methods
    def _create_matrix(self, width, height, gpio_slowdown):
        """
        Create a matrix with specified parameters

        :param width: Width of the display
        :type width: int
        :param height: Height of the display
        :type height: int
        :param gpio_slowdown: GPIO Slowdown factor for flicker reduction.
        :type gpio_slowdown: int
        :return:
        """
        # Create a matrix. This is hard-coded for now.
        matrix_options = RGBMatrixOptions()
        matrix_options.cols = width
        matrix_options.rows = height
        matrix_options.chain_length = 1
        matrix_options.parallel = 1
        matrix_options.hardware_mapping = 'adafruit-hat-pwm'
        matrix_options.disable_hardware_pulsing = True
        matrix_options.gpio_slowdown = gpio_slowdown
        return RGBMatrix(options=matrix_options)

    def _find_font_size_clock(self, width, height):
        # Clock size can always be
        font_size = None
        for hour in range(0, 24):
            hour = str(hour).zfill(2)
            for minute in range(0, 60):
                minute = str(minute).zfill(2)
                time_string = hour + ":" + minute
                # time_size = self._scale_font(str(time_string), width, height)
                time_size = rgbmultitool.util.scale_font(str(time_string), self._font, width, height)
                if font_size is None:
                    font_size = time_size
                else:
                    if time_size < font_size:
                        font_size = time_size
        return font_size

    def _find_font_size_range(self, depth, min_depth, w=None, h=None):
        # Default the width to the whole matrix
        if w is None:
            w = self._matrix_width
        # Default the height to the whole matrix
        if h is None:
            h = self._matrix_height
        font_size = None
        while depth >= min_depth:
            depth_string = self._range_string(depth)
            print("Trying depth string '{}'".format(depth_string))
            # depth_size = self._scale_font(depth_string, w, h)
            depth_size = rgbmultitool.util.scale_font(depth_string, self._font, w, h)
            if font_size is None:
                font_size = depth_size
            else:
                if depth_size < font_size:
                    font_size = depth_size
            depth = (depth.magnitude - 1) * depth.units
        return font_size

    @staticmethod
    def _frame_lateral(width, height):
        """
        Draw lateral zone frames on either side of the display.
        Border is one pixel, with one pixel down the middle.

        :return:
        """

        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Left Rectangle
        draw.rectangle([(0, 0), (2, height - 5)], width=1)
        # Right Rectangle
        draw.rectangle([(width - 3, 0), (width - 1, height - 5)], width=1)
        return img

    @staticmethod
    def _frame_strobe(width, height):
        """
        Draws the border box for the strobe along the bottom of the display.
        Border is one pixel, with one pixel open in the middle.

        :param width: Width of the matrix
        :type width: int
        :param height: Height of the matrix
        :type height: int
        :return: Image
        """
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle([(0, height - 3), (width - 1, height - 1)], width=1)
        return img

    # def _icon_network(self, net_status=False, mqtt_status=False, x_input=None, y_input=None):
    #     """
    #     Draw a network icon based on current status. Icon will be color coded based on the statuses.
    #     Green = Connected
    #     Red = Not connected
    #     Yellow = Unable to connect because of other errors (ie: MQTT can't connect because network is down)
    #
    #     :param net_status: Network connection status
    #     :type net_status: bool
    #     :param mqtt_status: MQTT broker connection status
    #     :type mqtt_status: bool
    #     :param x_input: X position of the icon. Defaults to 5 pixels from the right side.
    #     :type x_input: int
    #     :param y_input: Y position of the icon. Defaults to 5 pixels from the bottom.
    #     :type y_input: int
    #     :return:
    #     """
    #
    #     # determine the network status color based on combined network and MQTT status.
    #     if net_status is False:
    #         net_color = 'red'
    #         mqtt_color = 'yellow'
    #     elif net_status is True:
    #         net_color = 'green'
    #         if mqtt_status is False:
    #             mqtt_color = 'red'
    #         elif mqtt_status is True:
    #             mqtt_color = 'green'
    #         else:
    #             raise ValueError("Network Icon draw got invalid MQTT status value {}.".format(net_status))
    #     else:
    #         raise ValueError("Network Icon draw got invalid network status value {}.".format(net_status))
    #
    #     # Default to lower right placement if no alternate positions given.
    #     if x_input is None:
    #         x_input = self._matrix_width - 5
    #     if y_input is None:
    #         y_input = self._matrix_height - 5
    #
    #     w = self._matrix_width
    #     h = self._matrix_height
    #     img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    #     draw = ImageDraw.Draw(img)
    #     draw.rectangle([x_input + 1, y_input, x_input + 3, y_input + 2], outline=mqtt_color, fill=mqtt_color)
    #     # Base network line.
    #     draw.line([x_input, y_input + 4, x_input + 4, y_input + 4], fill=net_color)
    #     # Network stem
    #     draw.line([x_input + 2, y_input + 3, x_input + 2, y_input + 4], fill=net_color)
    #     return img

    def _icon_vehicle(self, x_input=None, y_input=None):
        # Defaults because you can't reference object variables in parameters.
        # Default to lower_left.
        if x_input is None:
            x_input = 0
        if y_input is None:
            y_input = self._matrix_height

        w = self._matrix_width
        h = self._matrix_height
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Draw the vehicle box.

        draw.rectangle([x_input + 2, y_input, x_input + 4, y_input - 5], outline='green', fill='green')
        # Lateral sensor. Presuming one!
        draw.line([x_input + 3, y_input - 7, x_input + 3, y_input - 7],
                  fill=self._status_color(SENSOR_QUALITY_WARN)['fill'])
        # Lateral sensors.
        return img

    # def _output_image(self, image):
    #     """
    #     Send an image to the display.
    #
    #     :param image:
    #     :return:
    #     """
    #     # Send to the matrix
    #     self._matrix.SetImage(image.convert('RGB'))
    #
    #     image_buffer = BytesIO()
    #     # Put in the staging variable for pickup, base64 encoded.
    #     image.save(image_buffer, format='PNG')
    #     self.current = b64encode(image_buffer.getvalue())

    # Divide into roughly equal parts. Found this here:
    # https://stackoverflow.com/questions/52697875/split-number-into-rounded-numbers
    @staticmethod
    def _parts(a, b):
        q, r = divmod(a, b)
        return [q + 1] * r + [q] * (b - r)

    def _placard(self, text, color, font_size=None, w_adjust=8, h_adjust=4):
        """
        Write arbitrary text on the image in the appropriate size.

        :param text: Text to format
        :type text: str
        :param color: Color of the text
        :param font_size: Font size of the text. Will auto-scale if not provided.
        :type font_size: int
        :param w_adjust: Margin for the width. Will be divded equally from the left and right
        (ie: w_adjust=8 takes 4 pixels from left and right)
        :type w_adjust: int
        :param h_adjust: Margin for the height. Shifts upward from the bottom of the display.
        :type h_adjust: int
        :return: Image
        """
        img = Image.new("RGBA", (self._matrix_width, self._matrix_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # If no font size was specified, dynamically size the text to fit the space we have.
        if font_size is None:
            font_size = self._scale_font(text, self._matrix_width - w_adjust, self._matrix_height - h_adjust)
            # self._logger.debug("Calling RGBMT scale_font with font: {} ({})".format(self._font, type(self._font)))
            # font_size = rgbmultitool.util.scale_font(text, self._font, self._matrix_width - w_adjust, self._matrix_height - h_adjust)
        font = ImageFont.truetype(font=self._font, size=font_size)
        # Make the text. Center it in the middle of the area, using the derived font size.
        draw.text((self._matrix_width / 2, (self._matrix_height - 4) / 2), text,
                  fill=ImageColor.getrgb(color), font=font, anchor="mm")
        return img

    def _placard_range(self, input_range, range_quality, bay_state):
        """

        :param input_range: Range to display
        :param range_quality: Range quality, used to color-code the text.
        :param bay_state: Operating state of the bay. Used to determine which
        :return:
        """
        self._logger.debug("Creating range placard with range {} and quality {}".format(input_range, range_quality))
        # Define a default range string. This should never show up.
        range_string = "NOVAL"
        text_color = 'white'

        # Override string states. If the range quality has these values, we go ahead and show the string rather than the
        # measurement.
        if range_quality == SENSOR_QUALITY_BACKUP:
            return self._layers['backup']
        elif range_quality in (SENSOR_QUALITY_DOOROPEN, SENSOR_QUALITY_BEYOND):
            # DOOROPEN is when the detector cannot get a reflection, ie: the door is open.
            # BEYOND is when a reading is found but it's beyond the defined length of the bay.
            # Either way, this indicates either no vehicle is present yet, or a vehicle is present but past the garage
            # door
            if bay_state == BAYSTATE_DOCKING:
                return self._layers['approach']
            elif bay_state == BAYSTATE_UNDOCKING:
                return self._layers['clear']
        elif input_range == 'unknown':
            return self._layers['noval']
        else:
            try:
                range_converted = input_range.to(self._target_unit)
            except AttributeError:
                self._logger.warning("Placard input range was '{}' ({}), cannot convert. Using raw input".
                                     format(input_range, type(input_range)))
                range_string = input_range
            else:
                range_string = self._range_string(range_converted)

        # Determine a color based on quality
        if range_quality in ('critical', 'back_up'):
            text_color = 'red'
        elif range_quality == 'warning':
            text_color = 'yellow'
        elif range_quality == 'door_open':
            text_color = 'white'
        else:
            text_color = 'green'
        # Now we can get it formatted and return it.
        self._logger.debug("Requesting placard with range string {} in color {}".format(range_string, text_color))
        return self._placard(range_string, text_color)

    @staticmethod
    def _pm_indicator(width, height):
        """
        Draw a PM indicator

        :param width: Width of the display
        :type width: int
        :param height: Height of the display
        :type height: int
        :return: Image
        """
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle((width-2, 0, width, 2), fill='green', outline='green', width=1)
        return img

    def _progress_bar(self, range_pct):
        """
        Draw a progress bar based on percentage of range covered.

        :param range_pct:
        :return: Image
        """
        img = Image.new("RGBA", (self._matrix_width, self._matrix_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, self._matrix_width - 1, self._matrix_height - 1), fill=None, outline='white', width=1)
        self._logger.debug("Total matrix width: {}".format(self._matrix_width))
        self._logger.debug("Range percentage: {}".format(range_pct))
        progress_pixels = int((self._matrix_width - 2) * range_pct)
        self._logger.debug("Progress bar pixels: {}".format(progress_pixels))
        draw.line((1, self._matrix_height - 2, 1 + progress_pixels, self._matrix_height - 2), fill='green', width=1)
        return img

    def _range_string(self, input_range):
        """
        Format a given range into a string for display.

        :param input_range:
        :param unit_system:
        :return: str
        """
        if self.unit_system == 'imperial':
            if abs(input_range.magnitude) < 12:
                range_string = "{}\"".format(round(input_range.magnitude, 1))
            else:
                feet = int(input_range.to("in").magnitude // 12)
                inches = round(input_range.to("in").magnitude % 12)
                range_string = "{}'{}\"".format(feet, inches)
        else:
            range_meters = input_range.to("m").magnitude
            if range_meters <= 0.5:
                range_string = "{} cm".format(round(range_meters / 100, 2))
            else:
                range_string = "{} m".format(round(range_meters, 2))
        return range_string

    @staticmethod
    def _rectangle_striped(input_image, start, end, pricolor='red', seccolor='yellow'):
        """
        Create a rectangled with zebra-stripes at a 45-degree angle.

        :param input_image: Image to draw onto
        :type input_image: Image
        :param start: Start coordinates, X, Y
        :type start: tuple or list
        :param end: End coordinates, X, Y
        :type end: tuple or list
        :param pricolor: Primary color.
        :param seccolor: Secondary color.
        :return: Image
        """
        # Simple breakout of input. Replace with something better later, maybe.
        x_start = start[0]
        y_start = start[1]
        x_end = end[0]
        y_end = end[1]

        # Create a drawing object on the provided image.
        draw = ImageDraw.Draw(input_image)

        # Start out with the primary color.
        current_color = pricolor
        # track current column.
        current_x = x_start - (y_end - y_start)
        current_y = y_start
        while current_x <= x_end:
            line_start = [current_x, y_start]
            line_end = [current_x + (y_end - y_start), y_end]
            # Trim the lines.
            if line_start[0] < x_start:
                diff = x_start - line_start[0]
                # Move the X start to the right and the Y start down.
                line_start = [x_start, y_start + diff]
            if line_end[0] > x_end:
                diff = line_end[0] - x_end
                # Move the X start back to the left and the Y start up.
                line_end = [x_end, y_end - diff]
            draw.line([line_start[0], line_start[1], line_end[0], line_end[1]],
                      fill=current_color,
                      width=1
                      )
            # Rotate the color.
            if current_color == pricolor:
                current_color = seccolor
            else:
                current_color = pricolor
            # Increment the current X
            current_x += 1
        return input_image

    def _scale_font(self, text, w, h):
        # Start at font size 1.
        fontsize = 1
        while True:
            font = ImageFont.truetype(font=self._font, size=fontsize)
            bbox = font.getbbox(text)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            if text_width < w and text_height < h:
                fontsize += 1
            else:
                break
        return fontsize

    def _setup_layers(self):
        """
        Create static layers that can be composited as needed.

        :return:
        """
        # Initialize the layers.
        self._layers['frame_approach'] = self._frame_strobe(self._matrix_width, self._matrix_height)
        self._layers['frame_lateral'] = self._frame_lateral(self._matrix_width, self._matrix_height)
        self._layers['approach'] = self._placard('APPROACH', 'blue')
        self._layers['clear'] = self._placard('CLEAR!', 'white')
        self._layers['backup'] = self._placard('BACK UP!', 'red')
        self._layers['noval'] = self._placard('NOVAL', 'red')
        self._layers['error'] = self._placard('ERROR', 'red')
        self._layers['offline'] = self._placard('OFFLINE', 'white')
        self._layers['pm_indicator'] = self._pm_indicator(self._matrix_width, self._matrix_height)

    def _status_color(self, status):
        """
        Convert a status into a color
        :param status:
        :return:
        """
        # Pre-defined quality-color mappings.
        color_table = {
            SENSOR_QUALITY_OK: {'border': (0, 128, 0, 255), 'fill': (0, 128, 0, 255)},
            SENSOR_QUALITY_WARN: {'border': (255, 255, 0, 255), 'fill': (255, 255, 0, 255)},
            SENSOR_QUALITY_CRIT: {'border': (255, 0, 0, 255), 'fill': (255, 0, 0, 255)},
            SENSOR_QUALITY_NOOBJ: {'border': (255, 255, 255, 255), 'fill': (0, 0, 0, 0)}
        }
        try:
            return color_table[status]
        except KeyError:
            # Since red is used for 'critical', blue is the 'error' color.
            return {'border': (0, 255, 255, 0), 'fill': (0, 255, 255, 0)}

    ## Private Properties
    @property
    def _target_unit(self):
        """
        Unit for output conversion, determined by the overall unit system.
        Imperial always uses inches, metric always uses meters.
        :return:
        """

        if self.unit_system == 'imperial':
            return 'in'
        elif self.unit_system == 'metric':
            return 'm'
        else:
            return None
