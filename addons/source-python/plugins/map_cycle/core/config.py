# =============================================================================
# >> IMPORTS
# =============================================================================
# Python
from configparser import ConfigParser

# Map Cycle
from .paths import CONFIG_INI_PATH, CONFIG_SERVER_INI_PATH


# =============================================================================
# >> GLOBAL VARIABLES
# =============================================================================
if CONFIG_SERVER_INI_PATH.isfile():
    _path = CONFIG_SERVER_INI_PATH
else:
    _path = CONFIG_INI_PATH


config = ConfigParser()
config.read(_path)
