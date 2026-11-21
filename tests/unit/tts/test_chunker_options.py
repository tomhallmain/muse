import json
import os
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from tts.chunker import BracketLinePolicy, Chunker, ChunkingOptions, SplitStrategy
from tts.text_cleaner_ruleset import TextModifierRule
from utils.app_paths import resource_path


def _example_profile(name):
    path = resource_path("library_data", "data", "config_example.json")
    with open(path, encoding="utf-8") as f:
        return [TextModifierRule(**rule) for rule in json.load(f)["text_cleaner_profiles"][name]]


@pytest.fixture(autouse=True)
def no_global_rules(monkeypatch):
    """Keep the user's configured global ruleset out of these tests."""
    monkeypatch.setattr(Chunker.cleaner, "rules", [])
    monkeypatch.setattr(Chunker.cleaner, "profiles", {"de_historical": _example_profile("de_historical")})


def _str_chunks(text, options=None, locale=None, **kwargs):
    chunker = Chunker(options=options, skip_redundant=False, **kwargs)
    return chunker, list(chunker.get_str_chunks(text, locale=locale))


def _file_chunks(tmp_path, text, options=None, locale=None):
    path = tmp_path / "input.txt"
    path.write_text(text, encoding="utf-8")
    chunker = Chunker(options=options, skip_redundant=False)
    return chunker, list(chunker.get_chunks(str(path), locale=locale))


class TestBracketLines:
    def test_default_drops_and_records(self):
        chunker, chunks = _str_chunks("a b\n(c) d\n")
        assert chunks == ["a b"]
        assert chunker.dropped_lines == [(2, "(c) d")]

    def test_annotation_only(self, tmp_path):
        options = ChunkingOptions(bracket_lines=BracketLinePolicy.ANNOTATION_ONLY, join_wrapped_lines=True)
        chunker, chunks = _file_chunks(tmp_path, "[Chorus]\na b\n(= weiten) Ring.\n", options)
        assert chunks == ["a b (= weiten) Ring."]
        assert chunker.dropped_lines == [(1, "[Chorus]")]

    def test_never(self):
        _, chunks = _str_chunks("[Chorus]\nhello there", ChunkingOptions(bracket_lines=BracketLinePolicy.NEVER))
        assert len(chunks) == 1
        assert "[Chorus]" in chunks[0]

    def test_record_dropped_off(self):
        chunker, _ = _str_chunks("a b\n(c) d\n", ChunkingOptions(record_dropped=False))
        assert chunker.dropped_lines == []


class TestJoinAndDehyphenate:
    def test_join_lines_file_mode(self, tmp_path):
        _, chunks = _file_chunks(tmp_path, "eins\nzwei\n\ndrei\n", ChunkingOptions(join_wrapped_lines=True))
        assert chunks == ["eins zwei", "drei"]

    def test_default_file_mode_keeps_newlines(self, tmp_path):
        _, chunks = _file_chunks(tmp_path, "eins\nzwei\n\ndrei\n")
        assert chunks == ["eins\nzwei", "drei"]

    def test_dehyphenate(self):
        _, chunks = _str_chunks("Wir haben Voll-\nmond, und", ChunkingOptions.for_documents())
        assert chunks == ["Wir haben Vollmond, und"]

    def test_keep_elision_hyphen(self):
        _, chunks = _str_chunks("Nord-\nund Südamerika", ChunkingOptions.for_documents(), locale="de")
        assert chunks == ["Nord- und Südamerika"]

    def test_keep_capitalised_compound(self):
        _, chunks = _str_chunks("Wein-\nFaß", ChunkingOptions.for_documents())
        assert chunks == ["Wein- Faß"]


class TestSplitting:
    @staticmethod
    def _sentence(tokens):
        return " ".join(["Wort"] + ["wort"] * (tokens - 2) + ["ende."])

    def test_sentence_split(self):
        text = " ".join(self._sentence(120) for _ in range(3))
        options = ChunkingOptions(split_strategy=SplitStrategy.SENTENCES, max_chunk_tokens=200)
        chunker, chunks = _str_chunks(text, options)
        assert len(chunks) == 3
        assert all(chunk.endswith(".") for chunk in chunks)
        assert chunker.split_chunks == [0]

    def test_huge_sentence_falls_back_to_tokens(self):
        options = ChunkingOptions(split_strategy=SplitStrategy.SENTENCES, max_chunk_tokens=200)
        _, chunks = _str_chunks(self._sentence(450), options)
        assert len(chunks) > 1
        assert all(Chunker.count_tokens(chunk) <= 199 for chunk in chunks)

    def test_token_count_uses_any_whitespace(self):
        assert Chunker.count_tokens("a\nb c") == 3


class TestTextRules:
    def test_locale_scoped_rule_skipped(self):
        rule = TextModifierRule("\\bx\\b", "Ten", locales=["en"])
        assert rule.apply("2 x 5", "de") == "2 x 5"
        assert rule.apply("2 x 5", "de-DE") == "2 x 5"
        assert rule.apply("2 x 5", "en") == "2 Ten 5"

    @staticmethod
    def _apply_profile(text, locale):
        for rule in Chunker.cleaner.resolve_rules(["de_historical"]):
            text = rule.apply(text, locale)
        return text

    def test_profile_rule(self):
        assert self._apply_profile("Ueber die Oeffnung", "de") == "Über die Öffnung"

    def test_profile_leaves_english_alone(self):
        assert self._apply_profile("Aeneas", "en") == "Aeneas"

    def test_profile_leaves_letter_names_alone(self):
        assert self._apply_profile('"Ae", "Oe"', "de") == '"Ae", "Oe"'

    def test_unknown_profile_raises(self):
        with pytest.raises(ValueError):
            Chunker.cleaner.resolve_rules(["no_such_profile"])

    def test_extra_rules_not_global(self):
        rule_count = len(Chunker.cleaner.rules)
        with_profile = Chunker(skip_redundant=False, extra_rules=Chunker.cleaner.resolve_rules(["de_historical"]))
        without_profile = Chunker(skip_redundant=False)
        assert list(with_profile.get_str_chunks("Ueber die Oeffnung", locale="de")) == ["Über die Öffnung"]
        assert list(without_profile.get_str_chunks("Ueber die Oeffnung", locale="de")) == ["Ueber die Oeffnung"]
        assert len(Chunker.cleaner.rules) == rule_count


class TestInvocation:
    @pytest.fixture
    def tts_runner(self):
        pytest.importorskip("vlc")
        import tts.tts_runner as tts_runner
        return tts_runner

    def test_locale_defaults_to_config_language(self, tts_runner, monkeypatch):
        invocation = tts_runner.TTSSpeakInvocation.create(
            lambda chunk, inv: None, tts_runner.TTSConfig(model=None, language="de")
        )
        seen = []

        def fake_get_str_chunks(text, split_on_each_line=False, locale=None):
            seen.append(locale)
            return iter([text])

        monkeypatch.setattr(invocation.chunker, "get_str_chunks", fake_get_str_chunks)
        try:
            invocation.process_text("Hallo")
        finally:
            invocation.cleanup()
        assert seen == ["de"]

    def test_preview_has_no_side_effects(self, tts_runner, tmp_path, monkeypatch):
        def no_provider(_config):
            raise AssertionError("preview must not create a provider")

        monkeypatch.setattr(tts_runner, "get_provider", no_provider)
        path = tmp_path / "book.txt"
        path.write_text("[Chorus]\nWir haben Voll-\nmond.\n\n(= weiten) Ring.\n", encoding="utf-8")
        output_dir = tts_runner.TextToSpeechRunner.output_directory
        before = set(os.listdir(output_dir)) if os.path.isdir(output_dir) else set()

        config = tts_runner.TTSConfig(model=None, chunking=ChunkingOptions.for_documents(), skip_redundant=False)
        preview = tts_runner.TextToSpeechRunner.preview_file(config, str(path))

        after = set(os.listdir(output_dir)) if os.path.isdir(output_dir) else set()
        assert after == before
        assert preview.chunks == ["Wir haben Vollmond.", "(= weiten) Ring."]
        assert preview.dropped_lines == [(1, "[Chorus]")]
        assert preview.split_chunks == []


# Set MUSE_TTS_REGRESSION_BOOK to a copy of Erstes_deutsches_Buch.txt to run this.
_BOOK = os.environ.get("MUSE_TTS_REGRESSION_BOOK")


@pytest.mark.skipif(not _BOOK or not os.path.isfile(_BOOK), reason="regression book not available")
def test_default_options_paragraph_count_on_book():
    chunker = Chunker(skip_redundant=False)
    with open(_BOOK, encoding="utf8") as f:
        paragraphs = list(chunker._yield_chunks(f))
    assert len(paragraphs) == 241
