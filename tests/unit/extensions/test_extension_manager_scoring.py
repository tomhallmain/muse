"""Tests for LLM- and embedding-assisted search-result scoring (extensions/extension_manager.py)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from extensions.extension_manager import ExtensionManager
from extensions.llm import LLMResponseException


def _manager(llm=None):
    manager = ExtensionManager.__new__(ExtensionManager)
    manager.llm = llm or MagicMock()
    manager.prompter = SimpleNamespace(get_prompt=lambda name: "QUERY\nCANDIDATES")
    return manager


def _candidate(title, detail="", seconds=None):
    return SimpleNamespace(n=title, d=detail, xfgk=lambda: seconds)


def _llm_returning(response):
    llm = MagicMock()
    llm.generate_json_get_value.return_value = None if response is None else SimpleNamespace(response=response)
    return llm


@pytest.mark.unit
class TestMWithLlmScore:
    def test_no_llm_score_omits_key_and_uses_mechanical_weights(self):
        manager = ExtensionManager.__new__(ExtensionManager)
        metrics = manager._m("abc", "abc def")
        assert "llm_score" not in metrics
        # substring_match=3/7, word_overlap=1.0, string_similarity=1-4/7, presentation_penalty=0.08
        assert metrics["overall_quality"] == pytest.approx(0.52)

    def test_llm_score_included_and_raises_quality_for_weak_mechanical_match(self):
        manager = ExtensionManager.__new__(ExtensionManager)
        mechanical_only = manager._m("abc", "totally unrelated")
        with_score = manager._m("abc", "totally unrelated", llm_score=1.0)
        assert with_score["llm_score"] == 1.0
        assert with_score["overall_quality"] > mechanical_only["overall_quality"]

    def test_llm_score_of_zero_lowers_quality_for_strong_mechanical_match(self):
        manager = ExtensionManager.__new__(ExtensionManager)
        mechanical_only = manager._m("abc", "abc")
        with_score = manager._m("abc", "abc", llm_score=0.0)
        assert with_score["overall_quality"] < mechanical_only["overall_quality"]


@pytest.mark.unit
class TestCandidateBlock:
    def test_all_three_fields_are_labelled_and_numbered(self):
        block = ExtensionManager._c(2, _candidate("A Title", detail="A Detail", seconds=272.0))
        assert block.splitlines() == ["2:", "title: A Title", "duration: 4:32",
                                      "description: A Detail"]

    def test_an_unset_runtime_leaves_the_line_out(self):
        block = ExtensionManager._c(0, _candidate("A Title", detail="A Detail"))
        assert block.splitlines() == ["0:", "title: A Title", "description: A Detail"]

    def test_an_empty_detail_leaves_the_line_out(self):
        block = ExtensionManager._c(0, _candidate("A Title", seconds=272.0))
        assert block.splitlines() == ["0:", "title: A Title", "duration: 4:32"]

    def test_a_blank_detail_leaves_the_line_out(self):
        block = ExtensionManager._c(0, _candidate("A Title", detail="   \n  "))
        assert block.splitlines() == ["0:", "title: A Title"]

    def test_breaks_in_the_detail_are_collapsed(self):
        """The reply is keyed on the block numbering, so a detail that kept its
        own breaks would read as further numbered blocks."""
        block = ExtensionManager._c(3, _candidate("A Title", detail="one\ntwo\r\nthree"))
        assert block.splitlines() == ["3:", "title: A Title", "description: one two three"]

    def test_a_long_detail_is_capped(self):
        detail = "x" * (ExtensionManager.D_CAP + 50)
        block = ExtensionManager._c(0, _candidate("A Title", detail=detail))
        assert block.splitlines()[-1] == "description: " + "x" * ExtensionManager.D_CAP + "..."

    def test_a_short_detail_is_left_whole(self):
        block = ExtensionManager._c(0, _candidate("A Title", detail="short"))
        assert block.splitlines()[-1] == "description: short"

    def test_an_hour_plus_runtime_carries_its_hours(self):
        """The case the runtime is there for: a whole-record upload the title
        alone would pass off as a single piece."""
        block = ExtensionManager._c(0, _candidate("A Title", seconds=11400.0))
        assert "duration: 3:10:00" in block


@pytest.mark.unit
class TestLlmScoreOptions:
    def test_the_prompt_carries_every_field(self):
        llm = _llm_returning({"0": 0.5})
        manager = _manager(llm=llm)
        manager._llm_score_options("q", [_candidate("A Title", detail="A Detail", seconds=272.0)])
        prompt = llm.generate_json_get_value.call_args[0][0]
        assert "title: A Title" in prompt
        assert "description: A Detail" in prompt
        assert "duration: 4:32" in prompt

    def test_blocks_are_separated_by_a_blank_line(self):
        llm = _llm_returning({"0": 0.5, "1": 0.5})
        manager = _manager(llm=llm)
        manager._llm_score_options("q", [_candidate("First"), _candidate("Second")])
        prompt = llm.generate_json_get_value.call_args[0][0]
        assert "title: First\n\n1:\ntitle: Second" in prompt

    def test_valid_response_returns_int_keyed_scores(self):
        manager = _manager(llm=_llm_returning({"0": 0.9, "1": 0.1}))
        scores = manager._llm_score_options("q", [_candidate("a"), _candidate("b")])
        assert scores == {0: 0.9, 1: 0.1}

    def test_llm_call_failure_returns_none(self):
        manager = _manager(llm=_llm_returning(None))
        assert manager._llm_score_options("q", [_candidate("a")]) is None

    def test_llm_response_exception_returns_none(self):
        llm = MagicMock()
        llm.generate_json_get_value.side_effect = LLMResponseException("boom")
        manager = _manager(llm=llm)
        assert manager._llm_score_options("q", [_candidate("a")]) is None

    def test_wrong_length_response_returns_none(self):
        manager = _manager(llm=_llm_returning({"0": 0.9}))
        assert manager._llm_score_options("q", [_candidate("a"), _candidate("b")]) is None

    def test_non_dict_response_returns_none(self):
        manager = _manager(llm=_llm_returning([0.9]))
        assert manager._llm_score_options("q", [_candidate("a")]) is None

    def test_out_of_range_score_returns_none(self):
        manager = _manager(llm=_llm_returning({"0": 1.5}))
        assert manager._llm_score_options("q", [_candidate("a")]) is None

    def test_non_numeric_score_returns_none(self):
        manager = _manager(llm=_llm_returning({"0": "high"}))
        assert manager._llm_score_options("q", [_candidate("a")]) is None

    def test_bool_score_returns_none(self):
        manager = _manager(llm=_llm_returning({"0": True}))
        assert manager._llm_score_options("q", [_candidate("a")]) is None

    def test_non_numeric_index_returns_none(self):
        manager = _manager(llm=_llm_returning({"not-a-number": 0.5}))
        assert manager._llm_score_options("q", [_candidate("a")]) is None

    def test_out_of_bounds_index_returns_none(self):
        manager = _manager(llm=_llm_returning({"5": 0.5}))
        assert manager._llm_score_options("q", [_candidate("a")]) is None


@pytest.mark.unit
class TestMWithEmbeddingScore:
    def test_no_embedding_score_omits_key_and_uses_mechanical_weights(self):
        manager = ExtensionManager.__new__(ExtensionManager)
        metrics = manager._m("abc", "abc def")
        assert "embedding_score" not in metrics

    def test_embedding_score_included_and_raises_quality_for_weak_mechanical_match(self):
        manager = ExtensionManager.__new__(ExtensionManager)
        mechanical_only = manager._m("abc", "totally unrelated")
        with_score = manager._m("abc", "totally unrelated", embedding_score=1.0)
        assert with_score["embedding_score"] == 1.0
        assert with_score["overall_quality"] > mechanical_only["overall_quality"]

    def test_embedding_score_of_zero_lowers_quality_for_strong_mechanical_match(self):
        manager = ExtensionManager.__new__(ExtensionManager)
        mechanical_only = manager._m("abc", "abc")
        with_score = manager._m("abc", "abc", embedding_score=0.0)
        assert with_score["overall_quality"] < mechanical_only["overall_quality"]

    def test_embedding_score_weighs_less_than_llm_score(self):
        """Both signals move quality the same direction; the embedding's smaller
        slice of the weight means it moves it by less."""
        manager = ExtensionManager.__new__(ExtensionManager)
        with_llm = manager._m("abc", "totally unrelated", llm_score=1.0)
        with_embedding = manager._m("abc", "totally unrelated", embedding_score=1.0)
        baseline = manager._m("abc", "totally unrelated")
        assert (with_llm["overall_quality"] - baseline["overall_quality"]) > (
            with_embedding["overall_quality"] - baseline["overall_quality"])

    def test_both_signals_present_still_sums_to_a_valid_weighting(self):
        manager = ExtensionManager.__new__(ExtensionManager)
        metrics = manager._m("abc", "abc def", llm_score=0.8, embedding_score=0.6)
        assert metrics["llm_score"] == 0.8
        assert metrics["embedding_score"] == 0.6
        assert 0.0 <= metrics["overall_quality"] <= 1.0


@pytest.mark.unit
class TestEmbeddingScoreOptions:
    def test_valid_vectors_return_int_keyed_similarity_scores(self, monkeypatch):
        manager = ExtensionManager.__new__(ExtensionManager)
        vectors = [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]
        monkeypatch.setattr("extensions.extension_manager.embed_texts", lambda texts: vectors)
        scores = manager._embedding_score_options("q", [_candidate("a"), _candidate("b")])
        assert scores[0] == pytest.approx(1.0)
        assert scores[1] == pytest.approx(0.0)

    def test_unavailable_embedding_model_returns_none(self, monkeypatch):
        manager = ExtensionManager.__new__(ExtensionManager)
        monkeypatch.setattr("extensions.extension_manager.embed_texts", lambda texts: None)
        assert manager._embedding_score_options("q", [_candidate("a")]) is None

    def test_wrong_length_vectors_returns_none(self, monkeypatch):
        manager = ExtensionManager.__new__(ExtensionManager)
        monkeypatch.setattr("extensions.extension_manager.embed_texts", lambda texts: [[1.0, 0.0]])
        assert manager._embedding_score_options("q", [_candidate("a"), _candidate("b")]) is None

    def test_embedding_call_raising_returns_none(self, monkeypatch):
        manager = ExtensionManager.__new__(ExtensionManager)

        def _raise(texts):
            raise RuntimeError("boom")

        monkeypatch.setattr("extensions.extension_manager.embed_texts", _raise)
        assert manager._embedding_score_options("q", [_candidate("a")]) is None

    def test_opposed_vectors_are_clamped_to_zero(self, monkeypatch):
        manager = ExtensionManager.__new__(ExtensionManager)
        vectors = [[1.0, 0.0], [-1.0, 0.0]]
        monkeypatch.setattr("extensions.extension_manager.embed_texts", lambda texts: vectors)
        scores = manager._embedding_score_options("q", [_candidate("a")])
        assert scores[0] == 0.0
