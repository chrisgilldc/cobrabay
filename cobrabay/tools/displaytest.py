"""
Cobrabay Display Tester
"""

from rgbmatrix import RGBMatrix, RGBMatrixOptions

mo = RGBMatrixOptions()
mo.cols=64
mo.rows=32
mo.chain_length=1
mo.parallel=1
mo.disable_hardware_pulsing = True
mo.gpio_slowdown=4
mo.hardware_mapping='adafruit-hat-pwm'
matrix = RGBMatrix(options=mo)
