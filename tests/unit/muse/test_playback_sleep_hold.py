"""Playback's use of lib.sleep_prevention: one hold at a time, each acquire
matched by exactly one release, and none left once playback ends."""

from unittest.mock import MagicMock

import pytest
import vlc

import muse.playback as playback_module
from lib.sleep_prevention import WakeLevel
from muse.playback import Playback


@pytest.fixture
def wake_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(playback_module, "acquire_wake", lambda level: calls.append(("acquire", level)))
    monkeypatch.setattr(playback_module, "release_wake", lambda level: calls.append(("release", level)))
    return calls


def _playback(state=vlc.State.Playing, is_video=False):
    playback = Playback.__new__(Playback)
    playback._wake_level = WakeLevel.NONE
    playback.vlc_media_player = MagicMock()
    playback.vlc_media_player.get_state.return_value = state
    playback.track = MagicMock()
    playback.track.get_is_video.return_value = is_video
    return playback


def _balance(calls):
    held = {}
    for action, level in calls:
        held[level] = held.get(level, 0) + (1 if action == "acquire" else -1)
    return {level: n for level, n in held.items() if n}


def test_audio_holds_the_system_level_once(wake_calls):
    playback = _playback()
    for _ in range(5):
        playback._update_sleep_hold()
    assert wake_calls == [("acquire", WakeLevel.SYSTEM)]


def test_video_holds_the_display_level(wake_calls):
    playback = _playback(is_video=True)
    playback._update_sleep_hold()
    assert wake_calls == [("acquire", WakeLevel.DISPLAY)]


def test_pausing_releases_and_resuming_reacquires(wake_calls):
    playback = _playback()
    playback._update_sleep_hold()
    playback.vlc_media_player.get_state.return_value = vlc.State.Paused
    playback._update_sleep_hold()
    assert _balance(wake_calls) == {}
    playback.vlc_media_player.get_state.return_value = vlc.State.Playing
    playback._update_sleep_hold()
    assert _balance(wake_calls) == {WakeLevel.SYSTEM: 1}


def test_switching_tracks_acquires_the_new_level_before_releasing_the_old(wake_calls):
    playback = _playback()
    playback._update_sleep_hold()
    playback.track.get_is_video.return_value = True
    playback._update_sleep_hold()
    assert wake_calls == [
        ("acquire", WakeLevel.SYSTEM),
        ("acquire", WakeLevel.DISPLAY),
        ("release", WakeLevel.SYSTEM),
    ]
    assert _balance(wake_calls) == {WakeLevel.DISPLAY: 1}


def test_release_sleep_hold_leaves_nothing_held_and_is_safe_to_repeat(wake_calls):
    playback = _playback(is_video=True)
    playback._update_sleep_hold()
    playback.release_sleep_hold()
    playback.release_sleep_hold()
    assert _balance(wake_calls) == {}
    assert playback._wake_level == WakeLevel.NONE
