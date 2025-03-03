import pytest
from pathlib import Path
from muse import PlaybackConfig, Playlist
from utils.globals import PlaylistSortType
from library_data.media_track import MediaTrack

@pytest.mark.integration
class TestPlaybackIntegration:
    @pytest.mark.slow
    def test_playlist_track_management(self, sample_audio_file, mock_data_callbacks):
        """Test playlist track management functionality."""
        playlist = Playlist(data_callbacks=mock_data_callbacks)
        
        # Create MediaTrack and verify file exists
        assert sample_audio_file.exists(), "Sample audio file not found in fixtures"
        track = MediaTrack(str(sample_audio_file))
        
        # Add track and verify
        playlist.insert_upcoming_tracks([track], overwrite_existing_at_index=False)
        
        # Check track is in playlist
        assert playlist.size() == 1
        assert playlist.remaining_count() == 1
        
        # Get next track and verify
        next_track, old_grouping, new_grouping = playlist.next_track()
        assert next_track is not None
        assert Path(next_track.filepath).exists()
        
    @pytest.mark.slow
    def test_playback_config_with_directory(self, sample_audio_file, mock_data_callbacks):
        """Test PlaybackConfig with directory override."""
        audio_dir = sample_audio_file.parent
        config = PlaybackConfig(
            override_dir=str(audio_dir),
            data_callbacks=mock_data_callbacks
        )
        
        # Verify config settings
        assert config.directories == [str(audio_dir)]
        assert isinstance(config.list, Playlist)
        assert not config.playing
        
        # Set playing and verify
        config.set_playing(True)
        assert config.playing
        assert PlaybackConfig.get_playing_config() == config
        PlaybackConfig.OPEN_CONFIGS.clear()