from setuptools import setup

setup(
    name="swda",
    version="2.6.1",
    py_modules=["installer"],
    entry_points={
        "console_scripts": [
            "swda = installer:main",
        ]
    },
    install_requires=[],
)
