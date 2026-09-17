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
        # Only deps actually imported by swda/ code (repl.py has an
        # IPython-to-stdlib fallback; pydantic is duck-typed optional).
        "prime": [
            "ipython>=8.0.0",
        ],
    },
)
