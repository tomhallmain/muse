import datetime
import os
import glob
import random
import time

from library_data.audio_track import AudioTrack
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
        self.current_song_index = -1
        self.total = int(args.total) if args else -1
        self.type = WorkflowType[args.workflow_tag] if args else WorkflowType.RANDOM
        self.directories = args.directories if args else ([override_dir] if override_dir else [])
        self.overwrite = args.overwrite if args else False
        self.list = []
        self.next_track_override = None
        PlaybackConfig.OPEN_CONFIGS.append(self)

    def maximum_plays(self):
        return 1

    def get_list(self):
        if len(self.list) != 0:
            return self.list
        l = []
        count = 0
        for directory in self.directories:
            for f in self._get_directory_files(directory):
                if MediaFileType.is_media_filetype(f):
                    l += [os.path.join(directory, f)]
                    count += 1
                    if count > 5000:
                        break
                elif os.path.isfile(f) and config.debug:
                    Utils.log("Skipping non-media file: " + f)
        self.list = l
        if self.type == WorkflowType.RANDOM:
            random.shuffle(self.list)
        elif self.type == WorkflowType.SEQUENCE:
            self.list.sort()
        return self.list

    def get_audio_track_list(self):
        Utils.log("Building audio track cache")
        return [AudioTrack(t) for t in self.get_list()]

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
        if len(l) == 0 or self.current_song_index >= len(l):
            return None
        self.current_song_index += 1
        return AudioTrack(l[self.current_song_index])

    def upcoming_track(self):
        if self.next_track_override is not None:
            upcoming_track = AudioTrack(self.next_track_override)
            upcoming_track.set_is_extended()
            return upcoming_track
        l = self.get_list()
        if len(l) == 0 or self.current_song_index >= len(l):
            return None
        return AudioTrack(l[self.current_song_index + 1])

    def set_next_track_override(self, new_file):
        self.next_track_override = new_file

    @staticmethod
    def force_extension(new_file):
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
