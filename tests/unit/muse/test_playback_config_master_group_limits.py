"""Tests for PlaybackConfigMaster's per-group track-count and time limits."""
import pytest

from muse.playback_config_master import PlaybackConfigMaster
from muse.playlist import GROUP_MAX_MINUTES_KEY, GROUP_MAX_TRACKS_KEY
from utils.app_info_cache import app_info_cache
from utils.globals import TrackResult


@pytest.mark.unit
class TestGroupTrackLimit:
    def test_unlimited_by_default(self):
        master = PlaybackConfigMaster()
        result = TrackResult(current_grouping="Bach", group_position=50)
        assert not master.has_exceeded_group_limits(result)

    def test_limit_not_reached_below_max(self):
        app_info_cache.set(GROUP_MAX_TRACKS_KEY, 3)
        master = PlaybackConfigMaster()
        result = TrackResult(current_grouping="Bach", group_position=2)
        assert not master.has_exceeded_group_limits(result)

    def test_limit_reached_at_max(self):
        app_info_cache.set(GROUP_MAX_TRACKS_KEY, 3)
        master = PlaybackConfigMaster()
        result = TrackResult(current_grouping="Bach", group_position=3)
        assert master.has_exceeded_group_limits(result)

    def test_no_grouping_active_bypasses_limit(self):
        """current_grouping unset means no grouping sort is active; limits don't apply."""
        app_info_cache.set(GROUP_MAX_TRACKS_KEY, 1)
        master = PlaybackConfigMaster()
        result = TrackResult(current_grouping=None, group_position=5)
        assert not master.has_exceeded_group_limits(result)


@pytest.mark.unit
class TestGroupTimeLimit:
    def test_unlimited_by_default(self):
        master = PlaybackConfigMaster()
        master.update_group_time("Bach", 10_000)
        result = TrackResult(current_grouping="Bach")
        assert not master.has_exceeded_group_limits(result)

    def test_limit_not_reached_below_max(self):
        app_info_cache.set(GROUP_MAX_MINUTES_KEY, 5)
        master = PlaybackConfigMaster()
        master.update_group_time("Bach", 200)
        result = TrackResult(current_grouping="Bach")
        assert not master.has_exceeded_group_limits(result)

    def test_limit_reached_at_max(self):
        app_info_cache.set(GROUP_MAX_MINUTES_KEY, 5)
        master = PlaybackConfigMaster()
        master.update_group_time("Bach", 200)
        master.update_group_time("Bach", 150)  # cumulative 350s >= 300s (5 min)
        result = TrackResult(current_grouping="Bach")
        assert master.has_exceeded_group_limits(result)

    def test_time_resets_on_group_change(self):
        app_info_cache.set(GROUP_MAX_MINUTES_KEY, 5)
        master = PlaybackConfigMaster()
        master.update_group_time("Bach", 250)
        master.update_group_time("Vivaldi", 50)
        assert master._current_group == "Vivaldi"
        assert master._current_group_time == 50
        result = TrackResult(current_grouping="Vivaldi")
        assert not master.has_exceeded_group_limits(result)
