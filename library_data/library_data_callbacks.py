class LibraryDataCallbacks:
    def __init__(self, get_all_filepaths, get_all_tracks, get_track, instance):
        self.get_all_filepaths = get_all_filepaths
        self.get_all_tracks = get_all_tracks
        self.get_track = get_track
        self.instance = instance

    def identify_compilation_name(self, track, all_tracks=None):
        """
        Identifies if a track is part of a compilation by analyzing album titles.
        Delegates to the LibraryData instance method.
        """
        return self.instance.identify_compilation_name(track, all_tracks)

    def identify_compilation_tracks(self, tracks):
        """
        Process a list of tracks to identify compilations.
        Delegates to the LibraryData instance method.
        """
        return self.instance.identify_compilation_tracks(tracks)
