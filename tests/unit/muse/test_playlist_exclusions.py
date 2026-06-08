"""
Tests for the playlist track exclusion feature.

Covers:
- Playlist.__init__ filtering via app_info_cache exclusion list (default ["TTS"])
- Playback.get_track() toast notification when tracks were excluded
"""
import pytest
from unittest.mock import MagicMock

from utils.globals import TrackResult


# ---------------------------------------------------------------------------
# Playlist-level filtering
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPlaylistTrackExclusions:
    def test_tts_tracks_excluded_by_default(self, mock_data_callbacks):
        from muse.playlist import Playlist
        tracks = ["/music/track.flac", "/tts_output/TTS_hello.mp3"]
        playlist = Playlist(tracks, data_callbacks=mock_data_callbacks)
        assert "/tts_output/TTS_hello.mp3" not in playlist.in_sequence
        assert "/music/track.flac" in playlist.in_sequence

    def test_excluded_count_matches_filtered_tracks(self, mock_data_callbacks):
        from muse.playlist import Playlist
        tracks = ["/music/a.flac", "/tts/TTS_1.mp3", "/tts/TTS_2.mp3"]
        playlist = Playlist(tracks, data_callbacks=mock_data_callbacks)
        assert playlist.excluded_count == 2

    def test_excluded_count_zero_when_nothing_matches(self, mock_data_callbacks):
        from muse.playlist import Playlist
        tracks = ["/music/a.flac", "/music/b.flac"]
        playlist = Playlist(tracks, data_callbacks=mock_data_callbacks)
        assert playlist.excluded_count == 0

    def test_exclusion_is_case_sensitive(self, mock_data_callbacks):
        from muse.playlist import Playlist
        # "TTS" (uppercase) must not match "tts_voice" (lowercase)
        tracks = ["/output/tts_voice.mp3", "/output/TTS_UPPER.mp3", "/music/good.flac"]
        playlist = Playlist(tracks, data_callbacks=mock_data_callbacks)
        assert playlist.excluded_count == 1
        assert "/output/TTS_UPPER.mp3" not in playlist.in_sequence
        assert "/output/tts_voice.mp3" in playlist.in_sequence
        assert "/music/good.flac" in playlist.in_sequence

    def test_no_false_positives_for_tts_substring_in_words(self, mock_data_callbacks):
        from muse.playlist import Playlist
        # Real-world false positives from the logs: "tts" embedded inside artist/album words.
        # None of these should be excluded by the default "TTS" filter.
        tracks = [
            r"F:\iTunes Music\Tempesta di Mare & Clara Rottsolk\Scarlatti_ Cantatas\01 Tu sei.m4a",
            r"F:\iTunes Music\Tokyo String Quartet\Schubert\05 Quartettsatz.m4a",
            r"F:\iTunes Music\Ronn McFarlane\Highland King Vol. 2\28 The Newest Scotts Measure.m4a",
            r"F:\iTunes Music\His Majesties Sagbutts and Cornetts\Venice Preserved\01 Canzon.m4a",
            "/music/clean_track.flac",
        ]
        playlist = Playlist(tracks, data_callbacks=mock_data_callbacks)
        assert playlist.excluded_count == 0
        assert len(playlist.in_sequence) == 5

    def test_tts_label_in_filename_still_excluded(self, mock_data_callbacks):
        from muse.playlist import Playlist
        # Confirm that genuine TTS output files are still caught after the fix.
        tracks = [
            "/tts_output/TTS_hello.mp3",
            "/tts_output/TTS_goodbye.mp3",
            "/music/good.flac",
        ]
        playlist = Playlist(tracks, data_callbacks=mock_data_callbacks)
        assert playlist.excluded_count == 2
        assert "/music/good.flac" in playlist.in_sequence

    def test_pending_tracks_also_filtered(self, mock_data_callbacks):
        from muse.playlist import Playlist
        tracks = ["/tts/TTS_1.mp3", "/music/good.flac"]
        playlist = Playlist(tracks, data_callbacks=mock_data_callbacks)
        assert "/tts/TTS_1.mp3" not in playlist.pending_tracks

    def test_empty_exclusion_list_passes_all_tracks(self, mock_data_callbacks):
        from muse.playlist import Playlist, TRACK_EXCLUSIONS_KEY
        from utils.app_info_cache import app_info_cache
        app_info_cache.set(TRACK_EXCLUSIONS_KEY, [])
        tracks = ["/tts/TTS_hello.mp3", "/music/track.flac"]
        playlist = Playlist(tracks, data_callbacks=mock_data_callbacks)
        assert playlist.excluded_count == 0
        assert len(playlist.in_sequence) == 2

    def test_custom_exclusions_from_cache(self, mock_data_callbacks):
        from muse.playlist import Playlist, TRACK_EXCLUSIONS_KEY
        from utils.app_info_cache import app_info_cache
        app_info_cache.set(TRACK_EXCLUSIONS_KEY, ["JINGLE"])
        tracks = ["/ads/JINGLE_intro.mp3", "/tts/TTS_track.mp3", "/music/good.flac"]
        playlist = Playlist(tracks, data_callbacks=mock_data_callbacks)
        # Only "JINGLE" is in the custom list — TTS is not excluded
        assert playlist.excluded_count == 1
        assert "/ads/JINGLE_intro.mp3" not in playlist.in_sequence
        assert "/tts/TTS_track.mp3" in playlist.in_sequence

    def test_empty_playlist_has_zero_excluded_count(self, mock_data_callbacks):
        from muse.playlist import Playlist
        playlist = Playlist([], data_callbacks=mock_data_callbacks)
        assert playlist.excluded_count == 0


# ---------------------------------------------------------------------------
# Playback toast notification
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestExclusionToast:
    @pytest.fixture(autouse=True)
    def mock_vlc(self, monkeypatch):
        import muse.playback as playback_mod
        mock_inst = MagicMock()
        mock_inst.media_player_new.return_value = MagicMock()
        monkeypatch.setattr(playback_mod, "INSTANCE", mock_inst)

    def _make_playback_with_excluded_count(self, count, mock_data_callbacks, ui_callbacks=None):
        """Create a Playback whose mocked playlist reports `count` excluded tracks."""
        from muse.playback import Playback
        from muse.playback_config import PlaybackConfig
        pc = PlaybackConfig(data_callbacks=mock_data_callbacks, explicit_tracks=[])
        p = Playback(playback_config=pc, ui_callbacks=ui_callbacks, run=None)
        mock_config = MagicMock()
        mock_config.next_track.return_value = TrackResult()
        mock_config.enable_long_track_splitting = False
        mock_config.get_list.return_value.excluded_count = count
        p._playback_config = mock_config
        return p

    def test_toast_fires_when_tracks_excluded(self, mock_data_callbacks):
        ui = MagicMock()
        p = self._make_playback_with_excluded_count(3, mock_data_callbacks, ui_callbacks=ui)
        p.get_track()
        ui.toast.assert_called_once()
        assert "3" in ui.toast.call_args[0][0]

    def test_toast_message_includes_count(self, mock_data_callbacks):
        ui = MagicMock()
        p = self._make_playback_with_excluded_count(7, mock_data_callbacks, ui_callbacks=ui)
        p.get_track()
        assert "7" in ui.toast.call_args[0][0]

    def test_toast_fires_only_once_across_multiple_calls(self, mock_data_callbacks):
        ui = MagicMock()
        p = self._make_playback_with_excluded_count(2, mock_data_callbacks, ui_callbacks=ui)
        p.get_track()
        p.get_track()
        assert ui.toast.call_count == 1

    def test_no_toast_when_excluded_count_is_zero(self, mock_data_callbacks):
        ui = MagicMock()
        p = self._make_playback_with_excluded_count(0, mock_data_callbacks, ui_callbacks=ui)
        p.get_track()
        ui.toast.assert_not_called()

    def test_no_crash_when_no_ui_callbacks(self, mock_data_callbacks):
        p = self._make_playback_with_excluded_count(5, mock_data_callbacks, ui_callbacks=None)
        p.get_track()  # must not raise
