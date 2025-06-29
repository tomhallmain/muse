import random
from typing import List, Optional, TYPE_CHECKING

from library_data.media_track import MediaTrack
from utils.app_info_cache import app_info_cache
from utils.config import config
from utils.globals import PlaylistSortType, HistoryType
from utils.logging_setup import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from library_data.library_data_callbacks import LibraryDataCallbacks


class Playlist:
    recently_played_filepaths: List[str] = []
    recently_played_albums: List[str] = []
    recently_played_artists: List[str] = []
    recently_played_composers: List[str] = []
    recently_played_genres: List[str] = []
    recently_played_forms: List[str] = []
    recently_played_instruments: List[str] = []

    @staticmethod
    def load_recently_played_lists() -> None:
        for history_type in HistoryType:
            setattr(Playlist, history_type.value, app_info_cache.get(history_type.value, []))

    @staticmethod
    def store_recently_played_lists() -> None:
        for history_type in HistoryType:
            app_info_cache.set(history_type.value, getattr(Playlist, history_type.value))

    @staticmethod
    def update_list(_list: List[str], item: str = "", sort_type: PlaylistSortType = PlaylistSortType.RANDOM) -> None:
        if item is None or item.strip() == "":
            return
        if item in _list:
            _list.remove(item)
        _list.insert(0, item)
        check_count = Playlist.get_recently_played_check_count(sort_type)
        if len(_list) > check_count:
            _list[:] = _list[:check_count]

    @staticmethod
    def get_recently_played_check_count(sort_type: PlaylistSortType) -> int:
        recently_played_check_count = abs(int(config.playlist_recently_played_check_count))
        # Note that some groupings will infer an overriden count because they are such broad groupings.
        if sort_type == PlaylistSortType.GENRE_SHUFFLE:
            recently_played_check_count = int(max(recently_played_check_count / 1000, 1))
        elif sort_type == PlaylistSortType.FORM_SHUFFLE:
            recently_played_check_count = int(max(recently_played_check_count / 150, 1))
        elif sort_type == PlaylistSortType.INSTRUMENT_SHUFFLE:
            recently_played_check_count = int(max(recently_played_check_count / 60, 1))
        elif sort_type == PlaylistSortType.COMPOSER_SHUFFLE:
            recently_played_check_count = int(max(recently_played_check_count / 4, 1))
        elif sort_type == PlaylistSortType.ARTIST_SHUFFLE:
            recently_played_check_count = int(max(recently_played_check_count / 4, 1))
        elif sort_type == PlaylistSortType.ALBUM_SHUFFLE:
            recently_played_check_count = int(max(recently_played_check_count / 2, 1))
        return recently_played_check_count

    @staticmethod
    def update_recently_played_lists(track: MediaTrack) -> None:
        Playlist.update_list(Playlist.recently_played_filepaths, track.filepath)
        Playlist.update_list(Playlist.recently_played_albums, track.album, sort_type=PlaylistSortType.ALBUM_SHUFFLE)
        Playlist.update_list(Playlist.recently_played_artists, track.artist, sort_type=PlaylistSortType.ARTIST_SHUFFLE)
        Playlist.update_list(Playlist.recently_played_composers, track.composer, sort_type=PlaylistSortType.COMPOSER_SHUFFLE)
        Playlist.update_list(Playlist.recently_played_genres, track.get_genre(), sort_type=PlaylistSortType.GENRE_SHUFFLE)
        Playlist.update_list(Playlist.recently_played_forms, track.get_form(), sort_type=PlaylistSortType.FORM_SHUFFLE)
        Playlist.update_list(Playlist.recently_played_instruments, track.get_instrument(), sort_type=PlaylistSortType.INSTRUMENT_SHUFFLE)

    def __init__(self, tracks: List[str] = [], _type: PlaylistSortType = PlaylistSortType.SEQUENCE, 
                 data_callbacks: Optional['LibraryDataCallbacks'] = None, start_track: Optional[MediaTrack] = None, 
                 check_entire_playlist: bool = False) -> None:
        self.in_sequence: List[str] = list(tracks)
        self.sort_type: PlaylistSortType = _type
        self.pending_tracks: List[str] = list(tracks)
        self.played_tracks: List[str] = []
        self.extensions: List[MediaTrack] = []
        self.current_track_index: int = -1
        self.start_track: Optional[MediaTrack] = start_track
        self.data_callbacks: Optional['LibraryDataCallbacks'] = data_callbacks
        assert self.data_callbacks is not None and \
                self.data_callbacks.get_track is not None and \
                self.data_callbacks.get_all_tracks is not None
        # Build sorted tracks list using LibraryData callback to reduce load time
        self.sorted_tracks: List[MediaTrack] = []
        for track_filepath in list(tracks):
            track = self.data_callbacks.get_track(track_filepath)
            self.sorted_tracks.append(track)
        logger.info(f"Playlist length: {self.size()}")
        if self.size() > 0:
            self.sort(check_entire_playlist=check_entire_playlist)

    def size(self) -> int:
        return len(self.in_sequence)

    def remaining_count(self) -> int:
        return len(self.pending_tracks)

    def is_valid(self) -> bool:
        return len(self.in_sequence) > 0

    def insert_upcoming_tracks(self, tracks: List[MediaTrack], idx: Optional[int] = None, 
                             offset: int = 1, overwrite_existing_at_index: bool = True) -> None:
        if idx is None:
            idx = self.current_track_index
        idx += offset
        if overwrite_existing_at_index:
            del self.sorted_tracks[idx]
        for track in sorted(tracks, reverse=True):
            self.pending_tracks.insert(0, track.filepath) # this list is unordered
            self.sorted_tracks.insert(idx, track)
            self.in_sequence.append(track.filepath)

    def insert_extension(self, track: MediaTrack) -> None:
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

    def get_upcoming_tracks(self, count: int = 1) -> List[MediaTrack]:
        # NOTE: This returns the state of upcoming tracks assuming that no grouping will be skipped.
        return self.sorted_tracks[self.current_track_index + 1:self.current_track_index + 1 + count]

    def next_track(self, skip_grouping: bool = False, places_from_current: int = 0) -> tuple[Optional[MediaTrack], Optional[str], Optional[str]]:
        """Returns the next track, old grouping, and new grouping.
        NOTE - Modifies self.current_track_index and pending / played tracks properties.

        Args:
            skip_grouping: If True, skip the grouping check
            places_from_current: The number of places from the current track to get the next track
        Returns:
            tuple: (next_track, old_grouping, new_grouping)
        """
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
                    logger.info(f"Skipped {skip_counter} tracks due to same grouping ({old_grouping} -> {new_grouping})")
            else:
                old_grouping = previous_track_attr
                new_grouping = next_track_attr
                logger.info("")
        Playlist.update_recently_played_lists(next_track)
        self.print_upcoming("next_track after")
        return next_track, old_grouping, new_grouping

    def upcoming_track(self, places_from_current: int = 1) -> tuple[Optional[MediaTrack], Optional[str], Optional[str]]:
        """Returns the upcoming track, old grouping, and new grouping.
        NOTE - Does not modify playlist properties.
        
        Args:
            places_from_current: The number of places from the current track to get the upcoming track
        
        Returns:
            tuple: (upcoming_track, old_grouping, new_grouping)
        """
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

    def current_track(self) -> Optional[MediaTrack]:
        try:
            return self.sorted_tracks[self.current_track_index]
        except IndexError:
            return None

    def get_next_grouping(self):
        """Get the next grouping that will be encountered in the playlist.
        
        This method finds the first upcoming track that belongs to a different group
        than the current track's group. If no grouping change is found (all remaining
        tracks are in the same group), returns None.
        
        Returns:
            str or None: The name of the next grouping, or None if no grouping change found
        """
        if not self.sort_type.is_grouping_type():
            return None
        
        if len(self.sorted_tracks) == 0 or self.current_track_index < 0:
            return None
        
        # Get current track's grouping
        current_track = self.current_track()
        if current_track is None:
            return None
        
        attr_getter_name = self.sort_type.getter_name_mapping()
        current_track_attr = getattr(current_track, attr_getter_name)
        if callable(current_track_attr):
            current_track_attr = current_track_attr()
        
        # Iterate through upcoming tracks to find the first different grouping
        for i in range(self.current_track_index + 1, len(self.sorted_tracks)):
            upcoming_track = self.sorted_tracks[i]
            upcoming_track_attr = getattr(upcoming_track, attr_getter_name)
            if callable(upcoming_track_attr):
                upcoming_track_attr = upcoming_track_attr()
            
            if upcoming_track_attr != current_track_attr:
                return upcoming_track_attr
        
        # No grouping change found - all remaining tracks are in the same group
        return None

    def sort(self, check_entire_playlist=False):
        """Sorts the playlist according to the specified sort type with optional memory-based shuffling.
        
        The method handles several sort types:
        - SEQUENCE: Maintains original track order
        - RANDOM: Completely randomizes tracks with no grouping consideration
        - Other types (ALBUM_SHUFFLE, ARTIST_SHUFFLE, etc.): Groups tracks by attribute and applies
          memory-based shuffling to avoid recently played groups
        
        For non-RANDOM sorts, the method first seeds a random start track (unless user-specified)
        to add variety to the initial grouping, then applies memory-based shuffling to avoid
        recently played groups in the early portion of the playlist.
        
        Args:
            check_entire_playlist (bool): If True, uses thorough memory-based shuffling that
                                        guarantees no recently played groups in early portion
        """
        grouping_attr_getter_name = None
        do_set_start_track = self.start_track is not None
        grouping_attr_getter_name = self.sort_type.getter_name_mapping()
        if self.sort_type == PlaylistSortType.RANDOM:
            random.shuffle(self.sorted_tracks)
        elif not do_set_start_track:
            # This will seed a random start track on the sequence so the sort below will have more randomness.
            self.start_track = random.choice(self.sorted_tracks)
            self.set_start_track(grouping_attr_getter_name, do_print=False)
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
            self.shuffle_with_memory_for_attr(grouping_attr_getter_name, history_type, check_entire_playlist)
        if do_set_start_track:
            # The user specified a start track, it's not random
            self.set_start_track(grouping_attr_getter_name)

    def shuffle_with_memory_for_attr(self, track_attr: str, history_type: HistoryType, check_entire_playlist=False):
        """Main entry point for reducing recently played tracks in the playlist.
        
        This method looks at the first config.playlist_recently_played_check_count tracks
        and ensures they haven't been played recently. If they have, it decides if they need
        to be reshuffled into a later position in the playlist. As earlier tracks are reshuffled
        to the end of the playlist, later tracks may also have been played recently and thus
        also need to be reshuffled.
        
        The method can use either a thorough approach (scour_playlist) that guarantees no recently
        played tracks in the early portion while preserving grouping integrity, or a less thorough
        approach (reshuffle_tracks) that may leave some recently played tracks but preserves more
        of the original randomization.
        
        Args:
            track_attr (str): The attribute name to check on each track (e.g., 'album', 'artist')
            history_type (HistoryType): The type of history to check against (e.g., albums, artists)
            check_entire_playlist (bool): If True, uses the thorough scour_playlist method instead
                                        of the default reshuffle_tracks method
                                        
        Returns:
            int: Number of attempts made to reduce recently played tracks in the playlist
        """
        recently_played_attr_list = list(getattr(Playlist, history_type.value))
        recently_played_check_count = Playlist.get_recently_played_check_count(self.sort_type)
        logger.info(f"Recently played check count for {history_type.value}: {recently_played_check_count}")
        if len(recently_played_attr_list) == 0:
            return 0
        elif len(recently_played_attr_list) > recently_played_check_count:
            recently_played_attr_list = recently_played_attr_list[:recently_played_check_count]
        
        # Minimum playlist size to attempt any shuffling
        MIN_PLAYLIST_SIZE = 200
        # Target playlist size for full check count
        TARGET_PLAYLIST_SIZE = max(recently_played_check_count * 2, MIN_PLAYLIST_SIZE)
        
        if self.size() < MIN_PLAYLIST_SIZE:
            # Playlist is too small to bother with memory-based shuffling
            return 0
            
        # Scale the check count based on playlist size
        if self.size() < TARGET_PLAYLIST_SIZE:
            # Linearly scale the check count based on playlist size
            # e.g., 1000 tracks would use 50% of the check count
            scale_factor = self.size() / TARGET_PLAYLIST_SIZE
            recently_played_check_count = int(recently_played_check_count * scale_factor)
            # Ensure we check at least a minimum number of tracks
            recently_played_check_count = max(recently_played_check_count, 50)
            
        if check_entire_playlist:
            return self.scour_playlist(track_attr, recently_played_attr_list, recently_played_check_count)
        else:
            return self.reshuffle_tracks(track_attr, recently_played_attr_list, recently_played_check_count)

    def scour_playlist(self, track_attr, recently_played_attr_list, recently_played_check_count):
        """Scours the playlist to ensure the first N tracks don't contain recently played attributes.
        
        This method is used to maintain variety in playlists across sessions by ensuring that tracks 
        with recently played attributes (like albums, artists, genres, etc.) are moved out of the
        earliest portion of the playlist.
        
        Args:
            track_attr (str): The attribute name to check on each track (e.g., 'album', 'artist')
            recently_played_attr_list (list): List of attribute values that have been recently played
            recently_played_check_count (int): Number of tracks from the start to check and maintain
            
        Returns:
            int: Number of tracks checked during the process. Returns 0 if no reshuffling was needed.
        """
        tracks_checked = 0
        max_tracks_to_check = min(100000, self.size())  # Reasonable limit for most playlists
        total_moved = 0
        logger.info(f"Scouring playlist for tracks not in {len(recently_played_attr_list)} recently played {track_attr}s with {recently_played_check_count} tracks to check")

        while tracks_checked < max_tracks_to_check:
            tracks_to_be_reshuffled = []
            earliest_tracks = list(self.sorted_tracks[:recently_played_check_count])
            
            # First pass: identify tracks that need to be reshuffled
            for track in earliest_tracks:
                if getattr(track, track_attr) in recently_played_attr_list:
                    tracks_to_be_reshuffled.append(track)
            
            # If no tracks need reshuffling, we're done
            if not tracks_to_be_reshuffled:
                if total_moved > 0:
                    logger.info(f"Successfully moved all {total_moved} tracks with recently played {track_attr} out of first {recently_played_check_count} positions")
                else:
                    logger.info(f"No tracks needed reshuffling for {track_attr}")
                return tracks_checked
                
            logger.info(f"Found {len(tracks_to_be_reshuffled)} tracks with recently played {track_attr} in first {recently_played_check_count} positions")
                
            # Remove tracks that need reshuffling and add them to the end
            for track in tracks_to_be_reshuffled:
                self.sorted_tracks.remove(track)
                self.sorted_tracks.append(track)
                total_moved += 1
            
            tracks_checked += len(earliest_tracks)
            
        logger.info(f"Hit max tracks limit ({max_tracks_to_check}) while trying to move tracks with recently played {track_attr}")
        return tracks_checked

    def reshuffle_tracks(self, track_attr, recently_played_attr_list, recently_played_check_count):
        """A less thorough alternative to scour_playlist for reducing recently played tracks.
        
        This method attempts to reduce the number of recently played tracks in the earliest portion
        of the playlist by moving them to the end. Unlike scour_playlist, it:
        - Makes multiple passes through the early part of the playlist to gradually improve distribution
        - May not completely eliminate recently played tracks from the earliest portion
        - Stops after reaching a stable minimum or hitting max attempts
        
        This method provides fewer guarantees about the final playlist distribution, but it may end up
        producing playlists more to the users taste by including some recently played tracks sooner and
        preserving some of the earlier randomization.
   
        Args:
            track_attr (str): The attribute name to check on each track (e.g., 'album', 'artist')
            recently_played_attr_list (list): List of attribute values that have been recently played
            recently_played_check_count (int): Number of tracks from the start to check and maintain
            
        Returns:
            int: Number of reshuffling attempts made before reaching a stable state or max attempts
        """
        # Reshuffle twice as many tracks as checked to reduce reshuffling iterations
        doubled_check_count = recently_played_check_count * 2
        earliest_tracks = list(self.sorted_tracks[:doubled_check_count])
        tracks_to_be_reshuffled = []
        tracks_to_check = []
        count = 0
        attempts = 0
        max_attempts = 30
        stable_attempts = 0
        min_stable_attempts = 5  # Number of attempts with same count before considering it stable
        last_track_count = None
        for track in earliest_tracks:
            if getattr(track, track_attr) in recently_played_attr_list:
                tracks_to_be_reshuffled.append(track)
                if count < recently_played_check_count:
                    tracks_to_check.append(track)
                elif len(tracks_to_check) == 0:
                    break
            count += 1
        while len(tracks_to_check) > 0:
            current_check_count = len(tracks_to_check)
            logger.info(f"Reshuffling playlist recently played track count: {current_check_count} (attempt {attempts})")
            
            # Check if we've hit a stable minimum
            if last_track_count is not None and current_check_count == last_track_count:
                stable_attempts += 1
                if stable_attempts >= min_stable_attempts:
                    logger.info(f"Found stable minimum of {current_check_count} tracks after {attempts} attempts")
                    break
            else:
                stable_attempts = 0
            last_track_count = current_check_count

            for track in tracks_to_be_reshuffled:
                self.sorted_tracks.remove(track)
                self.sorted_tracks.append(track)
            tracks_to_be_reshuffled.clear()
            tracks_to_check.clear()
            earliest_tracks = list(self.sorted_tracks[:doubled_check_count])
            count = 0
            for track in earliest_tracks:
                if getattr(track, track_attr) in recently_played_attr_list:
                    tracks_to_be_reshuffled.append(track)
                    if count < recently_played_check_count:
                        tracks_to_check.append(track)
                    elif len(tracks_to_check) == 0:
                        break
                count += 1
            attempts += 1
            if attempts == max_attempts:
                logger.info(f"Hit max attempts limit, too many recently played tracks found in playlist")
                return attempts
        return attempts

    def set_start_track(self, grouping_attr_getter_name, do_print=True):
        if self.start_track is None:
            return
        if self.start_track not in self.sorted_tracks:
            raise Exception("Playlist start track not in playlist!")
        if self.sort_type == PlaylistSortType.RANDOM:
            logger.info(f"Setting playlist start track to {self.start_track}")
            self.sorted_tracks.remove(self.start_track)
            self.sorted_tracks.insert(0, self.start_track)
        elif self.sort_type == PlaylistSortType.SEQUENCE:
            logger.info(f"Setting playlist start track to {self.start_track}")
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
            if do_print:
                logger.info(f"Setting playlist start track attribute {grouping_attr_getter_name} to {track_attr_to_extract}")
            if is_callable:
                extracted = [track for track in self.sorted_tracks if getattr(track, grouping_attr_getter_name)() == track_attr_to_extract]
            else:
                extracted = [track for track in self.sorted_tracks if getattr(track, grouping_attr_getter_name) == track_attr_to_extract]
            if do_print:
                logger.info(f"Found {len(extracted)} tracks with attribute {grouping_attr_getter_name} equal to {track_attr_to_extract}")
            for track in extracted:
                self.sorted_tracks.remove(track)
            index = extracted.index(self.start_track)
            extracted = extracted[index:] + extracted[:index]
            self.sorted_tracks = extracted + self.sorted_tracks

    def get_group_count(self, group_text: str) -> int:
        if self.sort_type == PlaylistSortType.SEQUENCE or self.sort_type == PlaylistSortType.RANDOM:
            return 1
        attr_getter_name = self.sort_type.getter_name_mapping()
        is_callable_attr = attr_getter_name.startswith("get_")
        def is_matching_group(track: MediaTrack) -> bool:
            nonlocal group_text
            nonlocal is_callable_attr
            nonlocal attr_getter_name
            if is_callable_attr:
                return getattr(track, attr_getter_name)() == group_text
            else:
                return getattr(track, attr_getter_name) == group_text
        count = len([t for t in self.sorted_tracks if is_matching_group(t)])
        logger.info(f"Group {group_text} has {count} tracks")
        return count




