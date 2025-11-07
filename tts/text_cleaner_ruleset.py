
import re

from utils.config import config
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
    
    # Locale-specific overrides (can be extended later)
    _locale_overrides = {}
    
    @classmethod
    def register_locale(cls, locale, ones=None, teens=None, tens=None, 
                       hundred=None, thousand=None, million=None, and_word=None, 
                       approximately=None, negative=None, to=None):
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
        """
        cls._locale_overrides[locale] = {
            'ones': ones or cls.ONES,
            'teens': teens or cls.TEENS,
            'tens': tens or cls.TENS,
            'hundred': hundred or cls.HUNDRED,
            'thousand': thousand or cls.THOUSAND,
            'million': million or cls.MILLION,
            'and': and_word or cls.AND,
            'approximately': approximately or cls.APPROXIMATELY,
            'negative': negative or cls.NEGATIVE,
            'to': to or cls.TO
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
            'to': cls.TO
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
        
        result = []
        
        # Handle millions
        if num >= 1000000:
            millions = num // 1000000
            result.append(cls.convert_number(millions, locale))
            result.append(million)
            num %= 1000000
        
        # Handle thousands
        if num >= 1000:
            thousands = num // 1000
            result.append(cls.convert_number(thousands, locale))
            result.append(thousand)
            num %= 1000
        
        # Handle hundreds
        if num >= 100:
            hundreds = num // 100
            result.append(ones[hundreds])
            result.append(hundred)
            num %= 100
            if num > 0:
                result.append(and_word)
        
        # Handle tens and ones
        if num >= 20:
            tens_place = (num // 10) * 10
            ones_place = num % 10
            if ones_place > 0:
                # Use hyphen for compound numbers like "twenty-one"
                result.append(f"{tens[tens_place]}-{ones[ones_place]}")
            else:
                result.append(tens[tens_place])
        elif num >= 10:
            result.append(teens[num])
        elif num > 0:
            result.append(ones[num])
        
        result_str = " ".join(result)
        if add_approximately:
            return f"{approximately} {result_str}"
        return result_str
    
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
        pattern = r'\b(-?\d+)\b'
        
        def replace_number(match):
            num_str = match.group(1)
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
        
        # Load number words configuration from config if available
        if hasattr(config, 'number_words') and config.number_words:
            self._load_number_words_from_config(config.number_words)
    
    def _load_number_words_from_config(self, number_words_config):
        """
        Load number words configuration from config.
        
        Args:
            number_words_config: Dict mapping locale codes to number word configurations.
                Each locale config should have: ones, teens, tens, hundred, thousand, million, and, approximately, negative, to
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
                    to=words_config.get('to')
                )
                logger.info(f"Registered number words for locale: {locale}")
            except Exception as e:
                logger.warning(f"Failed to load number words for locale {locale}: {e}")
        
    def clean(self, text, locale=None):
        for rule in self.rules:
            text = rule.apply(text, locale)
        # Convert numeric digits to words for TTS processing
        text = NumberToWordsConverter.convert_text_numbers(text, locale)
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
