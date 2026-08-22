"""Unit tests for utils.config.Config.

Covers the muse_language_learning_languages migration: a config.json written
before the multi-language feature existed only has the legacy singular
muse_language_learning_language / muse_language_learning_language_level
fields, and Config must migrate those into the new list on load -- but only
when the new field was never set at all, not when the user explicitly
emptied it to disable the feature.
"""
import json

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
