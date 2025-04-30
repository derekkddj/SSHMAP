import yaml
from .paths import SSHMAP_PATH

class Config:
    def __init__(self, path=f"{SSHMAP_PATH}/config.yml"):
        with open(path, "r") as f:
            self._config = yaml.safe_load(f)

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
