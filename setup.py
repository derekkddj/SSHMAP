# setup.py
from setuptools import setup, find_packages
import os

setup(
    name="sshmap",
    version="1.0.0",
    packages=find_packages(),
    # Include the top-level CLI modules
    py_modules=["SSHMAP", "sshmap_execute", "sshmap_cli", "sshmap_web", "web_app"],
    # Include non-Python files
    include_package_data=True,
    package_data={
        '': ['templates/*.html', 'static/css/*.css', 'static/js/*.js'],
    },
    data_files=[
        ('sshmap/templates', ['templates/index.html']),
        ('sshmap/static/css', ['static/css/style.css']),
        ('sshmap/static/js', ['static/js/app.js']),
    ],
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
            # Exposes the web interface as `sshmap-web`
            "sshmap-web=sshmap_web:main",
            # Exposes the CLI as `sshmap-cli`
            "sshmap-cli=sshmap_cli:main",
        ]
    },
)
