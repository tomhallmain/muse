import datetime
import os
import glob
import time

from library_data.audio_track import AudioTrack
from muse.playlist import Playlist
from utils.app_info_cache import app_info_cache
from utils.config import config
from utils.globals import MediaFileType, WorkflowType
from utils.utils import Utils


class PlaybackConfig:
    DIRECTORIES_CACHE = {}
    LAST_EXTENSION_PLAYED = datetime.datetime.now()
    OPEN_CONFIGS = []
    READY_FOR_EXTENSION = True

    @staticmethod
    def new_playback_config(override_dir=None):
        return PlaybackConfig(override_dir=override_dir)

    @staticmethod
    def store_directory_cache():
        app_info_cache.set("directories_cache", PlaybackConfig.DIRECTORIES_CACHE)

    @staticmethod
    def load_directory_cache():
        PlaybackConfig.DIRECTORIES_CACHE = app_info_cache.get("directories_cache", default_val={})

    def __init__(self, args=None, override_dir=None):
        self.total = int(args.total) if args else -1
        self.type = WorkflowType[args.workflow_tag] if args else WorkflowType.RANDOM
        self.directories = args.directories if args else ([override_dir] if override_dir else [])
        self.overwrite = args.overwrite if args else False
        self.enable_dynamic_volume = args.enable_dynamic_volume if args else True
        self.enable_long_track_splitting  = args.enable_long_track_splitting if args else False
        self.long_track_splitting_time_cutoff_minutes = args.long_track_splitting_time_cutoff_minutes if args else 20
        self.list = Playlist()
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
        l = []
        count = 0
        for directory in self.directories:
            for f in self._get_directory_files(directory):
                if MediaFileType.is_media_filetype(f):
                    l += [os.path.join(directory, f)]
                    count += 1
                    if count > 100000:
                        break
                elif os.path.isfile(f) and config.debug:
                    Utils.log("Skipping non-media file: " + f)
        self.list = Playlist(l, self.type)
        return self.list

    def get_audio_track_list(self):
        Utils.log("Building audio track cache")
        return [AudioTrack(t) for t in self.get_list().in_sequence]

    def _get_directory_files(self, directory):
        if directory not in PlaybackConfig.DIRECTORIES_CACHE or self.overwrite:
            files = glob.glob(os.path.join(directory, "**/*"), recursive = True)
            PlaybackConfig.DIRECTORIES_CACHE[directory] = files
        else:
            files = PlaybackConfig.DIRECTORIES_CACHE[directory]
        return files

    def next_track(self):
        if self.next_track_override is not None:
            next_track = AudioTrack(self.next_track_override)
            next_track.set_is_extended()
            self.next_track_override = None
            PlaybackConfig.READY_FOR_EXTENSION = True
            return next_track
        l = self.get_list()
        return l.next_track()

    def upcoming_track(self):
        if self.next_track_override is not None:
            upcoming_track = AudioTrack(self.next_track_override)
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
