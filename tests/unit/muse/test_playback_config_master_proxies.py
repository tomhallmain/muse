"""Tests for PlaybackConfigMaster's property proxies onto its active PlaybackConfig.

Playback reaches these through the master wrapper for any multi-config run
(the ordinary "press play" path, not just extension interleaving), so a
proxy missing here breaks basic playback rather than a narrow feature.
"""
import pytest

from muse.playback_config import PlaybackConfig
from muse.playback_config_master import PlaybackConfigMaster


@pytest.mark.unit
class TestDataCallbacksProxy:
    def test_proxies_to_the_active_config(self, mock_data_callbacks):
        """Regression: Playback._ensure_album_artwork reads data_callbacks
        straight off whatever _playback_config is, which is a
        PlaybackConfigMaster on the ordinary "press play" path."""
        pc = PlaybackConfig(data_callbacks=mock_data_callbacks, explicit_tracks=[])
        master = PlaybackConfigMaster(playback_configs=[pc])

        assert master.data_callbacks is mock_data_callbacks

    def test_none_with_no_active_config(self):
        master = PlaybackConfigMaster()

        assert master.data_callbacks is None
