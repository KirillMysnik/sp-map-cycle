# =============================================================================
# >> IMPORTS
# =============================================================================
# Source.Python
from paths import CFG_PATH, GAME_PATH, LOG_PATH, PLUGIN_DATA_PATH

# Map Cycle
from ..info import info


# =============================================================================
# >> GLOBAL VARIABLES
# =============================================================================
MC_DATA_PATH = PLUGIN_DATA_PATH / info.name
MC_CFG_PATH = CFG_PATH / info.name

# config.ini / config_server.ini
CONFIG_INI_PATH = MC_CFG_PATH / "config.ini"
CONFIG_SERVER_INI_PATH = MC_CFG_PATH / "config_server.ini"

# mapcycle.json
MAPCYCLE_JSON_PATH = MC_CFG_PATH / "mapcycle.json"

# List of files to upload to players
DOWNLOADLIST_PATH = MC_CFG_PATH / "downloadlist.txt"

MAPS_DIR = GAME_PATH / "maps"
WORKSHOP_DIR = MAPS_DIR / "workshop"
MAPCYCLE_TXT_PATH1 = GAME_PATH / "cfg" / "mapcycle.txt"
MAPCYCLE_TXT_PATH2 = GAME_PATH / "mapcycle.txt"
DEFAULT_MAPCYCLE_TXT_PATH = GAME_PATH / "cfg" / "mapcycle_default.txt"
DBDUMP_DIR = LOG_PATH / info.name
DBDUMP_HTML_PATH = DBDUMP_DIR / "databasedump.html"
DBDUMP_TXT_PATH = DBDUMP_DIR / "databasedump.txt"
TEMPLATES_DIR = MC_DATA_PATH / "templates"
