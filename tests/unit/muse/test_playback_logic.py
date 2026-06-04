"""Unit tests for muse/playback.py.

Strategy: patch the module-level `INSTANCE` so that `Playback.__init__`'s
`INSTANCE.media_player_new()` call returns a MagicMock.  All VLC media-player
interactions (get_state, get_time, is_playing, audio_set_volume, …) are then
asserted on that mock.

Methods that drive real VLC playback (`run`, `play_one_song`, `register_new_song`)
are not covered here — they require actual audio output and a live VLC instance.

Isolation: `reset_app_globals` (autouse from root conftest) clears
`PlaybackConfig.open_configs` before and after each test.
"""

import vlc
from unittest.mock import MagicMock

import pytest

from utils.globals import TrackResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_vlc_instance(monkeypatch):
    """Replace the module-level VLC instance so no real audio device is needed.

    autouse=True ensures every test in this module uses the mock, preventing
    accidental real-VLC calls even if a test constructs Playback directly
    instead of going through the `playback` fixture.
    """
    import muse.playback as playback_mod
    mock_inst = MagicMock()
    mock_inst.media_player_new.return_value = MagicMock()
    monkeypatch.setattr(playback_mod, "INSTANCE", mock_inst)
    return mock_inst


@pytest.fixture
def playback(mock_vlc_instance, mock_data_callbacks):
    """A Playback with an empty playlist and no run/ui context."""
    from muse.playback import Playback
    from muse.playback_config import PlaybackConfig
    pc = PlaybackConfig(data_callbacks=mock_data_callbacks, explicit_tracks=[])
    return Playback(playback_config=pc, ui_callbacks=None, run=None)


@pytest.fixture
def mock_track():
    t = MagicMock()
    t.filepath = "/music/test.flac"
    t.is_invalid.return_value = False
    t.get_volume.return_value = (-20.0, -10.0)
    t.get_is_video.return_value = False
    t.get_album_artwork.return_value = None
    t.get_track_text_file.return_value = "/music/test.txt"
    t.get_track_length.return_value = 120.0
    return t


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPlaybackInit:
    def test_vlc_media_player_created_from_instance(self, mock_vlc_instance, mock_data_callbacks):
        from muse.playback import Playback
        from muse.playback_config import PlaybackConfig
        pc = PlaybackConfig(data_callbacks=mock_data_callbacks, explicit_tracks=[])
        Playback(playback_config=pc, ui_callbacks=None, run=None)
        mock_vlc_instance.media_player_new.assert_called_once()

    def test_initial_state(self, playback):
        assert playback.track is None
        assert playback.count == 0
        assert not playback.has_played_first_track
        assert not playback._timer_volume_override


# ---------------------------------------------------------------------------
# has_muse / get_muse
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMuseAccess:
    def test_has_muse_false_when_no_run(self, playback):
        assert not playback.has_muse()

    def test_get_muse_raises_when_none(self, playback):
        with pytest.raises(Exception, match="No Muse instance found"):
            playback.get_muse()


# ---------------------------------------------------------------------------
# Timer volume override
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestTimerVolumeOverride:
    def test_enable_override_sets_flag_and_volume(self, playback):
        playback.set_timer_volume_override(True, 15)
        assert playback._timer_volume_override is True
        assert playback._timer_override_volume == 15

    def test_disable_override_clears_flag(self, playback):
        playback._timer_volume_override = True
        playback.set_timer_volume_override(False)
        assert playback._timer_volume_override is False

    def test_enable_without_volume_keeps_previous_volume(self, playback):
        playback._timer_override_volume = 25
        playback.set_timer_volume_override(True)
        assert playback._timer_override_volume == 25


# ---------------------------------------------------------------------------
# set_volume
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSetVolume:
    def test_timer_override_uses_override_volume(self, playback):
        playback._timer_volume_override = True
        playback._timer_override_volume = 15
        playback.set_volume()
        playback.vlc_media_player.audio_set_volume.assert_called_once_with(15)

    def test_normal_volume_derived_from_track(self, playback, mock_track):
        playback.track = mock_track
        mock_track.get_volume.return_value = (-20.0, -10.0)
        playback.set_volume()
        call_arg = playback.vlc_media_player.audio_set_volume.call_args[0][0]
        assert 0 <= call_arg <= 100

    def test_very_quiet_track_gets_boosted(self, playback, mock_track):
        playback.track = mock_track
        mock_track.get_volume.return_value = (-60.0, -55.0)   # mean < -50
        playback.set_volume()
        call_arg = playback.vlc_media_player.audio_set_volume.call_args[0][0]
        assert call_arg > 0


# ---------------------------------------------------------------------------
# _is_track_at_end
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestIsTrackAtEnd:
    def test_ended_vlc_state_returns_true(self, playback):
        playback.vlc_media_player.get_state.return_value = vlc.State.Ended
        assert playback._is_track_at_end() is True

    def test_zero_length_returns_false(self, playback):
        playback.vlc_media_player.get_state.return_value = vlc.State.Playing
        playback.vlc_media_player.get_length.return_value = 0
        assert playback._is_track_at_end() is False

    def test_negative_time_returns_false(self, playback):
        playback.vlc_media_player.get_state.return_value = vlc.State.Playing
        playback.vlc_media_player.get_length.return_value = 10000
        playback.vlc_media_player.get_time.return_value = -1
        assert playback._is_track_at_end() is False

    def test_within_threshold_returns_true(self, playback):
        playback.vlc_media_player.get_state.return_value = vlc.State.Playing
        playback.vlc_media_player.get_length.return_value = 10000
        playback.vlc_media_player.get_time.return_value = 9600   # >= 10000 - 500
        assert playback._is_track_at_end() is True

    def test_before_threshold_returns_false(self, playback):
        playback.vlc_media_player.get_state.return_value = vlc.State.Playing
        playback.vlc_media_player.get_length.return_value = 10000
        playback.vlc_media_player.get_time.return_value = 5000
        assert playback._is_track_at_end() is False


# ---------------------------------------------------------------------------
# _should_continue_track_wait
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestShouldContinueTrackWait:
    def test_skip_track_stops_wait(self, playback):
        playback._run_context.skip_track = True
        assert playback._should_continue_track_wait() is False

    def test_is_playing_continues_wait(self, playback):
        playback._run_context.skip_track = False
        playback.vlc_media_player.is_playing.return_value = True
        assert playback._should_continue_track_wait() is True

    def test_not_playing_not_paused_stops_wait(self, playback):
        playback._run_context.skip_track = False
        playback.vlc_media_player.is_playing.return_value = False
        playback._run_context.is_paused = False
        assert playback._should_continue_track_wait() is False

    def test_paused_not_at_end_continues_wait(self, playback):
        playback._run_context.skip_track = False
        playback.vlc_media_player.is_playing.return_value = False
        playback._run_context.is_paused = True
        playback.vlc_media_player.get_state.return_value = vlc.State.Playing
        playback.vlc_media_player.get_length.return_value = 10000
        playback.vlc_media_player.get_time.return_value = 1000
        assert playback._should_continue_track_wait() is True


# ---------------------------------------------------------------------------
# get_track — flow control paths
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetTrack:
    def test_empty_playlist_returns_false(self, playback):
        assert playback.get_track() is False

    def test_clears_seek_target_and_delegates(self, playback):
        mock_config = MagicMock()
        mock_config.next_track.return_value = TrackResult()
        mock_config.enable_long_track_splitting = False
        playback._playback_config = mock_config
        playback._run_context.seek_target_filepath = "/some/path.flac"

        playback.get_track()

        assert playback._run_context.seek_target_filepath is None
        mock_config.seek_to_track.assert_called_once_with("/some/path.flac")

    def test_did_advance_passes_places_from_current(self, playback):
        mock_config = MagicMock()
        mock_config.next_track.return_value = TrackResult()
        mock_config.enable_long_track_splitting = False
        playback._playback_config = mock_config
        playback.did_advance = True
        playback.places_from_current = 2
        playback.has_attempted_track_split = True   # skip ensure_splittable_track

        playback.get_track()

        mock_config.next_track.assert_called_once_with(
            skip_grouping=False, places_from_current=2
        )

    def test_skip_grouping_flag_cleared_after_call(self, playback):
        mock_config = MagicMock()
        mock_config.next_track.return_value = TrackResult()
        mock_config.enable_long_track_splitting = False
        playback._playback_config = mock_config
        playback._run_context.skip_grouping = True

        playback.get_track()

        assert playback._run_context.skip_grouping is False

    def test_valid_track_returns_true(self, playback, mock_track):
        mock_config = MagicMock()
        mock_config.next_track.return_value = TrackResult(track=mock_track)
        mock_config.enable_long_track_splitting = False
        playback._playback_config = mock_config
        playback.has_attempted_track_split = True

        assert playback.get_track() is True
        assert playback.track is mock_track


# ---------------------------------------------------------------------------
# split_track_if_needed
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSplitTrackIfNeeded:
    def test_no_split_when_disabled(self, playback, mock_track):
        playback._playback_config.enable_long_track_splitting = False
        track, did_split, split_failed = playback.split_track_if_needed(mock_track)
        assert track is mock_track
        assert did_split is False
        assert split_failed is False


# ---------------------------------------------------------------------------
# get_grouping_type
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetGroupingType:
    def test_returns_sort_type_from_list(self, playback):
        from utils.globals import PlaylistSortType
        mock_config = MagicMock()
        mock_config.get_list.return_value.sort_type = PlaylistSortType.RANDOM
        playback._playback_config = mock_config
        assert playback.get_grouping_type() == PlaylistSortType.RANDOM

    def test_returns_empty_string_on_attribute_error(self, playback):
        mock_config = MagicMock()
        mock_config.get_list.side_effect = AttributeError
        playback._playback_config = mock_config
        assert playback.get_grouping_type() == ""


# ---------------------------------------------------------------------------
# increment_count
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestIncrementCount:
    def test_increments_count(self, playback):
        playback.increment_count()
        assert playback.count == 1

    def test_does_not_increment_on_skip(self, playback):
        playback._run_context.skip_track = True
        playback.increment_count()
        assert playback.count == 0

    def test_returns_false_when_total_unlimited(self, playback):
        # Default total is -1 (unlimited)
        assert playback.increment_count() is False

    def test_returns_true_when_count_exceeds_total(self, playback):
        playback._playback_config.total = 0
        assert playback.increment_count() is True


# ---------------------------------------------------------------------------
# delay
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDelay:
    def test_no_delay_before_first_track(self, playback):
        playback.has_played_first_track = False
        # Should return immediately; no time.sleep call needed
        playback.delay()

    def test_no_delay_after_failed_track(self, playback):
        playback.has_played_first_track = True
        playback.last_track_failed = True
        playback.delay()   # Must not block


# ---------------------------------------------------------------------------
# Seek, pause, resume, stop
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestVlcDelegates:
    def test_seek_to_time_calls_set_time(self, playback):
        playback.seek_to_time(5000)
        playback.vlc_media_player.set_time.assert_called_once_with(5000)

    def test_pause_delegates_to_vlc(self, playback):
        playback.pause()
        playback.vlc_media_player.pause.assert_called_once()

    def test_resume_delegates_to_vlc(self, playback):
        playback.resume()
        playback.vlc_media_player.play.assert_called_once()

    def test_stop_delegates_to_vlc(self, playback):
        playback.stop()
        playback.vlc_media_player.stop.assert_called_once()


# ---------------------------------------------------------------------------
# Track accessors
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestTrackAccessors:
    def test_get_track_text_file_none_when_no_track(self, playback):
        assert playback.get_track_text_file() is None

    def test_get_track_text_file_returns_path(self, playback, mock_track):
        playback.track = mock_track
        assert playback.get_track_text_file() == "/music/test.txt"

    def test_get_current_track_artwork_raises_when_no_track(self, playback):
        with pytest.raises(Exception, match="Track is invalid"):
            playback.get_current_track_artwork()

    def test_get_current_track_artwork_raises_when_invalid(self, playback, mock_track):
        mock_track.is_invalid.return_value = True
        playback.track = mock_track
        with pytest.raises(Exception, match="Track is invalid"):
            playback.get_current_track_artwork()

    def test_get_current_track_artwork_returns_art(self, playback, mock_track):
        mock_track.get_album_artwork.return_value = "/art/cover.jpg"
        playback.track = mock_track
        assert playback.get_current_track_artwork() == "/art/cover.jpg"


# ---------------------------------------------------------------------------
# update_ui
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestUpdateUi:
    def test_noop_when_no_callbacks(self, playback, mock_track):
        playback.track = mock_track
        playback.ui_callbacks = None
        playback.update_ui()   # must not raise
