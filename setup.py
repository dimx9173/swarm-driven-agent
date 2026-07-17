from setuptools import setup

setup(
    name="swda",
    version="1.2.8",
    py_modules=["installer"],
    entry_points={
        "console_scripts": [
            "swda = installer:main",
        ]
    },
    install_requires=[],
)
