from enum import Enum
import glob
import os
import pickle
import random
import subprocess
import threading

from extensions.library_extender import LibraryExtender
from extensions.soup_utils import SoupUtils
from library_data.blacklist import blacklist
from library_data.composer import composers_data
from library_data.library_data_callbacks import LibraryDataCallbacks
from library_data.media_track import MediaTrack
from muse.playback_config import PlaybackConfig
from utils.app_info_cache import app_info_cache
from utils.config import config
from utils.globals import MediaFileType
from utils.job_queue import JobQueue
from utils.utils import Utils
from utils.translations import I18N

_ = I18N._

libary_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)))


class LibraryDataSearch:
    def __init__(self, all="", title="", artist="", composer="", album="", genre="", instrument="", max_results=200):
        self.all = all.lower()
        self.title = title.lower()
        self.artist = artist.lower()
        self.composer = composer.lower()
        self.album = album.lower()
        self.genre = genre.lower()
        self.instrument = instrument.lower()
        self.max_results = max_results

        self.results = []

    def is_valid(self):
        for name in ["all", "title", "artist", "composer", "album", "genre", "instrument"]:
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
        if len(self.artist) > 0 and audio_track.searchable_artist is not None and self.artist in audio_track.searchable_artist:
            self.results.append(audio_track)
            return True
        if len(self.composer) > 0 and audio_track.searchable_composer is not None and self.composer in audio_track.searchable_composer:
            self.results.append(audio_track)
            return True
        if len(self.album) > 0 and audio_track.searchable_album is not None and self.album in audio_track.searchable_album:
            self.results.append(audio_track)
            return True
        if len(self.genre) > 0 and audio_track.searchable_genre is not None and self.genre in audio_track.searchable_genre:
            self.results.append(audio_track)
            return True
        return False

    def get_results(self):
        return self.results


class TrackAttribute(Enum):
    TITLE = "title"
    ALBUM = "album"
    ARTIST = "artist"
    COMPOSER = "composer"
    GENRE = "genre"
    INSTRUMENT = "instrument"


class LibraryData:
    extension_thread_started = False
    extension_thread_delayed_complete = False
    DIRECTORIES_CACHE = {}
    MEDIA_TRACK_CACHE = {}
    all_tracks = [] # this list should be contained within the values of MEDIA_TRACK_CACHE, but may not be equivalent to the values
    EXTENSION_QUEUE = JobQueue("Extension queue")
    DELAYED_THREADS = []
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
        return files

    @staticmethod
    def get_all_filepaths(directories):
        l = []
        count = 0
        for directory in directories:
            for f in LibraryData.get_directory_files(directory):
                if MediaFileType.is_media_filetype(f):
                    l += [os.path.join(directory, f)]
                    count += 1
                    if count > 100000:
                        break
                elif config.debug and os.path.isfile(f):
                    Utils.log("Skipping non-media file: " + f)
        return l

    @staticmethod
    def get_all_tracks():
        with LibraryData.get_tracks_lock:
            if len(LibraryData.all_tracks) == 0:
                all_directories = config.get_all_directories()
                LibraryData.all_tracks = [LibraryData.get_track(f) for f in LibraryData.get_all_filepaths(all_directories)]
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
        self.composers = composers_data
        self.ui_callbacks = ui_callbacks
        self.data_callbacks = LibraryDataCallbacks(
            LibraryData.get_all_filepaths,
            LibraryData.get_all_tracks,
            LibraryData.get_track,
        )

    def do_search(self, library_data_search):
        if not isinstance(library_data_search, LibraryDataSearch):
            raise TypeError('Library data search must be of type LibraryDataSearch')
        if not library_data_search.is_valid():
            Utils.log_yellow('Invalid search query')
            return library_data_search

        for audio_track in LibraryData.get_all_tracks():
            if library_data_search.test(audio_track) is None:
                break

        return library_data_search

    def resolve_track(self, audio_track):
        # Find any highly similar tracks in the library to this track.
        pass

    def start_extensions_thread(self, initial_sleep=True):
        if LibraryData.extension_thread_started:
            return
        Utils.log('Starting extensions thread')
        LibraryData.get_all_tracks()
        Utils.start_thread(self._run_extensions, use_asyncio=False, args=(initial_sleep,))
        LibraryData.extension_thread_started = True

    def reset_extension(self):
        LibraryData.EXTENSION_QUEUE.cancel()
        closed_one_thread = False
        for thread in LibraryData.DELAYED_THREADS:
            thread.terminate()
            thread.join()
            closed_one_thread = True

        LibraryData.DELAYED_THREADS = []
        LibraryData.extension_thread_started = False
        if closed_one_thread:
            Utils.log("Reset extension thread.")
        self.start_extensions_thread()

    def _run_extensions(self, initial_sleep=True):
        if initial_sleep:
            sleep_time_seconds = random.randint(200, 1200)
            check_cadence = 150
            while sleep_time_seconds > 0:
                sleep_time_seconds -= check_cadence
                if sleep_time_seconds <= 0:
                    break
                if self.ui_callbacks is not None:
                    self.ui_callbacks.update_extension_status(_("Extension thread waiting for {0} minutes").format(round(float(sleep_time_seconds) / 60)))
                Utils.long_sleep(check_cadence, "extension thread")
        while True:
            self._extend_by_random_composer()
            LibraryData.extension_thread_delayed_complete = False
            sleep_time_minutes = random.randint(60, 90)
            check_cadence = 2
            while sleep_time_minutes > 0:
                sleep_time_minutes -= check_cadence
                if sleep_time_minutes <= 0:
                    break
                if LibraryData.extension_thread_delayed_complete and self.ui_callbacks is not None:
                    self.ui_callbacks.update_extension_status(_("Extension thread waiting for {0} minutes").format(sleep_time_minutes))
                Utils.long_sleep(check_cadence * 60, "extension thread")

    def _extend_randomly(self):
        Utils.log('Extending randomly')
        pass

    def _extend_by_random_composer(self):
        composer = random.choice(composers_data.get_composer_names())
        Utils.log('Extending by random composer: ' + composer)
        self.extend(value=composer, attr=TrackAttribute.COMPOSER)

    def _extend(self, value="", attr=None, strict=False):
        if attr == TrackAttribute.TITLE:
            self.extend_by_title(value, strict=strict)
        if attr == TrackAttribute.ALBUM:
            self.extend_by_album(value, strict=strict)
        if attr == TrackAttribute.ARTIST:
            self.extend_by_artist(value, strict=strict)
        if attr == TrackAttribute.COMPOSER:
            self.extend_by_composer(value)
        if attr == TrackAttribute.GENRE:
            self.extend_by_genre(value, strict=strict)
        if attr == TrackAttribute.INSTRUMENT:
            self.extend_by_instrument(value, strict=strict)
        next_job_args = self.EXTENSION_QUEUE.take()
        if next_job_args is not None:
            Utils.long_sleep(300, "extension thread job wait")
            Utils.start_thread(self._extend, use_asyncio=False, args=next_job_args)
        else:
            self.EXTENSION_QUEUE.job_running = False

    def extend(self, value="", attr=None, strict=False):
        args=(value, attr, strict)
        if self.EXTENSION_QUEUE.has_pending() or self.EXTENSION_QUEUE.job_running:
            self.EXTENSION_QUEUE.add(args)
        else:
            self.EXTENSION_QUEUE.job_running = True
            Utils.start_thread(self._extend, use_asyncio=False, args=args)

    def extend_by_title(self, title, strict=False):
        self._simple(title, attr=TrackAttribute.TITLE, strict=None)

    def extend_by_album(self, album, strict=False):
        self._simple(album, attr=TrackAttribute.ALBUM, strict=None)

    def extend_by_artist(self, artist, strict=False):
        # TODO
        self._simple("music by " + artist, attr=TrackAttribute.ARTIST, strict=None)

    def extend_by_composer(self, composer_name):
        composer = composers_data.get_data(composer_name)
        # TODO
        self._simple("music by " + composer_name, attr=TrackAttribute.COMPOSER, strict=composer)

    def extend_by_genre(self, genre, strict=False):
        # TODO
        self._simple("music from the genre " + genre, attr=TrackAttribute.GENRE, strict=None)

    def extend_by_instrument(self, instrument, strict=False):
        self._simple("music for the " + instrument, attr=TrackAttribute.INSTRUMENT, strict=None)

    def _simple(self, q, m=6, depth=0, attr=None, strict=None):
        r = self.s(q, m)
        if r is not None and r.i():
            a = r.o()
            b = random.choice(a)
            counter = 0
            failed = False
            for i in a:
                Utils.log("Extension option: " + i.n + " " + i.x())
            while (b is None or b.y
                    or self.is_in_library(b)
                    or (strict and self._strict_test(b, attr, strict))
                    or self._is_blacklisted(b)):
                counter += 1
                b = random.choice(a)
                if counter > 10:
                    failed = True
                    break
            if failed:
                if depth > 4:
                    raise Exception(f"Unable to find valid results: {q}")
                self._simple(q, m=m*2, depth=depth+1)
                return
            name = SoupUtils.clean_html(b.n)
            Utils.log_yellow(f"Selected option: {name} - {b.x()}")
            Utils.log(b.d)
            Utils.start_thread(self._delayed, use_asyncio=False, args=(b,))
        else:
            if r is None:
                Utils.log_yellow("Tracking too many requests.")
            else:
                Utils.log_yellow(f'No results found for "{q}"')

    def is_in_library(self, b):
        if b.w is None or b.w.strip() == "":
            raise Exception("No ID found: " + str(b.x()))
        search = LibraryDataSearch(title=b.w)
        self.do_search(search)
        return len(search.results) > 0

    def _strict_test(self, b, attr, strict):
        if attr is None or strict is None:
            raise Exception("No strict test attribute specified")
        if attr == TrackAttribute.COMPOSER:
            for indicator in strict.indicators:
                if indicator.lower() in b.n.lower() or indicator.lower() in b.d.lower():
                    return False
            if "biography" in b.n.lower() or "biography" in b.d.lower():
                return False
        return True

    def _is_blacklisted(self, b):
        item = blacklist.test(SoupUtils.clean_html(b.n))
        if item is not None:
            Utils.log_yellow(f"Blacklisted: {item} ({b.n})")
            return True
        item = blacklist.test(b.d)
        if item is not None:
            Utils.log_yellow(f"Blacklisted: {item}\n{b.d}")
            return True
        return False

    def delayed(self, b):
        thread = Utils.start_thread(self._delayed, use_asyncio=False, args=(b,))
        LibraryData.DELAYED_THREADS.append(thread)

    def _delayed(self, b, sleep=True):
        if sleep:
            time_seconds = random.randint(1000, 2000)
            check_cadence = 150
            while time_seconds > 0:
                time_seconds -= check_cadence
                if time_seconds <= 0:
                    break
                if self.ui_callbacks is not None:
                    self.ui_callbacks.update_extension_status(_("Extension \"{0}\" waiting for {1} minutes").format(SoupUtils.clean_html(b.n), round(float(time_seconds) / 60)))
                Utils.long_sleep(check_cadence, "Extension thread delay wait")
        a = b.da(g=config.directories[0])
        e1 = " Destination: "
        Utils.log_yellow(f"extending delayed: {a}")
        e = "[download]"
        p = subprocess.Popen(a, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        o, __ = p.communicate()
        f = "[ExtractAudio]"
        _e = None
        _f = None
        for line in o.split("\n"):
            print(line)
            if line.startswith(e + e1):
                _e = line[len(e + e1):]
            if line.startswith(f + e1):
                _f = line[len(f + e1):]
        if _f is None or not os.path.exists(_f):
            Utils.log_yellow("F was not found" if _f is None else "F was found but invalid: " + _f)
            if _e is None or not os.path.exists(_e):
                Utils.log_yellow("E was not found" if _e is None else "E was found but invalid: " + _e)
                close_match = self.check_dir_for_close_match(_e)
                if close_match is not None:
                    _f = close_match
                else:
                    LibraryData.extension_thread_delayed_complete = True
                    raise Exception(f"No output found {b}")
            else:
                _f = _e
        PlaybackConfig.assign_extension(_f)
        if self.ui_callbacks is not None:
            self.ui_callbacks.update_extension_status(_("Extension \"{0}\" ready").format(SoupUtils.clean_html(b.n)))
        LibraryData.extension_thread_delayed_complete = True

    def check_dir_for_close_match(self, t):
        if t is None or t.strip() == "":
            return None
        _dir = os.path.abspath(config.directories[0])
        for f in os.listdir(_dir):
            filepath = os.path.join(_dir, f)
            if os.path.isfile(filepath) and Utils.is_similar_strings(filepath, t, True):
                Utils.log(f"Found close match: {f}")
                return filepath
        return None

    def s(self, q, x=1):
        Utils.log(f"s: {q}")
        return LibraryExtender.isyMOLB_(q, m=x)

