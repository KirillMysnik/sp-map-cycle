from translations.strings import LangStrings, TranslationStrings

from sp_map_cycle.rgba_chat import process_string


class RecursiveTranslationStrings(TranslationStrings):
    """
    This class provides recursive get_string method.
    """
    def get_string(self, language=None, **tokens):
        """Accept other TranslationStrings instances as token values."""
        for token_name, token in self.tokens.items():
            if isinstance(token, TranslationStrings):
                new_tokens = self.tokens.copy()
                del new_tokens[token_name]    # To avoid infinite recursion

                token = token.get_string(language, **new_tokens)
                self.tokens[token_name] = token

        for token_name, token in tokens.items():
            if isinstance(token, TranslationStrings):
                new_tokens = tokens.copy()
                del new_tokens[token_name]    # To avoid infinite recursion

                token = token.get_string(language, **new_tokens)
                tokens[token_name] = token

        return super().get_string(language, **tokens)


class ColoredRecursiveTranslationStrings(RecursiveTranslationStrings):
    """
    This class provides recursive get_string method that processes
    all resulting string with color processing method from rgba_chat module.
    """
    def get_string(self, language=None, **tokens):
        return process_string(super().get_string(language, **tokens))


class BaseLangStrings(LangStrings):
    """
    This is LangStrings class but after initialization replaces all
    TranslationStrings values with an instances of the given
    dict-inherited base class.
    """
    def __init__(self, infile, encoding='utf_8', base=TranslationStrings):
        super().__init__(infile, encoding)

        for key, value in self.items():
            if isinstance(value, TranslationStrings):
                new_translation_strings = base()

                for key_, value_ in value.items():
                    new_translation_strings[key_] = value_

                self[key] = new_translation_strings
