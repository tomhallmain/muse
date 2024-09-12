import os
import random

from utils.globals import MediaFileType

class PlaybackConfig:
    def __init__(self, args):
        self.current_song_index = -1
        self.directories = args.directories

    def maximum_plays(self):
        return 1

    def generate_list(self):
        l = []
        count = 0
        for directory in self.directories:
            for f in os.listdir(directory):
                if MediaFileType.is_media_filetype(f):
                    l += [os.path.join(directory, f)]
                    count += 1
                    if count > 5000:
                        break
                else:
                    print("Skipping non-media file: " + f)
        return l

    def next_song(self):
        l = self.generate_list()
        if len(l) == 0 or self.current_song_index >= len(l):
            return None
        self.current_song_index += 1
        return l[self.current_song_index]
