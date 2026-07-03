"""Unit tests for Utils.get_language_code_for_name / get_english_language_name.

get_language_code_for_name is the reverse of the existing get_english_language_name
(code -> English display name); it exists to migrate the legacy single
muse_language_learning_language name field into a language code for the new
muse_language_learning_languages list (see utils.config.Config.__init__).
"""
import pytest

from utils.utils import Utils


@pytest.mark.unit
class TestGetLanguageCodeForName:
    def test_known_language_name_maps_to_code(self):
        assert Utils.get_language_code_for_name("German") == "de"

    def test_english_maps_to_en(self):
        assert Utils.get_language_code_for_name("English") == "en"

    def test_none_maps_to_en(self):
        assert Utils.get_language_code_for_name(None) == "en"

    def test_blank_maps_to_en(self):
        assert Utils.get_language_code_for_name("   ") == "en"

    def test_round_trips_with_get_english_language_name(self):
        for code in ("de", "es", "fr", "it", "pt", "ru"):
            name = Utils.get_english_language_name(code)
            assert Utils.get_language_code_for_name(name) == code
