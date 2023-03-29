from setuptools import setup, find_packages

setup(
    name="CobraBay",
    version="0.1.0",
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