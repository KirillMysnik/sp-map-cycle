from configparser import ConfigParser

from .paths import MC_DATA_PATH


CONFIG_FILE = MC_DATA_PATH / "config.ini"

config = ConfigParser()
config.read(CONFIG_FILE)
