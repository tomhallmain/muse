"""Unit tests for utils.config.Config.

Covers the muse_language_learning_languages migration: a config.json written
before the multi-language feature existed only has the legacy singular
muse_language_learning_language / muse_language_learning_language_level
fields, and Config must migrate those into the new list on load -- but only
when the new field was never set at all, not when the user explicitly
emptied it to disable the feature.
"""
import json
import os
import sys

import pytest

from utils.config import Config


@pytest.mark.unit
class TestLanguageLearningLanguagesMigration:
    def test_migrates_legacy_single_language_when_new_field_absent(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({
            "muse_language_learning_language": "German",
            "muse_language_learning_language_level": "intermediate",
        }))

        cfg = Config(config_path=str(config_path))

        assert cfg.muse_language_learning_languages == [
            {"language_code": "de", "level": "intermediate"},
        ]

    def test_migration_falls_back_to_intermediate_when_level_blank(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({
            "muse_language_learning_language": "German",
            "muse_language_learning_language_level": "",
        }))

        cfg = Config(config_path=str(config_path))

        assert cfg.muse_language_learning_languages == [
            {"language_code": "de", "level": "intermediate"},
        ]

    def test_preserves_existing_multi_language_list(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({
            "muse_language_learning_language": "German",
            "muse_language_learning_language_level": "intermediate",
            "muse_language_learning_languages": [
                {"language_code": "fr", "level": "beginner"},
                {"language_code": "es", "level": "advanced"},
            ],
        }))

        cfg = Config(config_path=str(config_path))

        # The legacy fields are ignored once the new list is present at all.
        assert cfg.muse_language_learning_languages == [
            {"language_code": "fr", "level": "beginner"},
            {"language_code": "es", "level": "advanced"},
        ]

    def test_preserves_explicit_empty_list_as_disabled(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({
            "muse_language_learning_language": "German",
            "muse_language_learning_language_level": "intermediate",
            "muse_language_learning_languages": [],
        }))

        cfg = Config(config_path=str(config_path))

        # Must NOT be re-seeded from the legacy fields -- [] means the user
        # deliberately turned language learning off.
        assert cfg.muse_language_learning_languages == []


@pytest.mark.unit
class TestLocaleSetting:
    def test_saved_locale_is_installed(self, tmp_path):
        from utils.translations import I18N
        previous = I18N.locale
        I18N.install_locale("en", verbose=False)
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"locale": "de"}))
        try:
            cfg = Config(config_path=str(config_path))
            assert cfg.locale == "de"
            assert I18N.locale == "de"
        finally:
            I18N.install_locale(previous or "en", verbose=False)

    def test_missing_locale_keeps_the_installed_language(self, tmp_path):
        from utils.translations import I18N
        previous = I18N.locale
        I18N.install_locale("fr", verbose=False)
        config_path = tmp_path / "config.json"
        config_path.write_text("{}")
        try:
            cfg = Config(config_path=str(config_path))
            assert cfg.locale == "fr"
            assert I18N.locale == "fr"
        finally:
            I18N.install_locale(previous or "en", verbose=False)


@pytest.mark.unit
class TestFillMissingDefaults:
    """A config file written before a setting existed should gain it on save,
    rather than leaving the setting invisible and uneditable."""

    def test_adds_a_setting_the_file_predates(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"max_search_results": 50}))
        cfg = Config(config_path=str(config_path))
        assert "auto_fix_album_artwork" not in cfg.dict

        added = cfg.fill_missing_defaults()

        assert "auto_fix_album_artwork" in added
        assert cfg.dict["auto_fix_album_artwork"] is False

    def test_does_not_overwrite_a_value_already_present(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"max_search_results": 50}))
        cfg = Config(config_path=str(config_path))

        added = cfg.fill_missing_defaults()

        assert "max_search_results" not in added
        assert cfg.dict["max_search_results"] == 50

    def test_skips_keys_whose_default_is_none(self, tmp_path):
        """set_values() coerces by type on load, so a null written for a str-typed
        setting would read back as the string "None"."""
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({}))
        cfg = Config(config_path=str(config_path))
        assert cfg.open_weather_api_key is None

        cfg.fill_missing_defaults()

        assert "open_weather_api_key" not in cfg.dict

    def test_known_keys_collected_from_every_registration_helper(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({}))
        cfg = Config(config_path=str(config_path))

        assert "max_search_results" in cfg.known_keys      # set_values
        assert "prompts_directory" in cfg.known_keys       # set_directories
        assert "artists_file" in cfg.known_keys            # set_filepaths

    def test_save_config_persists_the_filled_keys(self, tmp_path, monkeypatch):
        # keeps the swap file save_config writes inside tmp_path
        monkeypatch.setattr(Config, "CONFIGS_DIR_LOC", str(tmp_path))
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"max_search_results": 50}))
        cfg = Config(config_path=str(config_path))

        assert cfg.save_config() is True

        written = json.loads(config_path.read_text())
        assert written["max_search_results"] == 50
        assert written["auto_fix_album_artwork"] is False

    def test_save_config_never_overwrites_the_example(self, tmp_path, monkeypatch):
        """With no config.json, the example is read; saving must create config.json instead."""
        monkeypatch.setattr(Config, "CONFIGS_DIR_LOC", str(tmp_path))
        example_path = tmp_path / "config_example.json"
        example_text = json.dumps({"max_search_results": 50})
        example_path.write_text(example_text, encoding="utf-8")
        monkeypatch.setattr(sys.modules[Config.__module__], "CONFIG_EXAMPLE_PATH", str(example_path))
        cfg = Config(config_path=str(example_path))
        cfg.set_config_value("open_weather_city", "München")

        assert cfg.save_config() is True

        assert example_path.read_text(encoding="utf-8") == example_text
        config_text = (tmp_path / "config.json").read_text(encoding="utf-8")
        assert "München" in config_text
        assert cfg.config_path == str(tmp_path / "config.json")


def _home_expanduser(home):
    def expand(path):
        if path == "~":
            return str(home)
        if isinstance(path, str) and path.startswith("~/"):
            return str(home / path[2:])
        return path
    return expand


@pytest.mark.unit
class TestTildeDirectories:
    def test_existing_tilde_directory_is_expanded(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        coqui = home / "repos" / "TTS"
        coqui.mkdir(parents=True)
        monkeypatch.setattr(os.path, "expanduser", _home_expanduser(home))
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"coqui_tts_location": "~/repos/TTS"}))

        cfg = Config(config_path=str(config_path))

        assert cfg.coqui_tts_location == str(coqui)

    def test_missing_tilde_directory_stays_in_the_file(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(os.path, "expanduser", _home_expanduser(home))
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"coqui_tts_location": "~/repos/TTS"}))

        cfg = Config(config_path=str(config_path))

        # The runtime value stays unset, but the typed path is still what the
        # settings field has to show.
        assert cfg.coqui_tts_location == ""
        assert cfg.dict["coqui_tts_location"] == "~/repos/TTS"

    def test_saving_an_existing_tilde_directory_stores_the_expanded_path(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        coqui = home / "repos" / "TTS"
        coqui.mkdir(parents=True)
        monkeypatch.setattr(os.path, "expanduser", _home_expanduser(home))
        config_path = tmp_path / "config.json"
        config_path.write_text("{}")
        cfg = Config(config_path=str(config_path))

        assert cfg.set_config_value("coqui_tts_location", "~/repos/TTS") is True
        assert cfg.coqui_tts_location == os.path.normpath(os.path.realpath(str(coqui)))
