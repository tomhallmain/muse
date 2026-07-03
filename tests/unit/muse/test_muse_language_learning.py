"""Unit tests for Muse's multi-language language-learning support.

Covers three things added alongside DJPersona.can_teach_languages /
prompt_overrides:
  - Muse._teachable_language_codes(): intersects config.muse_language_learning_languages
    with the active persona's can_teach_languages.
  - Muse.set_topic(): excludes Topic.LANGUAGE_LEARNING when nothing is teachable.
  - Muse.teach_language(): picks one teachable language per call (personas with
    more than one rotate between them) and fills the prompt from it.
  - Muse.get_prompt(): persona prompt_overrides take priority, and -- since an
    override has no per-language file on disk -- it must be localized via the
    LLM-translation path rather than the file-lookup path (which would
    silently ignore the override).
"""
import importlib

import pytest

from muse.dj_persona import DJPersona
from muse.muse_spot_profile import MuseSpotProfile
from muse.run_context import RunContext
from utils.globals import Topic, TrackResult


def _add_test_persona(persona_manager, voice_name="test_teacher_voice", **overrides):
    kwargs = dict(
        name="Test Teacher",
        voice_name=voice_name,
        s="F",
        tone="friendly",
        characteristics=[],
        system_prompt="You are a friendly DJ.",
        language="English",
        language_code="en",
        is_mock=True,
    )
    kwargs.update(overrides)
    persona = DJPersona(**kwargs)
    persona_manager.add_persona(persona)
    persona_manager.set_current_persona(persona.voice_name)
    return persona


@pytest.fixture
def muse_instance(mock_args, mock_data_callbacks):
    from muse import Muse
    run_context = RunContext()
    return Muse(args=mock_args, library_data=mock_data_callbacks, run_context=run_context, ui_callbacks=None)


@pytest.fixture
def spot_profile_no_track():
    return MuseSpotProfile(
        previous_track=None,
        track_result=TrackResult(None),
        last_track_failed=False,
        skip_track=False,
        grouping_type=None,
    )


@pytest.fixture
def cfg():
    return importlib.import_module("utils.config").config


@pytest.mark.unit
class TestTeachableLanguageCodes:
    def test_no_configured_languages_returns_empty(self, muse_instance, cfg, monkeypatch):
        monkeypatch.setattr(cfg, "muse_language_learning_languages", [])
        assert muse_instance._teachable_language_codes() == []

    def test_no_persona_falls_back_to_all_configured(self, muse_instance, cfg, monkeypatch):
        monkeypatch.setattr(cfg, "muse_language_learning_languages", [
            {"language_code": "de", "level": "intermediate"},
        ])
        monkeypatch.setattr(muse_instance.memory.get_persona_manager(), "current_persona", None)
        assert muse_instance._teachable_language_codes() == ["de"]

    def test_wildcard_persona_can_teach_all_configured(self, muse_instance, cfg, monkeypatch):
        monkeypatch.setattr(cfg, "muse_language_learning_languages", [
            {"language_code": "de", "level": "intermediate"},
            {"language_code": "fr", "level": "beginner"},
        ])
        pm = muse_instance.memory.get_persona_manager()
        _add_test_persona(pm, can_teach_languages=["*"])
        assert set(muse_instance._teachable_language_codes()) == {"de", "fr"}

    def test_persona_restricted_to_subset(self, muse_instance, cfg, monkeypatch):
        monkeypatch.setattr(cfg, "muse_language_learning_languages", [
            {"language_code": "de", "level": "intermediate"},
            {"language_code": "fr", "level": "beginner"},
            {"language_code": "es", "level": "advanced"},
        ])
        pm = muse_instance.memory.get_persona_manager()
        _add_test_persona(pm, can_teach_languages=["fr", "es"])
        assert muse_instance._teachable_language_codes() == ["fr", "es"]

    def test_persona_with_no_overlap_returns_empty(self, muse_instance, cfg, monkeypatch):
        monkeypatch.setattr(cfg, "muse_language_learning_languages", [
            {"language_code": "de", "level": "intermediate"},
        ])
        pm = muse_instance.memory.get_persona_manager()
        _add_test_persona(pm, can_teach_languages=["fr"])
        assert muse_instance._teachable_language_codes() == []


@pytest.mark.unit
class TestSetTopicExcludesLanguageLearning:
    def test_excluded_when_nothing_teachable(self, muse_instance, spot_profile_no_track, monkeypatch):
        captured = {}

        def fake_get_topic(previous_track, excluded_topics=None):
            captured["excluded"] = excluded_topics
            return None

        monkeypatch.setattr(muse_instance, "get_topic", fake_get_topic)
        monkeypatch.setattr(muse_instance, "_teachable_language_codes", lambda: [])

        muse_instance.set_topic(spot_profile_no_track)

        assert Topic.LANGUAGE_LEARNING in captured["excluded"]

    def test_not_excluded_when_teachable(self, muse_instance, spot_profile_no_track, monkeypatch):
        captured = {}

        def fake_get_topic(previous_track, excluded_topics=None):
            captured["excluded"] = excluded_topics
            return None

        monkeypatch.setattr(muse_instance, "get_topic", fake_get_topic)
        monkeypatch.setattr(muse_instance, "_teachable_language_codes", lambda: ["de"])

        muse_instance.set_topic(spot_profile_no_track)

        assert Topic.LANGUAGE_LEARNING not in captured["excluded"]


@pytest.mark.unit
class TestTeachLanguage:
    def test_uses_persona_only_teachable_language(self, muse_instance, cfg, spot_profile_no_track, monkeypatch):
        monkeypatch.setattr(cfg, "muse_language_learning_languages", [
            {"language_code": "fr", "level": "beginner"},
            {"language_code": "es", "level": "advanced"},
        ])
        pm = muse_instance.memory.get_persona_manager()
        # Only French overlaps -- this persona's choice is deterministic even
        # though teach_language() picks randomly among teachable candidates.
        _add_test_persona(pm, can_teach_languages=["fr"])

        monkeypatch.setattr(muse_instance, "get_prompt", lambda topic: "{LANGUAGE}|{LEVEL}|{WORD}")
        monkeypatch.setattr(muse_instance, "generate_text", lambda prompt, **kw: prompt)
        monkeypatch.setattr(muse_instance, "_get_random_word", lambda: "bonjour")
        captured = {}
        monkeypatch.setattr(
            muse_instance, "say_at_some_point",
            lambda text, spot_profile, topic: captured.update(text=text, topic=topic),
        )

        muse_instance.teach_language(spot_profile_no_track)

        assert captured["text"] == "French|beginner|bonjour"
        assert captured["topic"] == Topic.LANGUAGE_LEARNING

    def test_rotates_between_multiple_teachable_languages(self, muse_instance, cfg, spot_profile_no_track, monkeypatch):
        monkeypatch.setattr(cfg, "muse_language_learning_languages", [
            {"language_code": "fr", "level": "beginner"},
            {"language_code": "es", "level": "advanced"},
        ])
        pm = muse_instance.memory.get_persona_manager()
        _add_test_persona(pm, can_teach_languages=["fr", "es"])

        import muse.muse as muse_module
        monkeypatch.setattr(muse_module.random, "choice", lambda seq: "es")

        monkeypatch.setattr(muse_instance, "get_prompt", lambda topic: "{LANGUAGE}|{LEVEL}|{WORD}")
        monkeypatch.setattr(muse_instance, "generate_text", lambda prompt, **kw: prompt)
        monkeypatch.setattr(muse_instance, "_get_random_word", lambda: "hola")
        captured = {}
        monkeypatch.setattr(
            muse_instance, "say_at_some_point",
            lambda text, spot_profile, topic: captured.update(text=text),
        )

        muse_instance.teach_language(spot_profile_no_track)

        assert captured["text"] == "Spanish|advanced|hola"

    def test_raises_when_nothing_teachable(self, muse_instance, cfg, spot_profile_no_track, monkeypatch):
        monkeypatch.setattr(cfg, "muse_language_learning_languages", [
            {"language_code": "de", "level": "intermediate"},
        ])
        pm = muse_instance.memory.get_persona_manager()
        _add_test_persona(pm, can_teach_languages=["fr"])

        with pytest.raises(Exception):
            muse_instance.teach_language(spot_profile_no_track)


@pytest.mark.unit
class TestGetPromptOverrides:
    def test_override_used_when_translation_disabled(self, muse_instance, monkeypatch):
        monkeypatch.setattr(muse_instance.args, "use_system_language_for_all_topics", False)
        pm = muse_instance.memory.get_persona_manager()
        persona = _add_test_persona(pm, prompt_overrides={"weather": "Custom weather prompt"})

        assert muse_instance.get_prompt(Topic.WEATHER) == "Custom weather prompt"

    def test_no_override_returns_file_prompt(self, muse_instance, monkeypatch):
        monkeypatch.setattr(muse_instance.args, "use_system_language_for_all_topics", False)
        pm = muse_instance.memory.get_persona_manager()
        _add_test_persona(pm, prompt_overrides={})

        expected = muse_instance.prompter.get_prompt_update_history(Topic.WEATHER)
        assert muse_instance.get_prompt(Topic.WEATHER) == expected

    def test_override_is_translated_not_looked_up_by_file(self, muse_instance, monkeypatch):
        """Regression: an override has no prompts/<lang>/<topic>.txt on disk, so
        the translation path must re-translate the override text itself rather
        than falling through to the per-language file lookup (which would
        silently discard the override)."""
        monkeypatch.setattr(muse_instance.args, "use_system_language_for_all_topics", True)
        monkeypatch.setattr(muse_instance, "should_use_two_call_approach", lambda: False)

        pm = muse_instance.memory.get_persona_manager()
        persona = _add_test_persona(
            pm, language_code="de", can_teach_languages=["*"],
            prompt_overrides={"weather": "Override weather text"},
        )

        called = {}

        def fake_get_prompt_with_language(topic, language_code):
            called["file_lookup"] = True
            return "SHOULD NOT BE USED"

        def fake_generate_text(prompt, **kw):
            called["translation_prompt"] = prompt
            return "TRANSLATED"

        monkeypatch.setattr(muse_instance.prompter, "get_prompt_with_language", fake_get_prompt_with_language)
        monkeypatch.setattr(muse_instance, "generate_text", fake_generate_text)

        result = muse_instance.get_prompt(Topic.WEATHER)

        assert "file_lookup" not in called
        assert "Override weather text" in called["translation_prompt"]
        assert result == "TRANSLATED"

    def test_language_learning_skips_translation_when_persona_language_is_configured(
        self, muse_instance, cfg, monkeypatch,
    ):
        monkeypatch.setattr(muse_instance.args, "use_system_language_for_all_topics", True)
        pm = muse_instance.memory.get_persona_manager()
        persona = _add_test_persona(pm, language_code="de")
        monkeypatch.setattr(cfg, "muse_language_learning_languages", [
            {"language_code": "de", "level": "intermediate"},
        ])

        expected = muse_instance.prompter.get_prompt_update_history(Topic.LANGUAGE_LEARNING)
        assert muse_instance.get_prompt(Topic.LANGUAGE_LEARNING) == expected
