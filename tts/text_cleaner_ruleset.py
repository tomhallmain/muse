
import re

from utils.config import config
from utils.utils import Utils


class TextModifierRule:
    def __init__(self, pattern, replacement, simple_replacement=False, start=False, end=False):
        self._pattern = pattern if simple_replacement else re.compile(pattern)
        self._replacement = replacement
        self._simple_replace = simple_replacement
        self._start = start
        self._end = end
    
    def apply(self, text):
        if not (self._start and self._end):
            if self._simple_replace:
                text = text.replace(self._pattern, self._replacement)
            else:
                text = re.sub(self._pattern, self._replacement, text)
        else:
            if self._start:
                if self._simple_replace:
                    if text.startswith(self._pattern):
                        text = self._replacement + text[len(self._pattern):]
                else:
                    text = re.sub(self._pattern, self._replacement, text, flags=re.M | re.S)
            if self._end:
                if self._simple_replace:
                    if text.endswith(self._pattern):
                        text = text[:-len(self._pattern)] + self._replacement
                else:
                    text = re.sub(self._pattern, self._replacement, text[::-1], flags=re.M | re.S)[::-1]
        return text

    def __str__(self) -> str:
        return f'{self._pattern} -> {self._replacement}'


class TextCleanerRuleset:
    def __init__(self):
        self.rules = []

        for rule_config in config.text_cleaner_ruleset:
            rule = TextModifierRule(**rule_config)
            self.add_rule(rule)
            Utils.log(f"Added rule: {rule}")
        
    def clean(self, text):
        for rule in self.rules:
            text = rule.apply(text)
        # Unfortunately, the quote characters from other languages are not well supported by most TTS models.
        text = text.replace("\u201c", '"').replace('\u201d', '"')
        text = text.replace("\u00ab", '"').replace('\u00bb', '"')
        return text

    def add_rule(self, rule):
        self.rules.append(rule)
