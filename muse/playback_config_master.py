from copy import deepcopy
import datetime
import time
from utils.app_info_cache import app_info_cache
from utils.globals import PlaylistSortType
from utils.logging_setup import get_logger

logger = get_logger(__name__)

class PlaybackConfigMaster:
    playlist_history_max_size = 1000
    playlist_history = []
    LAST_EXTENSION_PLAYED = datetime.datetime.now()
    READY_FOR_EXTENSION = True
    
    @staticmethod
    def load_playlist_history():
        PlaybackConfigMaster.playlist_history = app_info_cache.get("playlist_history", default_val=[])

    @staticmethod
    def save_playlist_history():
        app_info_cache.set("playlist_history", PlaybackConfigMaster.playlist_history)

    @staticmethod
    def assign_extension(new_file):
        while not PlaybackConfigMaster.READY_FOR_EXTENSION:
            logger.info("Waiting for config to accept extension...")
            time.sleep(5)
        logger.info("Assigning extension to playback")
        PlaybackConfigMaster.READY_FOR_EXTENSION = False
        for open_config in PlaybackConfigMaster.OPEN_CONFIGS:
            open_config.overwrite = True
            open_config.get_list()
            open_config.set_next_track_override(new_file)

    def __init__(self, playback_configs=None, songs_per_config=None):
        """Initialize PlaybackConfigMaster with ordered configurations.
        
        Args:
            playback_configs (list): List of PlaybackConfig objects
            songs_per_config (list): List of integers specifying how many songs to play from each config
                                    (default: 1 song per config)
        """
        self.playback_configs = playback_configs or []
        self.songs_per_config = songs_per_config or [1] * len(self.playback_configs)
        if len(self.songs_per_config) != len(self.playback_configs):
            self.songs_per_config = [1] * len(self.playback_configs)
        
        # Precompute the sequence of configurations and their playlist positions
        self._precompute_sequence()
        
        self.current_playback_config = None
        self.current_playback_config_index = -1
        self.current_sequence_index = -1
        self.played_tracks = []
        self.next_track_override = None
        self.playing = False
        PlaybackConfigMaster.OPEN_CONFIGS.append(self)

    def _precompute_sequence(self):
        """Precompute the sequence of configurations and their playlist positions."""
        self.sequence = []
        max_sequence_length = 100000  # Arbitrary large number
        
        # For each configuration, add its songs to the sequence
        for config_index, config in enumerate(self.playback_configs):
            for _ in range(self.songs_per_config[config_index]):
                self.sequence.append((config_index, len(self.sequence)))
                
                # Stop if we've reached the maximum sequence length
                if len(self.sequence) >= max_sequence_length:
                    return

    def get_master_playlist(self, previous_tracks=100, upcoming_tracks=100):
        """Get a window of tracks around the current position in the sequence.
        
        Args:
            previous_tracks (int): Number of previous tracks to include (default: 100)
            upcoming_tracks (int): Number of upcoming tracks to include (default: 100)
            
        Returns:
            tuple: (previous_tracks_list, upcoming_tracks_list)
        """
        if not self.sequence:
            return [], []

        # Calculate the window boundaries
        sequence_length = len(self.sequence)
        current_pos = self.current_sequence_index if self.current_sequence_index >= 0 else 0
        
        # Get previous tracks
        prev_start = max(0, current_pos - previous_tracks)
        prev_tracks = []
        for i in range(prev_start, current_pos):
            config_index, _ = self.sequence[i]
            config = self.playback_configs[config_index]
            # Get the track that would be played at this position
            track = config.get_list().get_track_at_position(i - prev_start)
            if track:
                prev_tracks.append(track)

        # Get upcoming tracks
        next_end = min(sequence_length, current_pos + upcoming_tracks + 1)
        next_tracks = []
        for i in range(current_pos + 1, next_end):
            config_index, _ = self.sequence[i]
            config = self.playback_configs[config_index]
            # Get the track that would be played at this position
            track = config.get_list().get_track_at_position(i - current_pos - 1)
            if track:
                next_tracks.append(track)

        return prev_tracks, next_tracks

    def get_playing_config(self):
        """Get the currently playing configuration."""
        if self.playing:
            return self
        return None

    def get_playing_track(self):
        """Get the currently playing track."""
        if not self.playing:
            return None
        return self.current_track()

    def maximum_plays(self):
        """Get maximum number of plays."""
        return 1

    def length(self):
        """Get total length of all configurations."""
        return sum(config.length() for config in self.playback_configs)

    def remaining_count(self):
        """Get total remaining tracks across all configurations."""
        return sum(config.remaining_count() for config in self.playback_configs)

    def get_list(self):
        """Get the current playlist from the active configuration."""
        if self.current_playback_config:
            return self.current_playback_config.get_list()
        return None

    def set_playing(self, playing=True):
        """Set playing state."""
        self.playing = playing

    def next_track(self, skip_grouping=False, places_from_current=0):
        """Get next track from current configuration."""
        self.set_playing()
        if self.next_track_override is not None:
            next_track = self.next_track_override
            self.next_track_override = None
            PlaybackConfigMaster.READY_FOR_EXTENSION = True
            return next_track, None, None

        # Move to next position in sequence
        self.current_sequence_index = (self.current_sequence_index + 1) % len(self.sequence)
        config_index, _ = self.sequence[self.current_sequence_index]
        self.current_playback_config = self.playback_configs[config_index]
        self.current_playback_config_index = config_index

        # Get next track from current config
        next_track, old_grouping, new_grouping = self.current_playback_config.next_track(
            skip_grouping=skip_grouping, 
            places_from_current=places_from_current
        )

        # Handle random playback with history
        if self.current_playback_config.type == PlaylistSortType.RANDOM:
            max_attempts = 10  # Prevent infinite loops
            attempts = 0
            taper_history_to = min(
                self.current_playback_config.remaining_count(), 
                PlaybackConfigMaster.playlist_history_max_size
            )
            
            while (attempts < max_attempts and 
                   next_track.get_track_details() in PlaybackConfigMaster.playlist_history[:taper_history_to]):
                next_track, old_grouping, new_grouping = self.current_playback_config.next_track(
                    skip_grouping=skip_grouping,
                    places_from_current=places_from_current
                )
                taper_history_to = min(
                    self.current_playback_config.remaining_count(),
                    PlaybackConfigMaster.playlist_history_max_size
                )
                attempts += 1

        # Update history
        track_details = next_track.get_track_details()
        if track_details not in PlaybackConfigMaster.playlist_history:
            PlaybackConfigMaster.playlist_history.insert(0, track_details)
            if len(PlaybackConfigMaster.playlist_history) > PlaybackConfigMaster.playlist_history_max_size:
                PlaybackConfigMaster.playlist_history.pop()

        self.played_tracks.append(next_track)
        return next_track, old_grouping, new_grouping

    def upcoming_track(self, places_from_current=1):
        """Get upcoming track from next configuration."""
        if self.next_track_override is not None:
            return self.next_track_override, None, None

        # Get next position in sequence
        next_sequence_index = (self.current_sequence_index + 1) % len(self.sequence)
        config_index, _ = self.sequence[next_sequence_index]
        next_config = self.playback_configs[config_index]
        
        return next_config.upcoming_track(places_from_current=places_from_current)

    def current_track(self):
        """Get current track from current configuration."""
        if self.current_playback_config:
            return self.current_playback_config.current_track()
        return None

    def set_next_track_override(self, new_file):
        """Set next track override."""
        self.next_track_override = new_file

    def split_track(self, track, do_split_override=True, offset=1):
        """Split track using current configuration's method."""
        if self.current_playback_config:
            return self.current_playback_config.split_track(track, do_split_override, offset)
        raise Exception("No current configuration available")

    def __str__(self) -> str:
        """String representation of the master configuration."""
        config_strs = [str(config) for config in self.playback_configs]
        return f"PlaybackConfigMaster(configs=[{', '.join(config_strs)}], songs_per_config={self.songs_per_config})"

    def __eq__(self, other) -> bool:
        """Equality comparison."""
        if not isinstance(other, PlaybackConfigMaster):
            return False
        return (self.playback_configs == other.playback_configs and 
                self.songs_per_config == other.songs_per_config)

    def __hash__(self) -> int:
        """Hash implementation."""
        return hash((tuple(self.playback_configs), tuple(self.songs_per_config)))

    def __deepcopy__(self, memo):
        """Deep copy implementation."""
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        for k, v in self.__dict__.items():
            if not k == "playback_configs":  # Skip copying playback_configs as they should be shared
                setattr(result, k, deepcopy(v, memo))
        return result

