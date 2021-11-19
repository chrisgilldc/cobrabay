####
# Cobra Bay Library
####

from adafruit_display_text.label import Label
from adafruit_bitmap_font import bitmap_font
from adafruit_display_text import bitmap_label
import board
import displayio
import framebufferio
import rgbmatrix
import terminalio
import digitalio
import adafruit_aw9523
# Import all the shapes
from adafruit_display_shapes.line import Line
from adafruit_display_shapes.sparkline import Sparkline
from adafruit_display_shapes.polygon import Polygon
from adafruit_display_shapes.rect import Rect
import time
from math import floor, ceil

class CobraBay:
	def __init__(self):
		# Release any previous displays
		displayio.release_displays()

		# Maximum range at which detection should start.
		self.max_detect_range = 276
		self.current_range = 50
		# Timer for the approach strobe
		self.timer_approach_strobe = time.monotonic_ns()
		self.approach_strobe_offset = 1
		# Time the process started, used to simulate approaches.
		self.start_time= time.time()
		
		# Set up access to the expansion board
		# If it's not connected, drop back to simulation.
		self.i2c = board.I2C()
		try:
			self.aw = adafruit_aw9523.AW9523(self.i2c)
		except:
			pass
		else:
			self.sensors = {}
			self.sensors['trigger'] = {}
			self.sensors['echo'] = {}
			# Configure sensor pins
			## Center
			self.sensors['trigger']['center_left'] = self.aw.get_pin(0)
			self.sensors['echo']['center_left'] = self.aw.get_pin(1)
			self.sensors['trigger']['center_right'] = self.aw.get_pin(2)
			self.sensors['echo']['center_right'] = self.aw.get_pin(3)
			## Left side
			self.sensors['trigger']['left_front'] = self.aw.get_pin(4)
			self.sensors['echo']['left_front'] = self.aw.get_pin(5)
			self.sensors['trigger']['left_rear'] = self.aw.get_pin(6)
			self.sensors['echo']['left_rear'] = self.aw.get_pin(7)
			## Right side
			self.sensors['trigger']['right_front'] = self.aw.get_pin(8)
			self.sensors['echo']['right_front'] = self.aw.get_pin(9)
			self.sensors['trigger']['right_rear'] = self.aw.get_pin(10)
			self.sensors['echo']['right_rear'] = self.aw.get_pin(11)
		
			# Initialize all triggers
			for trigger in self.sensors['trigger'].keys():
				self.sensors['trigger'][trigger].switch_to_output(value=False)
			# Initialize all echos
			for echo in self.sensors['echo'].keys():
				self.sensors['echo'][echo].switch_to_input()
		
		# Create an RGB matrix. This is for a 64x32 matrix on a Metro M4 Airlift.
		matrix = rgbmatrix.RGBMatrix(
			width=64, height=32, bit_depth=1, 
			rgb_pins=[board.D2, board.D3, board.D4, board.D5, board.D6, board.D7], 
			addr_pins=[board.A0, board.A1, board.A2, board.A3], 
			clock_pin=board.A4, latch_pin=board.D10, output_enable_pin=board.D9)
			
		# Associate the RGB matrix with a Display so that we can use displayio features	
		self.display = framebufferio.FramebufferDisplay(matrix, auto_refresh=True)
		#self.display.refresh(minimum_frames_per_second=0)
	
		# Set up the frame.
		self.display.show(self._Frame())
		
		# load the fonts
		self.base_font = {
			'18': bitmap_font.load_font('fonts/Interval-Book-18.bdf'),
			'12': bitmap_font.load_font('fonts/Interval-Book-12.bdf'),
			'8': bitmap_font.load_font('fonts/Interval-Book-8.bdf'),
			}

	
	def _StopSign(self):
		stopsign = displayio.Group()
		# Useful polygon calculator:
		# https://www.mathopenref.com/coordpolycalc.html
		# Target width of the sign.
		width = 10 * 2
		fill_color = 0xCF142B
		outline_color = 0xFFFFFF
		i = 0
		h_origin = int(self.display.width / 2)
		v_origin = int(self.display.height / 2)
		
		while i <= width:
			# Coordinates. Starts in upper left, goes around in a circle.
			coords = [
				# Top
				(h_origin - floor((i/3)/2), v_origin - floor(i/2)),
				(h_origin + ceil((i/3)/2), v_origin - floor(i/2)),
				# Right
				(h_origin + ceil(i/2), v_origin - floor((i/3)/2)),
				(h_origin + ceil(i/2), v_origin + ceil((i/3)/2)),
				# Bottom
				(h_origin + ceil((i/3)/2), v_origin + ceil(i/2)),
				(h_origin - floor((i/3)/2), v_origin + ceil(i/2)),
				# Left
				(h_origin - floor(i/2), v_origin + ceil((i/3)/2)),
				(h_origin - floor(i/2), v_origin - floor((i/3)/2))
				]
			# Width 0 is just a single point.
			if i == 0:
				pass
			# Width 1 is a box around that point.	
			if i < width:
				ring = Polygon(coords, outline=fill_color)
			if i == width:
				ring = Polygon(coords, outline=outline_color)
			# Add the prepared ring to the group
			i = i + 1
			stopsign.append(ring)
			
		return stopsign
	
	def _UpdateDistance(self,sensor):
		# Set trigger pin high for 10ms.
		self.sensors['trigger'][sensor]
		
		range = adafruit_display_text.label.Label(
			terminalio.FONT,
			color=0xff0000,
			text=distance)
		range.x = display.width / 2
		range.y = 8
		
	def Range(self,sensor):
		# Update it
		self._UpdateDistance(self,sensor)

	def _SideWarning(self,side):
		pass

	def _Frame(self):
		frame = displayio.Group()
		# Approach frame
		frame.append(Rect(4,29,56,3,outline=0xFFFFFF))
		# Left guidance
		frame.append(Rect(0,0,3,32,outline=0xFFFFFF))
		# Right guidance
		frame.append(Rect(61,0,3,32,outline=0xFFFFFF))	
		return frame
		
	def _DisplayDistance(self):
		# Positioning for labels
		label_position = ( 
			floor(self.display.width / 2), # X - Middle of the display
			floor( ( self.display.height - 4 ) / 2) ) # Y - half the height, with space removed for the approach strobe
		
		# Calculate actual range
		range_feet = floor(self.current_range / 12)
		range_inches = self.current_range % 12  

		# Figure out proper coloring
		if self.current_range <= 12:
			range_color = 0xFF0000
		elif self.current_range <= 48:
			range_color = 0xFFFF00
		elif self.current_range > self.max_detect_range:
			range_color = 0x0000FF
		else:
			range_color = 0x00FF00

		# Decide which to display.
		
		range_group = displayio.Group()
		
		if self.current_range >= self.max_detect_range:
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
		if self.current_range is not None and self.current_range < self.max_detect_range:
		
			# Compare tracking range to current range
			bar_blocker = floor(available_width * (1-( self.current_range / self.max_detect_range )))
			## Left
			approach_strobe.append(Line(5,30,5+bar_blocker,30,0xFFFFFF))
			## Right
			approach_strobe.append(Line(58,30,58-bar_blocker,30,0xFFFFFF))
			# Strober.
			# Set change speed in seconds.
			wait = 100
			wait = wait * 1000000
			if  time.monotonic_ns() - self.timer_approach_strobe >= wait:
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
		
	def UpdateScreen(self):
		# Assemble the groups
		master_group = displayio.Group()
		master_group.append(self._Frame())
		master_group.append(self._ApproachStrobe())
		master_group.append(self._DisplayDistance())
		self.display.show(master_group)
		
		# Set a static distance, for label testing.
		self.current_range = 150
		
		# Simulate an approach, simply.
		#self.current_range = 276 - ((time.time() - self.start_time) * 17)
		#if self.current_range <= 0:
		#	self.current_range = 300
		#	self.start_time = time.time() + 10