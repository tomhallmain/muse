import datetime
import os
import random
import subprocess

from extensions.llm import LLM
from extensions.library_extender import LibraryExtender
from extensions.soup_utils import SoupUtils
from muse.playback_config import PlaybackConfig
from muse.prompter import Prompter
from utils.app_info_cache import app_info_cache
from utils.config import config
from utils.globals import TrackAttribute, ExtensionStrategy
from utils.job_queue import JobQueue
from utils.utils import Utils
from utils.translations import I18N

_ = I18N._


class ExtensionManager:
    # This class should hold a short history of library extensions
    # with convenience methods for filing them into the right
    # directories, querying them, showing in UI, removing, etc.
    # Each new extension should be registered here

    extensions = []
    strategy = ExtensionStrategy.RANDOM
    extension_thread_delayed_complete = False
    EXTENSION_QUEUE = JobQueue("Extension queue")
    DELAYED_THREADS = []
    max_extensions_length = 100000
    minimum_allowed_duration_seconds = 120
    extension_thread = None

    @staticmethod
    def load_extensions():
        ExtensionManager.extensions = app_info_cache.get("extensions", [])
    
    @staticmethod
    def store_extensions():
        app_info_cache.set("extensions", list(ExtensionManager.extensions))

    def __init__(self, ui_callbacks, data_callbacks):
        self.llm = LLM()
        self.prompter = Prompter()
        self.extension_wait_min = 60
        self.extension_wait_expected_max = 90
        self.ui_callbacks = ui_callbacks
        self.data_callbacks = data_callbacks

    def start_extensions_thread(self, initial_sleep=True, overwrite_cache=False, voice=None):
        Utils.log('Starting extensions thread')
        if ExtensionManager.extension_thread is not None and ExtensionManager.extension_thread.is_alive():
            Utils.log('Extension thread already running')
            return
        ExtensionManager.extension_thread = Utils.start_thread(self._run_extensions, use_asyncio=False, args=(initial_sleep, voice))
        ExtensionManager.extension_thread_started = True

    def reset_extension(self, restart_thread=True):
        """Reset the extension system, optionally restarting the thread."""
        try:
            ExtensionManager.EXTENSION_QUEUE.cancel()
            closed_one_thread = False
            
            # Clean up main extension thread
            if ExtensionManager.extension_thread is not None and ExtensionManager.extension_thread.is_alive():
                # Set a flag to signal the thread to stop
                ExtensionManager.extension_thread.should_stop = True
                ExtensionManager.extension_thread.join(timeout=5.0)  # Wait up to 5 seconds
                if ExtensionManager.extension_thread.is_alive():
                    Utils.log_warning("Extension thread did not terminate gracefully")
                    # Force cleanup of the thread
                    ExtensionManager.extension_thread = None
                closed_one_thread = True
                
            # Clean up delayed threads
            for thread in ExtensionManager.DELAYED_THREADS:
                if thread.is_alive():
                    # Set a flag to signal the thread to stop
                    thread.should_stop = True
                    thread.join(timeout=5.0)  # Wait up to 5 seconds
                    if thread.is_alive():
                        Utils.log_warning("Delayed thread did not terminate gracefully")
                    closed_one_thread = True

            ExtensionManager.DELAYED_THREADS = []
            ExtensionManager.extension_thread_started = False
            if closed_one_thread:
                Utils.log("Reset extension thread.")
            if restart_thread:
                self.start_extensions_thread()
        except Exception as e:
            Utils.log_red(f"Error during extension reset: {str(e)}")
            # Ensure we don't leave the system in an inconsistent state
            ExtensionManager.extension_thread = None
            ExtensionManager.DELAYED_THREADS = []
            ExtensionManager.extension_thread_started = False

    def get_extension_sleep_time(self, min_value, max_value):
        current_track = PlaybackConfig.get_playing_track()
        if current_track is not None and current_track.get_track_length() > max_value:
            length = int(current_track.get_track_length())
            min_value += length
            max_value += length
            Utils.log("Increased extension sleep time for long track, new range: {0}min-{1}min".format(min_value/60, max_value/60))
        return random.randint(min_value, max_value)


    def _run_extensions(self, initial_sleep=True, voice=None):
        if initial_sleep:
            sleep_time_seconds = random.randint(200, 1200)
            check_cadence = 150
            while sleep_time_seconds > 0:
                sleep_time_seconds -= check_cadence
                if sleep_time_seconds <= 0:
                    break
                if self.ui_callbacks is not None:
                    self.ui_callbacks.update_extension_status(_("Extension thread waiting for {0} minutes").format(round(float(sleep_time_seconds) / 60)))
                Utils.long_sleep(check_cadence, "extension thread", total=sleep_time_seconds, print_cadence=180)
            Utils.log("Extension thread woke up")
        while True:
            self._extend_by_random_attr(voice)
            ExtensionManager.extension_thread_delayed_complete = False
            sleep_time_minutes = int(self.get_extension_sleep_time(3600, 5400) / 60)
            check_cadence = 1
            while sleep_time_minutes > 0:
                sleep_time_minutes -= check_cadence
                if sleep_time_minutes <= 0:
                    break
                if ExtensionManager.extension_thread_delayed_complete and self.ui_callbacks is not None:
                    self.ui_callbacks.update_extension_status(_("Extension thread waiting for {0} minutes").format(sleep_time_minutes))
                Utils.long_sleep(check_cadence * 60, "extension thread", total=sleep_time_minutes * 60, print_cadence=180)

    def _extend_by_random_attr(self, voice=None):
        extendible_attrs = {
            TrackAttribute.ARTIST: lambda: random.choice(self.data_callbacks.instance.artists.get_artist_names()),
            TrackAttribute.COMPOSER: lambda: random.choice(self.data_callbacks.instance.composers.get_composer_names()),
            TrackAttribute.GENRE: lambda: random.choice(self.data_callbacks.instance.genres.get_genre_names()),
            TrackAttribute.FORM: lambda: random.choice(self.data_callbacks.instance.forms.get_form_names()),
            TrackAttribute.INSTRUMENT: lambda: random.choice(self.data_callbacks.instance.instruments.get_instrument_names()),
        }
        if len(self.data_callbacks.instance.artists.get_artist_names()) == 0:
            del extendible_attrs[TrackAttribute.ARTIST]
        if len(self.data_callbacks.instance.composers.get_composer_names()) == 0:
            del extendible_attrs[TrackAttribute.COMPOSER]
        if len(self.data_callbacks.instance.genres.get_genre_names()) == 0:
            del extendible_attrs[TrackAttribute.GENRE]
        if len(self.data_callbacks.instance.forms.get_form_names()) == 0:
            del extendible_attrs[TrackAttribute.FORM]
        if len(self.data_callbacks.instance.instruments.get_instrument_names()) == 0:
            del extendible_attrs[TrackAttribute.INSTRUMENT]
        if len(extendible_attrs) == 0:
            raise Exception("No extensible attributes found!")
        attr = random.choice(list(extendible_attrs.keys()))
        value = extendible_attrs[attr]()

        Utils.log(f'Extending by random {attr}: {value}')
        if voice is not None:
            muse_to_say = _("Coming up soon, we'll be listening to a new track from the {0} {1}.").format(attr.get_translation(), value)
            voice.prepare_to_say(muse_to_say, save_for_last=True)
        self.extend(value=value, attr=attr, strict=True)

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

        # Set up the next thread to run another extension
        next_job_args = self.EXTENSION_QUEUE.take()
        if next_job_args is not None:
            Utils.long_sleep(300, "extension thread job wait")
            Utils.start_thread(self._extend, use_asyncio=False, args=next_job_args)
        else:
            self.EXTENSION_QUEUE.job_running = False

    def extend(self, value="", attr=None, strict=False):
        args=[value, attr, strict]
        if self.EXTENSION_QUEUE.has_pending() or self.EXTENSION_QUEUE.job_running:
            self.EXTENSION_QUEUE.add(args)
        else:
            self.EXTENSION_QUEUE.job_running = True
            print(args)
            Utils.start_thread(self._extend, use_asyncio=False, args=args)

    def extend_by_title(self, title, strict=False):
        self._simple("track title: \"" + title + "\"", attr=TrackAttribute.TITLE, strict=(title if strict else None))

    def extend_by_album(self, album, strict=False):
        self._simple("album title: \"" + album + "\"", attr=TrackAttribute.ALBUM, strict=(album if strict else None))

    def extend_by_artist(self, artist, strict=False):
        prompt = self.prompter.get_prompt("search_artist")
        result = self.llm.generate_json_get_value(prompt.replace("ARTIST", artist), "search_query")
        query = result.response if result else artist
        self._simple(query, attr=TrackAttribute.ARTIST, strict=(artist if strict else None))

    def extend_by_composer(self, composer_name):
        composer = self.data_callbacks.instance.composers.get_data(composer_name)
        self._simple("music composed by " + composer_name, attr=TrackAttribute.COMPOSER, strict=composer)

    def extend_by_genre(self, genre, strict=False):
        prompt = self.prompter.get_prompt("search_genre")
        result = self.llm.generate_json_get_value(prompt.replace("GENRE", genre), "search_query")
        query = result.response if result else genre
        self._simple(query, attr=TrackAttribute.GENRE, strict=(genre if strict else None))

    def extend_by_instrument(self, instrument, genre="Classical", strict=False):
        prompt = self.prompter.get_prompt("search_instrument")
        prompt = prompt.replace("INSTRUMENT", instrument).replace("GENRE", genre)
        result = self.llm.generate_json_get_value(prompt, "search_query")
        query = result.response if result else f"{instrument} {genre}"
        self._simple(query, attr=TrackAttribute.INSTRUMENT, strict=(instrument if strict else None))

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
                   or b.xfgi(self.minimum_allowed_duration_seconds)
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
                self._simple(q, m=m*2, depth=depth+1, attr=attr, strict=strict)
                return
            name = SoupUtils.clean_html(b.n)
            Utils.log_yellow(f"Selected option: {name} - {b.x()}")
            Utils.log(b.d)
            self.delayed(b, attr, s=q)
        else:
            if r is None:
                Utils.log_yellow("Tracking too many requests.")
            else:
                Utils.log_yellow(f'No results found for "{q}"')

    def is_in_library(self, b):
        if b.w is None or b.w.strip() == "":
            raise Exception("No ID found: " + str(b.x()))
        return self.data_callbacks.instance.is_in_library(title=b.w.strip())

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
        return strict.strip().lower() in b.n.lower() or strict.strip().lower() in b.d.lower()

    def _is_blacklisted(self, b):
        item = self.data_callbacks.instance.blacklist.test(SoupUtils.clean_html(b.n))
        if item is not None:
            Utils.log_yellow(f"Blacklisted: {item} ({b.n})")
            return True
        item = self.data_callbacks.instance.blacklist.test(b.d)
        if item is not None:
            Utils.log_yellow(f"Blacklisted: {item}\n{b.d}")
            return True
        return False

    def delayed(self, b, attr, s):
        thread = Utils.start_thread(self._delayed, use_asyncio=False, args=[b, attr, s,])
        ExtensionManager.DELAYED_THREADS.append(thread)

    def _delayed(self, b, attr, s, sleep=True):
        if sleep:
            time_seconds = self.get_extension_sleep_time(1000, 2000)
            check_cadence = 150
            while time_seconds > 0:
                time_seconds -= check_cadence
                if time_seconds <= 0:
                    break
                if self.ui_callbacks is not None:
                    self.ui_callbacks.update_extension_status(_("Extension \"{0}\" waiting for {1} minutes").format(SoupUtils.clean_html(b.n), round(float(time_seconds) / 60)))
                Utils.long_sleep(check_cadence, "Extension thread delay wait", total=time_seconds, print_cadence=180)
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
                    ExtensionManager.extension_thread_delayed_complete = True
                    raise Exception(f"No output found {b}")
            else:
                _f = _e
        obj = dict(b.u)
        obj["filename"] = _f
        obj["date"] = datetime.datetime.now().isoformat()
        obj["strategy"] = ExtensionManager.strategy.name
        obj["track_attr"] = attr.name
        obj["search_query"] = s
        ExtensionManager.extensions.append(obj)
        PlaybackConfig.assign_extension(_f)
        if self.ui_callbacks is not None:
            self.ui_callbacks.update_extension_status(_("Extension \"{0}\" ready").format(SoupUtils.clean_html(b.n)))
            # TODO update ExtensionsWindow as well if it's open
        ExtensionManager.extension_thread_delayed_complete = True

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
