
import re

from utils.config import config
from utils.logging_setup import get_logger
from utils.translations import I18N

_ = I18N._
logger = get_logger(__name__)


class TextModifierRule:
    def __init__(self, pattern, replacement, simple_replacement=False, start=False, end=False):
        self._pattern = pattern if simple_replacement else re.compile(pattern)
        self._replacement = replacement
        self._is_locale_specific = isinstance(replacement, dict)
        self._simple_replace = simple_replacement
        self._start = start
        self._end = end
    
    def _get_replacement(self, locale):
        if self._is_locale_specific:
            if locale is not None and locale in self._replacement:
                return self._replacement[locale]
            else:
                # If no locale is specified, use the default locale
                if locale is not None:
                    logger.warning(f"No replacement found for locale {locale}, using default locale {I18N.locale}")
                try:
                    return self._replacement[I18N.locale]
                except KeyError:
                    raise ValueError(f"No replacement found for locale {locale} nor default locale {I18N.locale}")
        else:
            return self._replacement

    def apply(self, text, locale=None):
        replacement = self._get_replacement(locale)
        if not self._start and not self._end:
            if self._simple_replace:
                text = text.replace(self._pattern, replacement)
            else:
                text = re.sub(self._pattern, replacement, text)
        else:
            if self._start:
                if self._simple_replace:
                    if text.startswith(self._pattern):
                        text = replacement + text[len(self._pattern):]
                else:
                    text = re.sub(self._pattern, replacement, text, flags=re.M | re.S)
            if self._end:
                if self._simple_replace:
                    if text.endswith(self._pattern):
                        text = text[:-len(self._pattern)] + replacement
                else:
                    text = re.sub(self._pattern, replacement, text[::-1], flags=re.M | re.S)[::-1]
        return text

    def __str__(self) -> str:
        return f'{self._pattern} -> {self._replacement}'


class TextCleanerRuleset:
    def __init__(self):
        self.rules = []

        for rule_config in config.text_cleaner_ruleset:
            rule = TextModifierRule(**rule_config)
            self.add_rule(rule)
            logger.info(f"Added rule: {rule}")
        
    def clean(self, text, locale=None):
        for rule in self.rules:
            text = rule.apply(text, locale)
        # Unfortunately, the quote characters from other languages are not well supported by most TTS models.
        text = text.replace("\u201c", '"').replace('\u201e', '"')
        text = text.replace("\u201c", '"').replace('\u201d', '"')
        text = text.replace("\u00ab", '"').replace('\u00bb', '"')
        text = re.sub("#+", "#", text)
        text = re.sub("#()", _("Number \\1"), text)
        text = re.sub("(\\*)+", " ", text)
        return text

    def add_rule(self, rule):
        self.rules.append(rule)
