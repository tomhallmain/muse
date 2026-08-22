"""Tests for how Playback drives the two affinity passes on a grouping change.

The attribute pass runs inline; the model pass is handed to a thread because it
can take seconds and must never hold up a track. These tests run the "thread"
inline so the ordering between the two passes is observable.
"""

import pytest

from muse.playback import Playback


class _Playlist:
    def __init__(self, learned=True, embedding_learned=None):
        self.calls = []
        self._learned = learned
        self._embedding_learned = learned if embedding_learned is None else embedding_learned

    def resort_upcoming(self):
        self.calls.append("resort")
        return True

    def refresh_llm_group_scores(self):
        self.calls.append("score")
        return self._learned

    def refresh_embedding_group_scores(self):
        self.calls.append("embed")
        return self._embedding_learned


def _playback(playlist):
    playback = Playback.__new__(Playback)
    playback._affinity_scoring_active = False
    playback._playback_config = type("_Config", (), {"get_list": lambda _self: playlist})()
    return playback


@pytest.fixture
def inline_threads(monkeypatch):
    """Run what would be a background thread inline, so its effect is visible."""
    started = []

    def _start(callable_, use_asyncio=True, args=None):
        started.append(callable_)
        callable_(*(args or []))
        return None

    monkeypatch.setattr("muse.playback.Utils.start_thread", _start)
    return started


@pytest.mark.unit
class TestResortUpcomingTracks:
    def test_the_attribute_pass_runs_before_the_model_passes(self, inline_threads):
        """The cheap pass must not wait on the model calls, and the window is
        rearranged once for the grouping change rather than once per signal."""
        playlist = _Playlist()
        _playback(playlist)._resort_upcoming_tracks()

        assert playlist.calls == ["resort", "score", "embed", "resort"]

    def test_nothing_learned_means_no_second_reorder(self, inline_threads):
        playlist = _Playlist(learned=False)
        _playback(playlist)._resort_upcoming_tracks()

        assert playlist.calls == ["resort", "score", "embed"]

    def test_one_signal_declining_still_counts_the_other(self, inline_threads):
        """Embeddings are off unless a model has been pulled, so the chat signal
        has to stand on its own."""
        playlist = _Playlist(learned=True, embedding_learned=False)
        _playback(playlist)._resort_upcoming_tracks()

        assert playlist.calls == ["resort", "score", "embed", "resort"]

    def test_a_raising_signal_does_not_stop_the_other(self, inline_threads):
        playlist = _Playlist()
        playlist.refresh_llm_group_scores = lambda: (_ for _ in ()).throw(RuntimeError("no ollama"))
        _playback(playlist)._resort_upcoming_tracks()

        assert playlist.calls == ["resort", "embed", "resort"]

    def test_no_playlist_is_not_an_error(self, inline_threads):
        playback = Playback.__new__(Playback)
        playback._affinity_scoring_active = False
        playback._playback_config = type("_Config", (), {"get_list": lambda _self: None})()

        playback._resort_upcoming_tracks()

        assert inline_threads == []

    def test_a_scoring_pass_already_running_is_not_duplicated(self, inline_threads):
        """A run of rapid group skips would otherwise queue a call per skip
        against one local model."""
        playlist = _Playlist()
        playback = _playback(playlist)
        playback._affinity_scoring_active = True

        playback._resort_upcoming_tracks()

        assert playlist.calls == ["resort"]
        assert inline_threads == []

    def test_the_guard_is_released_after_a_pass(self, inline_threads):
        playback = _playback(_Playlist())
        playback._resort_upcoming_tracks()

        assert playback._affinity_scoring_active is False

    def test_the_guard_is_released_when_every_signal_raises(self, monkeypatch, inline_threads):
        def _raise():
            raise RuntimeError("no ollama")

        playlist = _Playlist()
        playlist.refresh_llm_group_scores = _raise
        playlist.refresh_embedding_group_scores = _raise
        playback = _playback(playlist)

        playback._resort_upcoming_tracks()

        assert playback._affinity_scoring_active is False
        assert playlist.calls == ["resort"]

    def test_the_guard_is_released_when_the_thread_cannot_start(self, monkeypatch):
        def _cannot_start(*_a, **_k):
            raise RuntimeError("can't start new thread")

        monkeypatch.setattr("muse.playback.Utils.start_thread", _cannot_start)
        playback = _playback(_Playlist())

        playback._resort_upcoming_tracks()

        assert playback._affinity_scoring_active is False

    def test_a_failing_attribute_pass_does_not_propagate(self, inline_threads):
        playlist = _Playlist()
        playlist.resort_upcoming = lambda: (_ for _ in ()).throw(RuntimeError("bad playlist"))
        playback = _playback(playlist)

        playback._resort_upcoming_tracks()

        assert inline_threads == []
