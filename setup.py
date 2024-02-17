from setuptools import setup, find_packages
import CobraBay

setup(
    name="CobraBay",
    version=CobraBay.__version__,
    packages=find_packages(),
    package_data={
        "": ["*.ttf"]
    },
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "cobrabay = CobraBay.cli.cobrabay:main",
            "cbsensormgr = CobraBay.cli.cbsensormgr:main"
        ]
    }
)