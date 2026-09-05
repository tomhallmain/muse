"""
Integration tests for MuseMemory.get_spot_profile() registration gating.

Playback builds a spot profile on every track transition, including the branch
that runs when the DJ is inactive (Playback.generate_silent_spot_profile). Those
silent profiles must not enter the memory lists: all_spot_profiles is persisted
and bounded, so registering them evicts genuine spoken history into snapshots.

Uses the module-level muse_memory singleton (already re-pointed to a fresh
isolated instance by the autouse isolated_singletons fixture) to drive real
MuseMemory.get_spot_profile() calls -- the same path used at runtime.
"""
import time
import pytest

from utils.globals import TrackResult


@pytest.fixture(autouse=True)
def clear_spot_session():
    """Reset class-level track/spoken history between tests."""
    from muse.muse_spot_profile import MuseSpotProfile
    MuseSpotProfile.clear_session()
    yield
    MuseSpotProfile.clear_session()


@pytest.fixture
def memory():
    import muse.muse_memory as mm
    return mm.muse_memory


@pytest.mark.integration
class TestSpotProfileRegistration:
    def test_an_active_muse_registers_the_profile(self, memory, mock_tracks):
        memory.get_spot_profile(previous_track=None, track_result=TrackResult(mock_tracks[0]),
                                can_speak=True)

        assert len(memory.all_spot_profiles) == 1
        assert len(memory.current_session_spot_profiles) == 1

    def test_an_inactive_muse_registers_nothing(self, memory, mock_tracks):
        memory.get_spot_profile(previous_track=None, track_result=TrackResult(mock_tracks[0]),
                                can_speak=False)

        assert memory.all_spot_profiles == []
        assert memory.current_session_spot_profiles == []

    def test_the_profile_is_still_returned_when_inactive(self, memory, mock_tracks):
        """Playback appends it to its own list and reads it back, so it is built
        either way -- only the memory registration is skipped."""
        t0, t1 = mock_tracks[:2]

        spot_profile = memory.get_spot_profile(previous_track=t0, track_result=TrackResult(t1),
                                               can_speak=False)

        assert spot_profile is not None
        assert spot_profile.track is t1
        assert spot_profile.previous_track is t0
        assert spot_profile.talk_about_something is False

    def test_existing_history_is_left_untouched_by_silent_spots(self, memory, mock_tracks):
        t0, t1, t2 = mock_tracks[:3]
        memory.get_spot_profile(previous_track=None, track_result=TrackResult(t0), can_speak=True)
        time.sleep(0.02)
        spoken = list(memory.all_spot_profiles)

        for _ in range(5):
            memory.get_spot_profile(previous_track=t1, track_result=TrackResult(t2), can_speak=False)

        assert memory.all_spot_profiles == spoken

    def test_silent_spots_do_not_advance_the_spot_index(self, memory, mock_tracks):
        """get_spot_index() counts the session profiles created before this one,
        so a silent stretch would otherwise push every later spot's index -- and
        the walk behind it -- upward."""
        t0, t1, t2 = mock_tracks[:3]

        memory.get_spot_profile(previous_track=None, track_result=TrackResult(t0), can_speak=True)
        time.sleep(0.02)
        for _ in range(3):
            memory.get_spot_profile(previous_track=t0, track_result=TrackResult(t1), can_speak=False)
            time.sleep(0.02)
        second_spoken = memory.get_spot_profile(previous_track=t1, track_result=TrackResult(t2),
                                                can_speak=True)

        assert second_spoken.get_spot_index() == 1

    def test_no_snapshot_is_created_by_a_silent_spot(self, memory, mock_tracks):
        """The eviction path is what the persisted memory loses history to."""
        memory.max_memory_size = 1
        memory.get_spot_profile(previous_track=None, track_result=TrackResult(mock_tracks[0]),
                                can_speak=True)
        time.sleep(0.02)
        snapshots_before = dict(memory._historical_snapshots)

        for _ in range(3):
            memory.get_spot_profile(previous_track=mock_tracks[0],
                                    track_result=TrackResult(mock_tracks[1]), can_speak=False)

        assert memory._historical_snapshots == snapshots_before
        assert len(memory.all_spot_profiles) == 1
