from colors import Color

from advanced_ts import BaseLangStrings

from ..info import info


# Map color variables in translation files to actual Color instances
COLOR_SCHEME = {
    'color_tag': Color(242, 242, 242),
    'color_lightgreen': Color(67, 121, 183),
    'color_default': Color(242, 242, 242),
    'color_error': Color(255, 54, 54),
}
COLORFUL_SIGN = '\x01'


strings_common = BaseLangStrings(info.basename + "/strings")
strings_config = BaseLangStrings(info.basename + "/config")
strings_mapnames = BaseLangStrings(info.basename + "/mapnames")
strings_popups = BaseLangStrings(info.basename + "/popups")
