####
# CobraBay - Command line invoker
####


import lib.cobrabay as cobrabay
from pid import PidFile


# Initialize the object.
cb = cobrabay.CobraBay()

# Start the main operating loop.
#with PidFile('CobraBay'):
cb.run()