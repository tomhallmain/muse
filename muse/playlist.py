import random

from utils.app_info_cache import app_info_cache
from utils.config import config
from utils.globals import PlaylistSortType, HistoryType
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
        for history_type in HistoryType:
            setattr(Playlist, history_type.value, app_info_cache.get(history_type.value, []))

    @staticmethod
    def store_recently_played_lists():
        for history_type in HistoryType:
            app_info_cache.set(history_type.value, getattr(Playlist, history_type.value))

    @staticmethod
    def update_list(_list=[], item="", sort_type=PlaylistSortType.RANDOM):
        if item is None or item.strip() == "":
            return
        if item in _list:
            _list.remove(item)
        _list.insert(0, item)
        check_count = Playlist.get_recently_played_check_count(sort_type)
        if len(_list) > check_count:
            del _list[-check_count:]

    @staticmethod
    def get_recently_played_check_count(sort_type):
        recently_played_check_count = abs(int(config.playlist_recently_played_check_count))
        # Note that some groupings will infer an overriden count because they are such broad groupings.
        if sort_type == PlaylistSortType.GENRE_SHUFFLE:
            recently_played_check_count = int(max(recently_played_check_count / 1000, 1))
        elif sort_type == PlaylistSortType.FORM_SHUFFLE:
            recently_played_check_count = int(max(recently_played_check_count / 150, 1))
        elif sort_type == PlaylistSortType.INSTRUMENT_SHUFFLE:
            recently_played_check_count = int(max(recently_played_check_count / 60, 1))
        elif sort_type == PlaylistSortType.COMPOSER_SHUFFLE:
            recently_played_check_count = int(max(recently_played_check_count / 2, 1))
        elif sort_type == PlaylistSortType.ARTIST_SHUFFLE:
            recently_played_check_count = int(max(recently_played_check_count / 2, 1))
        return recently_played_check_count

    @staticmethod
    def update_recently_played_lists(track):
        Playlist.update_list(Playlist.recently_played_filepaths, track.filepath)
        Playlist.update_list(Playlist.recently_played_albums, track.album, sort_type=PlaylistSortType.ALBUM_SHUFFLE)
        Playlist.update_list(Playlist.recently_played_artists, track.artist, sort_type=PlaylistSortType.ARTIST_SHUFFLE)
        Playlist.update_list(Playlist.recently_played_composers, track.composer, sort_type=PlaylistSortType.COMPOSER_SHUFFLE)
        Playlist.update_list(Playlist.recently_played_genres, track.get_genre(), sort_type=PlaylistSortType.GENRE_SHUFFLE)
        Playlist.update_list(Playlist.recently_played_forms, track.get_form(), sort_type=PlaylistSortType.FORM_SHUFFLE)
        Playlist.update_list(Playlist.recently_played_instruments, track.get_instrument(), sort_type=PlaylistSortType.INSTRUMENT_SHUFFLE)

    def __init__(self, tracks=[], _type=PlaylistSortType.SEQUENCE, data_callbacks=None, start_track=None):
        self.in_sequence = list(tracks)
        self.sort_type = _type
        self.pending_tracks = list(tracks)
        self.played_tracks = []
        self.extensions = []
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
        if self.size() > 0:
            self.sort()

    def size(self):
        return len(self.in_sequence)

    def remaining_count(self):
        return len(self.pending_tracks)

    def is_valid(self):
        return len(self.in_sequence) > 0

    def insert_upcoming_tracks(self, tracks, idx=None, offset=1, overwrite_existing_at_index=True):
        if idx is None:
            idx = self.current_track_index
        idx += offset
        if overwrite_existing_at_index:
            del self.sorted_tracks[idx]
        for track in sorted(tracks, reverse=True):
            self.pending_tracks.insert(0, track.filepath) # this list is unordered
            self.sorted_tracks.insert(idx, track)
            self.in_sequence.append(track.filepath)

    def insert_extension(self, track):
        self.insert_upcoming_tracks([track], overwrite_existing_at_index=False)
        self.extensions.append(track)

    def print_upcoming(self, caller=""):
        if True: # keep this function for debug purposes
            return
        print(f"UPCOMING TRACKS (caller {caller})")
        count = 0
        for i in range(self.current_track_index - 1, self.current_track_index + 5, 1):
            track = self.sorted_tracks[i]
            is_excerpt = "" if track.parent_filepath is None else " (excerpt)"
            current_track_index_append = " (current track index)" if i == self.current_track_index else ""
            print(f"{i}{current_track_index_append}: {track}{is_excerpt}")
            count += 1
            if count > 5:
                break
        return count

    def get_upcoming_tracks(self, count=1):
        # NOTE: This returns the state of upcoming tracks assuming that no grouping will be skipped.
        return self.sorted_tracks[self.current_track_index + 1:self.current_track_index + 1 + count]

    def next_track(self, skip_grouping=False, places_from_current=0):
        # NOTE - Modifies self.current_track_index and pending / played tracks properties
        if len(self.sorted_tracks) == 0 or (self.current_track_index + places_from_current) >= len(self.sorted_tracks):
            return None, None, None
        self.print_upcoming("next_track before")
        old_grouping = None
        new_grouping = None
        original_index = int(self.current_track_index)
        for i in range(1 + places_from_current):
            self.current_track_index += 1
            next_track = self.sorted_tracks[self.current_track_index]
            filepath = next_track.get_parent_filepath()
            self.pending_tracks.remove(filepath)
            self.played_tracks.append(filepath)
        if skip_grouping or self.sort_type.is_grouping_type():
            previous_track = None if self.current_track_index == 0 else self.sorted_tracks[original_index]
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
                        filepath = next_track.get_parent_filepath()
                        self.pending_tracks.remove(filepath)
                        self.played_tracks.append(filepath)
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
        self.print_upcoming("next_track after")
        return next_track, old_grouping, new_grouping

    def upcoming_track(self, places_from_current=1):
        # NOTE - Does not modify playlist properties
        upcoming_track_index = self.current_track_index + places_from_current
        if len(self.sorted_tracks) == 0 or (upcoming_track_index) >= len(self.sorted_tracks):
            return None, None, None
        self.print_upcoming("upcoming_track before")
        old_grouping = None
        new_grouping = None
        if upcoming_track_index < len(self.sorted_tracks):
            upcoming_track = self.sorted_tracks[upcoming_track_index]
        else:
            upcoming_track = None
        if self.sort_type.is_grouping_type():
            if self.current_track_index > -1 and self.current_track_index < len(self.sorted_tracks):
                current_track = self.sorted_tracks[self.current_track_index]
            else:
                current_track = None
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
        self.print_upcoming("upcoming_track after")
        return upcoming_track, old_grouping, new_grouping

    def current_track(self):
        try:
            return self.sorted_tracks[self.current_track_index]
        except IndexError:
            return None

    def sort(self):
        grouping_attr_getter_name = None
        list_name_mapping = None
        do_set_start_track = self.start_track is not None
        grouping_attr_getter_name = self.sort_type.getter_name_mapping()
        if self.sort_type == PlaylistSortType.RANDOM:
            random.shuffle(self.sorted_tracks)
        elif not do_set_start_track:
            # This will seed a random start track on the sequence
            # so the sort below will have more randomness.
            self.start_track = random.choice(self.sorted_tracks)
            self.set_start_track(grouping_attr_getter_name)
        if self.sort_type != PlaylistSortType.SEQUENCE:
            if self.sort_type != PlaylistSortType.RANDOM:
                attr_set = set()
                is_callable_attr = grouping_attr_getter_name.startswith("get_")
                for track in self.sorted_tracks:
                    attr = getattr(track, grouping_attr_getter_name)
                    if is_callable_attr:
                        attr = attr()
                    attr_set.add(attr)
                all_attrs_list = list(attr_set)
                if is_callable_attr:
                    self.sorted_tracks.sort(key=lambda t: (all_attrs_list.index(getattr(t, grouping_attr_getter_name)()), t.filepath))
                else:
                    self.sorted_tracks.sort(key=lambda t: (all_attrs_list.index(getattr(t, grouping_attr_getter_name)), t.filepath))
            history_type = self.sort_type.grouping_list_name_mapping()
            self.shuffle_with_memory_for_attr(grouping_attr_getter_name, history_type)
        if do_set_start_track:
            # The user specified a start track, it's not random
            self.set_start_track(grouping_attr_getter_name)

    def shuffle_with_memory_for_attr(self, track_attr: str, history_type: HistoryType):
        # Look at the first config.playlist_recently_played_check_count (1000 default)
        # tracks and ensure they haven't been played recently. If they have, then
        # decide if they need to be reshuffled into a later position in the playlist.
        # As earlier tracks are reshuffled to the end of the playlist, later tracks 
        # may also have been played recently and thus also need to be reshuffled.
        attempts = 0
        max_attempts = 30
        recently_played_attr_list = getattr(Playlist, history_type.value)
        recently_played_check_count = Playlist.get_recently_played_check_count(track_attr)
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
            Utils.log(f"Reshuffling playlist recently played track count: {len(tracks_to_be_reshuffled)} (attempt {attempts})")
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

    def set_start_track(self, grouping_attr_getter_name):
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
            if grouping_attr_getter_name is None:
                raise Exception(f"Playlist start track attribute {grouping_attr_getter_name} not set!")
            track_attr_to_extract = getattr(self.start_track, grouping_attr_getter_name)
            is_callable = False
            if callable(track_attr_to_extract):
                is_callable = True
                track_attr_to_extract = track_attr_to_extract()
            Utils.log(f"Setting playlist start track attribute {grouping_attr_getter_name} to {track_attr_to_extract}")
            if is_callable:
                extracted = [track for track in self.sorted_tracks if getattr(track, grouping_attr_getter_name)() == track_attr_to_extract]
            else:
                extracted = [track for track in self.sorted_tracks if getattr(track, grouping_attr_getter_name) == track_attr_to_extract]
            Utils.log(f"Found {len(extracted)} tracks with attribute {grouping_attr_getter_name} equal to {track_attr_to_extract}")
            for track in extracted:
                self.sorted_tracks.remove(track)
            index = extracted.index(self.start_track)
            extracted = extracted[index:] + extracted[:index]
            self.sorted_tracks = extracted + self.sorted_tracks

    def get_group_count(self, group_text):
        if self.sort_type == PlaylistSortType.SEQUENCE or self.sort_type == PlaylistSortType.RANDOM:
            return 1
        attr_getter_name = self.sort_type.getter_name_mapping()
        is_callable_attr = attr_getter_name.startswith("get_")
        def is_matching_group(track):
            nonlocal group_text
            nonlocal is_callable_attr
            nonlocal attr_getter_name
            if is_callable_attr:
                return getattr(track, attr_getter_name)() == group_text
            else:
                return getattr(track, attr_getter_name) == group_text
        count = len([t for t in self.sorted_tracks if is_matching_group(t)])
        Utils.log(f"Group {group_text} has {count} tracks")
        return count




