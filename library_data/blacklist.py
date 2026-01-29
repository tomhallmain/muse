import csv
import json
import os
import re

from utils.globals import AppInfo, BlacklistMode
from utils.encryptor import symmetric_encrypt_data_to_file, symmetric_decrypt_data_from_file
from utils.logging_setup import get_logger
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._

logger = get_logger("blacklist")


def normalize_accents_for_regex(text: str, is_regex: bool = False) -> str:
    """Convert accented characters to regex patterns that match all accent variations.
    
    This function takes a string and converts accented characters to regex patterns
    that will match the character with any accent combination, preventing filter evasion
    through accent variations.
    
    Args:
        text: The input text to normalize
        is_regex: Whether the input text is already a regex pattern
        
    Returns:
        str: The text with accented characters converted to regex patterns
    """
    # Mapping of base characters to their common accented variations
    accent_patterns = {
        'a': '[aàáâãäåāăąǎǟǡǻȁȃȧɐɑ]',
        'A': '[AÀÁÂÃÄÅĀĂĄǍǞǠǺȀȂȦɐ]',
        'e': '[eèéêëēĕėęěȅȇȩɇ]',
        'E': '[EÈÉÊËĒĔĖĘĚȄȆȨ]',
        'i': '[iìíîïĩīĭįıǐȉȋɨ]',
        'I': '[IÌÍÎÏĨĪĬĮİǏȈȊ]',
        'o': '[oòóôõöøōŏőǒǫǭǿȍȏȫȭȯȱɵ]',
        'O': '[OÒÓÔÕÖØŌŎŐǑǪǬǾȌȎȪȬȮȰ]',
        'u': '[uùúûüũūŭůűųǔǖǘǚǜȕȗ]',
        'U': '[UÙÚÛÜŨŪŬŮŰŲǓǕǗǙǛȔȖ]',
        'c': '[cçćĉċč]',
        'C': '[CÇĆĈĊČ]',
        'n': '[nñńņňŋ]',
        'N': '[NÑŃŅŇŊ]',
        's': '[sśŝşš]',
        'S': '[SŚŜŞŠ]',
        'z': '[zźżž]',
        'Z': '[ZŹŻŽ]',
        'y': '[yýÿŷ]',
        'Y': '[YÝŸŶ]',
        'l': '[lł]',
        'L': '[LŁ]',
        'd': '[dđ]',
        'D': '[DĐ]',
        't': '[tþ]',
        'T': '[TÞ]',
        'r': '[rř]',
        'R': '[RŘ]',
        'g': '[gğ]',
        'G': '[GĞ]',
        'h': '[hħ]',
        'H': '[HĦ]',
        'j': '[jĵ]',
        'J': '[JĴ]',
        'k': '[kķ]',
        'K': '[KĶ]',
        'w': '[wŵ]',
        'W': '[WŴ]',
        'x': '[xẋ]',
        'X': '[XẊ]',
        'b': '[bḃ]',
        'B': '[BḂ]',
        'f': '[fḟ]',
        'F': '[FḞ]',
        'm': '[mṁ]',
        'M': '[MṀ]',
        'p': '[pṗ]',
        'P': '[PṖ]',
        'v': '[vṽ]',
        'V': '[VṼ]',
    }
    
    if is_regex:
        # For regex patterns, we need to be more careful to avoid breaking existing patterns
        # We'll use a more sophisticated approach that handles character classes properly
        result = text
        i = 0
        while i < len(result):
            char = result[i]
            
            # Skip if we're inside a character class [...]
            if char == '[':
                # Find the matching closing bracket
                bracket_count = 1
                j = i + 1
                while j < len(result) and bracket_count > 0:
                    if result[j] == '[':
                        bracket_count += 1
                    elif result[j] == ']':
                        bracket_count -= 1
                    j += 1
                i = j
                continue
            
            # Skip if we're dealing with an escaped character
            if char == '\\' and i + 1 < len(result):
                # Skip the escaped character
                i += 2
                continue
            
            # Replace the character if it's a base character
            if char in accent_patterns:
                pattern = accent_patterns[char]
                result = result[:i] + pattern + result[i+1:]
                i += len(pattern)  # Skip ahead by the length of the replacement
            else:
                i += 1
        return result
    else:
        # For non-regex patterns, simple replacement is safe
        result = text
        for base_char, pattern in accent_patterns.items():
            result = result.replace(base_char, pattern)
        return result


class BlacklistException(Exception):
    def __init__(self, message, whitelist, filtered):
        self.message = message
        self.whitelist = whitelist
        self.filtered = filtered
        super().__init__(self.message)


class BlacklistItem:
    def __init__(
        self,
        string: str,
        enabled: bool = True,
        use_regex: bool = False,
        use_word_boundary: bool = True,
        use_space_as_optional_nonword: bool = True,
        exception_pattern: str = None,
    ):
        self.enabled = enabled
        self.use_regex = use_regex
        self.use_word_boundary = use_word_boundary
        self.exception_pattern = exception_pattern
        self.use_space_as_optional_nonword = use_space_as_optional_nonword
        
        # Process the string based on the new property
        
        if use_regex:
            # For regex patterns, store the original string and apply accent normalization carefully
            self.string = string  # Keep original case for regex patterns
            # Apply accent normalization with regex-aware handling
            normalized_string = normalize_accents_for_regex(string, is_regex=True)
            processed_string = normalized_string
            if use_space_as_optional_nonword:
                # Convert spaces to optional non-word character patterns
                processed_string = re.sub(r'\s+', r'(\\W)*', processed_string)
            # Use glob-to-regex conversion for regex mode with case-insensitive flag
            self.regex_pattern = re.compile(self._glob_to_regex(processed_string), re.IGNORECASE)
        else:
            # For non-regex patterns, convert to lowercase and use simple word boundary pattern
            self.string = string.lower()
            if use_space_as_optional_nonword:
                # Split on whitespace, escape tokens, and join with an optional non-word pattern.
                # This avoids leaving the backslash that escapes spaces from re.escape() in front of the inserted group.
                words = re.split(r'\s+', self.string)
                processed_string = r'(?:\W)*'.join(re.escape(w) for w in words if w)
            else:
                processed_string = re.escape(self.string)
            # Apply accent normalization to prevent filter evasion via accent variations
            processed_string = normalize_accents_for_regex(processed_string, is_regex=True)
            # Use simple word boundary pattern for exact match mode
            if use_word_boundary:
                self.regex_pattern = re.compile(r'(^|\W)' + processed_string)
            else:
                self.regex_pattern = re.compile(processed_string)
        
        # Compile exception pattern if provided
        self.exception_regex_pattern = None
        if exception_pattern:
            try:
                self.exception_regex_pattern = re.compile(exception_pattern, re.IGNORECASE)
            except re.error:
                # If exception pattern is invalid, set it to None
                self.exception_pattern = None
                self.exception_regex_pattern = None

        # print(f"BlacklistItem: {self.string} -> {self.regex_pattern.pattern}")

    def to_dict(self) -> dict:
        return {
            "string": self.string,
            "enabled": self.enabled,
            "use_regex": self.use_regex,
            "use_word_boundary": self.use_word_boundary,
            "use_space_as_optional_nonword": self.use_space_as_optional_nonword,
            "exception_pattern": self.exception_pattern,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BlacklistItem":
        if not isinstance(data, dict):
            return None
        if "string" not in data or not isinstance(data["string"], str):
            return None
        enabled = data.get("enabled", True)
        if not isinstance(enabled, bool):
            enabled = True
        use_regex = data.get("use_regex", False)
        if not isinstance(use_regex, bool):
            use_regex = False
        use_word_boundary = data.get("use_word_boundary", True)
        if not isinstance(use_word_boundary, bool):
            use_word_boundary = True
        use_space_as_optional_nonword = data.get("use_space_as_optional_nonword", True)
        if not isinstance(use_space_as_optional_nonword, bool):
            use_space_as_optional_nonword = True
        exception_pattern = data.get("exception_pattern", None)
        if exception_pattern is not None and not isinstance(exception_pattern, str):
            exception_pattern = None
        return cls(data["string"], enabled, use_regex, use_word_boundary, use_space_as_optional_nonword, exception_pattern)

    def matches_tag(self, tag: str) -> bool:
        """Check if a tag matches this blacklist item.
        
        Args:
            tag: The tag to check against this blacklist item
            
        Returns:
            bool: True if the tag matches this blacklist item, False otherwise
        """
        if not self.use_regex:
            # For regex patterns, use the original tag (case-insensitive matching is handled by the regex)
            # For non-regex patterns, convert tag to lowercase
            tag = tag.lower()
            
        # Always use the compiled regex pattern for the base string
        if self.regex_pattern.search(tag):
            # Check if there's an exception pattern that would unfilter this tag
            if self.exception_regex_pattern and self.exception_regex_pattern.search(tag):
                return False  # Exception pattern matches, so don't filter this tag
            return True
                
        return False

    def _glob_to_regex(self, pattern: str) -> str:
        """Convert a glob pattern to a regex pattern with optional word start boundary matching.
        
        Args:
            pattern: The glob pattern to convert
            
        Returns:
            str: The regex pattern with optional word start boundary matching
        """
        regex_pattern = ''
        prev_char = None
        two_prev_char = None
        for char in pattern:
            if char == '*':
                if (two_prev_char == '\\' and prev_char == '.') or prev_char == ')':
                    regex_pattern += '*'
                else:
                    regex_pattern += '.*'
            elif char != '.':
                if prev_char == '.':
                    regex_pattern += '.'
                regex_pattern += char
            prev_char = char
            two_prev_char = prev_char
        
        # Add word boundary matching: (^|\W) at start only if requested.
        # This ensures the pattern matches at the start of a word.
        # If the user wants to add boundary matching to the end,
        # they can do this by adding (\W|$) to the end of the pattern.
        if self.use_word_boundary:
            regex_pattern = r'(^|\W)' + regex_pattern
        
        return regex_pattern

    def remove_blacklisted_content(self, tag: str) -> str:
        """Remove blacklisted content from a tag.
        
        Args:
            tag: The tag to process
            
        Returns:
            str: The tag with blacklisted content removed
        """
        # Remove the matched pattern from the tag (works for both regex and non-regex)
        cleaned_tag = re.sub(self.regex_pattern, '', tag)
        # Clean up extra whitespace
        cleaned_tag = re.sub(r'\s+', ' ', cleaned_tag).strip()
        return cleaned_tag

    def __eq__(self, other: object) -> bool:
        if isinstance(other, BlacklistItem):
            return self.string == other.string
        if isinstance(other, str):
            return self.string == other
        return False

    def __hash__(self) -> int:
        return hash(self.string)

    def __str__(self) -> str:
        return self.string


class Blacklist:
    TAG_BLACKLIST: list[BlacklistItem] = []
    DEFAULT_BLACKLIST_FILE_LOC = os.path.join(os.path.dirname(__file__), "data", "blacklist_default.enc")
    _version_cache = None  # In-memory cache for get_version(); invalidated when blacklist changes

    blacklist_mode = BlacklistMode.REMOVE_ENTIRE_TAG
    blacklist_silent_removal = False

    @staticmethod
    def get_blacklist_mode() -> BlacklistMode:
        return Blacklist.blacklist_mode

    @staticmethod
    def set_blacklist_mode(mode: BlacklistMode) -> None:
        Blacklist.blacklist_mode = mode

    @staticmethod
    def get_blacklist_silent_removal() -> bool:
        return Blacklist.blacklist_silent_removal

    @staticmethod
    def set_blacklist_silent_removal(silent: bool) -> None:
        Blacklist.blacklist_silent_removal = silent

    @staticmethod
    def get_version() -> str:
        """Get a version string that changes when the blacklist changes.

        This version is computed from the blacklist items themselves, so it will
        change whenever items are added, removed, or modified. This can be used
        to invalidate caches that depend on the blacklist state.

        Returns:
            str: A version string (hash) representing the current blacklist state
        """
        version_cache = Blacklist._version_cache
        if version_cache is not None:
            # Quick check: if the list length changed, version definitely changed
            if len(Blacklist.TAG_BLACKLIST) != version_cache[0]:
                version_cache = None
                Blacklist._version_cache = None

        if version_cache is None:
            # Compute version from blacklist items
            # Include enabled state, string, and regex settings in the hash
            version_data = []
            for item in Blacklist.TAG_BLACKLIST:
                version_data.append((
                    item.string,
                    item.enabled,
                    item.use_regex,
                    item.use_word_boundary,
                    item.use_space_as_optional_nonword,
                    item.exception_pattern
                ))
            # Sort to ensure consistent ordering
            version_data.sort()

            # Create a hash from the version data
            import hashlib
            version_str = json.dumps(version_data, sort_keys=True)
            version_hash = hashlib.md5(version_str.encode('utf-8')).hexdigest()

            # Cache in memory; invalidated when blacklist changes
            version_cache = (len(Blacklist.TAG_BLACKLIST), version_hash)
            Blacklist._version_cache = version_cache

        return version_cache[1]

    @staticmethod
    def is_empty() -> bool:
        return len(Blacklist.TAG_BLACKLIST) == 0

    @staticmethod
    def add_item(item: BlacklistItem) -> None:
        Blacklist.TAG_BLACKLIST.append(item)
        Blacklist.sort()
        Blacklist._version_cache = None

    @staticmethod
    def remove_item(item: BlacklistItem, do_save: bool = True) -> bool:
        """Remove a BlacklistItem from the blacklist."""
        try:
            Blacklist.TAG_BLACKLIST.remove(item)
            Blacklist._version_cache = None
            return True
        except ValueError:
            return False

    @staticmethod
    def get_items() -> list[BlacklistItem]:
        return Blacklist.TAG_BLACKLIST

    @staticmethod
    def clear() -> None:
        Blacklist.TAG_BLACKLIST.clear()
        Blacklist._version_cache = None

    @staticmethod
    def sort() -> None:
        Blacklist.TAG_BLACKLIST.sort(key=lambda x: x.string.lower())

    @staticmethod
    def set_blacklist(blacklist, clear_cache: bool = False) -> None:
        """Set the blacklist to a list of BlacklistItem objects.

        Args:
            blacklist: List of BlacklistItem objects to set
            clear_cache: Unused; kept for API compatibility.
        """
        validated_blacklist = []
        
        # Convert each item to a BlacklistItem
        for item in blacklist:
            if isinstance(item, dict):
                blacklist_item = BlacklistItem.from_dict(item)
                if blacklist_item:
                    validated_blacklist.append(blacklist_item)
            elif isinstance(item, str):
                validated_blacklist.append(BlacklistItem(item))
            elif isinstance(item, BlacklistItem):
                validated_blacklist.append(item)
            else:
                logger.error(f"Invalid blacklist item type: {type(item)}")
        
        Blacklist.TAG_BLACKLIST = validated_blacklist
        Blacklist._version_cache = None

    @staticmethod
    def add_to_blacklist(tag, enabled: bool = True, use_regex: bool = False, exception_pattern: str = None) -> None:
        """Add a tag to the blacklist. If tag is a string, convert to BlacklistItem.
        
        Args:
            tag: The tag string or BlacklistItem to add
            enabled: Whether the item should be enabled (default: True)
            use_regex: Whether to use regex matching (default: False)
            exception_pattern: Optional regex pattern to unfilter tags that would otherwise be filtered
        """
        if isinstance(tag, str):
            tag = BlacklistItem(tag, enabled=enabled, use_regex=use_regex, exception_pattern=exception_pattern)
        Blacklist.add_item(tag)

    @staticmethod
    def find_blacklisted_items(text: str) -> dict:
        """Find any blacklisted items in the given text.
        
        Args:
            text: The text to check for blacklisted items
            
        Returns:
            dict: A dictionary mapping found blacklisted tags to their blacklist items.
                 Empty if no blacklisted items are found.
        """
        filtered = {}
        user_tags = text.split(',')
        
        for tag in user_tags:
            # Clean the tag by removing parentheses and extra whitespace
            tag = tag.strip()
            if not tag:
                continue
                
            # Remove outer parentheses if they exist
            while tag.startswith('(') or tag.startswith('['):
                tag = tag[1:].strip()
            while tag.endswith(')') or tag.endswith(']'):
                tag = tag[:-1].strip()
                
            for blacklist_item in Blacklist.TAG_BLACKLIST:
                if not blacklist_item.enabled:
                    continue
                if blacklist_item.matches_tag(tag):
                    filtered[tag] = blacklist_item.string
                    break
                    
        return filtered

    @staticmethod
    def get_violation_item(string: str) -> BlacklistItem:
        """Check if a single string violates any blacklist items.
        
        Args:
            string: The string to check against the blacklist
            
        Returns:
            BlacklistItem: The first blacklist item that matches the string, or None if no violations
        """
        for blacklist_item in Blacklist.TAG_BLACKLIST:
            if blacklist_item.enabled and blacklist_item.matches_tag(string):
                return blacklist_item
        return None

    @staticmethod
    def import_blacklist_csv(filename: str) -> None:
        """Import blacklist from a CSV file. Adds items to the current blacklist (does not clear existing items).

        Expected format:
        string
        tag1
        tag2
        
        Or with optional enabled state:
        string,enabled
        tag1,true
        tag2,false
        """
        with open(filename, 'r', encoding='utf-8') as f:
            # Read first line to determine format
            first_line = f.readline().strip()
            f.seek(0)  # Reset file pointer to start
            
            if ',' in first_line:
                # Two-column format with headers
                reader = csv.DictReader(f)
                for row in reader:
                    enabled = True
                    if 'enabled' in row:
                        enabled_str = row['enabled'].lower()
                        enabled = enabled_str == 'true' or enabled_str == 't' or enabled_str == '1'
                    Blacklist.add_to_blacklist(BlacklistItem(row['string'].strip(), enabled))
            else:
                # Single-column format
                reader = csv.reader(f)
                for row in reader:
                    if row and row[0].strip():
                        Blacklist.add_to_blacklist(BlacklistItem(row[0].strip()))

    @staticmethod
    def import_blacklist_json(filename: str) -> None:
        """Import blacklist from a JSON file. Adds items to the current blacklist (does not clear existing items).

        Expected format:
        ["tag1", "tag2", "tag3"]
        
        Or with optional enabled state:
        [
            {"string": "tag1", "enabled": true},
            {"string": "tag2", "enabled": false}
        ]
        """
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        Blacklist.add_to_blacklist(BlacklistItem(item))
                    elif isinstance(item, dict) and 'string' in item:
                        enabled = item.get('enabled', True)
                        Blacklist.add_to_blacklist(BlacklistItem(item['string'], enabled))
                    else:
                        logger.error(f"Invalid item type in JSON blacklist import: {type(item)}")
            else:
                raise ValueError("Invalid JSON format for blacklist import")

    @staticmethod
    def import_blacklist_txt(filename: str) -> None:
        """Import blacklist from a text file. Adds items to the current blacklist (does not clear existing items).

        Expected format:
        tag1
        tag2
        # Comment line
        tag3
        """
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    Blacklist.add_to_blacklist(BlacklistItem(line))

    @staticmethod
    def export_blacklist_csv(filename: str) -> None:
        """Export blacklist to a CSV file."""
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['string', 'enabled'])
            writer.writeheader()
            for item in Blacklist.TAG_BLACKLIST:
                writer.writerow(item.to_dict())

    @staticmethod
    def export_blacklist_json(filename: str) -> None:
        """Export blacklist to a JSON file."""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump([item.to_dict() for item in Blacklist.TAG_BLACKLIST], f, indent=2)

    @staticmethod
    def export_blacklist_txt(filename: str) -> None:
        """Export blacklist to a text file."""
        with open(filename, 'w', encoding='utf-8') as f:
            for item in Blacklist.TAG_BLACKLIST:
                if item.enabled:
                    f.write(f"{item.string}\n")
                else:
                    f.write(f"# {item.string}\n")

    @staticmethod
    def save_cache() -> None:
        """No-op; kept for API compatibility (e.g. blacklist window store_blacklist)."""
        pass

    @staticmethod
    def encrypt_blacklist() -> None:
        """Encrypt the default blacklist items."""
        try:
            blacklist_dicts = [item.to_dict() for item in Blacklist.get_items()]
            blacklist_json = json.dumps(blacklist_dicts)
            encoded_data = Utils.preprocess_data_for_encryption(blacklist_json)
            symmetric_encrypt_data_to_file(encoded_data, Blacklist.DEFAULT_BLACKLIST_FILE_LOC, (AppInfo.APP_IDENTIFIER + "_blacklist").encode("utf-8"))
        except Exception as e:
            raise Exception(f"Error encrypting blacklist: {e}", e)

    @staticmethod
    def decrypt_blacklist() -> None:
        """Decrypt the default blacklist items."""
        try:
            encoded_data = symmetric_decrypt_data_from_file(Blacklist.DEFAULT_BLACKLIST_FILE_LOC, (AppInfo.APP_IDENTIFIER + "_blacklist").encode("utf-8"))
            blacklist_json = Utils.postprocess_data_from_decryption(encoded_data)
            blacklist_dicts = json.loads(blacklist_json)
            Blacklist.set_blacklist([BlacklistItem.from_dict(item) for item in blacklist_dicts])
        except Exception as e:
            import traceback
            raise Exception(f"Error decrypting blacklist: {e}\n{traceback.format_exc()}")

    @staticmethod
    def clear_cache_file() -> None:
        """No-op; kept for API compatibility (filter cache was removed)."""
        pass



if __name__ == "__main__":
    print("Testing accent normalization patterns...")
    
    # Test cases: (input, should_match, should_not_match)
    test_cases = [
        ("cafe", ["cafe", "café", "cafë", "cafè"], ["coffee", "tea"]),
        ("test w b", ["test w b", "test w b", "tëst w b"], ["test x b", "different"]),
        ("hello", ["hello", "héllo", "hëllo"], ["goodbye", "hi"]),
    ]
    
    for input_string, should_match, should_not_match in test_cases:
        print(f"\nTesting: '{input_string}'")
        item = BlacklistItem(input_string)
        print(f"Pattern: {item.regex_pattern.pattern}")
        
        # Test matches that should work
        for test_word in should_match:
            matches = item.matches_tag(test_word)
            status = "✓" if matches else "✗"
            print(f"  {status} '{test_word}' -> {matches}")
        
        # Test matches that should NOT work
        for test_word in should_not_match:
            matches = item.matches_tag(test_word)
            status = "✓" if not matches else "✗"
            print(f"  {status} '{test_word}' -> {matches} (should be False)")
    
    print("\n" + "="*50)
    print("Testing regex patterns with accent normalization...")
    
    # Test regex patterns
    regex_test_cases = [
        ("test(\W)*a", ["test a", "tëst a", "test á"], ["test b", "different"]),
        ("[ai]pple", ["apple", "ipple"], ["orange", "banana"]),
    ]
    
    for input_string, should_match, should_not_match in regex_test_cases:
        print(f"\nTesting regex: '{input_string}'")
        item = BlacklistItem(input_string, use_regex=True)
        print(f"Pattern: {item.regex_pattern.pattern}")
        
        # Test matches that should work
        for test_word in should_match:
            matches = item.matches_tag(test_word)
            status = "✓" if matches else "✗"
            print(f"  {status} '{test_word}' -> {matches}")
        
        # Test matches that should NOT work
        for test_word in should_not_match:
            matches = item.matches_tag(test_word)
            status = "✓" if not matches else "✗"
            print(f"  {status} '{test_word}' -> {matches} (should be False)")
