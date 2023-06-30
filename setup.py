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
            "CobraBay = CobraBay.cli.main:main",
            "cbsensortest = CobraBay.cli.sensor_test:main"
        ]
    }
)