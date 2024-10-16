import os
import glob
import random

from utils.app_info_cache import app_info_cache
from utils.config import config
from utils.globals import MediaFileType, WorkflowType

class PlaybackConfig:
    DIRECTORIES_CACHE = {}

    @staticmethod
    def store_directory_cache():
        app_info_cache.set("directories_cache", PlaybackConfig.DIRECTORIES_CACHE)

    @staticmethod
    def load_directory_cache():
        PlaybackConfig.DIRECTORIES_CACHE = app_info_cache.get("directories_cache", default_val={})

    def __init__(self, args):
        self.current_song_index = -1
        self.type = WorkflowType[args.workflow_tag]
        self.directories = args.directories
        self.overwrite = args.overwrite
        self.list = []

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
                    print("Skipping non-media file: " + f)
        self.list = l
        if self.type == WorkflowType.RANDOM:
            random.shuffle(self.list)
        return self.list

    def _get_directory_files(self, directory):
        if directory not in PlaybackConfig.DIRECTORIES_CACHE or self.overwrite:
            files = glob.glob(directory + "\\**/*", recursive = True)
            PlaybackConfig.DIRECTORIES_CACHE[directory] = files
        else:
            files = PlaybackConfig.DIRECTORIES_CACHE[directory]
        return files

    def next_song(self):
        l = self.get_list()
        if len(l) == 0 or self.current_song_index >= len(l):
            return None
        self.current_song_index += 1
        return l[self.current_song_index]
    
    def __str__(self) -> str:
        return "PlaybackConfig(type=" + str(self.type) + ", directories=" + str(len(self.directories)) + ")"
