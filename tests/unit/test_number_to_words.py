import pytest
import sys
from pathlib import Path

# Add the project root directory to the Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tts.text_cleaner_ruleset import NumberToWordsConverter, TextCleanerRuleset


class TestNumberToWordsConverter:
    """Test class for NumberToWordsConverter functionality."""
    
    def test_single_digits(self):
        """Test conversion of single digits (0-9)."""
        assert NumberToWordsConverter.convert_number(0) == "zero"
        assert NumberToWordsConverter.convert_number(1) == "one"
        assert NumberToWordsConverter.convert_number(2) == "two"
        assert NumberToWordsConverter.convert_number(3) == "three"
        assert NumberToWordsConverter.convert_number(4) == "four"
        assert NumberToWordsConverter.convert_number(5) == "five"
        assert NumberToWordsConverter.convert_number(6) == "six"
        assert NumberToWordsConverter.convert_number(7) == "seven"
        assert NumberToWordsConverter.convert_number(8) == "eight"
        assert NumberToWordsConverter.convert_number(9) == "nine"
    
    def test_teens(self):
        """Test conversion of teen numbers (10-19)."""
        assert NumberToWordsConverter.convert_number(10) == "ten"
        assert NumberToWordsConverter.convert_number(11) == "eleven"
        assert NumberToWordsConverter.convert_number(12) == "twelve"
        assert NumberToWordsConverter.convert_number(13) == "thirteen"
        assert NumberToWordsConverter.convert_number(14) == "fourteen"
        assert NumberToWordsConverter.convert_number(15) == "fifteen"
        assert NumberToWordsConverter.convert_number(16) == "sixteen"
        assert NumberToWordsConverter.convert_number(17) == "seventeen"
        assert NumberToWordsConverter.convert_number(18) == "eighteen"
        assert NumberToWordsConverter.convert_number(19) == "nineteen"
    
    def test_tens(self):
        """Test conversion of tens (20, 30, 40, etc.)."""
        assert NumberToWordsConverter.convert_number(20) == "twenty"
        assert NumberToWordsConverter.convert_number(30) == "thirty"
        assert NumberToWordsConverter.convert_number(40) == "forty"
        assert NumberToWordsConverter.convert_number(50) == "fifty"
        assert NumberToWordsConverter.convert_number(60) == "sixty"
        assert NumberToWordsConverter.convert_number(70) == "seventy"
        assert NumberToWordsConverter.convert_number(80) == "eighty"
        assert NumberToWordsConverter.convert_number(90) == "ninety"
    
    def test_compound_numbers(self):
        """Test conversion of compound numbers (21, 45, etc.)."""
        assert NumberToWordsConverter.convert_number(21) == "twenty-one"
        assert NumberToWordsConverter.convert_number(32) == "thirty-two"
        assert NumberToWordsConverter.convert_number(45) == "forty-five"
        assert NumberToWordsConverter.convert_number(67) == "sixty-seven"
        assert NumberToWordsConverter.convert_number(89) == "eighty-nine"
        assert NumberToWordsConverter.convert_number(99) == "ninety-nine"
    
    def test_hundreds(self):
        """Test conversion of hundreds."""
        assert NumberToWordsConverter.convert_number(100) == "one hundred"
        assert NumberToWordsConverter.convert_number(200) == "two hundred"
        assert NumberToWordsConverter.convert_number(500) == "five hundred"
        assert NumberToWordsConverter.convert_number(101) == "one hundred and one"
        assert NumberToWordsConverter.convert_number(123) == "one hundred and twenty-three"
        assert NumberToWordsConverter.convert_number(234) == "two hundred and thirty-four"
        assert NumberToWordsConverter.convert_number(456) == "four hundred and fifty-six"
        assert NumberToWordsConverter.convert_number(789) == "seven hundred and eighty-nine"
        assert NumberToWordsConverter.convert_number(999) == "nine hundred and ninety-nine"
    
    def test_thousands(self):
        """Test conversion of thousands."""
        assert NumberToWordsConverter.convert_number(1000) == "one thousand"
        assert NumberToWordsConverter.convert_number(2000) == "two thousand"
        assert NumberToWordsConverter.convert_number(5000) == "five thousand"
        assert NumberToWordsConverter.convert_number(1001) == "one thousand one"
        assert NumberToWordsConverter.convert_number(1234) == "one thousand two hundred and thirty-four"
        assert NumberToWordsConverter.convert_number(5678) == "five thousand six hundred and seventy-eight"
        assert NumberToWordsConverter.convert_number(9999) == "nine thousand nine hundred and ninety-nine"
    
    def test_tens_of_thousands(self):
        """Test conversion of tens of thousands (round numbers)."""
        assert NumberToWordsConverter.convert_number(10000) == "ten thousand"
        assert NumberToWordsConverter.convert_number(20000) == "twenty thousand"
        assert NumberToWordsConverter.convert_number(50000) == "fifty thousand"
        assert NumberToWordsConverter.convert_number(100000) == "one hundred thousand"
        assert NumberToWordsConverter.convert_number(250000) == "two hundred and fifty thousand"
    
    def test_millions(self):
        """Test conversion of millions."""
        assert NumberToWordsConverter.convert_number(1000000) == "one million"
        assert NumberToWordsConverter.convert_number(2000000) == "two million"
        assert NumberToWordsConverter.convert_number(5000000) == "five million"
        assert NumberToWordsConverter.convert_number(1000001) == "one million one"
        assert NumberToWordsConverter.convert_number(1234567) == "one million two hundred and thirty-four thousand five hundred and sixty-seven"
        assert NumberToWordsConverter.convert_number(9999999) == "nine million nine hundred and ninety-nine thousand nine hundred and ninety-nine"
    
    def test_negative_numbers(self):
        """Test conversion of negative numbers."""
        assert NumberToWordsConverter.convert_number(-1) == "negative one"
        assert NumberToWordsConverter.convert_number(-10) == "negative ten"
        assert NumberToWordsConverter.convert_number(-21) == "negative twenty-one"
        assert NumberToWordsConverter.convert_number(-123) == "negative one hundred and twenty-three"
    
    def test_convert_text_numbers_single(self):
        """Test converting numbers in text (single numbers)."""
        assert NumberToWordsConverter.convert_text_numbers("I have 1 apple") == "I have one apple"
        assert NumberToWordsConverter.convert_text_numbers("There are 5 cats") == "There are five cats"
        assert NumberToWordsConverter.convert_text_numbers("The number is 10") == "The number is ten"
        assert NumberToWordsConverter.convert_text_numbers("I saw 21 birds") == "I saw twenty-one birds"
        assert NumberToWordsConverter.convert_text_numbers("Price: 100 dollars") == "Price: one hundred dollars"
        assert NumberToWordsConverter.convert_text_numbers("Year: 2024") == "Year: two thousand twenty-four"
    
    def test_convert_text_numbers_multiple(self):
        """Test converting multiple numbers in text."""
        result = NumberToWordsConverter.convert_text_numbers("I have 3 apples and 5 oranges")
        assert result == "I have three apples and five oranges"
        
        result = NumberToWordsConverter.convert_text_numbers("There were 10 people at 2 events")
        assert result == "There were ten people at two events"
        
        result = NumberToWordsConverter.convert_text_numbers("The temperature is 25 degrees and humidity is 60 percent")
        assert result == "The temperature is twenty-five degrees and humidity is sixty percent"
    
    def test_convert_text_numbers_with_word_boundaries(self):
        """Test that numbers are only converted when they are standalone words."""
        # Should not match numbers inside words
        result = NumberToWordsConverter.convert_text_numbers("test123test")
        assert result == "test123test"  # Should remain unchanged
        
        # Should match standalone numbers
        result = NumberToWordsConverter.convert_text_numbers("test 123 test")
        assert result == "test one hundred and twenty-three test"
    
    def test_convert_text_numbers_large_round_numbers(self):
        """Test that large round numbers are converted."""
        # Round numbers should be converted
        result = NumberToWordsConverter.convert_text_numbers("The population is 20000")
        assert "twenty thousand" in result
        assert "approximately" not in result.lower()
        
        result = NumberToWordsConverter.convert_text_numbers("The population is 100000")
        assert "one hundred thousand" in result
        assert "approximately" not in result.lower()
        
        result = NumberToWordsConverter.convert_text_numbers("The population is 2000000")
        assert "two million" in result
        assert "approximately" not in result.lower()
    
    def test_convert_text_numbers_specific_large_numbers(self):
        """Test that specific large numbers are rounded and marked as approximate."""
        # Specific numbers should be rounded and marked as approximate
        result = NumberToWordsConverter.convert_text_numbers("The population is 12345")
        assert "approximately" in result.lower()
        assert "twelve thousand" in result or "thirteen thousand" in result
        
        result = NumberToWordsConverter.convert_text_numbers("The population is 123456")
        assert "approximately" in result.lower()
        assert "thousand" in result or "hundred thousand" in result
        
        result = NumberToWordsConverter.convert_text_numbers("The population is 1234567")
        assert "approximately" in result.lower()
        assert "million" in result or "hundred thousand" in result
    
    def test_convert_text_numbers_very_large_numbers(self):
        """Test that numbers over 10 million remain as digits."""
        # Numbers over 10 million should remain as digits
        result = NumberToWordsConverter.convert_text_numbers("The population is 15000000")
        assert result == "The population is 15000000"
        
        result = NumberToWordsConverter.convert_text_numbers("The number is 12345678")
        assert result == "The number is 12345678"
    
    def test_convert_text_numbers_negative_in_text(self):
        """Test converting negative numbers in text."""
        result = NumberToWordsConverter.convert_text_numbers("The temperature is -5 degrees")
        assert result == "The temperature is negative five degrees"
        
        result = NumberToWordsConverter.convert_text_numbers("Balance: -100 dollars")
        assert result == "Balance: negative one hundred dollars"
        
        # Test negative large numbers with approximation
        result = NumberToWordsConverter.convert_text_numbers("The temperature is -12345 degrees")
        assert "negative" in result.lower()
        assert "approximately" in result.lower()
    
    def test_locale_registration(self):
        """Test locale-specific number word registration."""
        # Register a test locale
        NumberToWordsConverter.register_locale(
            "test",
            ones={0: "null", 1: "eins", 2: "zwei"},
            teens={10: "zehn", 11: "elf"},
            tens={20: "zwanzig"},
            hundred="hundert",
            thousand="tausend",
            million="millionen",
            and_word="und",
            approximately="ungefähr"
        )
        
        # Test that locale-specific words are used
        result = NumberToWordsConverter.convert_number(1, locale="test")
        assert result == "eins"
        
        result = NumberToWordsConverter.convert_number(10, locale="test")
        assert result == "zehn"
        
        result = NumberToWordsConverter.convert_number(100, locale="test")
        assert result == "eins hundert"
        
        result = NumberToWordsConverter.convert_number(1000000, locale="test")
        assert "millionen" in result
        
        # Test approximately
        result = NumberToWordsConverter.convert_number(12345, locale="test", add_approximately=True)
        assert "ungefähr" in result.lower()
        
        # Test that default locale still works
        result = NumberToWordsConverter.convert_number(1, locale=None)
        assert result == "one"
        
        # Clean up - remove test locale
        if "test" in NumberToWordsConverter._locale_overrides:
            del NumberToWordsConverter._locale_overrides["test"]
    
    def test_locale_fallback(self):
        """Test that missing locale falls back to default."""
        # Test with non-existent locale
        result = NumberToWordsConverter.convert_number(5, locale="nonexistent")
        assert result == "five"  # Should fall back to English
    
    def test_edge_cases(self):
        """Test edge cases and boundary conditions."""
        # Zero
        assert NumberToWordsConverter.convert_number(0) == "zero"
        
        # Round number at boundary (10000)
        result = NumberToWordsConverter.convert_text_numbers("The number is 10000")
        assert "ten thousand" in result
        
        # Empty text
        assert NumberToWordsConverter.convert_text_numbers("") == ""
        
        # Text with no numbers
        assert NumberToWordsConverter.convert_text_numbers("Hello world") == "Hello world"
        
        # Text with only numbers
        assert NumberToWordsConverter.convert_text_numbers("123") == "one hundred and twenty-three"
    
    def test_round_number_detection(self):
        """Test the _is_round_number method."""
        # Round numbers
        assert NumberToWordsConverter._is_round_number(10000) == True
        assert NumberToWordsConverter._is_round_number(20000) == True
        assert NumberToWordsConverter._is_round_number(100000) == True
        assert NumberToWordsConverter._is_round_number(2000000) == True
        
        # Specific numbers
        assert NumberToWordsConverter._is_round_number(12345) == False
        assert NumberToWordsConverter._is_round_number(123456) == False
        assert NumberToWordsConverter._is_round_number(1234567) == False
    
    def test_round_large_number(self):
        """Test the _round_large_number method."""
        # Round to nearest thousand
        assert NumberToWordsConverter._round_large_number(12345) == 12000
        assert NumberToWordsConverter._round_large_number(12500) == 13000
        assert NumberToWordsConverter._round_large_number(12499) == 12000
        
        # Round to nearest hundred thousand
        assert NumberToWordsConverter._round_large_number(1234567) == 1200000
        assert NumberToWordsConverter._round_large_number(1250000) == 1300000
        
        # Round to nearest million
        assert NumberToWordsConverter._round_large_number(12345678) == 12000000
        assert NumberToWordsConverter._round_large_number(12500000) == 13000000
        
        # Negative numbers
        assert NumberToWordsConverter._round_large_number(-12345) == -12000


class TestTextCleanerRulesetIntegration:
    """Test integration of number conversion with TextCleanerRuleset."""
    
    def test_clean_converts_numbers(self):
        """Test that TextCleanerRuleset.clean() converts numbers."""
        cleaner = TextCleanerRuleset()
        
        result = cleaner.clean("I have 5 apples", locale=None)
        assert "five" in result
        assert "5" not in result
        
        result = cleaner.clean("The temperature is 25 degrees", locale=None)
        assert "twenty-five" in result
        assert "25" not in result
    
    def test_clean_preserves_other_cleaning(self):
        """Test that number conversion works alongside other cleaning rules."""
        cleaner = TextCleanerRuleset()
        
        # Test that number conversion happens along with other cleaning
        result = cleaner.clean("I have 3 apples and 2 oranges", locale=None)
        assert "three" in result
        assert "two" in result
    
    def test_clean_with_locale(self):
        """Test that TextCleanerRuleset.clean() respects locale parameter."""
        cleaner = TextCleanerRuleset()
        
        # Test with default locale (should use English)
        result = cleaner.clean("I have 5 apples", locale="en")
        assert "five" in result
        
        # Test with None locale (should use English default)
        result = cleaner.clean("I have 5 apples", locale=None)
        assert "five" in result


if __name__ == "__main__":
    pytest.main([__file__])

