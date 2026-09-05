"""
UI tests for MediaFrame.set_playback_paused().

The frame stands in a spinning-record video for artwork the library has none
for. That video runs on the frame's own VLC player, separate from the one
Playback drives, so pausing playback leaves it turning unless the frame is told
to hold it.
"""
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def frame(qapp, monkeypatch):
    import ui_qt.media_frame as media_frame_mod

    # A real player is never needed here, and the frame builds none when VLC is
    # absent, so force the branch and stand in for the player either way.
    monkeypatch.setattr(media_frame_mod, "_VLC_AVAILABLE", True)
    media_frame = media_frame_mod.MediaFrame()
    media_frame.vlc_media_player = MagicMock()
    media_frame._controls_overlay = MagicMock()
    yield media_frame
    media_frame._mouse_poll_timer.stop()
    media_frame.deleteLater()


def _showing_video(frame):
    import ui_qt.media_frame as media_frame_mod
    frame._video_ui = media_frame_mod.VideoUI("record.mp4")
    return frame.vlc_media_player.set_pause


@pytest.mark.ui
class TestSetPlaybackPaused:
    def test_pausing_holds_the_record(self, frame):
        set_pause = _showing_video(frame)

        frame.set_playback_paused(True)

        set_pause.assert_called_once_with(1)

    def test_resuming_lets_it_turn_again(self, frame):
        set_pause = _showing_video(frame)

        frame.set_playback_paused(False)

        set_pause.assert_called_once_with(0)

    def test_repeated_pauses_do_not_toggle_it_back(self, frame):
        """The state arrives resolved, and set_pause takes it as such."""
        set_pause = _showing_video(frame)

        frame.set_playback_paused(True)
        frame.set_playback_paused(True)

        assert [call.args[0] for call in set_pause.call_args_list] == [1, 1]

    def test_still_artwork_is_left_alone(self, frame):
        """Nothing is showing but an image, so there is no player state to hold."""
        frame._video_ui = None

        frame.set_playback_paused(True)

        frame.vlc_media_player.set_pause.assert_not_called()

    def test_the_controls_overlay_still_follows(self, frame):
        _showing_video(frame)

        frame.set_playback_paused(True)

        frame._controls_overlay.set_paused.assert_called_once_with(True)
