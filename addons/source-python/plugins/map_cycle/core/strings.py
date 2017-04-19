# =============================================================================
# >> IMPORTS
# =============================================================================
# Source.Python
from colors import Color
from core import GAME_NAME
from translations.strings import LangStrings

# Map Cycle
from ..info import info


# =============================================================================
# >> GLOBAL VARIABLES
# =============================================================================
# Map color variables in translation files to actual Color instances
if GAME_NAME in ('csgo', ):
    COLOR_SCHEME = {
        'color_tag': "\x01",
        'color_highlight': "\x02",
        'color_default': "\x01",
        'color_error': "\x02",
    }
else:
    COLOR_SCHEME = {
        'color_tag': Color(242, 242, 242),
        'color_lightgreen': Color(67, 121, 183),
        'color_default': Color(242, 242, 242),
        'color_error': Color(255, 54, 54),
    }

common_strings = LangStrings(info.name + "/strings")
config_strings = LangStrings(info.name + "/config")
map_names_strings = LangStrings(info.name + "/map_names")
popups_strings = LangStrings(info.name + "/popups")
