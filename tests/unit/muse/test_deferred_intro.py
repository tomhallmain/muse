"""
Tests for the deferred DJ introduction feature.

At startup, change_voice() is called with skip_intro=True so music starts
immediately without waiting for intro generation. The intro is instead stored
as _pending_intro_persona and fires from prepare() once the first track has
played (i.e. when spot_profile.previous_track is not None).
"""
import datetime
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def muse_instance(mock_args, mock_data_callbacks):
    """Muse with _do_introduction stubbed to avoid LLM/TTS calls."""
    from muse.muse import Muse
    from muse.run_context import RunContext
    mock_args.muse = True
    run_context = RunContext()
    muse = Muse(args=mock_args, library_data=mock_data_callbacks,
                run_context=run_context, ui_callbacks=None)
    muse._do_introduction = MagicMock()
    muse.set_topic = MagicMock()
    # Personas are keyed by voice_name (e.g. "Royston Min"), not display name.
    # allow_mock_personas auto-creates a stub persona for any unknown name so
    # change_voice("Royston") hits the `if persona:` branch in tests.
    muse.memory.get_persona_manager().allow_mock_personas = True
    return muse


@pytest.fixture
def silent_spot_profile():
    """A spot profile mock that won't trigger any DJ speaking logic."""
    sp = MagicMock()
    sp.is_going_to_say_something.return_value = False
    sp.previous_track = None
    return sp


# ---------------------------------------------------------------------------
# change_voice() skip_intro behaviour
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestChangeVoiceSkipIntro:
    def test_skip_intro_sets_pending_persona(self, muse_instance):
        muse_instance.change_voice("Royston", skip_intro=True)
        assert muse_instance._pending_intro_persona is not None

    def test_skip_intro_does_not_call_do_introduction(self, muse_instance):
        muse_instance.change_voice("Royston", skip_intro=True)
        muse_instance._do_introduction.assert_not_called()

    def test_no_skip_intro_calls_do_introduction_immediately(self, muse_instance):
        muse_instance.change_voice("Royston", skip_intro=False)
        muse_instance._do_introduction.assert_called_once()

    def test_no_skip_intro_clears_pending_persona(self, muse_instance):
        muse_instance._pending_intro_persona = MagicMock()  # stale pending
        muse_instance.change_voice("Royston", skip_intro=False)
        assert muse_instance._pending_intro_persona is None

    def test_second_skip_intro_call_replaces_pending(self, muse_instance):
        """A second skip_intro=True call replaces, not stacks, the pending intro."""
        muse_instance.change_voice("Royston", skip_intro=True)
        first_pending = muse_instance._pending_intro_persona
        muse_instance.change_voice("Sofia", skip_intro=True)
        assert muse_instance._pending_intro_persona is not first_pending


# ---------------------------------------------------------------------------
# prepare() deferred intro trigger
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPrepareFiresDeferredIntro:
    def test_pending_intro_fires_when_previous_track_set(self, muse_instance, silent_spot_profile):
        pending = MagicMock()
        muse_instance._pending_intro_persona = pending
        silent_spot_profile.previous_track = MagicMock()  # first track has played

        muse_instance.prepare(silent_spot_profile)

        muse_instance._do_introduction.assert_called_once_with(
            pending, silent_spot_profile.get_upcoming_tracks_callback
        )

    def test_pending_intro_not_fired_when_no_previous_track(self, muse_instance, silent_spot_profile):
        muse_instance._pending_intro_persona = MagicMock()
        silent_spot_profile.previous_track = None  # no track played yet

        muse_instance.prepare(silent_spot_profile)

        muse_instance._do_introduction.assert_not_called()

    def test_pending_intro_cleared_after_firing(self, muse_instance, silent_spot_profile):
        muse_instance._pending_intro_persona = MagicMock()
        silent_spot_profile.previous_track = MagicMock()

        muse_instance.prepare(silent_spot_profile)

        assert muse_instance._pending_intro_persona is None

    def test_pending_intro_retained_when_no_previous_track(self, muse_instance, silent_spot_profile):
        pending = MagicMock()
        muse_instance._pending_intro_persona = pending
        silent_spot_profile.previous_track = None

        muse_instance.prepare(silent_spot_profile)

        assert muse_instance._pending_intro_persona is pending

    def test_was_spoken_set_when_deferred_intro_fires(self, muse_instance, silent_spot_profile):
        muse_instance._pending_intro_persona = MagicMock()
        silent_spot_profile.previous_track = MagicMock()

        muse_instance.prepare(silent_spot_profile)

        assert silent_spot_profile.was_spoken is True

    def test_no_intro_when_no_pending_persona(self, muse_instance, silent_spot_profile):
        muse_instance._pending_intro_persona = None
        silent_spot_profile.previous_track = MagicMock()

        muse_instance.prepare(silent_spot_profile)

        muse_instance._do_introduction.assert_not_called()


# ---------------------------------------------------------------------------
# check_schedules() skip_intro flag at startup vs. schedule change
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCheckSchedulesSkipIntroFlag:
    def test_startup_passes_skip_intro_true(self, muse_instance):
        """First check_schedules() call must pass skip_intro=True to change_voice."""
        assert muse_instance._last_checked_schedules is None
        muse_instance.change_voice = MagicMock()

        muse_instance.check_schedules()

        _, kwargs = muse_instance.change_voice.call_args
        assert kwargs.get("skip_intro") is True

    def test_schedule_change_passes_skip_intro_false(self, muse_instance):
        """A mid-session schedule change must pass skip_intro=False to change_voice."""
        # Simulate post-startup state
        muse_instance._last_checked_schedules = datetime.datetime.now()
        mock_schedule = MagicMock()
        mock_schedule.voice = "Sofia"
        # Ensure _schedule differs from the mock so a "change" is detected
        muse_instance._schedule = MagicMock()

        muse_instance.change_voice = MagicMock()
        with patch("muse.muse.SchedulesManager.get_active_schedule", return_value=mock_schedule):
            muse_instance.check_schedules()

        _, kwargs = muse_instance.change_voice.call_args
        assert kwargs.get("skip_intro") is False
