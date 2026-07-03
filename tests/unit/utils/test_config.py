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
