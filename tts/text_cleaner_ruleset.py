
import os
import re

from utils.config import config
from utils.app_paths import resource_path
from utils.logging_setup import get_logger
from utils.translations import I18N

_ = I18N._
logger = get_logger(__name__)


class NumberToWordsConverter:
    """
    Converts numeric digits to their word equivalents for TTS processing.
    Supports locale-specific implementations.
    """
    
    # English number words (default implementation)
    ONES = {
        0: "zero", 1: "one", 2: "two", 3: "three", 4: "four",
        5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"
    }
    
    TEENS = {
        10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen",
        15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen", 19: "nineteen"
    }
    
    TENS = {
        20: "twenty", 30: "thirty", 40: "forty", 50: "fifty",
        60: "sixty", 70: "seventy", 80: "eighty", 90: "ninety"
    }
    
    HUNDRED = "hundred"
    THOUSAND = "thousand"
    MILLION = "million"
    AND = "and"  # Used in English for "twenty-one", etc.
    APPROXIMATELY = "approximately"  # Used when rounding large numbers
    NEGATIVE = "negative"  # Used for negative numbers
    TO = "to"  # Used for ranges like "1651 to 1703"
    YEAR_OH = "oh"  # Used for the zero in years like "seventeen oh three"
    
    # How a language builds compound numbers; unset keys follow English, except that
    # years_in_pairs applies only to English words:
    # ones_before_tens: 21 is ones + "and" + tens ("einundzwanzig").
    # joined_compounds: everything below a million is one word, with no "and" after
    #     the hundreds (243 = "zweihundertdreiundvierzig").
    # compound_ones: the form a ones word takes inside a compound ("eins" -> "ein").
    # million_one, million_singular: exactly one million ("eine million").
    # years_as_hundreds: 1100-1999 are read in hundreds, as years are
    #     (1703 = "siebzehnhundertdrei").
    # years_in_pairs: 1100-1999 are read as two pairs of digits ("seventeen oh three").
    _COMPOUND_STYLES = {
        "en": {"years_in_pairs": True},
        "de": {"ones_before_tens": True, "joined_compounds": True, "compound_ones": {1: "ein"},
               "million_one": "eine", "million_singular": "million", "years_as_hundreds": True},
    }

    # Locale-specific overrides (can be extended later)
    _locale_overrides = {}

    @classmethod
    def register_locale(cls, locale, ones=None, teens=None, tens=None,
                       hundred=None, thousand=None, million=None, and_word=None,
                       approximately=None, negative=None, to=None,
                       ones_before_tens=None, joined_compounds=None, compound_ones=None,
                       million_one=None, million_singular=None, years_as_hundreds=None,
                       years_in_pairs=None, year_oh=None):
        """
        Register locale-specific number words.
        
        Args:
            locale: Language code (e.g., "en", "de", "es")
            ones: Dict mapping 0-9 to words
            teens: Dict mapping 10-19 to words
            tens: Dict mapping 20, 30, ..., 90 to words
            hundred: Word for "hundred"
            thousand: Word for "thousand"
            million: Word for "million"
            and_word: Word for "and" (used in compound numbers)
            approximately: Word for "approximately" (used when rounding)
            negative: Word for "negative" (used for negative numbers)
            to: Word for "to" (used in ranges like "1651 to 1703")
            ones_before_tens, joined_compounds, compound_ones, million_one,
            million_singular, years_as_hundreds, years_in_pairs: see _COMPOUND_STYLES.
            year_oh: Word for the zero in a paired year ("oh" in "seventeen oh three")
                Each defaults to the locale's language entry there, else to English.
        """
        defaults = cls._get_words_for_locale(None)
        language = (locale or "").replace("-", "_").split("_")[0].lower()
        style = cls._COMPOUND_STYLES.get(language, {})
        if ones_before_tens is None:
            ones_before_tens = style.get("ones_before_tens", False)
        if joined_compounds is None:
            joined_compounds = style.get("joined_compounds", False)
        if years_as_hundreds is None:
            years_as_hundreds = style.get("years_as_hundreds", False)
        if years_in_pairs is None:
            years_in_pairs = style.get("years_in_pairs", False)
        cls._locale_overrides[locale] = {
            'ones': {**defaults['ones'], **(ones or {})},
            'teens': {**defaults['teens'], **(teens or {})},
            'tens': {**defaults['tens'], **(tens or {})},
            'hundred': hundred or defaults['hundred'],
            'thousand': thousand or defaults['thousand'],
            'million': million or defaults['million'],
            'and': and_word or defaults['and'],
            'approximately': approximately or defaults['approximately'],
            'negative': negative or defaults['negative'],
            'to': to or defaults['to'],
            'ones_before_tens': bool(ones_before_tens),
            'joined_compounds': bool(joined_compounds),
            'compound_ones': {**style.get("compound_ones", {}), **(compound_ones or {})},
            'million_one': million_one or style.get("million_one"),
            'million_singular': (million_singular or style.get("million_singular")
                                 or million or defaults['million_singular']),
            'years_as_hundreds': bool(years_as_hundreds),
            'years_in_pairs': bool(years_in_pairs),
            'year_oh': year_oh or defaults['year_oh'],
        }

    @classmethod
    def _get_words_for_locale(cls, locale):
        """Get number words for a specific locale, falling back to English."""
        if locale and locale in cls._locale_overrides:
            return cls._locale_overrides[locale]
        return {
            'ones': cls.ONES,
            'teens': cls.TEENS,
            'tens': cls.TENS,
            'hundred': cls.HUNDRED,
            'thousand': cls.THOUSAND,
            'million': cls.MILLION,
            'and': cls.AND,
            'approximately': cls.APPROXIMATELY,
            'negative': cls.NEGATIVE,
            'to': cls.TO,
            'ones_before_tens': False,
            'joined_compounds': False,
            'compound_ones': {},
            'million_one': None,
            'million_singular': cls.MILLION,
            'years_as_hundreds': False,
            'years_in_pairs': True,
            'year_oh': cls.YEAR_OH,
        }
    
    @classmethod
    def convert_number(cls, num, locale=None, add_approximately=False):
        """
        Convert a number to its word representation.
        
        Args:
            num: Integer to convert
            locale: Optional locale code for language-specific conversion
            add_approximately: If True, prefix with "approximately"
            
        Returns:
            str: Word representation of the number
        """
        if num < 0:
            words = cls._get_words_for_locale(locale)
            negative_word = words['negative']
            prefix = f"{negative_word} "
            if add_approximately:
                approximately_word = words['approximately']
                prefix = f"{negative_word} {approximately_word} "
            return prefix + cls.convert_number(-num, locale, add_approximately=False)
        
        words = cls._get_words_for_locale(locale)
        ones = words['ones']
        teens = words['teens']
        tens = words['tens']
        hundred = words['hundred']
        thousand = words['thousand']
        million = words['million']
        and_word = words['and']
        approximately = words['approximately']
        
        if num == 0:
            result = ones[0]
            if add_approximately:
                return f"{approximately} {result}"
            return result
        
        joined = words['joined_compounds']
        compound_ones = words['compound_ones']
        result = []

        # Handle millions
        if num >= 1000000:
            millions = num // 1000000
            if millions == 1:
                result.append(words['million_one'] or cls.convert_number(1, locale))
                result.append(words['million_singular'])
            else:
                result.append(cls.convert_number(millions, locale))
                result.append(million)
            num %= 1000000

        below_million = []

        # Handle thousands
        if num >= 1000:
            thousands = num // 1000
            below_million.append(cls._multiplier_words(thousands, locale) if joined
                                 else cls.convert_number(thousands, locale))
            below_million.append(thousand)
            num %= 1000

        # Handle hundreds
        if num >= 100:
            hundreds = num // 100
            below_million.append(compound_ones.get(hundreds, ones[hundreds]) if joined
                                 else ones[hundreds])
            below_million.append(hundred)
            num %= 100
            if num > 0 and not joined:
                below_million.append(and_word)

        # Handle tens and ones
        if num >= 20:
            tens_place = (num // 10) * 10
            ones_place = num % 10
            if ones_place > 0 and words['ones_before_tens']:
                ones_word = compound_ones.get(ones_place, ones[ones_place])
                below_million.append(f"{ones_word}{and_word}{tens[tens_place]}")
            elif ones_place > 0:
                # Use hyphen for compound numbers like "twenty-one"
                below_million.append(f"{tens[tens_place]}-{ones[ones_place]}")
            else:
                below_million.append(tens[tens_place])
        elif num >= 10:
            below_million.append(teens[num])
        elif num > 0:
            below_million.append(ones[num])

        if below_million:
            result.append(("" if joined else " ").join(below_million))

        result_str = " ".join(result)
        if add_approximately:
            return f"{approximately} {result_str}"
        return result_str
    
    @classmethod
    def convert_year(cls, num, locale=None):
        """*num* (1100-1999) read as a year: "siebzehnhundertdrei", "seventeen oh three"."""
        words = cls._get_words_for_locale(locale)
        century, rest = cls.convert_number(num // 100, locale), num % 100
        if words['years_as_hundreds'] or rest == 0:
            parts = [century, words['hundred']]
            if rest:
                parts.append(cls.convert_number(rest, locale))
            return ("" if words['joined_compounds'] else " ").join(parts)
        if rest < 10:
            return f"{century} {words['year_oh']} {cls.convert_number(rest, locale)}"
        return f"{century} {cls.convert_number(rest, locale)}"

    @classmethod
    def _multiplier_words(cls, num, locale):
        """*num* as words in front of "thousand" in a joined compound.

        A final ones word takes its compound form there: 1000 is "eintausend" and
        101000 "einhunderteintausend", not "einstausend".
        """
        words = cls._get_words_for_locale(locale)
        text = cls.convert_number(num, locale)
        last = num % 100
        if 0 < last < 10 and last in words['compound_ones']:
            plain = words['ones'][last]
            if text.endswith(plain):
                text = text[:-len(plain)] + words['compound_ones'][last]
        return text

    @classmethod
    def _is_round_number(cls, num):
        """
        Check if a number is "round" (has trailing zeros that make it suitable for direct conversion).
        
        Args:
            num: Integer to check
            
        Returns:
            bool: True if the number is round (e.g., 20000, 500000), False if specific (e.g., 12345)
        """
        if num < 10000:
            return True  # All numbers under 10000 are considered "round" enough
        
        # Check if number has significant non-zero digits in lower places
        # For 10000-999999: check if last 3 digits are all zero (round to thousand)
        if num < 1000000:
            return (num % 1000) == 0
        
        # For 1000000-9999999: check if last 5 digits are all zero (round to hundred thousand)
        if num < 10000000:
            return (num % 100000) == 0
        
        # For larger numbers, consider them round if last 6 digits are zero
        return (num % 1000000) == 0
    
    @classmethod
    def _round_large_number(cls, num):
        """
        Round a large number to a reasonable precision for TTS.
        
        Args:
            num: Integer to round
            
        Returns:
            int: Rounded number
        """
        abs_num = abs(num)
        sign = -1 if num < 0 else 1
        
        if abs_num < 1000000:
            # Round to nearest thousand
            rounded = (abs_num + 500) // 1000 * 1000
        elif abs_num < 10000000:
            # Round to nearest hundred thousand
            rounded = (abs_num + 50000) // 100000 * 100000
        else:
            # Round to nearest million
            rounded = (abs_num + 500000) // 1000000 * 1000000
        
        return sign * rounded
    
    @classmethod
    def convert_text_numbers(cls, text, locale=None):
        """
        Find and convert all numeric digits in text to their word equivalents.
        Numbers over 10000 are rounded if they're specific, and marked as approximate.
        Numbers over 10 million are kept as digits.
        Handles date ranges (e.g., "1651-1703") by converting to "1651 to 1703".
        
        Args:
            text: Text string that may contain numbers
            locale: Optional locale code for language-specific conversion
            
        Returns:
            str: Text with numbers converted to words
        """
        words = cls._get_words_for_locale(locale)
        to_word = words['to']
        
        # First, handle date ranges (e.g., "1651-1703" or "1651 - 1703")
        # Pattern matches: number, optional whitespace, hyphen/dash, optional whitespace, number
        range_pattern = r'\b(\d+)\s*[-–—]\s*(\d+)\b'
        
        def replace_range(match):
            num1_str = match.group(1)
            num2_str = match.group(2)
            try:
                num1 = int(num1_str)
                num2 = int(num2_str)
                
                # Convert both numbers
                word1 = cls._convert_single_number(num1, locale)
                word2 = cls._convert_single_number(num2, locale)
                
                return f"{word1} {to_word} {word2}"
            except ValueError:
                return match.group(0)  # Return original if conversion fails
        
        # Replace ranges first
        text = re.sub(range_pattern, replace_range, text)
        

        # Now handle standalone numbers (but not negative numbers that are part of ranges)
        # Pattern to match integers, but not if preceded by a hyphen that's part of a range
        # This pattern matches standalone numbers, not numbers that are part of words
        # Standalone integers; \b fails on "-5", so use non-word-char boundaries instead.
        pattern = r'(?<!\w)-?\d+(?!\w)'
        
        def replace_number(match):
            num_str = match.group(0)
            # Skip if this looks like it might be part of a range we already handled
            # (though ranges should already be converted, this is a safety check)
            try:
                num = int(num_str)
                return cls._convert_single_number(num, locale)
            except ValueError:
                return num_str
        
        return re.sub(pattern, replace_number, text)
    
    @classmethod
    def _convert_single_number(cls, num, locale=None):
        """
        Convert a single number to words (helper method).
        
        Args:
            num: Integer to convert
            locale: Optional locale code for language-specific conversion
            
        Returns:
            str: Word representation of the number
        """
        abs_num = abs(num)
        
        # For numbers over 10 million, keep as digits
        if abs_num > 10000000:
            return str(num)
        
        if 1100 <= num <= 1999:
            words = cls._get_words_for_locale(locale)
            if words['years_as_hundreds'] or words['years_in_pairs']:
                return cls.convert_year(num, locale)

        # For numbers 0-9999, convert directly
        if abs_num <= 9999:
            return cls.convert_number(num, locale)
        
        # For numbers 10000-10000000, check if they need rounding
        if cls._is_round_number(abs_num):
            # Round number, convert directly
            return cls.convert_number(num, locale)
        else:
            # Specific number, round it and mark as approximate
            rounded = cls._round_large_number(num)
            return cls.convert_number(rounded, locale, add_approximately=True)


def primary_language(locale):
    """Return the language subtag of *locale* ("de-DE" / "de_DE" -> "de"), or None."""
    if not locale:
        return None
    return re.split(r"[-_]", locale, maxsplit=1)[0].lower()


class TextModifierRule:
    def __init__(self, pattern, replacement, simple_replacement=False, start=False, end=False,
                 locales=None):
        self._pattern = pattern if simple_replacement else re.compile(pattern)
        self._replacement = replacement
        self._is_locale_specific = isinstance(replacement, dict)
        self._simple_replace = simple_replacement
        self._start = start
        self._end = end
        # When set, the rule only applies to text in these languages.
        self._locales = None if locales is None else {primary_language(l) for l in locales}
    
    def applies_to(self, locale):
        if self._locales is None:
            return True
        return primary_language(locale or I18N.locale) in self._locales

    def _get_replacement(self, locale):
        if self._is_locale_specific:
            if locale is not None and locale not in self._replacement:
                locale = primary_language(locale)
            if locale is not None and locale in self._replacement:
                return self._replacement[locale]
            else:
                # If no locale is specified, use the default locale
                if locale is not None:
                    logger.warning(_("No replacement found for locale {0}, using default locale {1}").format(locale, I18N.locale))
                try:
                    return self._replacement[I18N.locale]
                except KeyError:
                    raise ValueError(f"No replacement found for locale {locale} nor default locale {I18N.locale}")
        else:
            return self._replacement

    def apply(self, text, locale=None):
        if not self.applies_to(locale):
            return text
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
        if self._locales is None:
            return f'{self._pattern} -> {self._replacement}'
        return f'{self._pattern} -> {self._replacement} ({", ".join(sorted(self._locales))})'


class TextCleanerRuleset:
    def __init__(self):
        self.rules = []

        for rule_config in config.text_cleaner_ruleset:
            rule = TextModifierRule(**rule_config)
            self.add_rule(rule)
            logger.info(f"Added rule: {rule}")
        
        self.profiles = {}
        for name, rule_configs in (getattr(config, "text_cleaner_profiles", None) or {}).items():
            self.profiles[name] = [TextModifierRule(**rule_config) for rule_config in rule_configs]
            logger.info(f"Loaded text cleaner profile {name} with {len(self.profiles[name])} rules")

        # Load number words configuration from config if available
        if hasattr(config, 'number_words') and config.number_words:
            self._load_number_words_from_config(config.number_words)
        
        # Load English detection words from dictionary_en.txt in the tts directory
        self.english_detection_words = set()
        dictionary_path = resource_path('tts', 'dictionary_en.txt')
        try:
            with open(dictionary_path, 'r', encoding='utf-8') as f:
                self.english_detection_words = set(line.strip().lower() for line in f if line.strip())
            logger.info(f"Loaded {len(self.english_detection_words)} English detection words from {dictionary_path}")
        except Exception as e:
            logger.warning(_("Failed to load English detection words from {0}: {1}").format(dictionary_path, e))
    
    def _load_number_words_from_config(self, number_words_config):
        """
        Load number words configuration from config.
        
        Args:
            number_words_config: Dict mapping locale codes to number word configurations.
                Each locale config should have: ones, teens, tens, hundred, thousand, million, and, approximately, negative, to.
                Optional: ones_before_tens, joined_compounds, years_as_hundreds and years_in_pairs (bool),
                year_oh ("oh"),
                compound_ones (e.g. {"1": "ein"}), million_one ("eine") and million_singular ("million");
                for "de" they default to the German compound form, so they are only needed to override it.
                Example:
                {
                    "de": {
                        "ones": {"0": "null", "1": "eins", ...},
                        "teens": {"10": "zehn", ...},
                        "tens": {"20": "zwanzig", ...},
                        "hundred": "hundert",
                        "thousand": "tausend",
                        "million": "millionen",
                        "and": "und",
                        "approximately": "ungefähr",
                        "negative": "negativ",
                        "to": "bis"
                    }
                }
        """
        for locale, words_config in number_words_config.items():
            try:
                # Convert string keys to integers for ones, teens, tens if needed
                ones = words_config.get('ones', {})
                if ones and len(ones) > 0 and isinstance(list(ones.keys())[0], str):
                    ones = {int(k): v for k, v in ones.items()}
                
                teens = words_config.get('teens', {})
                if teens and len(teens) > 0 and isinstance(list(teens.keys())[0], str):
                    teens = {int(k): v for k, v in teens.items()}
                
                tens = words_config.get('tens', {})
                if tens and len(tens) > 0 and isinstance(list(tens.keys())[0], str):
                    tens = {int(k): v for k, v in tens.items()}

                compound_ones = {int(k): v for k, v in (words_config.get('compound_ones') or {}).items()}

                NumberToWordsConverter.register_locale(
                    locale=locale,
                    ones=ones if ones else None,
                    teens=teens if teens else None,
                    tens=tens if tens else None,
                    hundred=words_config.get('hundred'),
                    thousand=words_config.get('thousand'),
                    million=words_config.get('million'),
                    and_word=words_config.get('and'),
                    approximately=words_config.get('approximately'),
                    negative=words_config.get('negative'),
                    to=words_config.get('to'),
                    ones_before_tens=words_config.get('ones_before_tens'),
                    joined_compounds=words_config.get('joined_compounds'),
                    million_one=words_config.get('million_one'),
                    million_singular=words_config.get('million_singular'),
                    years_as_hundreds=words_config.get('years_as_hundreds'),
                    years_in_pairs=words_config.get('years_in_pairs'),
                    year_oh=words_config.get('year_oh'),
                    compound_ones=compound_ones or None,
                )
                logger.info(f"Registered number words for locale: {locale}")
            except Exception as e:
                logger.warning(_("Failed to load number words for locale {0}: {1}").format(locale, e))
    
    def _is_likely_english(self, text):
        """
        Detect if text has a high probability of being English.
        Uses heuristics including common English words and patterns.
        
        Args:
            text: Text string to analyze
            
        Returns:
            bool: True if text is likely English, False otherwise
        """
        if not text or not text.strip():
            return False
        
        # Normalize text for analysis
        text_lower = text.lower()
        
        # Extract words (alphanumeric sequences)
        words = re.findall(r'\b[a-z]+\b', text_lower)
        
        if not words:
            return False
        
        # Calculate English word matches if we have detection words loaded
        english_word_count = 0
        if self.english_detection_words:
            english_word_count = sum(1 for word in words if word in self.english_detection_words)
            # If we have a good ratio of English words, likely English
            if len(words) > 0:
                english_ratio = english_word_count / len(words)
                if english_ratio > 0.5:  # At least 50% of words are common English words
                    return True
        
        # Pattern-based heuristics for English
        # Check for common English patterns and structures
        english_patterns = [
            r'\b(the|and|or|but|in|on|at|to|for|of|with|from|as|is|are|was|were|be|been|being|have|has|had|do|does|did|will|would|could|should|may|might|can|this|that|these|those|a|an)\b',
            r'\bing\b',  # Common English suffix
            r'\b(ed|ly|tion|ness|ment)\b',  # Common English suffixes
        ]
        
        pattern_matches = 0
        for pattern in english_patterns:
            matches = len(re.findall(pattern, text_lower))
            pattern_matches += matches
        
        # If we have significant pattern matches relative to word count, likely English
        if len(words) > 0:
            pattern_ratio = pattern_matches / len(words)
            if pattern_ratio > 0.30:  # At least 30% pattern matches
                return True
        
        # Default: if we can't determine, assume not English (conservative approach)
        return False
        
    def resolve_rules(self, profile_names=(), inline_rules=()):
        """
        Build the per-invocation rule list from named profiles (config.text_cleaner_profiles)
        followed by inline rule dicts. Raises ValueError for an unknown profile name.
        """
        rules = []
        for name in profile_names:
            if name not in self.profiles:
                raise ValueError(_("Unknown text cleaner profile: {0}").format(name))
            rules.extend(self.profiles[name])
        rules.extend(TextModifierRule(**rule_config) for rule_config in inline_rules)
        return rules

    def clean(self, text, locale=None, extra_rules=()):
        # Extra rules run first: document-specific normalisation (e.g. historical spelling)
        # has to happen before the global number and abbreviation rules see the text.
        for rule in extra_rules:
            text = rule.apply(text, locale)
        for rule in self.rules:
            text = rule.apply(text, locale)
        # Convert numeric digits to words for TTS processing
        if not self._is_likely_english(text):
            text = NumberToWordsConverter.convert_text_numbers(text, locale)
        # Unfortunately, the quote characters from other languages are not well supported by most TTS models.
        text = text.replace("\u201c", '"').replace('\u201e', '"')
        text = text.replace("\u201c", '"').replace('\u201d', '"')
        text = text.replace("\u00ab", '"').replace('\u00bb', '"')
        text = re.sub("#+", "#", text)
        hash_label_key = "Number \\1"
        maybe_false_hash_label = _(hash_label_key)
        text = re.sub(r"#\s*(\d+)", I18N.get_translation_override(hash_label_key, locale), text)
        text = re.sub("(\\*)+", " ", text)
        return text

    def add_rule(self, rule):
        self.rules.append(rule)
