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

    def next_track(self) -> None | MediaTrack:
        if len(self.sorted_tracks) == 0 or self.current_song_index >= len(self.sorted_tracks):
            return None
        self.current_song_index += 1
        next_track = self.sorted_tracks[self.current_song_index]
        self.pending_tracks.remove(next_track.filepath)
        self.played_tracks.append(next_track.filepath)
        Playlist.update_recently_played_lists(next_track)
        return next_track

    def upcoming_track(self) -> None | MediaTrack:
        if len(self.sorted_tracks) == 0 or (self.current_song_index + 1) >= len(self.sorted_tracks):
            return None
        return self.sorted_tracks[self.current_song_index + 1]

    def sort(self):
        if self.sort_type == PlaylistSortType.RANDOM:
            random.shuffle(self.sorted_tracks)
            self.shuffle_with_memory_for_attr("filepath", "recently_played_filepaths")
        elif self.sort_type == PlaylistSortType.ALBUM_SHUFFLE:
            album_set = set()
            for track in self.sorted_tracks:
                album_set.add(track.album)
            all_albums_list = list(album_set)

            self.sorted_tracks.sort(key=lambda t: (all_albums_list.index(t.album), t.filepath))
            self.shuffle_with_memory_for_attr("album", "recently_played_albums")
        elif self.sort_type == PlaylistSortType.ARTIST_SHUFFLE:
            artist_set = set()
            for track in self.sorted_tracks:
                artist_set.add(track.artist)
            all_artists_list = list(artist_set)
            self.sorted_tracks.sort(key=lambda t: (all_artists_list.index(t.artist), t.filepath))
            self.shuffle_with_memory_for_attr("artist", "recently_played_artists")
        elif self.sort_type == PlaylistSortType.COMPOSER_SHUFFLE:
            composer_set = set()
            for track in self.sorted_tracks:
                composer_set.add(track.composer)
            all_composers_list  = list(composer_set)
            self.sorted_tracks.sort(key=lambda t: (all_composers_list.index(t.composer), t.filepath))
            self.shuffle_with_memory_for_attr("composer", "recently_played_composers")
        elif self.sort_type == PlaylistSortType.GENRE_SHUFFLE:
            genre_set = set()
            for track in self.sorted_tracks:
                genre_set.add(track.genre)
            all_genres_list = list(genre_set)
            self.sorted_tracks.sort(key=lambda t: (all_genres_list.index(t.genre), t.filepath))
            self.shuffle_with_memory_for_attr("get_genre", "recently_played_genres")
        elif self.sort_type == PlaylistSortType.FORM_SHUFFLE:
            form_set = set()
            for track in self.sorted_tracks:
                form_set.add(track.get_form())
            all_forms_list = list(form_set)
            self.sorted_tracks.sort(key=lambda t: (all_forms_list.index(t.get_form()), t.filepath))
            self.shuffle_with_memory_for_attr("get_form", "recently_played_forms")
        elif self.sort_type == PlaylistSortType.INSTRUMENT_SHUFFLE:
            instrument_set = set()
            for track in self.sorted_tracks:
                instrument_set.add(track.get_instrument())
            all_instruments_list  = list(instrument_set)
            self.sorted_tracks.sort(key=lambda t: (all_instruments_list.index(t.get_instrument()), t.filepath))
            self.shuffle_with_memory_for_attr("get_instrument", "recently_played_instruments")

    def shuffle_with_memory_for_attr(self, track_attr, list_attr):
        # Look at the first config.playlist_recently_played_check_count (1000 default)
        # tracks and ensure they haven't been played recently. If they have, then
        # decide if they need to be reshuffled into a later position in the playlist.
        # As earlier tracks are reshuffled to the end of the playlist, later tracks 
        # may also have been played recently and thus also need to be reshuffled.
        attempts = 0
        max_attempts = 30
        recently_played_check_count = config.playlist_recently_played_check_count
        swap_list = list(getattr(Playlist, list_attr))
        # if track_attr == "genre":
        #     # Note that genre will have an overriden count of 1 just because it is so broad a grouping.
        #     recently_played_check_count = 1
        earliest_tracks = list(self.sorted_tracks[:recently_played_check_count])
        if len(getattr(Playlist, list_attr)) >= recently_played_check_count * 2:
            # The playlist is a short playlist compared to the library, and probably doesn't 
            # have enough tracks to satisfy the check conditions
            return
        tracks_to_be_reshuffled = []
        for track in earliest_tracks:
            if getattr(track, track_attr) in swap_list:
                tracks_to_be_reshuffled.append(track)
        while len(tracks_to_be_reshuffled) > 0:
            Utils.log(f"Reshuffling playlist recently played track count: {len(tracks_to_be_reshuffled)} (attempt {attempts})")
            for track in tracks_to_be_reshuffled:
                self.sorted_tracks.remove(track)
                self.sorted_tracks.append(track)
            tracks_to_be_reshuffled.clear()
            for track in earliest_tracks:
                if getattr(track, track_attr) in swap_list:
                    tracks_to_be_reshuffled.append(track)
            attempts += 1
            if attempts == max_attempts:
                Utils.log(f"Hit max attempts limit, too many recently played tracks found in playlist")
                return max_attempts # No extra reshuffle done
        setattr(Playlist, list_attr, swap_list)
        return attempts



