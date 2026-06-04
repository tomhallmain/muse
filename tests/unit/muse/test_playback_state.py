"""Unit tests for muse/playback_state.py."""

import pytest

from muse.playback_state import PlaybackStateManager
from muse.sort_config import SortConfig


@pytest.mark.unit
class TestPlaybackStateManager:
    def test_singleton_returns_same_instance(self):
        assert PlaybackStateManager() is PlaybackStateManager()

    def test_set_and_get_master_config(self):
        sentinel = object()
        PlaybackStateManager.set_master_config(sentinel)
        assert PlaybackStateManager.get_master_config() is sentinel

    def test_clear_master_config(self):
        PlaybackStateManager.set_master_config(object())
        PlaybackStateManager.clear_master_config()
        assert PlaybackStateManager.get_master_config() is None

    def test_set_and_get_override_sort_config(self):
        sc = SortConfig(skip_memory_shuffle=True)
        PlaybackStateManager.set_override_sort_config(sc)
        assert PlaybackStateManager.get_override_sort_config() == sc

    def test_load_override_sort_config_from_cache(self):
        from utils.app_info_cache import app_info_cache
        sc = SortConfig(skip_random_start=True)
        app_info_cache.set(PlaybackStateManager._SORT_CONFIG_CACHE_KEY, sc.to_dict())
        PlaybackStateManager._override_sort_config = None
        PlaybackStateManager.load_override_sort_config()
        assert PlaybackStateManager.get_override_sort_config() == sc

    def test_load_override_sort_config_ignores_all_defaults(self):
        from utils.app_info_cache import app_info_cache
        app_info_cache.set(PlaybackStateManager._SORT_CONFIG_CACHE_KEY, SortConfig().to_dict())
        PlaybackStateManager._override_sort_config = None
        PlaybackStateManager.load_override_sort_config()
        assert PlaybackStateManager.get_override_sort_config() is None

    def test_store_and_load_override_sort_config_round_trips(self):
        sc = SortConfig(check_count_override=4)
        PlaybackStateManager.set_override_sort_config(sc)
        PlaybackStateManager.store_override_sort_config()
        PlaybackStateManager._override_sort_config = None
        PlaybackStateManager.load_override_sort_config()
        assert PlaybackStateManager.get_override_sort_config() == sc
