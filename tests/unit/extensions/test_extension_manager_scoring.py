"""Tests for LLM-assisted search-result scoring (extensions/extension_manager.py)."""

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


def _candidate(title):
    return SimpleNamespace(n=title)


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
class TestLlmScoreOptions:
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
