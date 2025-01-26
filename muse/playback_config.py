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
    def new_playback_config(override_dir=None, data_callbacks=None):
        return PlaybackConfig(override_dir=override_dir, data_callbacks=data_callbacks)

    def __init__(self, args=None, override_dir=None, data_callbacks=None):
        self.total = int(args.total) if args else -1
        self.type = PlaylistSortType[args.workflow_tag] if args else PlaylistSortType.RANDOM
        self.directories = args.directories if args else ([override_dir] if override_dir else [])
        self.overwrite = args.overwrite if args else False
        self.enable_dynamic_volume = args.enable_dynamic_volume if args else True
        self.enable_long_track_splitting  = args.enable_long_track_splitting if args else False
        self.long_track_splitting_time_cutoff_minutes = args.long_track_splitting_time_cutoff_minutes if args else 20
        self.data_callbacks = data_callbacks
        self.list = Playlist(data_callbacks=self.data_callbacks)
        self.next_track_override = None
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
        l = self.data_callbacks.get_all_filepaths(self.directories)
        self.list = Playlist(l, self.type, data_callbacks=self.data_callbacks)
        return self.list

    def next_track(self):
        if self.next_track_override is not None:
            next_track = MediaTrack(self.next_track_override)
            next_track.set_is_extended()
            self.next_track_override = None
            PlaybackConfig.READY_FOR_EXTENSION = True
            return next_track
        l = self.get_list()
        return l.next_track()

    def upcoming_track(self):
        if self.next_track_override is not None:
            upcoming_track = MediaTrack(self.next_track_override)
            upcoming_track.set_is_extended()
            return upcoming_track
        l = self.get_list()
        return l.upcoming_track()

    def set_next_track_override(self, new_file):
        self.next_track_override = new_file

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
