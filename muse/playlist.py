import random

from library_data.media_track import MediaTrack
from utils.app_info_cache import app_info_cache
from utils.config import config
from utils.globals import PlaylistSortType
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._

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

    def __init__(self, tracks=[], _type=PlaylistSortType.SEQUENCE, data_callbacks=None, start_track=None):
        self.in_sequence = list(tracks)
        self.sort_type = _type
        self.pending_tracks = list(tracks)
        self.played_tracks = []
        self.current_track_index = -1
        self.start_track = start_track
        self.data_callbacks = data_callbacks
        assert self.data_callbacks is not None and \
                self.data_callbacks.get_track is not None and \
                self.data_callbacks.get_all_tracks is not None
        # Build sorted tracks list using LibraryData callback to reduce load time
        self.sorted_tracks = []
        for track_filepath in list(tracks):
            track = self.data_callbacks.get_track(track_filepath)
            self.sorted_tracks.append(track)
        Utils.log(f"Playlist length: {self.size()}")
        self.sort()

    def size(self):
        return len(self.in_sequence)

    def remaining_count(self):
        return len(self.pending_tracks)

    def is_valid(self):
        return len(self.in_sequence) > 0

    def next_track(self, skip_grouping=False):
        if len(self.sorted_tracks) == 0 or self.current_track_index >= len(self.sorted_tracks):
            return None, None, None
        old_grouping = None
        new_grouping = None
        self.current_track_index += 1
        next_track = self.sorted_tracks[self.current_track_index]
        self.pending_tracks.remove(next_track.filepath)
        self.played_tracks.append(next_track.filepath)
        if skip_grouping or self.sort_type.is_grouping_type():
            previous_track = None if self.current_track_index == 0 else self.sorted_tracks[self.current_track_index - 1]
            attr_getter_name = self.sort_type.getter_name_mapping()
            next_track_attr = getattr(next_track, attr_getter_name)
            previous_track_attr = getattr(previous_track, attr_getter_name) if previous_track is not None else None
            if callable(next_track_attr):
                next_track_attr = next_track_attr()
                previous_track_attr = previous_track_attr() if previous_track_attr is not None else None
            if previous_track_attr is not None and previous_track_attr == next_track_attr:
                if skip_grouping:
                    old_grouping = previous_track_attr
                    skip_counter = 0
                    while previous_track_attr == next_track_attr and self.current_track_index < len(self.sorted_tracks) - 1:
                        self.current_track_index += 1
                        next_track = self.sorted_tracks[self.current_track_index]
                        self.pending_tracks.remove(next_track.filepath)
                        self.played_tracks.append(next_track.filepath)
                        next_track_attr = getattr(next_track, attr_getter_name)
                        if callable(next_track_attr):
                            next_track_attr = next_track_attr()
                        new_grouping = next_track_attr
                        skip_counter += 1
                    Utils.log(f"Skipped {skip_counter} tracks due to same grouping ({old_grouping} -> {new_grouping})")
            else:
                old_grouping = previous_track_attr
                new_grouping = next_track_attr
                Utils.log("")
        Playlist.update_recently_played_lists(next_track)
        return next_track, old_grouping, new_grouping

    def upcoming_track(self):
        if len(self.sorted_tracks) == 0 or (self.current_track_index + 1) >= len(self.sorted_tracks):
            return None, None, None
        old_grouping = None
        new_grouping = None
        upcoming_track = self.sorted_tracks[self.current_track_index + 1] if self.current_track_index < len(self.sorted_tracks) - 1 else None
        if self.sort_type.is_grouping_type():
            current_track = self.sorted_tracks[self.current_track_index] if self.current_track_index > -1 and self.current_track_index < len(self.sorted_tracks) else None
            if current_track is not None and upcoming_track is not None:
                attr_getter_name = self.sort_type.getter_name_mapping()
                upcoming_track_attr = getattr(upcoming_track, attr_getter_name)
                current_track_attr = getattr(current_track, attr_getter_name)
                if callable(upcoming_track_attr):
                    upcoming_track_attr = upcoming_track_attr()
                    current_track_attr = current_track_attr()
                if upcoming_track_attr != current_track_attr:
                    old_grouping = current_track_attr
                    new_grouping = upcoming_track_attr
        return upcoming_track, old_grouping, new_grouping

    def current_track(self):
        return self.sorted_tracks[self.current_track_index]

    def sort(self):
        attr_getter_name = None
        list_name_mapping = None
        do_set_start_track = self.start_track is None
        if self.sort_type == PlaylistSortType.RANDOM:
            random.shuffle(self.sorted_tracks)
        elif not do_set_start_track:
            # This will seed a random start track on the sequence
            # so the sort below will have more randomness.
            self.start_track = random.choice(self.sorted_tracks)
            self.set_start_track(attr_getter_name)
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
        if do_set_start_track:
            # The user specified a start track, it's not random
            self.set_start_track(attr_getter_name)

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

    def set_start_track(self, track_attr):
        if self.start_track is None:
            return
        if self.start_track not in self.sorted_tracks:
            raise Exception("Playlist start track not in playlist!")
        if self.sort_type == PlaylistSortType.RANDOM:
            Utils.log(f"Setting playlist start track to {self.start_track}")
            self.sorted_tracks.remove(self.start_track)
            self.sorted_tracks.insert(0, self.start_track)
        elif self.sort_type == PlaylistSortType.SEQUENCE:
            Utils.log(f"Setting playlist start track to {self.start_track}")
            index = self.sorted_tracks.index(self.start_track)
            self.sorted_tracks = self.sorted_tracks[index:] + self.sorted_tracks[:index]
        else:
            track_attr_to_extract = getattr(self.start_track, track_attr)
            is_callable = False
            if callable(track_attr_to_extract):
                is_callable = True
                track_attr_to_extract = track_attr_to_extract()
            Utils.log(f"Setting playlist start track attribute {track_attr} to {track_attr_to_extract}")
            if is_callable:
                extracted = [track for track in self.sorted_tracks if getattr(track, track_attr)() == track_attr_to_extract]
            else:
                extracted = [track for track in self.sorted_tracks if getattr(track, track_attr) == track_attr_to_extract]
            Utils.log(f"Found {len(extracted)} tracks with attribute {track_attr} equal to {track_attr_to_extract}")
            for track in extracted:
                self.sorted_tracks.remove(track)
            index = extracted.index(self.start_track)
            extracted = extracted[index:] + extracted[:index]
            self.sorted_tracks = extracted + self.sorted_tracks

    def get_grouping_readable_name(self):
        if self.sort_type == PlaylistSortType.RANDOM or self.sort_type == PlaylistSortType.SEQUENCE:
            return None
        if self.sort_type == PlaylistSortType.ALBUM_SHUFFLE:
            return _("Album")
        if self.sort_type == PlaylistSortType.ARTIST_SHUFFLE:
            return _("Artist")
        if self.sort_type == PlaylistSortType.COMPOSER_SHUFFLE:
            return _("Composer")
        if self.sort_type == PlaylistSortType.GENRE_SHUFFLE:
            return _("Genre")
        if self.sort_type == PlaylistSortType.FORM_SHUFFLE:
            return _("Form")
        if self.sort_type == PlaylistSortType.INSTRUMENT_SHUFFLE:
            return _("Instrument")
        raise Exception(f"Unknown sort type {self.sort_type}")


