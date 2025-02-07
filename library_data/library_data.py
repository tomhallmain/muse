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
    def __init__(self, all="", title="", artist="", composer="", album="", genre="", instrument="", form="", max_results=200):
        self.all = all.lower()
        self.title = title.lower()
        self.artist = artist.lower()
        self.composer = composer.lower()
        self.album = album.lower()
        self.genre = genre.lower()
        self.instrument = instrument.lower()
        self.form = form.lower()
        self.max_results = max_results

        self.results = []

    def is_valid(self):
        for name in ["all", "title", "album", "artist", "composer", "genre", "instrument", "form"]:
            field = getattr(self, name)
            if field is not None and field.strip()!= "":
                print(f"{name} - \"{field}\"")
                return True
        return False

    def test(self, audio_track):
        if len(self.results) > self.max_results:
            return None
        if len(self.all) > 0:
            for field in [audio_track.searchable_title, audio_track.searchable_artist, audio_track.searchable_composer, audio_track.searchable_album]:
                if field is not None and self.all in field:
                    self.results.append(audio_track)
                    return True
        if len(self.title) > 0 and audio_track.searchable_title is not None and self.title in audio_track.searchable_title:
            self.results.append(audio_track)
            return True
        if len(self.album) > 0 and audio_track.searchable_album is not None and self.album in audio_track.searchable_album:
            self.results.append(audio_track)
            return True
        if len(self.artist) > 0 and audio_track.searchable_artist is not None and self.artist in audio_track.searchable_artist:
            self.results.append(audio_track)
            return True
        if len(self.composer) > 0 and audio_track.searchable_composer is not None and self.composer in audio_track.searchable_composer:
            self.results.append(audio_track)
            return True
        if len(self.genre) > 0 and audio_track.searchable_genre is not None and self.genre in audio_track.searchable_genre:
            self.results.append(audio_track)
            return True
        if len(self.instrument) > 0 and audio_track.get_instrumet() is not None and self.instrument in audio_track.get_instrumet().lower():
            self.results.append(audio_track)
            return True
        if len(self.form) > 0 and audio_track.get_form() is not None and self.form in audio_track.get_form().lower():
            self.results.append(audio_track)
            return True
        return False

    def get_results(self):
        return self.results

    def sort_results_by(self, attr=None):
        if len(self.results) == 0 or (attr is not None and attr.strip() == ""):
            return
        if attr is None:
            for _attr in ["title", "album", "artist", "composer", "genre", "instrument", "form"]:
                if len(getattr(self, _attr)) > 0:
                    if _attr in ["genre", "instrument", "form"]:
                        attr = "get_" + _attr
                    else:
                        attr = _attr
                    break
            if attr is None:
                Utils.log("No sortable attribute in search query.")
                return
        attr_test = getattr(self.results[0], attr)
        if callable(attr_test):
            self.results.sort(key=lambda t: (getattr(t, attr)(), t.filepath))
        else:
            self.results.sort(key=lambda t: (getattr(t, attr), t.filepath))


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
            Utils.log_red(e)

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

        for audio_track in LibraryData.get_all_tracks(overwrite=overwrite):
            if library_data_search.test(audio_track) is None:
                break

        return library_data_search

    def resolve_track(self, audio_track):
        # Find any highly similar tracks in the library to this track.
        pass # TODO

    def start_extensions_thread(self, initial_sleep=True, overwrite_cache=False, voice=None):
        if LibraryData.extension_thread_started:
            return
        LibraryData.get_all_tracks(overwrite=overwrite_cache, ui_callbacks=self.ui_callbacks)
        self.extension_manager.start_extensions_thread(initial_sleep, overwrite_cache, voice)

    def reset_extension(self):
        self.extension_manager.reset_extension()

    def is_in_library(self, title="", album="", artist="", composer="", form="", genre="", instrument=""):
        search = LibraryDataSearch(title=title, album=album, artist=artist, composer=composer, form=form, genre=genre, instrument=instrument)
        self.do_search(search)
        return len(search.results) > 0

