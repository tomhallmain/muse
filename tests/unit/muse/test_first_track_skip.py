"""
Isolated regression tests for Issue (1): Intermittent first-track skip.

Root cause (muse/playback.py  Playback.run()):

    self.vlc_media_player.play()
    time.sleep(0.5)                          # ← fixed 500 ms grace period
    cumulative_sleep_seconds = 0.5
    if not self.vlc_media_player.is_playing():
        self.last_track_failed = True
    while (self.vlc_media_player.is_playing()   # ← False → loop skipped entirely
           or self._run_context.is_paused)
          and not self._run_context.skip_track:
        time.sleep(0.5)
        ...
    self.vlc_media_player.stop()
    # Immediately loops back → get_track() returns SECOND track

VLC's `play()` call is asynchronous.  The player transitions through the states
STOPPED → OPENING → BUFFERING → PLAYING.  `is_playing()` only returns True once
it reaches the PLAYING state.  On a slow disk, large file, cold start, or under
heavy system load this transition can take well over 0.5 s.  When that happens
`is_playing()` is still False at the check point, the playback while-loop is
skipped, and the first track is silently discarded.

Proposed fix (see test_fixed_wait_for_playback below): replace the single
`sleep(0.5)` + `is_playing()` check with a polling loop that retries until
VLC reports PLAYING or an explicit timeout (e.g. 5 s) is exceeded.  Only mark
the track as failed once the timeout is exceeded.

The helper `wait_for_playback_start` at the bottom of this module is a drop-in
replacement for the current logic that can be embedded in Playback.run().
"""
import time
import pytest
from typing import Optional


# ---------------------------------------------------------------------------
# Mock VLC MediaPlayer
# ---------------------------------------------------------------------------

class SlowStartPlayer:
    """Simulates a VLC MediaPlayer that takes `startup_delay` seconds to start.

    Call sequence mirrors the real libvlc Python bindings used in Playback:
      - play()        – starts async playback
      - is_playing()  – returns False until startup_delay seconds after play()
      - stop()        – halts playback
    """

    def __init__(self, startup_delay: float = 0.0, play_duration: float = 2.0):
        """
        Args:
            startup_delay: seconds after play() before is_playing() returns True.
            play_duration: total seconds the track "plays" before stopping naturally.
        """
        self.startup_delay = startup_delay
        self.play_duration = play_duration
        self._play_called_at: Optional[float] = None
        self._stopped = True

        # Introspection counters – examined by tests
        self.play_call_count = 0
        self.stop_call_count = 0

    def play(self):
        self.play_call_count += 1
        self._play_called_at = time.monotonic()
        self._stopped = False

    def stop(self):
        self.stop_call_count += 1
        self._stopped = True

    def is_playing(self) -> bool:
        if self._play_called_at is None or self._stopped:
            return False
        elapsed = time.monotonic() - self._play_called_at
        if elapsed < self.startup_delay:
            return False
        if elapsed >= self.startup_delay + self.play_duration:
            return False  # track finished naturally
        return True

    # Stubs so the mock can be used in place of vlc.MediaPlayer
    def audio_set_volume(self, volume: int):
        pass

    def get_length(self) -> int:
        return int(self.play_duration * 1000)

    def get_time(self) -> int:
        if self._play_called_at is None:
            return 0
        return int((time.monotonic() - self._play_called_at) * 1000)


# ---------------------------------------------------------------------------
# Helpers: current vs. proposed logic
# ---------------------------------------------------------------------------

def _current_wait_logic(player: SlowStartPlayer) -> bool:
    """Reproduces the current (buggy) Playback.run() wait-and-check logic.

    Returns True if the track was considered to be playing (i.e. the main
    while-loop was entered at least once), False if it was immediately skipped.
    """
    player.play()
    time.sleep(0.5)                        # current fixed grace period

    if not player.is_playing():
        # current code sets last_track_failed = True here and the while-loop
        # guard evaluates to False → loop body is never executed → track skipped
        return False

    # Main playback while-loop (simplified: run one iteration then stop)
    if player.is_playing():
        player.stop()
        return True

    return False


def wait_for_playback_start(
    player: SlowStartPlayer,
    timeout: float = 5.0,
    poll_interval: float = 0.05,
) -> bool:
    """Proposed replacement for the fixed sleep(0.5) + single is_playing() check.

    Polls `player.is_playing()` at `poll_interval` intervals for up to
    `timeout` seconds.  Returns True once VLC reports it is playing; returns
    False only if the timeout is exceeded without the player starting.

    Drop-in for the relevant section of Playback.run():

        # BEFORE (buggy):
        self.vlc_media_player.play()
        time.sleep(0.5)
        if not self.vlc_media_player.is_playing():
            self.last_track_failed = True

        # AFTER (fixed):
        self.vlc_media_player.play()
        if not wait_for_playback_start(self.vlc_media_player):
            self.last_track_failed = True
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if player.is_playing():
            return True
        time.sleep(poll_interval)
    return False


def _fixed_wait_logic(player: SlowStartPlayer) -> bool:
    """Same test harness as _current_wait_logic but uses the proposed fix."""
    player.play()

    if not wait_for_playback_start(player, timeout=5.0, poll_interval=0.05):
        return False  # timed out

    # Main playback while-loop (simplified: run one iteration then stop)
    if player.is_playing():
        player.stop()
        return True

    return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFirstTrackSkipBug:
    """
    Verifies the root cause of the intermittent first-track skip.

    The current code sleeps a fixed 0.5 s then checks is_playing() exactly
    once.  When VLC's startup latency exceeds that 0.5 s window the check
    returns False, the playback loop is skipped, and the track is discarded.
    """

    def test_fast_vlc_start_plays_correctly(self):
        """Track with fast VLC startup (< 0.5 s) is played as expected."""
        player = SlowStartPlayer(startup_delay=0.1)
        played = _current_wait_logic(player)
        assert played, (
            "Fast-starting VLC should register as playing after the 0.5 s sleep"
        )

    def test_slow_vlc_start_triggers_bug(self):
        """
        DEMONSTRATES THE BUG:
        When VLC takes longer than 0.5 s to start, is_playing() returns False
        after the single sleep, the playback loop is never entered, and the
        track is silently skipped.
        """
        # startup_delay > 0.5 s → is_playing() still False when checked
        player = SlowStartPlayer(startup_delay=0.8)
        played = _current_wait_logic(player)

        assert not played, (
            "BUG CONFIRMED: a track whose VLC startup takes 0.8 s is "
            "silently skipped by the current 0.5 s fixed grace period"
        )

    def test_borderline_vlc_start_is_unreliable(self):
        """
        Startup close to the 0.5 s boundary is inherently flaky under the
        current logic – this is why the bug is intermittent in practice.

        With startup_delay = 0.45 s the track *may* play (if sleep(0.5)
        overshoots slightly) or may not (if the OS schedules sleep short).
        We don't assert a specific outcome here; we just document that the
        outcome is non-deterministic and depends on OS scheduling precision.
        """
        player = SlowStartPlayer(startup_delay=0.45)
        # Calling the current logic is sufficient; the assertion is omitted
        # because the result is OS-dependent.  The test documents the risk.
        _current_wait_logic(player)
        # No assertion – the point is to illustrate the fragility.

    def test_play_is_called_exactly_once(self):
        """Sanity: play() is called exactly once per track attempt."""
        player = SlowStartPlayer(startup_delay=0.1)
        _current_wait_logic(player)
        assert player.play_call_count == 1

    def test_stop_is_called_after_successful_play(self):
        """stop() must be called to release VLC resources after playback."""
        player = SlowStartPlayer(startup_delay=0.1)
        _current_wait_logic(player)
        assert player.stop_call_count == 1


@pytest.mark.unit
class TestFixedWaitForPlayback:
    """
    Verifies that the proposed polling-based wait_for_playback_start() fix
    correctly handles both fast and slow VLC startup scenarios.
    """

    def test_fast_start_still_plays(self):
        """Fix should not break the happy path."""
        player = SlowStartPlayer(startup_delay=0.1)
        played = _fixed_wait_logic(player)
        assert played, "Fast-starting track must still play with the fix applied"

    def test_slow_start_within_timeout_now_plays(self):
        """
        FIX VERIFIED:
        With startup_delay = 0.8 s (which the current code silently skips),
        the polling fix detects playback once VLC is ready and the track plays.
        """
        player = SlowStartPlayer(startup_delay=0.8)
        played = _fixed_wait_logic(player)
        assert played, (
            "A track whose VLC startup takes 0.8 s must play with the fix; "
            "the polling loop must wait long enough for VLC to reach PLAYING state"
        )

    def test_very_slow_start_within_timeout_plays(self):
        """Even a 3 s startup delay (within the 5 s timeout) must not skip."""
        player = SlowStartPlayer(startup_delay=3.0, play_duration=1.0)
        played = _fixed_wait_logic(player)
        assert played, "3 s startup delay is within the 5 s timeout; track must play"

    def test_startup_beyond_timeout_is_marked_failed(self):
        """
        If VLC genuinely never starts (startup_delay > timeout), the track
        should be marked as failed – not played and not hung forever.
        """
        player = SlowStartPlayer(startup_delay=999.0)  # never starts within timeout
        started = wait_for_playback_start(player, timeout=0.2, poll_interval=0.02)
        assert not started, (
            "A player that never reaches PLAYING state within the timeout "
            "must be reported as failed"
        )

    def test_wait_returns_quickly_on_immediate_play(self):
        """Polling overhead for an immediately-playing track should be minimal."""
        player = SlowStartPlayer(startup_delay=0.0)
        player.play()
        t0 = time.monotonic()
        started = wait_for_playback_start(player, timeout=5.0, poll_interval=0.05)
        elapsed = time.monotonic() - t0

        assert started
        # Should return almost immediately – well under 0.5 s
        assert elapsed < 0.5, (
            f"wait_for_playback_start took {elapsed:.3f}s for an immediately-"
            f"playing track; it should return in under one poll interval"
        )

    def test_play_call_count_unchanged(self):
        """The fix must not call play() more than once per track."""
        player = SlowStartPlayer(startup_delay=0.1)
        _fixed_wait_logic(player)
        assert player.play_call_count == 1

    def test_stop_called_after_successful_play(self):
        """stop() must still be called after successful playback."""
        player = SlowStartPlayer(startup_delay=0.1)
        _fixed_wait_logic(player)
        assert player.stop_call_count == 1


@pytest.mark.unit
class TestWaitForPlaybackStartHelper:
    """
    Direct unit tests for the wait_for_playback_start() helper.
    These document the expected contract independently of the playback harness.
    """

    def test_returns_true_when_playing_immediately(self):
        player = SlowStartPlayer(startup_delay=0.0)
        player.play()
        assert wait_for_playback_start(player, timeout=1.0, poll_interval=0.01)

    def test_returns_true_when_playing_before_timeout(self):
        player = SlowStartPlayer(startup_delay=0.15)
        player.play()
        assert wait_for_playback_start(player, timeout=1.0, poll_interval=0.01)

    def test_returns_false_when_never_playing_within_timeout(self):
        player = SlowStartPlayer(startup_delay=999.0)
        player.play()
        assert not wait_for_playback_start(player, timeout=0.1, poll_interval=0.01)

    def test_does_not_call_play(self):
        """wait_for_playback_start only polls; it must not call play() itself."""
        player = SlowStartPlayer(startup_delay=0.0)
        player.play()
        wait_for_playback_start(player, timeout=0.2, poll_interval=0.01)
        # play() was already called once before the helper; it must still be 1
        assert player.play_call_count == 1

    def test_respects_poll_interval(self):
        """Elapsed time should be bounded by timeout + one extra poll_interval."""
        player = SlowStartPlayer(startup_delay=999.0)  # will time out
        player.play()
        timeout = 0.10
        poll_interval = 0.02
        t0 = time.monotonic()
        wait_for_playback_start(player, timeout=timeout, poll_interval=poll_interval)
        elapsed = time.monotonic() - t0
        # Should not overshoot by more than one extra poll interval
        assert elapsed < timeout + poll_interval * 3, (
            f"Elapsed {elapsed:.3f}s exceeded timeout {timeout}s by more than "
            f"the allowed overshoot ({poll_interval * 3}s)"
        )
