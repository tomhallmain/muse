"""Unit tests for Utils language helpers.

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


@pytest.mark.unit
class TestGetDefaultUserLanguage:
    def test_lang_with_territory_and_encoding_is_the_language(self, monkeypatch):
        monkeypatch.setenv("LC_ALL", "")
        monkeypatch.setenv("LC_MESSAGES", "")
        monkeypatch.setenv("LANG", "de_DE.UTF-8")
        assert Utils.get_default_user_language() == "de"

    def test_plain_lang_is_kept(self, monkeypatch):
        monkeypatch.setenv("LC_ALL", "")
        monkeypatch.setenv("LC_MESSAGES", "")
        monkeypatch.setenv("LANG", "de")
        assert Utils.get_default_user_language() == "de"

    def test_posix_lang_is_ignored(self, monkeypatch):
        monkeypatch.setenv("LC_ALL", "C")
        monkeypatch.setenv("LC_MESSAGES", "POSIX")
        monkeypatch.delenv("LANG", raising=False)
        monkeypatch.setattr(Utils, "_macos_ui_language", staticmethod(lambda: None))
        monkeypatch.setattr("utils.utils.sys.platform", "linux")
        assert Utils.get_default_user_language() == "en"

    def test_macos_without_lang_uses_apple_languages(self, monkeypatch):
        monkeypatch.delenv("LC_ALL", raising=False)
        monkeypatch.delenv("LC_MESSAGES", raising=False)
        monkeypatch.delenv("LANG", raising=False)
        monkeypatch.setattr("utils.utils.sys.platform", "darwin")
        monkeypatch.setattr(Utils, "_macos_ui_language", staticmethod(lambda: "de"))
        assert Utils.get_default_user_language() == "de"
