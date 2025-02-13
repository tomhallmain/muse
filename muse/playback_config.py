import datetime
import time

from library_data.media_track import MediaTrack
from muse.playlist import Playlist
from utils.config import config
from utils.globals import PlaylistSortType
from utils.utils import Utils


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
        self.list = Playlist(data_callbacks=self.data_callbacks)
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
        self.list = Playlist(l, self.type, data_callbacks=self.data_callbacks, start_track=self.start_track)
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
            Utils.log(f"Assigned split track overrides: {tracks}")
        self.get_list().print_upcoming("split_track after")
        return tracks[0]

    @staticmethod
    def assign_extension(new_file):
        while not PlaybackConfig.READY_FOR_EXTENSION:
            Utils.log("Waiting for config to accept extension...")
            time.sleep(5)
        Utils.log("Assigning extension to playback")
        PlaybackConfig.READY_FOR_EXTENSION = False
        for open_config in PlaybackConfig.OPEN_CONFIGS:
            open_config.overwrite = True
            open_config.get_list()
            open_config.set_next_track_override(new_file)

    def __str__(self) -> str:
        return "PlaybackConfig(type=" + str(self.type) + ", directories=" + str(len(self.directories)) + ")"
