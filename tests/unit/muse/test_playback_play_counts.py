"""Tests for Playback recording a play count once enough of a track was heard."""

from types import SimpleNamespace

import pytest

import muse.playback as playback_module
from muse.playback import Playback


def _track(**overrides):
    values = dict(filepath="/m/a.mp3", parent_filepath=None, _is_stream=False,
                  get_track_length=lambda: 200.0)
    values.update(overrides)
    return SimpleNamespace(**values)


def _playback(track, failed=False):
    playback = Playback.__new__(Playback)
    playback.track = track
    playback.last_track_failed = failed
    return playback


@pytest.fixture
def recorded(monkeypatch):
    calls = []
    monkeypatch.setattr(playback_module.play_counts, "record_play", calls.append)
    monkeypatch.setattr(playback_module.play_counts.config, "play_count_threshold_ratio", 0.5, raising=False)
    monkeypatch.setattr(playback_module.play_counts.config, "play_count_threshold_cap_seconds", 0, raising=False)
    return calls


@pytest.mark.unit
class TestRecordPlayIfHeard:
    def test_enough_heard_records_once(self, recorded):
        track = _track()
        _playback(track)._record_play_if_heard(100.0)
        assert recorded == [track]

    def test_too_little_heard_records_nothing(self, recorded):
        _playback(_track())._record_play_if_heard(99.5)
        assert recorded == []

    def test_the_threshold_follows_the_track_length(self, recorded):
        track = _track(get_track_length=lambda: 100.0)
        _playback(track)._record_play_if_heard(50.0)
        assert recorded == [track]

    def test_an_unknown_track_length_records_nothing(self, recorded):
        _playback(_track(get_track_length=lambda: -1.0))._record_play_if_heard(1000.0)
        assert recorded == []

    @pytest.mark.parametrize("overrides", [{"_is_stream": True}, {"parent_filepath": "/m/whole.mp3"}])
    def test_streams_and_split_parts_are_skipped(self, recorded, overrides):
        _playback(_track(**overrides))._record_play_if_heard(1000.0)
        assert recorded == []

    def test_a_failed_start_is_skipped(self, recorded):
        _playback(_track(), failed=True)._record_play_if_heard(1000.0)
        assert recorded == []

    def test_a_recording_error_does_not_propagate(self, monkeypatch, recorded):
        def fail(track):
            raise RuntimeError("db locked")
        monkeypatch.setattr(playback_module.play_counts, "record_play", fail)
        _playback(_track())._record_play_if_heard(1000.0)


class _StreamTrack:
    _is_stream = True
    parent_filepath = None
    album = "Radio Example"

    def is_stream(self):
        return True

    def update_from_icy(self, artist, title):
        return True


@pytest.fixture
def heard(monkeypatch):
    calls = []
    monkeypatch.setattr(playback_module.play_counts, "record_stream_title",
                        lambda artist, title, station: calls.append((artist, title, station)))
    monkeypatch.setattr(playback_module.config, "radio_heard_min_seconds", 60, raising=False)
    return calls


def _stream_playback():
    playback = _playback(_StreamTrack())
    playback.ui_callbacks = None
    playback._run = None
    playback._icy_current_title = None
    return playback


@pytest.mark.unit
class TestStreamTitleHeard:
    def test_a_title_that_played_long_enough_is_recorded_on_the_next_change(self, heard):
        import time as time_module
        playback = _stream_playback()
        playback._on_icy_title_change("Band", "First")
        playback._icy_current_title = ("Band", "First", time_module.monotonic() - 61)
        playback._on_icy_title_change("Band", "Second")
        assert heard == [("Band", "First", "Radio Example")]

    def test_a_title_changed_away_from_quickly_is_not_recorded(self, heard):
        playback = _stream_playback()
        playback._on_icy_title_change("Band", "First")
        playback._on_icy_title_change("Band", "Second")
        assert heard == []

    def test_stopping_the_stream_records_the_title_playing(self, heard):
        import time as time_module
        playback = _stream_playback()
        playback._icy_current_title = ("Band", "Last", time_module.monotonic() - 61)
        playback._record_play_if_heard(0.0)
        assert heard == [("Band", "Last", "Radio Example")]
        playback._record_play_if_heard(0.0)
        assert len(heard) == 1
