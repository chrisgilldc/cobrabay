####
# Cobra Bay init
####

from .cobrabay import CobraBay
from .version import __version__

# def read_version():
#     print(__file__)
#     """Read a text file and return the content as a string."""
#     with io.open("/lib/cobrabay/version.py") as f:
#         return f.read()

print(__version__)
__repo__ = "https://github.com/chrisgilldc/cobraba.git"
__all__ = [
    "CobraBay",
    "Unit"]
