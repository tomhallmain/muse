import os

from utils.utils import Utils

class AudioTrack:
    def __init__(self, filepath):
        self.filepath = filepath
        if self.filepath is not None and self.filepath != "":
            self.basename = os.path.basename(filepath)
            self.album = Utils.get_relative_dirpath(os.path.dirname(os.path.abspath(filepath)))
            self.title, self.ext = os.path.splitext(self.basename)
        else:
            self.basename = None
            self.album = None
            self.title = None
            self.ext = None

    def is_invalid(self):
        if self.basename is None:
            return True
        if not os.path.isfile(self.filepath):
            raise Exception("Could not find song file path: " + self.filepath)
        return False

