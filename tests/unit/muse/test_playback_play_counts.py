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
