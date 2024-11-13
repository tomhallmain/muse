

from utils.config import config

class Artists:
    artists_file = config.artists_file

    def __init__(self):
        pass

    @staticmethod
    def get_artist(title, album, filepath):
        print(album)
        return ""