####
# Cobra Bay Library
####


import adafruit_aw9523, board, digitalio, displayio, framebufferio, rgbmatrix, sys, time, terminalio 
from adafruit_hcsr04 import HCSR04
from adafruit_display_text.label import Label
from adafruit_bitmap_font import bitmap_font
from adafruit_display_text import bitmap_label
from math import floor, ceil

class CobraBay:   
    def _CreateSensor(self,board,sensor_type, options):
       
        # The HC-SR04 sensor, or US-100 in HC-SR04 compatibility mode
        if sensor_type == 'hc-sr04':
            
            # Confirm trigger, echo and board are set. These are *required*.
            for parameter in ('board','trigger','echo'):
                if parameter not in options:
                    raise ValueError
                    return parameter
            # Set a custom timeout if necessary
                if 'timeout' not in options:
                    timeout = 0.1
                else:
                    timeout = options['timeout']
            
            # Check for going via an AW9523, and set it up that way.
            if config['board'] in ('0x58','0x59','0x5A','0x5B'):
                # If the desired board hasn't been initialized yet, do so.
                if options['board'] not in self.gpio_boards:
                    self.gpio_boards[options['board']] = adafruit_aw9523.AW9523(board.I2C,address=config['board'])
                return adafruit_hcsr04(
                    trigger=self.gpio_boards[options['board']].get_pin(options['trigger']),
                    echo=self.gpio_boards[options['board']].get_pin(options['echo']),
                    timeout)
            # If it's 'local', set up 
            elif config['board'] == 'local':
                # Use the exec call to convert the inbound pin number to the actual pin objects
                exec("tp = board.D{}".format(trigger))
                exec("ep = board.D{}".format(echo))
                return adafruit_hcsr04(trigger=tp,echo=ep,timeout)
                
        # VL53L1X sensor.
        elif sensor_type == 'vl53':
            
            
            
    # Provides a uniform interface to access different types of sensors.
    def _CheckSensor(self,sensor,sensor_type):
        if sensor_type == 'hc-sr04':
            
    
    def __init__(self,config):
        # Release any existing displays. Shouldn't be necessary during normal operations.
        displayio.release_displays()
        
        
        # Holding dicts
        self.sensors = {} # Holds sensors.
        self.ranges = {} # ranges as reported by each individual sensor
        self.status = {} # Processed status
        
        # Set up an internal dict for storing validated and processed config
        # Pre-loaded with defaults for optional parameters.
        self.config = {
            'approach_strobe_speed': 100, # Default to 100ms
            'units': 'metric', # Default to metric, which is the native
            'range_multiplier': 1, # Since metric is default, we don't need to modify the range units, since it's natively in centimeters.
            'sensor_pacing': 0.5
            }
        
        # Boards with GPIO pins. Always has 'local' as the native board. Can add additional boards (ie: AW9523) during initialization.
        self.gpio_boards = { 'local': board }
        
        # Set up variables from the input configuration
        ## Maximum detection range
        try:
            self.config['max_detect_range'] = config['max_detect_range']
        except:
            print("Maximum detect range must be configured.")
            sys.exit(1)
        
        # Try to pull over values from the config array. If present, they'll overwrite the default. If not, the default stands.
        for config_value in ('sensor_pacing','speed_limit','approach_strobe_speed'):
            try:
                self.config[config_value] = config[config_value]
            except:
                pass
        
        ### Default the current range to the max range + 100. This should trigger approach.
        self.current_range = self.config['max_detect_range'] + 100
        
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

        # Valid sensor names. Filter for this so we don't just allow *anything* in.
        valid_sensors = ('center','center_left','center_right','left','right','left_front','left_rear','right_front','right_rear')

        for sensor_name in config['pins']
            if sensor_name in valid_sensors:
                if board not in config['pins'][sensor_name]:
                    board = 
                else:
                    board = config['pins'][sensor_name]['board']
                try:
                    this_trigger_pin = sensor_controller.get_pin(config['pins'][sensor_name]['trigger'])
                    this_echo_pin = sensor.controller.get_pin(config['pins'][sensor_name]['echo'])
                
                
                    self.sensors[sensor_name] = HCSR04(
                        trigger_pin=config['pins'][sensor_name]['trigger'], 
                        echo_pin=config['pins'][sensor_name]['echo'], 
                        timeout=config['pins'][sensor_name]['timeout'])


            else:
               print("Invalid sensor name '" + sensor + ' found. Correct and restart!")
               sys.exit(1)
               
               
        for sensor_name in ('center_left', 'center_right'):
                # If an override is defined in the config, use that, otherwise, take the default.
                if sensor_name in config['pins']:

                else:
                    self.sensors[sensor_name] = HCSR04(
                        trigger_pin=default_pins[sensor_name]['trigger'],
                        echo_pin=default_pins[sensor_name]['echo'],
                        timeout=default_pins[sensor_name]['timeout'])

        # Initialize a list for every defined sensor.
        for sensor_name in self.sensors.keys():
            self.ranges[sensor_name] = []

        # Set an easy-to-process flag for if dual-center sensors are available.
        if 'center_left' in self.sensors and 'center_right' in self.sensors:
            self.config['center_dual'] = True
        else:
            self.config['center_dual'] = False

        # Other initialization

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
        
    # Create some artificial sensor data. Useful for testing the display when
    # sensors aren't connected
    def _SimulateSensors(self):
        self.current_range = 276 - ((time.time() - self.start_time) * 17)
        if self.current_range <= 0:
            self.current_range = 300
            self.start_time = time.time() + 10
        return

    def _UpdateSensor(self,sensor):
        # Try to get a new range and add it to the list for this sensor.
        try:
            self.ranges[sensor].append(self.sensors[sensor].distance)
        except RuntimeError:
            pass
        
        # Remove the oldest element if we have more than 10.
        while len(self.ranges[sensor]) > 10:
            del self.ranges[sensor][0]

        # Find the mode of the distance.
        mode = max(set(self.ranges[sensor]),key=self.ranges[sensor].count)
        print("Range array: " + str(self.ranges[sensor]))
        print("Mode: " + str(mode))
        
    def _DisplayDistance(self):
        # Positioning for labels
        label_position = ( 
            floor(self.display.width / 2), # X - Middle of the display
            floor( ( self.display.height - 4 ) / 2) ) # Y - half the height, with space removed for the approach strobe
        
        # Calculate actual range
        range_feet = floor(self.status['range'] / 12)
        range_feet = floor(self.status['range'] / 12)
        range_inches = self.status['range'] % 12  
        print("ft: " + str(range_feet) + " in: " + str(range_inches))

        # Figure out proper coloring
        if self.status['range'] <= 12:
            range_color = 0xFF0000
        elif self.status['range'] <= 48:
            range_color = 0xFFFF00
        elif self.status['range'] > self.config['max_detect_range']:
            range_color = 0x0000FF
        else:
            range_color = 0x00FF00

        # Decide which to display.
        
        range_group = displayio.Group()
        
        if self.status['range'] >= self.config['max_detect_range']:
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
                text=str(range_feet) + "'" + str(range_inches) + '"',
                color=range_color,
                anchor_point = (0.4,0.5),
                anchored_position = label_position
                )
            range_group.append(range_label)

        return range_group
        
    def _ApproachStrobe(self):
        approach_strobe = displayio.Group()
        # Portion of the bar to be static. Based on percent distance to parked.
        available_width = (self.display.width / 2) - 6
        # Are we in range and do we need a strobe?
        try:
            if self.status['range'] is None:
                return None
        except:
            pass
        if self.status['range'] < self.config['max_detect_range']:
            # Compare tracking range to current range
            bar_blocker = floor(available_width * (1-( self.current_range / self.config['max_detect_range'] )))
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
        
    def _UpdateDisplay(self):        
        # Assemble the groups
        master_group = displayio.Group()
        master_group.append(self._Frame())
        master_group.append(self._ApproachStrobe())
        master_group.append(self._DisplayDistance())
        self.display.show(master_group)


#    def Run(self):
#        # Set up the tasks
#        # Sensors. Use the simulator if set, otherwise the 'real' sensors.
#        if self.config['simulate_sensors']:
#            sensor_task = asyncio.create_task(self._SimulateSensors())
#        else:
#            sensor_task = asyncio.create_task(self._UpdateSensors())
#            
#        display_task = asyncio.create_task(self._UpdateDisplay())
#        await asyncio.gather(sensor_task,display_task)