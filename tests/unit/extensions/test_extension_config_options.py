"""Extension behaviour that used to be hardcoded and is now config-backed.

Each default matches the constant or literal it replaced, so these also guard
that exposing the settings did not change how extensions behave out of the box.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from extensions.extension_manager import ExtensionManager
from utils.config import config


@pytest.fixture(autouse=True)
def stub_llm_and_prompter(monkeypatch):
    """ExtensionManager.__init__ builds an LLM and a Prompter; neither is needed here."""
    monkeypatch.setattr("extensions.extension_manager.LLM", MagicMock())
    monkeypatch.setattr("extensions.extension_manager.Prompter", MagicMock())


def _manager(llm=None):
    manager = ExtensionManager.__new__(ExtensionManager)
    manager.llm = llm or MagicMock()
    manager.prompter = SimpleNamespace(get_prompt=lambda name: "QUERY\nCANDIDATES")
    return manager


class _Candidate:
    """Stands in for the search-result wrapper, with the duration predicates."""

    def __init__(self, title="Some Track", duration=300.0):
        self.n = title
        self.d = ""
        self.y = False
        self.w = "id-1"
        self.u = {}
        self.m = {}
        self._duration = duration

    def x(self):
        return self.n

    def ggi(self):
        return 0.5

    def xfgi(self, threshold):
        return self._duration < threshold

    def xfgj(self, threshold):
        return threshold > 0 and self._duration > threshold


def _permissive(manager, monkeypatch):
    """Neuter every _bad_option check except the ones under test."""
    for name in ("is_in_library", "_is_blacklisted", "_is_rejected",
                 "_is_compilation", "_not_music"):
        monkeypatch.setattr(ExtensionManager, name, lambda self, b: False)


@pytest.mark.unit
class TestCycleWaitTimes:
    def test_wait_fields_come_from_config(self, monkeypatch):
        monkeypatch.setattr(config, "extension_cycle_wait_minutes", [15, 25], raising=False)

        manager = ExtensionManager(ui_callbacks=None, data_callbacks=None)

        assert manager.extension_wait_min == 15
        assert manager.extension_wait_expected_max == 25

    def test_defaults_match_the_replaced_literals(self, monkeypatch):
        """_run_extensions used to call get_extension_sleep_time(3600, 5400)."""
        monkeypatch.delattr(config, "extension_cycle_wait_minutes", raising=False)

        manager = ExtensionManager(ui_callbacks=None, data_callbacks=None)

        assert manager.extension_wait_min * 60 == 3600
        assert manager.extension_wait_expected_max * 60 == 5400

    def test_string_entries_are_converted(self, monkeypatch):
        monkeypatch.setattr(config, "extension_cycle_wait_minutes", ["45", "50"], raising=False)

        manager = ExtensionManager(ui_callbacks=None, data_callbacks=None)

        assert (manager.extension_wait_min, manager.extension_wait_expected_max) == (45, 50)

    def test_unusable_range_falls_back_to_defaults(self, monkeypatch):
        """A hand-edited config could hold a single value or junk."""
        monkeypatch.setattr(config, "extension_cycle_wait_minutes", [90], raising=False)

        manager = ExtensionManager(ui_callbacks=None, data_callbacks=None)

        assert (manager.extension_wait_min, manager.extension_wait_expected_max) == (60, 90)


@pytest.mark.unit
class TestPendingReviewWindow:
    def test_delayed_uses_configured_bounds(self, monkeypatch):
        monkeypatch.setattr(config, "extension_pending_review_seconds", [10, 20], raising=False)
        manager = _manager()
        seen = {}

        def fake_sleep_time(min_value, max_value):
            seen["bounds"] = (min_value, max_value)
            raise RuntimeError("stop before the download")

        manager.get_extension_sleep_time = fake_sleep_time
        manager.ui_callbacks = None

        with pytest.raises(RuntimeError):
            manager._delayed(_Candidate(), None, "query")

        assert seen["bounds"] == (10, 20)


@pytest.mark.unit
class TestDurationLimits:
    def test_short_track_still_rejected_by_default(self, monkeypatch):
        manager = _manager()
        _permissive(manager, monkeypatch)
        assert manager._bad_option(_Candidate(duration=60.0))

    def test_long_track_allowed_when_no_ceiling_configured(self, monkeypatch):
        """A maximum of -1 must preserve the old behaviour of having no ceiling."""
        monkeypatch.setattr(config, "extension_track_duration_seconds", [120, -1], raising=False)
        manager = _manager()
        _permissive(manager, monkeypatch)
        assert not manager._bad_option(_Candidate(duration=9999.0))

    def test_long_track_rejected_once_ceiling_is_set(self, monkeypatch):
        monkeypatch.setattr(config, "extension_track_duration_seconds", [120, 600], raising=False)
        manager = _manager()
        _permissive(manager, monkeypatch)
        assert manager._bad_option(_Candidate(duration=9999.0))

    def test_track_inside_both_bounds_is_accepted(self, monkeypatch):
        monkeypatch.setattr(config, "extension_track_duration_seconds", [120, 600], raising=False)
        manager = _manager()
        _permissive(manager, monkeypatch)
        assert not manager._bad_option(_Candidate(duration=300.0))


@pytest.mark.unit
class TestEmojiTitles:
    """Detection is Utils.contains_emoji, whose pattern covers only emoticons
    (U+1F600-U+1F64F) and dingbats -- the other pictograph blocks are commented
    out in utils/utils.py. Test titles must use a character from those ranges."""

    EMOJI_TITLE = "Track \U0001F600"

    def test_skipped_by_default(self, monkeypatch):
        monkeypatch.setattr(config, "extension_allow_emoji_titles", False, raising=False)
        assert ExtensionManager._is_skipped_emoji_title(_Candidate(title=self.EMOJI_TITLE))

    def test_kept_when_allowed(self, monkeypatch):
        monkeypatch.setattr(config, "extension_allow_emoji_titles", True, raising=False)
        assert not ExtensionManager._is_skipped_emoji_title(_Candidate(title=self.EMOJI_TITLE))

    def test_symbol_outside_the_detected_ranges_is_not_an_emoji(self, monkeypatch):
        """A musical note sits in a commented-out block, so such a title was never
        skipped -- neither under the old 95% rule nor under the toggle."""
        monkeypatch.setattr(config, "extension_allow_emoji_titles", False, raising=False)
        assert not ExtensionManager._is_skipped_emoji_title(_Candidate(title="Track \U0001F3B5"))

    def test_plain_title_unaffected(self, monkeypatch):
        monkeypatch.setattr(config, "extension_allow_emoji_titles", False, raising=False)
        assert not ExtensionManager._is_skipped_emoji_title(_Candidate(title="Track"))

    def test_decision_is_deterministic(self, monkeypatch):
        """This replaced a random 95% skip; repeated calls must agree."""
        monkeypatch.setattr(config, "extension_allow_emoji_titles", False, raising=False)
        candidate = _Candidate(title=self.EMOJI_TITLE)
        assert len({ExtensionManager._is_skipped_emoji_title(candidate) for _ in range(50)}) == 1


@pytest.mark.unit
class TestLlmScoringToggle:
    def _run_simple(self, manager, monkeypatch, candidates):
        result = SimpleNamespace(i=lambda: True, o=lambda: candidates)
        manager.s = lambda q, m: result
        manager.data_callbacks = None
        # Stop right after the scoring decision.
        monkeypatch.setattr(ExtensionManager, "_bad_option",
                            lambda self, b, strict=None, attr=None: True)
        with pytest.raises(Exception):
            manager._simple("query", depth=99)

    def test_skipped_when_disabled_even_with_healthy_llm(self, monkeypatch):
        monkeypatch.setattr(config, "extension_enable_llm_scoring", False, raising=False)
        llm = MagicMock()
        llm.get_failure_count.return_value = 0
        manager = _manager(llm)
        called = []
        manager._llm_score_options = lambda q, a: called.append(q)

        self._run_simple(manager, monkeypatch, [_Candidate()])

        assert called == []

    def test_still_skipped_when_llm_is_failing(self, monkeypatch):
        monkeypatch.setattr(config, "extension_enable_llm_scoring", True, raising=False)
        llm = MagicMock()
        llm.get_failure_count.return_value = 3
        manager = _manager(llm)
        called = []
        manager._llm_score_options = lambda q, a: called.append(q)

        self._run_simple(manager, monkeypatch, [_Candidate()])

        assert called == []

    def test_runs_when_enabled_and_llm_healthy(self, monkeypatch):
        monkeypatch.setattr(config, "extension_enable_llm_scoring", True, raising=False)
        llm = MagicMock()
        llm.get_failure_count.return_value = 0
        manager = _manager(llm)
        called = []
        manager._llm_score_options = lambda q, a: called.append(q) or None

        self._run_simple(manager, monkeypatch, [_Candidate()])

        assert called == ["query"]


@pytest.mark.unit
class TestEmbeddingScoringToggle:
    def _run_simple(self, manager, monkeypatch, candidates):
        result = SimpleNamespace(i=lambda: True, o=lambda: candidates)
        manager.s = lambda q, m: result
        manager.data_callbacks = None
        # Stop right after the scoring decision.
        monkeypatch.setattr(ExtensionManager, "_bad_option",
                            lambda self, b, strict=None, attr=None: True)
        with pytest.raises(Exception):
            manager._simple("query", depth=99)

    def test_skipped_when_disabled(self, monkeypatch):
        monkeypatch.setattr(config, "extension_enable_embedding_scoring", False, raising=False)
        manager = _manager()
        manager._llm_score_options = lambda q, a: None
        called = []
        manager._embedding_score_options = lambda q, a: called.append(q)

        self._run_simple(manager, monkeypatch, [_Candidate()])

        assert called == []

    def test_runs_when_enabled(self, monkeypatch):
        monkeypatch.setattr(config, "extension_enable_embedding_scoring", True, raising=False)
        manager = _manager()
        manager._llm_score_options = lambda q, a: None
        called = []
        manager._embedding_score_options = lambda q, a: called.append(q) or None

        self._run_simple(manager, monkeypatch, [_Candidate()])

        assert called == ["query"]

    def test_runs_independently_of_llm_failure_state(self, monkeypatch):
        """Embeddings run locally via sentence-transformers, not through Ollama,
        so a failing chat model must not silence this signal too."""
        monkeypatch.setattr(config, "extension_enable_embedding_scoring", True, raising=False)
        monkeypatch.setattr(config, "extension_enable_llm_scoring", True, raising=False)
        llm = MagicMock()
        llm.get_failure_count.return_value = 3
        manager = _manager(llm)
        manager._llm_score_options = lambda q, a: None
        called = []
        manager._embedding_score_options = lambda q, a: called.append(q) or None

        self._run_simple(manager, monkeypatch, [_Candidate()])

        assert called == ["query"]


@pytest.mark.unit
class TestExtensionHistoryCap:
    def test_oldest_entries_dropped_past_the_cap(self, monkeypatch):
        """The cap used to be declared but never read, so history grew forever."""
        monkeypatch.setattr(config, "extension_history_max_length", 3, raising=False)
        monkeypatch.setattr(ExtensionManager, "extensions",
                            [{"n": i} for i in range(6)], raising=False)

        ExtensionManager._trim_extension_history()

        assert [e["n"] for e in ExtensionManager.extensions] == [3, 4, 5]

    def test_under_the_cap_is_untouched(self, monkeypatch):
        monkeypatch.setattr(config, "extension_history_max_length", 100, raising=False)
        monkeypatch.setattr(ExtensionManager, "extensions",
                            [{"n": i} for i in range(6)], raising=False)

        ExtensionManager._trim_extension_history()

        assert len(ExtensionManager.extensions) == 6

    def test_zero_means_unlimited(self, monkeypatch):
        monkeypatch.setattr(config, "extension_history_max_length", 0, raising=False)
        monkeypatch.setattr(ExtensionManager, "extensions",
                            [{"n": i} for i in range(6)], raising=False)

        ExtensionManager._trim_extension_history()

        assert len(ExtensionManager.extensions) == 6
