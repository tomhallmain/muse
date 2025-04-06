import glob
import os
import pickle
import threading

from extensions.extension_manager import ExtensionManager
from library_data.artist import artists_data
from library_data.blacklist import blacklist
from library_data.composer import composers_data
from library_data.form import forms_data
from library_data.genre import genre_data
from library_data.instrument import instruments_data
from library_data.library_data_callbacks import LibraryDataCallbacks
from library_data.media_track import MediaTrack
from utils.app_info_cache import app_info_cache
from utils.config import config
from utils.globals import MediaFileType
from utils.utils import Utils
from utils.translations import I18N

_ = I18N._

libary_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)))


class LibraryDataSearch:
    def __init__(self, all="", title="", album="", artist="", composer="", genre="", instrument="", form="",
                 selected_track_path=None, stored_results_count=0, max_results=200):
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

        self.results = []

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
        Utils.log(f"Stored count for {self}: {self.get_readable_stored_results_count()}")

    def get_readable_stored_results_count(self) -> str:
        if self.stored_results_count > self.max_results:
            results_str = f"{self.max_results}+"
        else:
            results_str = str(self.stored_results_count)
        return _("({0} results)").format(results_str)

    def set_selected_track_path(self, track):
        assert track is not None
        self.selected_track_path = str(track.filepath)
        Utils.log(f"Set selected track path on {self}: {self.selected_track_path}")

    def test(self, audio_track):
        if len(self.results) > self.max_results:
            return None
        # NOTE - don't use _get_searchable_track_attr here because would be slower
        if len(self.all) > 0:
            for field in [audio_track.searchable_title, audio_track.searchable_artist,
                          audio_track.searchable_composer, audio_track.searchable_album,
                          audio_track.searchable_genre, audio_track.get_instrument(), audio_track.get_form()]:
                if field is not None and self.all in field:
                    self.results.append(audio_track)
                    return True
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
        for search_attr, track_attr in attrs_to_get:
            track_value = getattr(audio_track, track_attr)
            if track_attr.startswith("get_"):
                track_value = track_value()
            if track_value is None or track_value.strip() == "":
                return False
            search_value = self.__dict__[search_attr]
            if search_value not in track_value:
                return False
        self.results.append(audio_track)
        return True

    def get_results(self):
        return self.results

    def sort_results_by(self, attr=None):
        if len(self.results) == 0 or attr is None or (attr is not None and attr.strip() == ""):
            return
        if attr is None:
            for _attr in ["title", "album", "artist", "composer", "genre", "instrument", "form"]:
                if len(getattr(self, _attr)) > 0:
                    attr = self._get_searchable_track_attr(_attr)
                    break
            if attr is None:
                Utils.log("No sortable attribute in search query.")
                return
        else:
            attr = self._get_searchable_track_attr(attr)
        attr_test = getattr(self.results[0], attr)
        if callable(attr_test):
            self.results.sort(key=lambda t: (getattr(t, attr)(), t.filepath))
        else:
            def convert_none_to_str(value):
                return "" if value is None else str(value)
            self.results.sort(key=lambda t: (convert_none_to_str(getattr(t, attr)), t.filepath))

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
            if key not in ("results", "stored_results_count") and getattr(value, key) != getattr(self, key):
                return False
        return True

    def __hash__(self):
        hash = 0
        for key in self.__dict__.keys():
            if key not in ("results", "stored_results_count"):
                hash += getattr(self, key).__hash__()
        return hash

    def to_json(self):
        if self.stored_results_count == 0:
            self.stored_results_count = len(self.results)
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

    @staticmethod
    def store_caches():
        app_info_cache.set("directories_cache", LibraryData.DIRECTORIES_CACHE)
        try:
            with open("app_media_track_cache", "wb") as f:
                pickle.dump(LibraryData.MEDIA_TRACK_CACHE,  f)
        except Exception as e:
            Utils.log_red(f"Error storing media track cache: {e}")

    @staticmethod
    def load_directory_cache():
        LibraryData.DIRECTORIES_CACHE = app_info_cache.get("directories_cache", default_val={})
    
    @staticmethod
    def load_media_track_cache():
        try:
            with open("app_media_track_cache", "rb") as f:
                LibraryData.MEDIA_TRACK_CACHE = pickle.load(f)
        except FileNotFoundError as e:
            Utils.log("No media track cache found, creating new one")

    @staticmethod
    def get_directory_files(directory, overwrite=False):
        if directory not in LibraryData.DIRECTORIES_CACHE or overwrite:
            files = glob.glob(os.path.join(directory, "**/*"), recursive = True)
            LibraryData.DIRECTORIES_CACHE[directory] = files
        else:
            files = LibraryData.DIRECTORIES_CACHE[directory]
        return list(files)

    @staticmethod
    def get_all_filepaths(directories, overwrite=False):
        l = []
        count = 0
        for directory in directories:
            for f in LibraryData.get_directory_files(directory, overwrite=overwrite):
                if MediaFileType.is_media_filetype(f):
                    l += [os.path.join(directory, f)]
                    count += 1
                    if count > 100000:
                        break
                elif config.debug and os.path.isfile(f):
                    Utils.log("Skipping non-media file: " + f)
        return l

    @staticmethod
    def get_all_tracks(overwrite=False, ui_callbacks=None):
        if overwrite:
            LibraryData.MEDIA_TRACK_CACHE = {}
            if ui_callbacks is not None:
                ui_callbacks.update_extension_status(_("Updating tracks"))
        with LibraryData.get_tracks_lock:
            if len(LibraryData.all_tracks) == 0 or overwrite:
                all_directories = config.get_all_directories()
                LibraryData.all_tracks = [LibraryData.get_track(f) for f in LibraryData.get_all_filepaths(all_directories, overwrite=overwrite)]
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


    def __init__(self, ui_callbacks=None):
        LibraryData.load_directory_cache()
        self.artists = artists_data
        self.blacklist = blacklist
        self.composers = composers_data
        self.forms = forms_data
        self.genres = genre_data
        self.instruments = instruments_data
        self.ui_callbacks = ui_callbacks
        self.data_callbacks = LibraryDataCallbacks(
            LibraryData.get_all_filepaths,
            LibraryData.get_all_tracks,
            LibraryData.get_track,
            self,
        )
        self.extension_manager = ExtensionManager(self.ui_callbacks, self.data_callbacks)

    def do_search(self, library_data_search, overwrite=False):
        if not isinstance(library_data_search, LibraryDataSearch):
            raise TypeError('Library data search must be of type LibraryDataSearch')
        if not library_data_search.is_valid():
            Utils.log_yellow('Invalid search query')
            return library_data_search

        Utils.log(f"Searching for tracks matching query {library_data_search}")

        for audio_track in LibraryData.get_all_tracks(overwrite=overwrite):
            if library_data_search.test(audio_track) is None:
                break

        library_data_search.set_stored_results_count()
        return library_data_search

    def resolve_track(self, audio_track):
        # Find any highly similar tracks in the library to this track.
        # Especially in the case that two master directories contain the same track files,
        # we want to prioritise the track in the master directory that contains the
        # most complete information (album art, lyrics, audio quality, etc).
        pass # TODO

    def start_extensions_thread(self, initial_sleep=True, overwrite_cache=False, voice=None):
        if LibraryData.extension_thread_started:
            return
        LibraryData.get_all_tracks(overwrite=overwrite_cache, ui_callbacks=self.ui_callbacks)
        self.extension_manager.start_extensions_thread(initial_sleep, overwrite_cache, voice)

    def reset_extension(self, restart_thread=True):
        self.extension_manager.reset_extension(restart_thread=restart_thread)

    def is_in_library(self, title="", album="", artist="", composer="", form="", genre="", instrument=""):
        search = LibraryDataSearch(title=title, album=album, artist=artist, composer=composer, form=form, genre=genre, instrument=instrument)
        self.do_search(search)
        return len(search.results) > 0

