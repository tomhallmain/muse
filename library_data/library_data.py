from datetime import datetime
import copy
import glob
import os
import pickle
import re
import threading
import traceback

from extensions.extension_manager import ExtensionManager
from library_data.artist import artists_data
from library_data.composer import composers_data
from library_data.form import forms_data
from library_data.genre import genre_data
from library_data.instrument import instruments_data
from library_data.library_data_callbacks import LibraryDataCallbacks
from library_data.media_track import MediaTrack
from utils.app_info_cache import app_info_cache
from utils.config import config
from utils.globals import MediaFileType, PlaylistSortType
from utils.logging_setup import get_logger
from utils.utils import Utils
from utils.translations import I18N

_ = I18N._

libary_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)))

logger = get_logger(__name__)

class LibraryDataSearch:
    def __init__(self, all="", title="", album="", artist="", composer="", genre="", instrument="", form="",
                 selected_track_path=None, stored_results_count=0, max_results=200, id=None, offset=0):
        self.all = all.lower()
        self.title = title.lower()
        self.album = album.lower()
        self.artist = artist.lower()
        self.composer = composer.lower()
        self.genre = genre.lower()
        self.instrument = instrument.lower()
        self.form = form.lower()
        self.stored_results_count = stored_results_count
        self.selected_track_path = selected_track_path
        self.max_results = max_results
        self.id = id
        self.offset = offset  # Offset for pagination

        self.results = []
        self.total_matches_count = 0  # Total matches found (including skipped ones)

    def is_valid(self):
        all_fields_empty = True
        for name in ["all", "title", "album", "artist", "composer", "genre", "instrument", "form"]:
            field = getattr(self, name)
            if field is not None and field.strip() != "":
                all_fields_empty = False
                break
        if all_fields_empty:
            return False
        return self.selected_track_path is None or os.path.isfile(self.selected_track_path)

    def set_stored_results_count(self):
        self.stored_results_count = len(self.results)
        logger.info(f"Stored count for {self}: {self.get_readable_stored_results_count()}")

    def get_readable_stored_results_count(self) -> str:
        if self.stored_results_count > self.max_results:
            results_str = f"{self.max_results}+"
        else:
            results_str = str(self.stored_results_count)
        return _("({0} results)").format(results_str)

    def set_selected_track_path(self, track):
        assert track is not None
        self.selected_track_path = str(track.filepath)
        logger.info(f"Set selected track path on {self}: {self.selected_track_path}")

    def test(self, audio_track):
        # Check if we've collected enough results for this page (max_results + 1 to detect if there are more)
        if len(self.results) > self.max_results:
            return None
        
        # Track total matches (including skipped ones)
        is_match = False
        
        # NOTE - don't use _get_searchable_track_attr here because would be slower
        if len(self.all) > 0:
            for field in [audio_track.searchable_title, audio_track.searchable_artist,
                          audio_track.searchable_composer, audio_track.searchable_album,
                          audio_track.searchable_genre, audio_track.get_instrument(), audio_track.get_form()]:
                if field is not None and self.all in field:
                    is_match = True
                    break
        else:
            attrs_to_get = []
            if len(self.title) > 0:
                attrs_to_get.append(("title", "searchable_title"))
            if len(self.album) > 0:
                attrs_to_get.append(("album", "searchable_album"))
            if len(self.artist) > 0:
                attrs_to_get.append(("artist", "searchable_artist"))
            if len(self.composer) > 0:
                attrs_to_get.append(("composer", "searchable_composer"))
            if len(self.genre) > 0:
                attrs_to_get.append(("genre", "searchable_genre"))
            if len(self.instrument) > 0:
                attrs_to_get.append(("instrument", "get_instrument"))
            if len(self.form) > 0:
                attrs_to_get.append(("form", "get_form"))
            
            is_match = True
            for search_attr, track_attr in attrs_to_get:
                track_value = getattr(audio_track, track_attr)
                if track_attr.startswith("get_"):
                    track_value = track_value()
                if track_value is None or track_value.strip() == "":
                    is_match = False
                    break
                search_value = self.__dict__[search_attr]
                if search_value not in track_value:
                    is_match = False
                    break
        
        if is_match:
            self.total_matches_count += 1
            
            # Only add to results if we're past the offset and haven't exceeded max_results + 1
            if self.total_matches_count > self.offset:
                self.results.append(audio_track)
                return True
            else:
                # Match found but we're still skipping due to offset
                return True  # Continue searching
        
        return False

    def get_results(self):
        return self.results

    def sort_results_by(self, attr=None):
        if len(self.results) == 0 or (attr is not None and attr.strip() == ""):
            return
        search_field = None
        if attr is None:
            for _attr in ["title", "album", "artist", "composer", "genre", "instrument", "form"]:
                if len(getattr(self, _attr)) > 0:
                    search_field = _attr
                    attr = self._get_searchable_track_attr(_attr)
                    break
            if attr is None:
                logger.info("No sortable attribute in search query.")
                return
        else:
            search_field = attr
            attr = self._get_searchable_track_attr(attr)

        search_value = getattr(self, search_field, "") if search_field else ""
        is_callable = callable(getattr(self.results[0], attr))

        def _sort_key(track):
            val = getattr(track, attr)
            if is_callable:
                val = val()
            val_str = val if val is not None else ""
            relevance = self._match_relevance(val_str, search_value)
            return (relevance, val_str, track.filepath)

        self.results.sort(key=_sort_key)

    @staticmethod
    def _match_relevance(value: str, query: str) -> int:
        """Score how well *query* matches inside *value*.

        Returns 0 (starts with query), 1 (word-boundary match),
        or 2 (substring / no match).
        """
        if not query or not value:
            return 2
        v = value.lower()
        if v.startswith(query):
            return 0
        idx = v.find(query)
        if idx > 0 and not v[idx - 1].isalnum():
            return 1
        return 2

    def _get_searchable_track_attr(self, search_attr) -> str:
        if search_attr == "title":
            return "searchable_title"
        elif search_attr == "album":
            return "searchable_album"
        elif search_attr  == "artist":
            return "searchable_artist"
        elif search_attr == "composer":
            return "searchable_composer"
        elif search_attr == "genre":
            return "searchable_genre"
        elif search_attr == "instrument":
            return "get_instrument"
        elif search_attr  == "form":
            return "get_form"
        else:
            raise Exception(f"Invalid search attribute: {search_attr}")

    def get_playlist_sort_type(self) -> PlaylistSortType:
        if len(self.title) > 0:
            return PlaylistSortType.TITLE
        elif len(self.album) > 0:
            return PlaylistSortType.ALBUM_SHUFFLE
        elif len(self.artist) > 0:
            return PlaylistSortType.ARTIST_SHUFFLE
        elif len(self.composer) > 0:
            return PlaylistSortType.COMPOSER_SHUFFLE
        elif len(self.genre) > 0:
            return PlaylistSortType.GENRE_SHUFFLE
        elif len(self.instrument) > 0:
            return PlaylistSortType.INSTRUMENT_SHUFFLE
        elif len(self.form) > 0:
            return PlaylistSortType.FORM_SHUFFLE
        else:
            return PlaylistSortType.RANDOM

    def get_first_available_track(self):
        for track in self.results:
            if not track.is_invalid():
                return track
        return None

    def __str__(self) -> str:
        out = ""
        for _attr in ["all", "title", "album", "artist", "composer", "genre", "instrument", "form"]:
            if len(getattr(self, _attr)) > 0:
                out += _attr + ": \"" + getattr(self, _attr) + "\", "
        return out[:-2]

    def get_inferred_sort_type(self) -> PlaylistSortType:
        """Infer the best PlaylistSortType from the populated search fields."""
        return PlaylistSortType.get_largest_scope_from_search_fields(
            composer=self.composer,
            artist=self.artist,
            genre=self.genre,
            instrument=self.instrument,
            form=self.form,
            album=self.album,
        )

    def matches_no_selected_track_path(self, value: object) -> bool:
        if not isinstance(value, LibraryDataSearch):
            return False
        for key in self.__dict__.keys():
            if key not in ("results", "stored_results_count", "selected_track_path") and getattr(value, key) != getattr(self, key):
                return False
        return True

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, LibraryDataSearch):
            return False
        for key in self.__dict__.keys():
            if key not in ("results", "stored_results_count", "total_matches_count", "offset") and getattr(value, key) != getattr(self, key):
                return False
        return True

    def __hash__(self):
        hash = 0
        for key in self.__dict__.keys():
            if key not in ("results", "stored_results_count", "total_matches_count", "offset"):
                hash += getattr(self, key).__hash__()
        return hash

    def to_json(self):
        if self.stored_results_count == 0:
            self.set_stored_results_count()
        return {
            "all": self.all,
            "title": self.title,
            "album": self.album,
            "artist": self.artist,
            "composer": self.composer,
            "genre": self.genre,
            "instrument": self.instrument,
            "form": self.form,
            "selected_track_path": self.selected_track_path,
            "stored_results_count": self.stored_results_count,
            "max_results": self.max_results,
            "id": self.id,
        }

    @staticmethod
    def from_json(json):
        return LibraryDataSearch(**json)


class LibraryData:
    extension_thread_started = False
    DIRECTORIES_CACHE = {}
    MEDIA_TRACK_CACHE = {}
    all_tracks = [] # this list should be contained within the values of MEDIA_TRACK_CACHE, but may not be equivalent to the values
    get_tracks_lock = threading.Lock()
    CACHE_FILENAME = "app_media_track_cache"
    DIRECTORIES_CACHE_FILENAME = "app_directories_cache"
    DIRECTORIES_CACHE_KEY = "directories_cache"  # Keep for migration/backward compatibility
    LIBRARY_REFRESH_TIME_KEY = "library_refresh_time"
    _directory_cache_loaded = False

    @staticmethod
    def store_caches():
        # Store DIRECTORIES_CACHE in separate pickle file (not in app_info_cache JSON)
        # This prevents MemoryError when cache is large
        try:
            with open(LibraryData.DIRECTORIES_CACHE_FILENAME, "wb") as f:
                pickle.dump(LibraryData.DIRECTORIES_CACHE, f)
        except Exception as e:
            logger.error(f"Error storing directories cache: {e}")
        
        try:
            with open(LibraryData.CACHE_FILENAME, "wb") as f:
                pickle.dump(LibraryData.MEDIA_TRACK_CACHE,  f)
        except Exception as e:
            logger.error(f"Error storing media track cache: {e}")

    @staticmethod
    def load_directory_cache(force_reload=False):
        # Prevent double loading unless force_reload is True
        if LibraryData._directory_cache_loaded and not force_reload:
            return
        
        # Reset flag if forcing reload
        if force_reload:
            LibraryData._directory_cache_loaded = False
        
        # Try loading from pickle file first (new method)
        try:
            if os.path.exists(LibraryData.DIRECTORIES_CACHE_FILENAME):
                with open(LibraryData.DIRECTORIES_CACHE_FILENAME, "rb") as f:
                    LibraryData.DIRECTORIES_CACHE = pickle.load(f)
                logger.debug(f"Loaded directories cache from {LibraryData.DIRECTORIES_CACHE_FILENAME}")
                LibraryData._directory_cache_loaded = True
                return
        except Exception as e:
            logger.warning(f"Failed to load directories cache from pickle file: {e}")
        
        # Fallback: try loading from app_info_cache (for migration from old format)
        try:
            cached_data = app_info_cache.get(LibraryData.DIRECTORIES_CACHE_KEY, default_val={})
            if cached_data:
                # Make a deep copy to avoid reference issues that could cause duplication
                LibraryData.DIRECTORIES_CACHE = copy.deepcopy(cached_data)
                logger.info("Loaded directories cache from app_info_cache (migrating to pickle file)")
                # Migrate to pickle file
                try:
                    with open(LibraryData.DIRECTORIES_CACHE_FILENAME, "wb") as f:
                        pickle.dump(LibraryData.DIRECTORIES_CACHE, f)
                    # Remove from app_info_cache to free up memory and persist immediately
                    app_info_cache.set(LibraryData.DIRECTORIES_CACHE_KEY, {})
                    try:
                        app_info_cache.store()
                        logger.info("Migrated directories cache to pickle file and removed from app_info_cache")
                    except Exception as e:
                        logger.warning(f"Migrated directories cache but failed to persist removal from app_info_cache: {e}")
                except Exception as e:
                    logger.warning(f"Failed to migrate directories cache to pickle file: {e}")
                LibraryData._directory_cache_loaded = True
                return
        except Exception as e:
            logger.debug(f"Failed to load directories cache from app_info_cache: {e}")
        
        # If both fail, start with empty cache
        LibraryData.DIRECTORIES_CACHE = {}
        LibraryData._directory_cache_loaded = True
    
    @staticmethod
    def load_media_track_cache():
        try:
            with open(LibraryData.CACHE_FILENAME, "rb") as f:
                LibraryData.MEDIA_TRACK_CACHE = pickle.load(f)
        except FileNotFoundError as e:
            logger.info("No media track cache found, creating new one")

    @staticmethod
    def get_cache_update_time():
        """Get the last modification time of the media track cache file."""
        # First try to get the actual library refresh time from app_info_cache
        refresh_time_str = app_info_cache.get(LibraryData.LIBRARY_REFRESH_TIME_KEY)
        if refresh_time_str:
            try:
                return datetime.fromisoformat(refresh_time_str)
            except Exception as e:
                logger.warning(f"Error parsing library refresh time: {e}")
        
        # Fallback to file modification time if no refresh time is recorded
        if os.path.exists(LibraryData.CACHE_FILENAME):
            try:
                mtime = os.path.getmtime(LibraryData.CACHE_FILENAME)
                return datetime.fromtimestamp(mtime)
            except Exception as e:
                logger.warning(f"Error getting cache file modification time: {e}")
                return None
        return None

    @staticmethod
    def _record_library_refresh_time():
        """Record the current time as the library refresh time in app_info_cache."""
        try:
            current_time = datetime.now()
            app_info_cache.set(LibraryData.LIBRARY_REFRESH_TIME_KEY, current_time.isoformat())
        except Exception as e:
            logger.warning(f"Error recording library refresh time: {e}")

    @staticmethod
    def get_directory_files(directory, overwrite=False):
        if directory not in LibraryData.DIRECTORIES_CACHE or overwrite:
            files = glob.glob(os.path.join(directory, "**/*"), recursive = True)
            LibraryData.DIRECTORIES_CACHE[directory] = files
        else:
            files = LibraryData.DIRECTORIES_CACHE[directory]
            # Even for cached results, verify file existence
            missing_files = [f for f in files if not os.path.exists(f)]
            if missing_files:
                logger.warning(f"Found {len(missing_files)} missing files in cache for {directory}. Consider refreshing the cache.")
                files = [f for f in files if os.path.exists(f)]
                LibraryData.DIRECTORIES_CACHE[directory] = files
        return list(files)

    @staticmethod
    def get_all_filepaths(directories, overwrite=False):
        l = []
        total_media_files_count = 0
        for directory in directories:
            for f in LibraryData.get_directory_files(directory, overwrite=overwrite):
                if MediaFileType.is_media_filetype(f):
                    l += [os.path.join(directory, f)]
                    total_media_files_count += 1
                    if total_media_files_count > 100000: # TODO maybe make this limit configurable
                        break
                elif config.debug and os.path.isfile(f):
                    logger.info("Skipping non-media file: " + f)
        return l

    @staticmethod
    def get_all_tracks(overwrite=False, app_actions=None, search_status_callback=None):
        # The app_actions.update_extension_status callback is used to update the status on the main window
        # while the search_status_callback is used to update the status on the search window.
        # If both are provided, both will be called for progress updates.
        any_callback = search_status_callback or (app_actions and app_actions.update_extension_status)
        if overwrite:
            # Clear caches when overwriting to force fresh reads
            LibraryData.MEDIA_TRACK_CACHE = {}
            LibraryData.DIRECTORIES_CACHE = {}
            if app_actions is not None:
                app_actions.update_extension_status(_("Updating tracks"))
        with LibraryData.get_tracks_lock:
            if len(LibraryData.all_tracks) == 0 or overwrite:
                all_directories = config.get_all_directories()
                all_filepaths = LibraryData.get_all_filepaths(all_directories, overwrite=overwrite)
                total_files = len(all_filepaths)
                
                # Clear existing tracks if overwriting
                if overwrite:
                    LibraryData.all_tracks = []
                
                # Process files with progress updates
                for i, filepath in enumerate(all_filepaths):
                    # Call status callback every 1000 files or at the end
                    if any_callback and (i % 1000 == 999 or i == total_files - 1):
                        try:
                            message = _("Refreshing cache... ({0}/{1} files)").format(i + 1, total_files)
                            if search_status_callback:
                                search_status_callback(message)
                            if app_actions:
                                app_actions.update_extension_status(message)
                        except Exception as e:
                            logger.error(f"Error in status callback: {e}")
                    
                    track = LibraryData.get_track(filepath)
                    if track is not None:
                        LibraryData.all_tracks.append(track)
                
                # Write any collected errors to file after cache refresh
                MediaTrack.write_errors_to_file()
                
                # Record the library refresh time in app_info_cache
                LibraryData._record_library_refresh_time()
            return LibraryData.all_tracks

    @staticmethod
    def get_track(filepath):
        if filepath in LibraryData.MEDIA_TRACK_CACHE:
            return LibraryData.MEDIA_TRACK_CACHE[filepath]
        elif filepath is None:
            return None
        else:
            track = MediaTrack(filepath)
            LibraryData.MEDIA_TRACK_CACHE[filepath] = track
            return track


    def __init__(self, app_actions=None):
        LibraryData.load_directory_cache()
        self.artists = artists_data
        self.composers = composers_data
        self.forms = forms_data
        self.genres = genre_data
        self.instruments = instruments_data
        self.app_actions = app_actions
        self.data_callbacks = LibraryDataCallbacks(
            LibraryData.get_all_filepaths,
            LibraryData.get_all_tracks,
            LibraryData.get_track,
            self,
        )
        self.extension_manager = ExtensionManager(self.app_actions, self.data_callbacks)

    def do_search(self, library_data_search, overwrite=False, completion_callback=None, search_status_callback=None):
        if not isinstance(library_data_search, LibraryDataSearch):
            raise TypeError('Library data search must be of type LibraryDataSearch')
        if not library_data_search.is_valid():
            logger.warning('Invalid search query')
            return library_data_search

        logger.info(f"Searching for tracks matching query {library_data_search}")

        # Get all tracks first to ensure cache is up to date
        all_tracks = LibraryData.get_all_tracks(overwrite=overwrite, search_status_callback=search_status_callback)
        total_files = len(all_tracks)

        if search_status_callback:
            search_status_callback("Searching for tracks...")
        
        # Search through tracks
        for i, audio_track in enumerate(all_tracks):
            # Call status callback every 5000 files or at the end
            if search_status_callback and (i % 5000 == 4999 or i == total_files - 1):
                try:
                    search_status_callback(_(
                        "Searching for tracks... ({0} files searched, {1} files may be remaining)").format(i + 1, total_files - i))
                except Exception as e:
                    logger.error(f"Error in status callback: {e}")

            if library_data_search.test(audio_track) is None:
                break

        library_data_search.set_stored_results_count()
        
        # Call the completion callback if provided
        if completion_callback:
            try:
                completion_callback(library_data_search)
            except Exception as e:
                logger.error(f"Error in search callback: {e}")
                
        return library_data_search

    def resolve_track(self, media_track):
        # Find any highly similar tracks in the library to this track.
        # Especially in the case that two master directories contain the same track files,
        # we want to prioritise the track in the master directory that contains the
        # most complete information (album art, lyrics, audio quality, etc).
        pass # TODO

    def start_extensions_thread(self, initial_sleep=True, overwrite_cache=False, voice=None):
        if LibraryData.extension_thread_started:
            return
        LibraryData.get_all_tracks(overwrite=overwrite_cache, app_actions=self.app_actions)
        self.extension_manager.start_extensions_thread(initial_sleep, overwrite_cache, voice)

    def reset_extension(self, restart_thread=True):
        self.extension_manager.reset_extension(restart_thread=restart_thread)

    def is_in_library(self, title="", album="", artist="", composer="", form="", genre="", instrument=""):
        search = LibraryDataSearch(title=title, album=album, artist=artist, composer=composer, form=form, genre=genre, instrument=instrument)
        self.do_search(search)
        return len(search.results) > 0

    def find_track_by_id(self, track_id, overwrite=False):
        """
        Attempt to find a track by its ID in the title.
        Returns the track if found, None otherwise.
        """
        if not track_id:
            return None
            
        logger.info(f"Attempting to find track by ID: {track_id}")
        all_tracks = LibraryData.get_all_tracks(overwrite=overwrite)
        for track in all_tracks:
            if track_id in track.title:  # Check in original title, not searchable_title
                logger.info(f"Found track by ID: '{track.title}'")
                return track
        logger.info("No track found by ID")
        return None

    def find_track_by_fuzzy_title(self, title, overwrite=False, max_results=-1):
        """
        Attempt to find tracks using fuzzy matching on the title.
        Returns a list of matching tracks, up to max_results (or all if max_results is -1).
        
        Args:
            title: The title to search for
            overwrite: Whether to overwrite the cache when searching
            max_results: Maximum number of results to return (-1 for all matches)
        """
        if not title or len(title) < 12:
            return []
            
        logger.info(f"No exact match found for '{title}', attempting fuzzy match...")
        # Get all tracks and try fuzzy matching
        all_tracks = LibraryData.get_all_tracks(overwrite=overwrite)
        
        # Collect distances for debugging and matching
        distances = []
        matches = []
        for track in all_tracks:
            if Utils.is_similar_strings(title, track.searchable_title):
                logger.info(f"Found fuzzy match: '{track.title}' for '{title}'")
                matches.append(track)
                if max_results != -1 and len(matches) >= max_results:
                    break
            else:
                # Collect distance for debugging
                distance = Utils.string_distance(title, track.searchable_title)
                distances.append((distance, track.searchable_title, track.title))
        
        # If no matches found, show closest matches
        if not matches and distances:
            logger.info(f"No fuzzy match found. Showing closest 200 matches for '{title}':")
            # Sort by distance and take top 200 
            distances.sort(key=lambda x: x[0])
            for distance, searchable_title, title in distances[:200]:
                logger.info(f"Distance: {distance}, Searchable: '{searchable_title}', Title: '{title}'")
        
        return matches

    # Cache for compilation names
    _compilation_cache = {}
    _compilation_cache_lock = threading.Lock()

    def _clean_album_title(self, title):
        """Helper to clean album titles by removing parenthetical content at the end."""
        # Remove content in parentheses at the end of the title
        cleaned = re.sub(r'\s*\([^)]*\)\s*$', '', title)
        return cleaned.strip()

    def _get_compilation_cache_key(self, track):
        """Creates a cache key for a track's compilation info based on identifying attributes."""
        # Use attributes that should be common across a compilation
        return (track.album, track.albumartist or track.artist)

    def identify_compilation_name(self, track):
        """
        Identifies if a track is part of a compilation by analyzing album titles.
        Returns the compilation name if found, otherwise returns the original album title.
        Uses caching for efficiency.
        
        Args:
            track (MediaTrack): The track to check for compilation membership
            
        Returns:
            str: The identified compilation name or original album title
        """
        if not track or not track.album:
            return None

        # First check if track already has a compilation name
        if track.compilation_name is not None:
            return track.compilation_name

        # Check cache next
        cache_key = self._get_compilation_cache_key(track)
        with self._compilation_cache_lock:
            if cache_key in self._compilation_cache:
                return self._compilation_cache[cache_key]
                
        # Find all albums that start with similar text
        similar_albums = []
        base_album = track.album  # Use original album title for comparison
        
        # Group albums by their common prefixes
        prefix_groups = {}  # prefix -> list of albums
        
        for other_track in LibraryData.all_tracks:
            if other_track.album and other_track.album != track.album:
                # Find the longest common prefix
                common_prefix = ''
                min_len = min(len(base_album), len(other_track.album))
                for i in range(min_len):
                    if base_album[i].lower() == other_track.album[i].lower():
                        common_prefix += base_album[i]
                    else:
                        break
                        
                # If common prefix is >70% of either album title and at least 5 chars
                # Only use if it's a meaningful name (not just "The" or similar)
                if len(common_prefix) >= 5:
                    prefix_ratio = len(common_prefix) / max(len(base_album), len(other_track.album))
                    if prefix_ratio > 0.7:
                        # Add to prefix group
                        if common_prefix not in prefix_groups:
                            prefix_groups[common_prefix] = []
                        prefix_groups[common_prefix].append(other_track.album)
                        similar_albums.append(other_track.album)
                        
        # If we found similar albums, find the most common meaningful prefix
        compilation_name = None
        if similar_albums:
            # Sort prefixes by length (longest first) and number of albums in group
            sorted_prefixes = sorted(
                prefix_groups.items(), 
                key=lambda x: (-len(x[0]), -len(x[1]))  # Sort by prefix length (desc) then group size (desc)
            )
            
            # Take the longest prefix that has at least 2 albums
            for prefix, albums in sorted_prefixes:
                if len(albums) >= 1:  # We already know this album matches too
                    cleaned_prefix = self._clean_album_title(prefix.strip())
                    if len(cleaned_prefix) >= 5:
                        compilation_name = cleaned_prefix
                        break
                    
        # Check metadata hints if no compilation found
        if not compilation_name:
            if track.totaldiscs and track.totaldiscs > 1:
                compilation_name = self._clean_album_title(base_album)
            elif track.compilation:
                compilation_name = self._clean_album_title(base_album)
            else:
                compilation_name = track.album  # Use original album title
                
        # Cache the result
        with self._compilation_cache_lock:
            self._compilation_cache[cache_key] = compilation_name
            
        # Store on the track object itself for future reference
        track.compilation_name = compilation_name
            
        return compilation_name

    def identify_compilation_tracks(self, tracks):
        """
        Process a list of tracks to identify compilations.
        Updates each track's compilation name based on analysis of all library tracks.
        
        Args:
            tracks (list): List of MediaTrack objects to analyze
            
        Returns:
            dict: Mapping of track filepaths to their compilation names
        """
        compilation_map = {}
        
        # Process each track
        for track in tracks:
            try:
                compilation_name = self.identify_compilation_name(track)
                compilation_map[track.filepath] = compilation_name
            except Exception as e:
                error_msg = f"Error processing compilation for track {track.title}: {str(e)}"
                logger.warning(error_msg)
                MediaTrack.collect_error(error_msg, traceback.format_exc())
                compilation_map[track.filepath] = track.album  # Fallback to original album name
        
        # Write any errors collected during compilation identification
        MediaTrack.write_errors_to_file()
            
        return compilation_map

    # TODO hook up this method to the UI
    def ensure_album_artwork_consistency(self, track):
        """
        Ensures that all tracks in an album have consistent artwork.
        If the given track has valid artwork, it will be used as the reference.
        If not, it will look for artwork from other tracks in the same album.
        
        Args:
            track (MediaTrack): The track to check and potentially update artwork for
            
        Returns:
            bool: True if artwork was updated, False otherwise
        """
        if not track.album:
            return False
            
        # Get all tracks in the same album
        album_tracks = []
        for t in self.all_tracks:
            if t.album == track.album:
                album_tracks.append(t)
                
        if len(album_tracks) < 2:
            return False
            
        # Check if current track has artwork
        if track.artwork:
            # This track has artwork, use it as reference
            # Make a copy of the artwork bytes to avoid shared references
            ref_artwork = bytes(track.artwork)
            updated = False
            
            # Update other tracks that don't have artwork
            for t in album_tracks:
                if t != track and not t.artwork:
                    try:
                        # Update metadata with the artwork copy
                        metadata = {'artwork': ref_artwork}
                        if t.update_metadata(metadata):
                            updated = True
                    except Exception as e:
                        logger.warning(f"Failed to update artwork for {t.title}: {str(e)}")
            
            return updated
        else:
            # Current track doesn't have artwork, look for it in other tracks
            for t in album_tracks:
                if t != track and t.artwork:
                    try:
                        # Make a copy of the artwork bytes before updating
                        artwork_copy = bytes(t.artwork)
                        metadata = {'artwork': artwork_copy}
                        if track.update_metadata(metadata):
                            return True
                    except Exception as e:
                        logger.warning(f"Failed to update artwork for {track.title}: {str(e)}")
            
            return False

