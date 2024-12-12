import json
import os
import re


class BlacklistException(Exception):
    """Thrown when multiple attemps with the same prompt all fail the blacklist tests."""
    pass



class Blacklist:
    def __init__(self, path=None):
        if path is None:
            library_data_dir = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))
            path = os.path.join(library_data_dir, "data", "blacklist.json")
            if not os.path.exists(path):
                path = os.path.join(library_data_dir, "data", "blacklist_example.json")
        with open(path, "r", encoding="UTF-8") as f:
            self._blacklist = json.load(f)
        self._patterns = {item: re.compile(r"(^|\W)" + Blacklist.fix_string_pattern(item)) for item in self._blacklist}

    def test(self, s):
        for item, pattern in self._patterns.items():
            if re.search(pattern, s):
                return item
        return None

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
