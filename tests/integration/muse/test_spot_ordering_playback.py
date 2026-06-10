"""
Integration test for spot-profile ordering through the real Playback prepare_muse()
sequence.

Rather than exercising the full VLC playback loop (which needs audio hardware),
this test drives the exact sequence that Playback.run() uses per track:

    get_track()                      → sets self.previous_track / self.track
    prepare_muse(delayed_prep=True)  → creates MuseSpotProfile via MuseMemory
    <track "plays" — simulated>
    has_played_first_track = True
    reset_muse()                     → consumed by Muse, removed from list

Real objects used end-to-end:
  • Playback   with mocked VLC media player (no audio device needed)
  • PlaybackConfig / Playlist  fed by the conftest mock_tracks
  • Muse       with prepare() and check_schedules() stubbed to skip LLM/TTS
  • MuseMemory (isolated singleton from isolated_singletons fixture)
  • MuseSpotProfile  — unmodified, exercises the real get_spot_index() path

time.sleep(0.02) between iterations ensures strictly increasing creation_time
even on Windows where the system clock only advances every ~15 ms.
"""
import time
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def clear_spot_session():
    from muse.muse_spot_profile import MuseSpotProfile
    MuseSpotProfile.clear_session()
    yield
    MuseSpotProfile.clear_session()


@pytest.fixture
def mock_vlc(monkeypatch):
    import muse.playback as playback_mod
    inst = MagicMock()
    inst.media_player_new.return_value = MagicMock()
    monkeypatch.setattr(playback_mod, "INSTANCE", inst)
    return inst


@pytest.mark.integration
class TestSpotOrderingThroughPlayback:
    def test_spot_index_and_say_good_day(self, mock_vlc, mock_tracks, mock_args, mock_data_callbacks):
        """
        Drive four prepare_muse(delayed_prep=True) cycles — identical to what
        Playback.run() does before each track — and verify that:
          - get_spot_index() returns 0, 1, 2, 3 for the four spots
          - say_good_day is False on spots 0, 1, and 3
          - say_good_day is True on spot 2 (the third spot in the session)
        """
        from muse.muse import Muse
        from muse.muse_spot_profile import MuseSpotProfile
        from muse.playback import Playback
        from muse.playback_config import PlaybackConfig
        from muse.run_context import RunContext

        # Build a real Muse; stub the parts that would hit LLM / TTS / schedules.
        mock_args.muse = True
        run_context = RunContext()
        muse = Muse(
            args=mock_args,
            library_data=mock_data_callbacks,
            run_context=run_context,
            ui_callbacks=None,
        )
        muse.prepare = MagicMock(side_effect=lambda sp: setattr(sp, "is_prepared", True))
        muse.check_schedules = MagicMock()
        muse.voice.finish_speaking = MagicMock()
        muse.memory.get_persona_manager().allow_mock_personas = True

        # PlaybackConfig expects filepath strings; Playlist resolves them to
        # MockMediaTrack objects via mock_data_callbacks.get_track().
        track_paths = [t.filepath for t in mock_tracks]
        pc = PlaybackConfig(data_callbacks=mock_data_callbacks, explicit_tracks=track_paths)
        mock_run = MagicMock()
        mock_run.args.muse = True
        mock_run.muse = muse
        mock_run.get_run_context.return_value = run_context
        playback = Playback(playback_config=pc, ui_callbacks=None, run=mock_run)

        collected = []

        with patch("muse.muse_spot_profile.random.random", return_value=0.0):
            for _ in range(4):
                time.sleep(0.02)          # guarantee distinct creation_time on Windows
                playback.get_track()
                playback.prepare_muse(delayed_prep=True)

                spot = playback.muse_spot_profiles[-1]
                collected.append(spot)

                # Simulate end-of-track cleanup (mirrors reset_muse + has_played_first_track)
                playback.muse_spot_profiles.clear()
                muse.has_started_prep = False
                playback.has_played_first_track = True

        assert len(collected) == 4

        assert collected[0].get_spot_index() == 0, "First spot should be index 0"
        assert not collected[0].say_good_day

        assert collected[1].get_spot_index() == 1, "Second spot should be index 1"
        assert not collected[1].say_good_day

        assert collected[2].get_spot_index() == 2, "Third spot should be index 2"
        assert collected[2].say_good_day, "say_good_day should fire on the third spot"

        assert collected[3].get_spot_index() == 3, "Fourth spot should be index 3"
        assert not collected[3].say_good_day
