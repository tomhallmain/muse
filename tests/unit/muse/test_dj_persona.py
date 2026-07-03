"""Unit tests for muse.dj_persona.DJPersona: can_teach_languages and prompt_overrides.

These two fields let more than one language be taught at once: the listener's
target languages live in config.muse_language_learning_languages (a list), and
each persona's can_teach_languages says which of those it is allowed to teach
("*" for any, specific codes otherwise) -- a persona with more than one code
rotates between them (see Muse.teach_language). prompt_overrides lets a
persona substitute its own text for a topic instead of the shared
prompts/<lang>/<topic>.txt file (see Muse.get_prompt).
"""
import pytest

from muse.dj_persona import DJPersona


def _make_persona(**overrides):
    kwargs = dict(
        name="Test DJ",
        voice_name="test_voice",
        s="M",
        tone="friendly",
        characteristics=["energetic"],
        system_prompt="You are a friendly DJ.",
        language="English",
        language_code="en",
        is_mock=True,
    )
    kwargs.update(overrides)
    return DJPersona(**kwargs)


@pytest.mark.unit
class TestCanTeachLanguagesValidation:
    def test_default_is_wildcard(self):
        persona = _make_persona()
        assert persona.can_teach_languages == ["*"]

    def test_explicit_none_defaults_to_wildcard(self):
        persona = _make_persona(can_teach_languages=None)
        assert persona.can_teach_languages == ["*"]

    def test_invalid_code_raises(self):
        with pytest.raises(ValueError):
            _make_persona(can_teach_languages=["xx"])

    def test_wildcard_alongside_codes_is_valid(self):
        # "*" is accepted anywhere in the list, not just alone.
        persona = _make_persona(can_teach_languages=["*", "de"])
        assert persona.can_teach_languages == ["*", "de"]


@pytest.mark.unit
class TestTeachableLanguageCodes:
    def test_wildcard_teaches_every_candidate(self):
        persona = _make_persona(can_teach_languages=["*"])
        assert persona.teachable_language_codes(["de", "fr"]) == ["de", "fr"]

    def test_specific_codes_intersect_with_candidates(self):
        # Sofia-style persona: can switch between French and Spanish.
        persona = _make_persona(can_teach_languages=["fr", "es"])
        assert persona.teachable_language_codes(["de", "fr", "es", "it"]) == ["fr", "es"]

    def test_no_overlap_returns_empty(self):
        persona = _make_persona(can_teach_languages=["de"])
        assert persona.teachable_language_codes(["fr", "es"]) == []

    def test_empty_candidates_returns_empty_even_with_wildcard(self):
        persona = _make_persona(can_teach_languages=["*"])
        assert persona.teachable_language_codes([]) == []


@pytest.mark.unit
class TestPromptOverrides:
    def test_default_is_empty_dict(self):
        persona = _make_persona()
        assert persona.prompt_overrides == {}

    def test_explicit_none_defaults_to_empty_dict(self):
        persona = _make_persona(prompt_overrides=None)
        assert persona.prompt_overrides == {}

    def test_get_prompt_override_returns_none_when_absent(self):
        persona = _make_persona()
        assert persona.get_prompt_override("language_learning") is None

    def test_get_prompt_override_returns_text_when_present(self):
        persona = _make_persona(prompt_overrides={"language_learning": "Custom text"})
        assert persona.get_prompt_override("language_learning") == "Custom text"

    def test_get_prompt_override_ignores_other_topics(self):
        persona = _make_persona(prompt_overrides={"weather": "Custom weather text"})
        assert persona.get_prompt_override("language_learning") is None


@pytest.mark.unit
class TestSerializationRoundTrip:
    def test_to_dict_from_dict_round_trip_preserves_new_fields(self):
        persona = _make_persona(
            can_teach_languages=["fr", "es"],
            prompt_overrides={"language_learning": "Custom text"},
        )
        restored = DJPersona.from_dict(persona.to_dict())
        assert restored.can_teach_languages == ["fr", "es"]
        assert restored.prompt_overrides == {"language_learning": "Custom text"}

    def test_from_dict_defaults_when_keys_missing(self):
        # Simulates a persona persisted before these fields existed.
        legacy_dict = {
            "name": "Legacy DJ",
            "voice_name": "legacy_voice",
            "s": "F",
            "tone": "warm",
            "characteristics": ["classic"],
            "system_prompt": "You are a legacy DJ.",
            "language": "English",
            "language_code": "en",
        }
        persona = DJPersona.from_dict(legacy_dict)
        assert persona.can_teach_languages == ["*"]
        assert persona.prompt_overrides == {}
