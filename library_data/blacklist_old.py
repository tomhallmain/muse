from collections import Counter
import json
import os
import re

from utils.config import config


class BlacklistException(Exception):
    """Thrown when multiple attemps with the same prompt all fail the blacklist tests."""
    pass



class Blacklist:
    def __init__(self, path=config.blacklist_file):
        with open(path, "r", encoding="UTF-8") as f:
            self._blacklist = json.load(f)
        self._patterns = {item: re.compile(r"(^|\W)" + Blacklist.fix_string_pattern(item)) for item in self._blacklist}

    def test(self, s, excluded_items=[]):
        for item, pattern in self._patterns.items():
            if len(excluded_items) > 0 and item in excluded_items:
                continue
            if re.search(pattern, s):
                return item
        return None

    def test_all(self, s, excluded_items=[], min_count=1):
        items = []
        for item, pattern in self._patterns.items():
            if len(excluded_items) > 0 and item in excluded_items:
                continue
            if re.search(pattern, s):
                items.append(item)
        if min_count > 1:
            items_copy = items[:]
            item_counts = Counter(items_copy)
            items = [item for item in items if item_counts[item] >= min_count]
        return items

    @staticmethod
    def fix_string_pattern(s):
        s = s.replace("(", "\\(")
        s = s.replace(")", "\\)")
        s = s.replace(".", "\\.")
        s = s.replace("*", "\\*")
        s = s.replace("+", "\\+")
        s = s.replace("?", "\\?")
        s = s.replace("[", "\\[")
        s = s.replace("]", "\\]")
        s = s.replace("{", "\\{")
        s = s.replace("}", "\\}")
        s = s.replace("^", "\\^")
        s = s.replace("$", "\\$")
        s = s.replace("|", "\\|")
        return s


blacklist = Blacklist()
