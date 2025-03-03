import pytest
from pathlib import Path
from dataclasses import dataclass
from muse import Muse, MuseSpotProfile, Playback, PlaybackConfig, Playlist
from utils.globals import PlaylistSortType
from library_data.media_track import MediaTrack

@dataclass
class MockArgs:
    """Mock command line arguments for testing."""
    enable_preparation: bool = True
    enable_dynamic_volume: bool = True
    enable_long_track_splitting: bool = False
    long_track_splitting_time_cutoff_minutes: int = 20
    total: int = -1
    playlist_sort_type: str = PlaylistSortType.RANDOM
    directories: list = None
    overwrite: bool = False
    track: str = None
    placeholder: bool = False

@pytest.mark.unit
class TestMuse:
    def test_muse_creation(self, mock_data_callbacks):
        """Test basic Muse instance creation."""
        args = MockArgs()
        muse = Muse(args=args, library_data=mock_data_callbacks)
        assert isinstance(muse, Muse)
        assert muse.args == args
        assert muse.library_data == mock_data_callbacks

@pytest.mark.unit
class TestMuseSpot:
    def test_muse_spot_creation(self, test_data_dir):
        """Test basic MuseSpot instance creation."""
        # Create MediaTrack objects from sample files
        track1 = MediaTrack(str(test_data_dir / "sample_500KB.mp3"))
        track2 = MediaTrack(str(test_data_dir / "sample_1MB.mp3"))
        
        # Test with only current track
        profile_single = MuseSpotProfile(
            previous_track=None,
            track=track1,
            last_track_failed=False,
            skip_track=False,
            old_grouping=None,
            new_grouping=None,
            grouping_type=None
        )
        assert profile_single.track == track1
        assert profile_single.previous_track is None
        assert not profile_single.last_track_failed
        assert not profile_single.has_already_spoken

        def get_previous_spot_profile_callback(idx=0):
            return profile_single
        
        # Test with both previous and current track
        profile_both = MuseSpotProfile(
            previous_track=track1,
            track=track2,
            last_track_failed=False,
            skip_track=False,
            old_grouping=None,
            new_grouping=None,
            grouping_type=None,
            get_previous_spot_profile_callback=get_previous_spot_profile_callback
        )
        assert profile_both.track == track2
        assert profile_both.previous_track == track1
        assert not profile_both.last_track_failed
        assert not profile_both.has_already_spoken

@pytest.mark.unit
class TestPlayback:
    def test_playback_config(self, mock_data_callbacks):
        """Test PlaybackConfig initialization and properties."""
        config = PlaybackConfig(data_callbacks=mock_data_callbacks)
        assert hasattr(config, 'enable_dynamic_volume')
        assert isinstance(config.enable_dynamic_volume, bool)

@pytest.mark.unit
class TestPlaybackConfig:
    def test_playback_config_initialization(self, mock_data_callbacks):
        """Test PlaybackConfig initialization with basic settings."""
        config = PlaybackConfig(data_callbacks=mock_data_callbacks)
        assert config.enable_dynamic_volume is True
        assert config.enable_long_track_splitting is False
        assert config.long_track_splitting_time_cutoff_minutes == 20
        assert isinstance(config.list, Playlist)

    def test_playback_config_static_methods(self):
        """Test PlaybackConfig static methods."""
        assert PlaybackConfig.get_playing_config() is None
        assert PlaybackConfig.get_playing_track() is None

@pytest.mark.unit
class TestPlaylist:
    def test_playlist_initialization(self, mock_data_callbacks):
        """Test Playlist initialization."""
        playlist = Playlist(data_callbacks=mock_data_callbacks)
        assert playlist.size() == 0
        assert playlist.remaining_count() == 0
        assert playlist.current_track() is None

    def test_playlist_sort_type(self, mock_data_callbacks):
        """Test Playlist with different sort types."""
        playlist = Playlist(_type=PlaylistSortType.SEQUENCE, data_callbacks=mock_data_callbacks)
        assert playlist.sort_type == PlaylistSortType.SEQUENCE

        playlist = Playlist(_type=PlaylistSortType.RANDOM, data_callbacks=mock_data_callbacks)
        assert playlist.sort_type == PlaylistSortType.RANDOM 