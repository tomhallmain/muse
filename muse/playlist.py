import random

from library_data.media_track import MediaTrack
from utils.app_info_cache import app_info_cache
from utils.config import config
from utils.globals import PlaylistSortType
from utils.utils import Utils

## TODO need a way to exclude certain artists from the smart sort based on recent plays


class Playlist:
    recently_played_filepaths = []
    recently_played_albums = []
    recently_played_artists = []
    recently_played_composers = []
    recently_played_genres = []
    recently_played_forms = []
    recently_played_instruments = []

    @staticmethod
    def load_recently_played_lists():
        Playlist.recently_played_filepaths = app_info_cache.get("recently_played_filepaths", [])
        Playlist.recently_played_albums = app_info_cache.get("recently_played_albums", [])
        Playlist.recently_played_artists = app_info_cache.get("recently_played_artists", [])
        Playlist.recently_played_composers = app_info_cache.get("recently_played_composers", [])
        Playlist.recently_played_genres = app_info_cache.get("recently_played_genres", [])
        Playlist.recently_played_forms = app_info_cache.get("recently_played_forms", [])
        Playlist.recently_played_instruments = app_info_cache.get("recently_played_instruments", [])

    @staticmethod
    def store_recently_played_lists():
        app_info_cache.set("recently_played_filepaths", Playlist.recently_played_filepaths)
        app_info_cache.set("recently_played_albums", Playlist.recently_played_albums)
        app_info_cache.set("recently_played_artists", Playlist.recently_played_artists)
        app_info_cache.set("recently_played_composers", Playlist.recently_played_composers)
        app_info_cache.set("recently_played_genres", Playlist.recently_played_genres)
        app_info_cache.set("recently_played_forms", Playlist.recently_played_forms)
        app_info_cache.set("recently_played_instruments", Playlist.recently_played_instruments)

    @staticmethod
    def update_list(_list=[], item=""):
        if item is None or item.strip() == "":
            return
        if item in _list:
            _list.remove(item)
        _list.insert(0, item)
        if len(_list) > config.playlist_recently_played_check_count:
            del _list[-config.playlist_recently_played_check_count:]

    @staticmethod
    def update_recently_played_lists(track):
        Playlist.update_list(Playlist.recently_played_filepaths, track.filepath)
        Playlist.update_list(Playlist.recently_played_albums, track.album)
        Playlist.update_list(Playlist.recently_played_artists, track.artist)
        Playlist.update_list(Playlist.recently_played_composers, track.composer)
        Playlist.update_list(Playlist.recently_played_genres, track.get_genre())
        Playlist.update_list(Playlist.recently_played_forms, track.get_form())
        Playlist.update_list(Playlist.recently_played_instruments, track.get_instrument())

    def __init__(self, tracks=[], _type=PlaylistSortType.SEQUENCE, data_callbacks=None):
        self.in_sequence = list(tracks)
        self.sort_type = _type
        self.pending_tracks = list(tracks)
        self.played_tracks = []
        self.current_song_index = -1
        self.data_callbacks = data_callbacks
        assert self.data_callbacks is not None and \
                self.data_callbacks.get_track is not None and \
                self.data_callbacks.get_all_tracks is not None
        # Build sorted tracks list using LibraryData callback to reduce load time
        self.sorted_tracks = []
        for track_filepath in list(tracks):
            track = self.data_callbacks.get_track(track_filepath)
            self.sorted_tracks.append(track)
        self.sort()

    def size(self):
        return len(self.in_sequence)

    def remaining_count(self):
        return len(self.pending_tracks)

    def is_valid(self):
        return len(self.in_sequence) > 0

    def next_track(self, skip_grouping=False) -> None | MediaTrack:
        if len(self.sorted_tracks) == 0 or self.current_song_index >= len(self.sorted_tracks):
            return None
        self.current_song_index += 1
        next_track = self.sorted_tracks[self.current_song_index]
        self.pending_tracks.remove(next_track.filepath)
        self.played_tracks.append(next_track.filepath)
        if skip_grouping:
            previous_track = None if self.current_song_index == 0 else self.sorted_tracks[self.current_song_index - 1]
            attr_getter_name = self.sort_type.getter_name_mapping()
            next_track_attr = getattr(next_track, attr_getter_name)
            previous_track_attr = getattr(previous_track, attr_getter_name)
            if callable(next_track_attr):
                next_track_attr = next_track_attr()
                previous_track_attr = previous_track_attr()
            while previous_track_attr == next_track_attr and self.current_song_index < len(self.sorted_tracks) - 1:
                self.current_song_index += 1
                next_track = self.sorted_tracks[self.current_song_index]
                self.pending_tracks.remove(next_track.filepath)
                self.played_tracks.append(next_track.filepath)
                next_track_attr = getattr(next_track, attr_getter_name)
                if callable(next_track_attr):
                    next_track_attr = next_track_attr()
        Playlist.update_recently_played_lists(next_track)
        return next_track

    def upcoming_track(self) -> None | MediaTrack:
        if len(self.sorted_tracks) == 0 or (self.current_song_index + 1) >= len(self.sorted_tracks):
            return None
        return self.sorted_tracks[self.current_song_index + 1]

    def sort(self):
        if self.sort_type == PlaylistSortType.RANDOM:
            random.shuffle(self.sorted_tracks)
        if self.sort_type != PlaylistSortType.SEQUENCE:
            attr_getter_name = self.sort_type.getter_name_mapping()
            if self.sort_type != PlaylistSortType.RANDOM:
                attr_set = set()
                is_callable_attr = attr_getter_name.startswith("get_")
                for track in self.sorted_tracks:
                    attr = getattr(track, attr_getter_name)
                    if is_callable_attr:
                        attr = attr()
                    attr_set.add(attr)
                all_attrs_list = list(attr_set)
                if is_callable_attr:
                    self.sorted_tracks.sort(key=lambda t: (all_attrs_list.index(getattr(t, attr_getter_name)()), t.filepath))
                else:
                    self.sorted_tracks.sort(key=lambda t: (all_attrs_list.index(getattr(t, attr_getter_name)), t.filepath))
            list_name_mapping = self.sort_type.grouping_list_name_mapping()
            self.shuffle_with_memory_for_attr(attr_getter_name, list_name_mapping)

    def shuffle_with_memory_for_attr(self, track_attr, list_attr):
        # Look at the first config.playlist_recently_played_check_count (1000 default)
        # tracks and ensure they haven't been played recently. If they have, then
        # decide if they need to be reshuffled into a later position in the playlist.
        # As earlier tracks are reshuffled to the end of the playlist, later tracks 
        # may also have been played recently and thus also need to be reshuffled.
        attempts = 0
        max_attempts = 30
        recently_played_check_count = config.playlist_recently_played_check_count
        recently_played_attr_list = getattr(Playlist, list_attr)
        # if track_attr == "genre":
        #     # Note that genre will have an overriden count of 1 just because it is so broad a grouping.
        #     recently_played_check_count = 1
        earliest_tracks = list(self.sorted_tracks[:recently_played_check_count])
        if self.size() <= recently_played_check_count * 2:
            # The playlist is a short playlist compared to the library, and probably doesn't 
            # have enough tracks to satisfy the check conditions
            return
        tracks_to_be_reshuffled = []
        for track in earliest_tracks:
            if getattr(track, track_attr) in recently_played_attr_list:
                tracks_to_be_reshuffled.append(track)
        while len(tracks_to_be_reshuffled) > 0:
            Utils.log(f"Reshuffling playlist recently played track count: {len(tracks_to_be_reshuffled)} (attempt {attempts}) - recently played tracks count = {len(tracks_to_be_reshuffled)}")
            for track in tracks_to_be_reshuffled:
                self.sorted_tracks.remove(track)
                self.sorted_tracks.append(track)
            tracks_to_be_reshuffled.clear()
            earliest_tracks = list(self.sorted_tracks[:recently_played_check_count])
            for track in earliest_tracks:
                if getattr(track, track_attr) in recently_played_attr_list:
                    tracks_to_be_reshuffled.append(track)
            attempts += 1
            if attempts == max_attempts:
                Utils.log(f"Hit max attempts limit, too many recently played tracks found in playlist")
                return max_attempts
        return attempts



