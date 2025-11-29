from copy import deepcopy
import datetime
import time

from library_data.media_track import MediaTrack
from muse.playlist import Playlist
from utils.config import config
from utils.globals import PlaylistSortType
from utils.logging_setup import get_logger

logger = get_logger(__name__)

class PlaybackConfig:
    LAST_EXTENSION_PLAYED = datetime.datetime.now()
    OPEN_CONFIGS = []
    READY_FOR_EXTENSION = True

    @staticmethod
    def get_playing_config():
        for config in PlaybackConfig.OPEN_CONFIGS:
            if config.playing:
                return config
        return None

    @staticmethod
    def get_playing_track():
        playing_config = PlaybackConfig.get_playing_config()
        if not playing_config:
            return None
        return playing_config.current_track()

    @staticmethod
    def new_playback_config(override_dir=None, data_callbacks=None):
        return PlaybackConfig(override_dir=override_dir, data_callbacks=data_callbacks)

    def __init__(self, args=None, override_dir=None, data_callbacks=None):
        self.total = int(args.total) if args else -1
        self.type = args.playlist_sort_type if args else PlaylistSortType.RANDOM
        self.directories = args.directories if args else ([override_dir] if override_dir else [])
        self.overwrite = args.overwrite if args else False
        self.enable_dynamic_volume = args.enable_dynamic_volume if args else True
        self.enable_long_track_splitting  = args.enable_long_track_splitting if args else False
        self.long_track_splitting_time_cutoff_minutes = args.long_track_splitting_time_cutoff_minutes if args else 20
        self.long_track_splitting_play_all = False
        self.data_callbacks = data_callbacks
        self.check_entire_playlist = args.check_entire_playlist if args else False
        self.list = Playlist(data_callbacks=self.data_callbacks, check_entire_playlist=self.check_entire_playlist)
        self.start_track = args.track if args else None
        self.next_track_override = None
        self.playing = False
        PlaybackConfig.OPEN_CONFIGS.append(self)

    def maximum_plays(self):
        return 1

    def length(self):
        return self.get_list().size()
    
    def reamining_count(self):
        return self.get_list().remaining_count()

    def get_list(self):
        if self.list.is_valid():
            return self.list
        l = self.data_callbacks.get_all_filepaths(self.directories, self.overwrite)
        self.list = Playlist(l, self.type, data_callbacks=self.data_callbacks, start_track=self.start_track,
                             check_entire_playlist=self.check_entire_playlist)
        return self.list

    def set_playing(self, playing=True):
        self.playing = playing

    def next_track(self, skip_grouping=False, places_from_current=0):
        self.set_playing()
        if self.next_track_override is not None:
            next_track = MediaTrack(self.next_track_override)
            next_track.set_is_extended()
            self.next_track_override = None
            PlaybackConfig.READY_FOR_EXTENSION = True
            return next_track, None, None
        l = self.get_list()
        next_track, old_grouping, new_grouping = l.next_track(skip_grouping=skip_grouping, places_from_current=places_from_current)
        return next_track, old_grouping, new_grouping

    def upcoming_track(self, places_from_current=1):
        if self.next_track_override is not None:
            upcoming_track = MediaTrack(self.next_track_override)
            upcoming_track.set_is_extended()
            return upcoming_track, None, None
        l = self.get_list()
        upcoming_track, old_grouping, new_grouping = l.upcoming_track(places_from_current=places_from_current)
        return upcoming_track, old_grouping, new_grouping

    def current_track(self):
        return self.get_list().current_track()

    def upcoming_grouping(self):
        """Get the next grouping that will be encountered in the playlist.
        
        Returns:
            str or None: The name of the next grouping, or None if no grouping change found
        """
        l = self.get_list()
        return l.get_next_grouping()

    def set_next_track_override(self, new_file):
        self.next_track_override = new_file

    def split_track(self, track, do_split_override=True, offset=1):
        self.get_list().print_upcoming("split_track before")
        tracks = track.extract_non_silent_track_parts(select_random_track_part=not self.long_track_splitting_play_all)
        if len(tracks) == 0:
            # Track split failed for some reason, skip to the next track
            raise Exception("Track split failed")
        if do_split_override:
            self.get_list().insert_upcoming_tracks(tracks, offset=offset)
            logger.info(f"Assigned split track overrides: {tracks}")
        self.get_list().print_upcoming("split_track after")
        return tracks[0]

    @staticmethod
    def assign_extension(new_file):
        while not PlaybackConfig.READY_FOR_EXTENSION:
            logger.info("Waiting for config to accept extension...")
            time.sleep(5)
        logger.info("Assigning extension to playback")
        PlaybackConfig.READY_FOR_EXTENSION = False
        for open_config in PlaybackConfig.OPEN_CONFIGS:
            open_config.overwrite = True
            open_config.get_list()
            open_config.set_next_track_override(new_file)

    def __str__(self) -> str:
        return "PlaybackConfig(type=" + str(self.type) + ", directories=" + str(len(self.directories)) + ")"

    def __eq__(self, other) -> bool:
        if not isinstance(other, PlaybackConfig):
            return False

        return self.type == other.type and self.directories == other.directories \
            and self.overwrite == other.overwrite and self.enable_dynamic_volume == other.enable_dynamic_volume \
            and self.enable_long_track_splitting == other.enable_long_track_splitting \
            and self.long_track_splitting_time_cutoff_minutes == other.long_track_splitting_time_cutoff_minutes \
            and self.long_track_splitting_play_all == other.long_track_splitting_play_all \
            and self.start_track == other.start_track \
            and self.check_entire_playlist == other.check_entire_playlist

    def __hash__(self) -> int:
        return hash((self.type, tuple(self.directories), self.overwrite, self.enable_dynamic_volume,
                     self.enable_long_track_splitting, self.long_track_splitting_time_cutoff_minutes,
                     self.long_track_splitting_play_all, self.start_track, self.check_entire_playlist))

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        for k, v in self.__dict__.items():
            if not k == "data_callbacks" and not k == "list":
                setattr(result, k, deepcopy(v, memo))
        return result

