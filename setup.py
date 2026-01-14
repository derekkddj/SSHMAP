# setup.py
from setuptools import setup, find_packages

setup(
    name="sshmap",
    version="1.0.0",
    packages=find_packages(),
    # Include the top-level CLI modules
    py_modules=["SSHMAP", "sshmap_execute", "sshmap_cli", "sshmap_web", "web_app"],
    # Runtime dependencies for the CLI
    install_requires=[
        "neo4j",
        "asyncssh",
        "pyyaml",
        "rich",
        "colorlog",
        "termcolor",
        "psutil",
        "pyvis",
        "flask",
    ],
    entry_points={
        "console_scripts": [
            # Exposes the CLI as `sshmap`
            "sshmap=SSHMAP:main",
            # Exposes the execute CLI as `sshmap-execute`
            "sshmap-execute=sshmap_execute:main",
        ]
    },
)
