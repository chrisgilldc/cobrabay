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
from CobraBay.const import *

ureg = UnitRegistry()
# TODO: Reorganize class to standard.
# FIXME: Pre-Bake font scaling.

class CBDisplay:
    def __init__(self,
                 width,
                 height,
                 gpio_slowdown,
                 font,
                 cbcore,
                 bottom_box=None,
                 unit_system="metric",
                 mqtt_image=True,
                 mqtt_update_interval=None,
                 strobe_speed=None,
                 log_level="WARNING"):
        """

        :param unit_system: Unit system. "imperial" or "metric", defaults to "metric"
        :type unit_system: str
        :param width: Width of the LED matrix, in pixels
        :type width: int
        :param height: Height of the LED matrix, in pixels
        :type height: int
        :param gpio_slowdown: GPIO pacing to prevent flicker
        :type gpio_slowdown: int
        :param bottom_box: Which bottom box to be. Can be "strobe", "progress" or "none"
        :type bottom_box: str
        :param strobe_speed: How fast the strober bugs should move.
        :type strobe_speed: Quantity(ms)
        :param font: Path to the font to use. Must be a TTF.
        :type font: Path
        :param cbcore: Reference to the Core object
        """
        # Get a logger!
        self._logger = logging.getLogger("CobraBay").getChild("Display")
        self._logger.setLevel(log_level.upper())
        self._logger.info("Display initializing...")
        self._logger.info("Display unit system: {}".format(unit_system))
        
        # Save parameters
        self._matrix_width = width
        self._matrix_height = height
        self._bottom_box = bottom_box
        self._strobe_speed = strobe_speed
        self._unit_system = unit_system
        # Based on unit system, set the target unit.
        if self._unit_system.lower() == 'imperial':
            self._target_unit = 'in'
        else:
            self._target_unit = 'm'
        self._cbcore = cbcore

        self._core_font = font

        # Operating settings. These get reset on every start.
        self._running = {'strobe_offset': 0, 'strobe_timer': monotonic_ns()}
        self._current_image = None

        # Layers dict.
        self._layers = {
            'lateral': {}
        }

        # Create static layers
        self._setup_layers()

        # Set up the matrix object itself.
        self._create_matrix(self._matrix_width, self._matrix_height, gpio_slowdown)

    # Method to set up image layers for use. This takes a command when the bay is ready so lateral zones can be prepped.
    def _setup_layers(self):
        # Initialize the layers.
        self._layers['frame_approach'] = self._frame_approach()
        self._layers['frame_lateral'] = self._frame_lateral()
        self._layers['approach'] = self._placard('APPROACH','blue')
        self._layers['error'] = self._placard('ERROR','red')

    # Have a bay register. This creates layers for the bay in advance so they can be composited faster.
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
        # If no lateral detectors are defined, do nothing else.
        if len(bay_obj.lateral_sorted) == 0:
            return

        # For convenient reference later.
        w = self._matrix_width
        h = self._matrix_height

        # Calculate the available pixels for each zones.
        avail_height = self._matrix_height - 6  #
        pixel_lengths = self._parts(avail_height, len(bay_obj.lateral_sorted))
        self._logger.debug("Split {} pixels for {} lateral zones into: {}".
                           format(avail_height,len(bay_obj.lateral_sorted),pixel_lengths))

        # Eventually replace this with the _status_color method.
        status_lookup = (
            {'status': DETECTOR_QUALITY_OK, 'border': (0,128,0,255), 'fill': (0,128,0,255)},
            {'status': DETECTOR_QUALITY_WARN, 'border': (255,255,0,255), 'fill': (255,255,0,255)},
            {'status': DETECTOR_QUALITY_CRIT,'border': (255,0,0,255), 'fill': (255,0,0,255)},
            {'status': DETECTOR_QUALITY_NOOBJ, 'border': (255,255,255,255), 'fill': (0,0,0,0)}
        )

        i = 0
        # Add in the used height of each bar to this variable. Since they're not guaranteed to be the same, we can't
        # just multiply.
        accumulated_height = 0
        for intercept in bay_obj.lateral_sorted:
            lateral = intercept.lateral
            self._logger.debug("Processing lateral zone: {}".format(lateral))
            self._layers[bay_obj.id][lateral] = {}
            for side in ('L','R'):
                self._layers[bay_obj.id][lateral][side] = {}
                if side == 'L':
                    line_w = 0
                    nointercept_x = 1
                elif side == 'R':
                    line_w = w - 3
                    nointercept_x = w-2
                else:
                    raise ValueError("Not a valid side option, this should never happen!")

                # Make an image for the 'fault' status.
                img = Image.new('RGBA', (w, h), (0,0,0,0))
                # Make a striped box for fault.
                img = self._rectangle_striped(
                    img,
                    (line_w, 1 + accumulated_height),
                    (line_w + 2, 1 + accumulated_height + pixel_lengths[i]),
                    pricolor='red',
                    seccolor='yellow'
                )
                self._layers[bay_obj.id][lateral][side]['fault'] = img
                del(img)

                # Make an image for no_object
                img = Image.new('RGBA', (w, h), (0,0,0,0))
                # Draw white lines up the section.
                draw = ImageDraw.Draw(img)
                draw.line([nointercept_x,1 + accumulated_height,nointercept_x,1 + accumulated_height + pixel_lengths[i]],
                          fill='white', width=1)
                self._layers[bay_obj.id][lateral][side][DETECTOR_NOINTERCEPT] = img
                del(img)

                for item in status_lookup:
                    self._logger.debug("Creating layer for side {}, status {} with border {}, fill {}."
                                       .format(side, item['status'], item['border'], item['fill']))
                    # Make the image.
                    img = Image.new('RGBA', (w, h), (0,0,0,0))
                    draw = ImageDraw.Draw(img)
                    # Draw the rectangle
                    draw.rectangle(
                        [line_w,1 + accumulated_height,line_w+2,1 + accumulated_height + pixel_lengths[i]],
                        fill=item['fill'],
                        outline=item['border'],
                        width=1)
                    # Put this in the right place in the lookup.
                    self._layers[bay_obj.id][lateral][side][item['status']] = img
                    # Write for debugging
                    # img.save("/tmp/CobraBay-{}-{}-{}.png".format(lateral,side,status[0]), format='PNG')
                    del(draw)
                    del(img)

            # Now add the height of this bar to the accumulated height, to get the correct start for the next time.
            accumulated_height += pixel_lengths[i]
            # Increment to the next zone.
            i += 1
        self._logger.debug("Created laterals for {}: {}".format(bay_obj.id, self._layers[bay_obj.id]))

    # General purpose message displayer
    def show(self, mode, system_status=None,  message=None, color="white", icons=True):
        """
        Show a general-purpose message on the display.

        :param system_status: Dict with the current network and mqtt connection status
        :type system_status: dict(network, mqtt)
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

        if mode == 'clock':
            string = datetime.now().strftime("%-I:%M %p")
            # Clock is always in green.
            color = "green"
        elif mode == 'message':
            if message is None:
                raise ValueError("Show requires a message when used in Message mode.")
            string = message
        else:
            raise ValueError("Show mode '{}' is not valid. Must be 'clock' or 'message'.".format(mode))

        # Make a base layer.
        img = Image.new("RGBA", (self._matrix_width, self._matrix_height), (0,0,0,255))
        # If enabled, put status icons at the bottom of the display.
        if icons and (system_status is not None):
            # Network status icon, shows overall network and MQTT status.
            network_icon = self._icon_network(system_status['network'],system_status['mqtt'])
            img = Image.alpha_composite(img, network_icon)
            # Adjust available placard height so we don't stomp over the icons.
            placard_h=6
        elif icons and (system_status is None):
            self._logger.warning("Icons requested but system status not provided. Skipping.")
            placard_h = 0
        else:
            placard_h = 0

        # Placard with the text.
        placard = self._placard(string, color, w_adjust=0, h_adjust=placard_h)
        img = Image.alpha_composite(img, placard)
        # Send it to the display!
        self._output_image(img)

    # Specific displayer for docking.
    def show_motion(self, direction, bay_obj):
        self._logger.debug("Show Motion received bay '{}'".format(bay_obj.name))

        # Don't do motion display if the bay isn't in a motion state.
        if bay_obj.state not in ('docking','undocking'):
            self._logger.error("Asked to show motion for bay that isn't performing a motion. Will not do!")
            return

        # For easy reference.
        w = self._matrix_width
        h = self._matrix_height
        # Make a base image, black background.
        final_image = Image.new("RGBA", (w, h), (0,0,0,255))

        ## Center area, the range number.
        self._logger.debug("Compositing range placard...")
        range_layer = self._placard_range(
            bay_obj.range.value,
            bay_obj.range.quality,
            bay_obj.state
        )
        final_image = Image.alpha_composite(final_image, range_layer)


        # ## Bottom strobe box.
        self._logger.debug("Compositing strobe...")
        try:
            if self._bottom_box.lower() == 'strobe':

                final_image = Image.alpha_composite(final_image,
                                                    self._strobe(
                                                        range_quality=bay_obj.range.quality,
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
            detector = bay_obj.detectors[intercept.lateral]
            # Hit the detector quality once. There's a slim chance this could change during the course of evaluation and
            # lead to wonky results.
            dq = detector.quality
            dv = detector.value
            if dq in (DETECTOR_NOINTERCEPT, DETECTOR_QUALITY_NOOBJ):
                # No intercept shows on both sides.
                combined_layers = Image.alpha_composite(
                    self._layers[bay_obj.id][detector.id]['L'][dq],
                    self._layers[bay_obj.id][detector.id]['R'][dq]
                )
                final_image = Image.alpha_composite(final_image, combined_layers)
            elif dq in (DETECTOR_QUALITY_OK, DETECTOR_QUALITY_WARN, DETECTOR_QUALITY_CRIT):
                # Pick which side the vehicle is offset towards.
                if detector.value == 0:
                    skew = ('L','R')  # In the rare case the value is exactly zero, show both sides.
                elif detector.side == 'R' and dv > 0:
                    skew = ('R')
                elif detector.side == 'R' and dv < 0:
                    skew = ('L')
                elif detector.side == 'L' and dv > 0:
                    skew = ('L')
                elif detector.side == 'L' and dv < 0:
                    skew = ('R')

                self._logger.debug("Compositing in lateral indicator layer for {} {} {}".format(detector.name, skew, dq))
                for item in skew:
                    selected_layer = self._layers[bay_obj.id][detector.id][item][dq]
                    final_image = Image.alpha_composite(final_image, selected_layer)
            else:
                combined_layers = Image.alpha_composite(
                    self._layers[bay_obj.id][detector.id]['L']['fault'],
                    self._layers[bay_obj.id][detector.id]['R']['fault']
                )
                final_image = Image.alpha_composite(final_image, combined_layers)
        self._logger.debug("Returning final image.")
        self._output_image(final_image)

    def _strobe(self, range_quality, range_pct):
        '''
        Construct a strober for the display.

        :param range_quality: Quality value of the range detector.
        :type range_quality: str
        :param range_pct: Percentage of distance from garage door to the parking point.
        :return:
        '''
        w = self._matrix_width
        h = self._matrix_height
        # Set up a base image to draw on.
        img = Image.new("RGBA", (w, h), (0,0,0,0))
        draw = ImageDraw.Draw(img)
        # Back up and emergency distances, we flash the whole bar.
        if range_quality in ('back_up','emergency'):
            if monotonic_ns() > self._running['strobe_timer'] + self._strobe_speed:
                try:
                    if self._running['strobe_color'] == 'red':
                        self._running['strobe_color'] = 'black'
                    elif self._running['strobe_color'] == 'black':
                        self._running['strobe_color'] = 'red'
                except KeyError:
                    self._running['strobe_color'] = 'red'
                self._running['strobe_timer'] = monotonic_ns()
            # draw.line([(1,h-2),(w-2,h-2)], fill=self._running['strobe_color'])
            draw.rectangle([(1,h-3),(w-2,h-1)], fill=self._running['strobe_color'])
        else:
            # If we need to back up, have blockers be zero
            if range_quality == 'back_up':
                blocker_width = 0
            else:
                # Calculate where the blockers need to be.
                available_width = (w-2)/2
                blocker_width = math.floor(available_width * (1-range_pct))
            self._logger.debug("Strober blocker width: {}".format(blocker_width))
            # Because of rounding, we can wind up with an entirely closed bar if we're not fully parked.
            # Thus, fudge the space unless we're okay.
            if range_quality != 'ok' and blocker_width > 28:
                blocker_width = 28
            # Draw the blockers.
            #draw.line([(1, h-2),(blocker_width+1, h-2)], fill="white")
            #draw.line([(w-blocker_width-2, h-2), (w-2, h-2)], fill="white")
            # If we're fully parked the line is full and there's nowhere for the bugs, so don't bother.
            if blocker_width < 30:
                left_strobe_start = blocker_width+2+self._running['strobe_offset']
                left_strobe_stop = left_strobe_start + 3
                if left_strobe_stop > (w/2)-1:
                    left_strobe_stop = (w/2)-1
                # draw.line([(left_strobe_start, h-2),(left_strobe_stop,h-2)], fill="red")
                draw.rectangle([(left_strobe_start, h - 3), (left_strobe_stop, h - 1)], fill="red")
                right_strobe_start = w - 2 - blocker_width - self._running['strobe_offset']
                right_strobe_stop = right_strobe_start - 3
                if right_strobe_stop < (w/2)+1:
                    right_strobe_stop = (w/2)+1
                # draw.line([(right_strobe_start, h - 2), (right_strobe_stop, h - 2)], fill="red")
                draw.rectangle([(right_strobe_start, h - 3), (right_strobe_stop, h - 1)], fill="red")
            # If time is up, move the strobe bug forward.
            if monotonic_ns() > self._running['strobe_timer'] + self._strobe_speed:
                self._running['strobe_offset'] += 1
                self._running['strobe_timer'] = monotonic_ns()
                # Don't let the offset push the bugs out to infinity.
                if self._running['strobe_offset'] > (w/2) - blocker_width:
                    self._running['strobe_offset'] = 0
        return img

    # Methods to create image objects that can then be composited.
    def _frame_approach(self):
        w = self._matrix_width
        h = self._matrix_height
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle([(0, h - 3), (w - 1, h - 1)], width=1)
        return img

    def _frame_lateral(self):
        # Localize matrix width and height, just to save readability
        w = self._matrix_width
        h = self._matrix_height
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Left Rectangle
        draw.rectangle([(0, 0), (2, h-5)], width=1)
        # Right Rectangle
        draw.rectangle([(w-3, 0), (w-1, h-5)], width=1)
        return img

    def _icon_network(self, net_status=False, mqtt_status=False, x_input=None, y_input=None):
        # determine the network status color based on combined network and MQTT status.
        if net_status is False:
            net_color = 'red'
            mqtt_color = 'yellow'
        elif net_status is True:
            net_color = 'green'
            if mqtt_status is False:
                mqtt_color = 'red'
            elif mqtt_status is True:
                mqtt_color = 'green'
            else:
                raise ValueError("Network Icon draw got invalid MQTT status value {}.".format(net_status))
        else:
            raise ValueError("Network Icon draw got invalid network status value {}.".format(net_status))

        # Default to lower right placement if no alternate positions given.
        if x_input is None:
            x_input = self._matrix_width-5
        if y_input is None:
            y_input = self._matrix_height-5

        w = self._matrix_width
        h = self._matrix_height
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle([x_input+1,y_input,x_input+3,y_input+2], outline=mqtt_color, fill=mqtt_color)
        # Base network line.
        draw.line([x_input,y_input+4,x_input+4,y_input+4],fill=net_color)
        # Network stem
        draw.line([x_input+2,y_input+3,x_input+2,y_input+4], fill=net_color)
        return img

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

        draw.rectangle([x_input+2,y_input,x_input+4,y_input-5], outline='green', fill='green')
        # Lateral sensor. Presuming one!
        draw.line([x_input+3,y_input-7,x_input+3,y_input-7],fill=self._status_color(DETECTOR_QUALITY_WARN)['fill'])
        # Lateral sensors.
        return img

    def _status_color(self, status):
        """
        Convert a status into a color
        :param status:
        :return:
        """
        # Pre-defined quality-color mappings.
        color_table = {
            DETECTOR_QUALITY_OK: {'border': (0,128,0,255), 'fill': (0,128,0,255)},
            DETECTOR_QUALITY_WARN: {'border': (255,255,0,255), 'fill': (255,255,0,255)},
            DETECTOR_QUALITY_CRIT: {'border': (255,0,0,255), 'fill': (255,0,0,255)},
            DETECTOR_QUALITY_NOOBJ: {'border': (255,255,255,255), 'fill': (0,0,0,0)}
        }
        try:
            return color_table[status]
        except KeyError:
            # Since red is used for 'critical', blue is the 'error' color.
            return {'border': (0, 255, 255, 0 ), 'fill': (0,255,255,0)}


    # Make a placard to show range.
    def _placard_range(self, input_range, range_quality, bay_state):
        self._logger.debug("Creating range placard with range {} and quality {}".format(input_range, range_quality))
        # Define a default range string. This should never show up.
        range_string = "NOVAL"
        text_color = 'white'

        # Override string states. If the range quality has these values, we go ahead and show the string rather than the
        # measurement.
        if range_quality == DETECTOR_QUALITY_BACKUP:
            range_string = "BACK UP!"
        elif range_quality in (DETECTOR_QUALITY_DOOROPEN, DETECTOR_QUALITY_BEYOND):
            # DOOROPEN is when the detector cannot get a reflection, ie: the door is open.
            # BEYOND is when a reading is found but it's beyond the defined length of the bay.
            # Either way, this indicates either no vehicle is present yet, or a vehicle is present but past the garage
            # door
            if bay_state == BAYSTATE_DOCKING:
                range_string = "APPROACH"
                text_color = 'blue'
            elif bay_state == BAYSTATE_UNDOCKING:
                range_string = "CLEAR!"
                text_color = 'white'
        elif input_range == 'unknown':
            range_string = "Unknown"
        else:
            try:
                range_converted = input_range.to(self._target_unit)
            except AttributeError:
                self._logger.warning("Placard input range was '{}' ({}), cannot convert. Using raw input".
                                     format(input_range, type(input_range)))
                range_string = input_range
            else:
                if self._unit_system.lower() == 'imperial':
                    if range_converted.magnitude < 12:
                        range_string = "{}\"".format(round(range_converted.magnitude,1))
                    else:
                        feet = int(range_converted.to(ureg.inch).magnitude // 12)
                        inches = round(range_converted.to(ureg.inch).magnitude % 12)
                        range_string = "{}'{}\"".format(feet,inches)
                else:
                    range_string = "{} m".format(round(range_converted.magnitude,2))

        # Determine a color based on quality
        if range_quality in ('critical','back_up'):
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

    # Generalized placard creator. Make an image for arbitrary text.
    def _placard(self,text,color,w_adjust=8,h_adjust=4):
        # Localize matrix and adjust.
        w = self._matrix_width
        h = self._matrix_height
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Find the font size we can use.
        font = ImageFont.truetype(font=self._core_font,
                                  size=self._scale_font(text, w-w_adjust, h-h_adjust))
        # Make the text. Center it in the middle of the area, using the derived font size.
        draw.text((w/2, (h-4)/2), text, fill=ImageColor.getrgb(color), font=font, anchor="mm")
        return img

    def _progress_bar(self, range_pct):
        img = Image.new("RGBA", (self._matrix_width, self._matrix_height), (0,0,0,0))
        draw = ImageDraw.Draw(img)
        draw.rectangle((0,0,self._matrix_width-1,self._matrix_height-1),fill=None, outline='white', width=1)
        self._logger.debug("Total matrix width: {}".format(self._matrix_width))
        self._logger.debug("Range percentage: {}".format(range_pct))
        progress_pixels = int((self._matrix_width-2)*range_pct)
        self._logger.debug("Progress bar pixels: {}".format(progress_pixels))
        draw.line((1,self._matrix_height-2,1+progress_pixels,self._matrix_height-2),fill='green', width=1)
        return img

    # Utility method to find the largest font size that can fit in a space.
    def _scale_font(self, text, w, h):
        # Start at font size 1.
        fontsize = 1
        while True:
            font = ImageFont.truetype(font=self._core_font, size=fontsize)
            bbox = font.getbbox(text)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            if text_width < w and text_height < h:
                fontsize += 1
            else:
                break
        return fontsize

    # Create a two-color, 45 degree striped rectangle
    @staticmethod
    def _rectangle_striped(input_image, start, end, pricolor='red', seccolor='yellow'):
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
        # image.save("/tmp/CobraBay-display.png", format='PNG')

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
