"""
Integration tests for MuseSpotProfile.get_spot_index() and say_good_day timing.

Uses the module-level muse_memory singleton (already re-pointed to a fresh isolated
instance by the autouse isolated_singletons fixture) to drive real
MuseMemory.get_spot_profile() calls — the same path used at runtime.

time.sleep(0.02) between profile creations is required to guarantee strictly
increasing creation_time values on Windows, whose clock only advances every ~15 ms.
"""
import time
import pytest
from unittest.mock import patch

from utils.globals import TrackResult


@pytest.fixture(autouse=True)
def clear_spot_session():
    """Reset class-level track/spoken history between tests."""
    from muse.muse_spot_profile import MuseSpotProfile
    MuseSpotProfile.clear_session()
    yield
    MuseSpotProfile.clear_session()


@pytest.mark.integration
class TestSpotIndexAndSayGoodDay:
    def test_spot_index_increments_and_say_good_day_fires_at_index_two(self, mock_tracks):
        import muse.muse_memory as mm
        memory = mm.muse_memory  # isolated fresh instance from isolated_singletons

        t0, t1, t2, t3 = mock_tracks[:4]

        with patch("muse.muse_spot_profile.random.random", return_value=0.0):
            sp0 = memory.get_spot_profile(previous_track=None, track_result=TrackResult(t0))
            assert sp0.get_spot_index() == 0
            assert not sp0.say_good_day

            time.sleep(0.02)
            sp1 = memory.get_spot_profile(previous_track=t0, track_result=TrackResult(t1))
            assert sp1.get_spot_index() == 1
            assert not sp1.say_good_day

            time.sleep(0.02)
            sp2 = memory.get_spot_profile(previous_track=t1, track_result=TrackResult(t2))
            assert sp2.get_spot_index() == 2
            assert sp2.say_good_day  # fires exactly here

            time.sleep(0.02)
            sp3 = memory.get_spot_profile(previous_track=t2, track_result=TrackResult(t3))
            assert sp3.get_spot_index() == 3
            assert not sp3.say_good_day

    def test_say_good_day_false_when_random_above_threshold(self, mock_tracks):
        """50 % chance: random >= 0.5 suppresses say_good_day even at index 2."""
        import muse.muse_memory as mm
        memory = mm.muse_memory

        t0, t1, t2 = mock_tracks[:3]

        with patch("muse.muse_spot_profile.random.random", return_value=0.5):
            memory.get_spot_profile(previous_track=None, track_result=TrackResult(t0))
            time.sleep(0.02)
            memory.get_spot_profile(previous_track=t0, track_result=TrackResult(t1))
            time.sleep(0.02)
            sp2 = memory.get_spot_profile(previous_track=t1, track_result=TrackResult(t2))

        assert sp2.get_spot_index() == 2
        assert not sp2.say_good_day  # 0.5 is not < 0.5
