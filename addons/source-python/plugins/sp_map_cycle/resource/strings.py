from translations.strings import TranslationStrings

from ..info import info
from ..recursive_translations import BaseLangStrings
from ..recursive_translations import ColoredRecursiveTranslationStrings
from ..recursive_translations import RecursiveTranslationStrings


# Map color variables in translation files to actual RGB values
COLOR_SCHEME = {
    'tag': "#242,242,242",
    'lightgreen': "#4379B7",
    'default': "#242,242,242",
    'error': "#FF3636",
}


strings_common = BaseLangStrings(
    info.basename + "/strings", base=ColoredRecursiveTranslationStrings)

strings_config = BaseLangStrings(
    info.basename + "/config", base=TranslationStrings)

strings_mapnames = BaseLangStrings(
    info.basename + "/mapnames", base=TranslationStrings)

strings_popups = BaseLangStrings(
    info.basename + "/popups", base=RecursiveTranslationStrings)


def insert_tokens(
        translation_strings,
        base=RecursiveTranslationStrings,
        **tokens):

    rs = base()
    for key, value in translation_strings.items():
        rs[key] = value

    rs.tokens.update(tokens)
    return rs
