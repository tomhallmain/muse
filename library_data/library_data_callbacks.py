

class LibraryDataCallbacks:
    def __init__(self, get_all_filepaths, get_all_tracks, get_track, instance):
        self.get_all_filepaths = get_all_filepaths
        self.get_all_tracks = get_all_tracks
        self.get_track = get_track
        self.instance = instance
