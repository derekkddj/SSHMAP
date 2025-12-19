import yaml
from .paths import SSHMAP_PATH
from .logger import sshmap_logger
import os


class Config:
    def __init__(self, path=f"{SSHMAP_PATH}/config.yml"):
        # If file does not exist, create it with default values
        try:
            with open(path, "r") as f:
                self._config = yaml.safe_load(f)
        except (FileNotFoundError, yaml.YAMLError):
            # Create a default config file if it doesn't exist or is malformed
            # Create the directory if it doesn't exist
            os.makedirs(os.path.dirname(path), exist_ok=True)
            sshmap_logger.error(
                f"Config file not found or malformed at {path}. Creating a new one with default values."
            )
            self._config = {
                "neo4j_uri": "bolt://localhost:7687",
                "neo4j_user": "neo4j",
                "neo4j_pass": "neo4j",
                "max_mask": 24,
                "ssh_ports": [22, 2222, 2223],
                "max_depth": 1,
                "scan_timeout": 10,
                "brute_new_credentials": False,
            }
            with open(path, "w") as f:
                yaml.dump(self._config, f)

    def __getitem__(self, key):
        return self._config[key]

    def __setitem__(self, key, value):
        self._config[key] = value

    def get(self, key, default=None):
        return self._config.get(key, default)

    def as_dict(self):
        return self._config


# Load once at import time
CONFIG = Config()
