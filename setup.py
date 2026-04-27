from setuptools import setup
from Cython.Build import cythonize
import os

# 🛰️ CYTHON SHIELD CONFIG
# We are compiling these folders into machine code (.so files)
# This makes them unreadable to hackers and slightly faster.
folders_to_compile = ["core", "telemetry"]

files_to_compile = []
for folder in folders_to_compile:
    for file in os.listdir(folder):
        if file.endswith(".py") and file != "__init__.py":
            files_to_compile.append(os.path.join(folder, file))

setup(
    ext_modules=cythonize(
        files_to_compile,
        compiler_directives={'language_level': "3"},
        annotate=False  # Don't produce the HTML debug files
    )
)
