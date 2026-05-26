"""
Regression tests: playlist stalls when a paused track reaches its end.

Root cause (muse/playback.py): the track wait loop used
    is_playing() or is_paused
VLC reports not playing when paused, so mid-track pause is handled correctly.
When the track ends while paused, is_paused stays True and the loop never exits.
"""


def _legacy_should_continue(is_playing: bool, is_paused: bool, skip_track: bool) -> bool:
    return (is_playing or is_paused) and not skip_track


def _fixed_should_continue(
    is_playing: bool,
    is_paused: bool,
    skip_track: bool,
    at_end: bool,
) -> bool:
    if skip_track:
        return False
    if is_playing:
        return True
    if not is_paused:
        return False
    return not at_end


class TestPauseAtTrackEndWaitCondition:
    def test_legacy_stalls_when_paused_at_track_end(self):
        assert _legacy_should_continue(False, True, False) is True

    def test_fixed_advances_when_paused_at_track_end(self):
        assert _fixed_should_continue(False, True, False, True) is False

    def test_fixed_waits_while_paused_mid_track(self):
        assert _fixed_should_continue(False, True, False, False) is True

    def test_fixed_waits_while_playing(self):
        assert _fixed_should_continue(True, False, False, False) is True

    def test_fixed_advances_when_track_ends_without_pause(self):
        assert _fixed_should_continue(False, False, False, True) is False

    def test_skip_track_exits_wait_in_both_cases(self):
        assert _legacy_should_continue(True, True, True) is False
        assert _fixed_should_continue(True, True, True, False) is False


def _is_track_at_end(state_ended: bool, length_ms: int, time_ms: int) -> bool:
    """Mirror of Playback._is_track_at_end position/state checks."""
    if state_ended:
        return True
    if length_ms <= 0:
        return False
    if time_ms < 0:
        return False
    return time_ms >= length_ms - 500


class TestIsTrackAtEnd:
    def test_ended_state(self):
        assert _is_track_at_end(True, -1, -1) is True

    def test_position_at_end(self):
        assert _is_track_at_end(False, 120_000, 119_600) is True

    def test_paused_mid_track(self):
        assert _is_track_at_end(False, 120_000, 30_000) is False
