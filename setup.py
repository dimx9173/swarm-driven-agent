from setuptools import setup, find_packages

setup(
    name="swda",
    version="3.0.0",
    packages=find_packages(),
    py_modules=["installer"],
    entry_points={
        "console_scripts": [
            "swda = swda.cli:main",
        ]
    },
    install_requires=[],
    extras_require={
        "prime": [
            "pydantic>=2.0.0",
            "ipython>=8.0.0",
            "litellm>=1.0.0",
            "pyyaml>=6.0",
        ]
    },
)
