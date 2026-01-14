import datetime
import os
import random
import re
import subprocess
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Union

from extensions.llm import LLM, LLMResponseException
from extensions.library_extender import LibraryExtender
from extensions.soup_utils import SoupUtils
from muse.playback_config import PlaybackConfig
from muse.prompter import Prompter
from utils.app_info_cache import app_info_cache
from utils.config import config
from utils.globals import TrackAttribute, ExtensionStrategy
from utils.job_queue import JobQueue
from utils.logging_setup import get_logger
from utils.utils import Utils
from utils.translations import I18N

if TYPE_CHECKING:
    from library_data.composer import Composer
    from library_data.media_track import MediaTrack

_ = I18N._

# Get logger for this module
logger = get_logger(__name__)

class ExtensionManager:
    # This class should hold a short history of library extensions
    # with convenience methods for filing them into the right
    # directories, querying them, showing in UI, removing, etc.
    # Each new extension should be registered here

    extensions: List[Dict[str, Any]] = []
    strategy: ExtensionStrategy = ExtensionStrategy.RANDOM
    extension_thread_delayed_complete: bool = False
    EXTENSION_QUEUE: JobQueue = JobQueue("Extension queue")
    DELAYED_THREADS: List[Any] = []
    max_extensions_length: int = 100000
    minimum_allowed_duration_seconds: int = 120
    extension_thread: Optional[Any] = None

    @staticmethod
    def load_extensions() -> None:
        ExtensionManager.extensions = app_info_cache.get("extensions", [])
        # Load strategy from cache, defaulting to RANDOM if not found
        strategy_name = app_info_cache.get("extension_strategy", "RANDOM")
        try:
            ExtensionManager.strategy = ExtensionStrategy[strategy_name]
        except KeyError:
            ExtensionManager.strategy = ExtensionStrategy.RANDOM
            logger.warning(f"Invalid strategy '{strategy_name}' found in cache, defaulting to RANDOM")
    
    @staticmethod
    def store_extensions() -> None:
        app_info_cache.set("extensions", list(ExtensionManager.extensions))
        app_info_cache.set("extension_strategy", ExtensionManager.strategy.name)

    def __init__(self, ui_callbacks: Optional[Any], data_callbacks: Optional[Any]) -> None:
        self.llm = LLM()
        self.prompter = Prompter()
        self.extension_wait_min: int = 60
        self.extension_wait_expected_max: int = 90
        self.ui_callbacks = ui_callbacks
        self.data_callbacks = data_callbacks

    def start_extensions_thread(self, initial_sleep: bool = True, overwrite_cache: bool = False, voice: Optional[Any] = None) -> None:
        logger.info('Starting extensions thread')
        if ExtensionManager.extension_thread is not None and ExtensionManager.extension_thread.is_alive():
            logger.info('Extension thread already running')
            return
        ExtensionManager.extension_thread = Utils.start_thread(self._run_extensions, use_asyncio=False, args=(initial_sleep, voice))
        ExtensionManager.extension_thread_started = True

    def reset_extension(self, restart_thread: bool = True) -> None:
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
                    logger.warning("Extension thread did not terminate gracefully")
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
                        logger.warning("Delayed thread did not terminate gracefully")
                    closed_one_thread = True

            ExtensionManager.DELAYED_THREADS = []
            ExtensionManager.extension_thread_started = False
            if closed_one_thread:
                logger.info("Reset extension thread.")
            if restart_thread:
                self.start_extensions_thread()
        except Exception as e:
            logger.error(f"Error during extension reset: {str(e)}")
            # Ensure we don't leave the system in an inconsistent state
            ExtensionManager.extension_thread = None
            ExtensionManager.DELAYED_THREADS = []
            ExtensionManager.extension_thread_started = False

    def get_extension_sleep_time(self, min_value: int, max_value: int) -> int:
        current_track = PlaybackConfig.get_playing_track()
        if current_track is not None and current_track.get_track_length() > max_value:
            length = int(current_track.get_track_length())
            min_value += length
            max_value += length
            logger.info("Increased extension sleep time for long track, new range: {0}min-{1}min".format(min_value/60, max_value/60))
        return random.randint(min_value, max_value)

    def _run_extensions(self, initial_sleep: bool = True, voice: Optional[Any] = None) -> None:
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
            logger.info("Extension thread woke up")
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

    def _extend_by_random_attr(self, voice: Optional[Any] = None) -> None:
        extendible_attrs: Dict[TrackAttribute, Callable[[], str]] = {
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

        logger.info(f'Extending by random {attr}: {value}')
        if voice is not None:
            muse_to_say = _("Coming up soon, we'll be listening to a new track from the {0} {1}.").format(attr.get_translation(), value)
            voice.prepare_to_say(muse_to_say, save_for_last=True)
        self.extend(value=value, attr=attr, strict=True)

    def _extend(self, value: str = "", attr: Optional[TrackAttribute] = None, strict: bool = False) -> None:
        try:
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
        except Exception as e:
            error_msg = _("Extension failed for {0} with value '{1}': {2}").format(
                attr.get_translation() if attr is not None else "", value, str(e))
            logger.warning(error_msg)
            if self.ui_callbacks is not None:
                self.ui_callbacks.update_extension_status(error_msg)
            ExtensionManager.extension_thread_delayed_complete = True
            # Don't re-raise the exception, let the thread continue

        # Set up the next thread to run another extension
        next_job_args = self.EXTENSION_QUEUE.take()
        if next_job_args is not None:
            Utils.long_sleep(300, "extension thread job wait")
            Utils.start_thread(self._extend, use_asyncio=False, args=next_job_args)
        else:
            self.EXTENSION_QUEUE.job_running = False

    def extend(self, value: str = "", attr: Optional[TrackAttribute] = None, strict: bool = False) -> None:
        args = [value, attr, strict]
        if self.EXTENSION_QUEUE.has_pending() or self.EXTENSION_QUEUE.job_running:
            self.EXTENSION_QUEUE.add(args)
        else:
            self.EXTENSION_QUEUE.job_running = True
            print(args)
            Utils.start_thread(self._extend, use_asyncio=False, args=args)

    def extend_by_title(self, title: str, strict: bool = False) -> None:
        self._simple("track title: \"" + title + "\"", attr=TrackAttribute.TITLE, strict=(title if strict else None))

    def extend_by_album(self, album: str, strict: bool = False) -> None:
        self._simple("album title: \"" + album + "\"", attr=TrackAttribute.ALBUM, strict=(album if strict else None))

    def extend_by_artist(self, artist: str, strict: bool = False) -> None:
        # Skip LLM call if it's been failing
        if self.llm.is_failing():
            query = artist
        else:
            try:
                prompt = self.prompter.get_prompt("search_artist")
                result = self.llm.generate_json_get_value(prompt.replace("ARTIST", artist), "search_query")
                query = result.response if result else artist
            except LLMResponseException as e:
                logger.warning(f"LLM call failed for artist '{artist}', falling back to simple query: {e}")
                query = artist
        self._simple(query, attr=TrackAttribute.ARTIST, strict=(artist if strict else None))

    def extend_by_composer(self, composer_name: str) -> None:
        composer = self.data_callbacks.instance.composers.get_data(composer_name)
        self._simple("music composed by " + composer_name, attr=TrackAttribute.COMPOSER, strict=composer)

    def extend_by_genre(self, genre: str, strict: bool = False) -> None:
        # Skip LLM call if it's been failing
        if self.llm.is_failing():
            query = genre
        else:
            try:
                prompt = self.prompter.get_prompt("search_genre")
                result = self.llm.generate_json_get_value(prompt.replace("GENRE", genre), "search_query")
                query = result.response if result else genre
            except LLMResponseException as e:
                logger.warning(f"LLM call failed for genre '{genre}', falling back to simple query: {e}")
                query = genre
        self._simple(query, attr=TrackAttribute.GENRE, strict=(genre if strict else None))

    def extend_by_instrument(self, instrument: str, genre: str = "Classical", strict: bool = False) -> None:
        # Skip LLM call if it's been failing
        if self.llm.is_failing():
            query = f"{instrument} {genre}"
        else:
            try:
                prompt = self.prompter.get_prompt("search_instrument")
                prompt = prompt.replace("INSTRUMENT", instrument).replace("GENRE", genre)
                result = self.llm.generate_json_get_value(prompt, "search_query")
                query = result.response if result else f"{instrument} {genre}"
            except LLMResponseException as e:
                logger.warning(f"LLM call failed for instrument '{instrument}' with genre '{genre}', falling back to simple query: {e}")
                query = f"{instrument} {genre}"
        self._simple(query, attr=TrackAttribute.INSTRUMENT, strict=(instrument if strict else None))

    def _simple(self, q: str, m: int = 6, depth: int = 0, attr: Optional[TrackAttribute] = None, strict: Optional[Union[str, 'Composer']] = None) -> None:
        r = self.s(q, m)
        if r is not None and r.i():
            a = r.o()
            for i in a:
                i.n = SoupUtils.clean_html(i.n)
                i.d = SoupUtils.clean_html(i.d)
                i.m = self._m(q, i.n)
                logger.info(f"Extension option: {i.n} {i.x()}")            
            opts = []
            shuffled = a.copy()
            random.shuffle(shuffled)
            # Slightly bias toward higher quality results
            for i in range(len(shuffled) - 1):
                if shuffled[i].ggi() < shuffled[i + 1].ggi() and random.random() < 0.3:
                    shuffled[i], shuffled[i + 1] = shuffled[i + 1], shuffled[i]
            for b in shuffled:
                if not self._bad_option(b, strict, attr):
                    opts.append(b)
                    if len(opts) >= 2:  # Found two valid options
                        break
            if len(opts) == 0:
                if depth > 4:
                    logger.error(f"Unable to find valid results after multiple attempts: {q}")
                    raise Exception(f"Unable to find valid results: {q}")
                self._simple(q, m=m*2, depth=depth+1, attr=attr, strict=strict)
                return
            b = opts[0]
            b1 = opts[1] if len(opts) > 1 else None
            logger.warning(f"Selected option: {b.n} - {b.x()}")
            if b1:
                logger.info(f"Backup option: {b1.n} - {b1.x()}")
            logger.info(b.d)
            self.delayed(b, attr, s=q, b1=b1)
        else:
            if r is None:
                logger.warning("Tracking too many requests.")
            else:
                logger.warning(f'No results found for "{q}"')

    def _bad_option(self, b, strict: bool = False, attr: Optional[TrackAttribute] = None) -> bool:
        return (b is None or b.y
                or b.xfgi(self.minimum_allowed_duration_seconds)
                or self.is_in_library(b)
                or (strict and self._strict_test(b, attr, strict))
                or self._is_blacklisted(b)
                or (Utils.contains_emoji(b.n) and random.random() > 0.05)  # 95% chance to skip emoji titles
                or self._is_compilation(b))  # Skip compilation albums/playlists

    def is_in_library(self, b) -> bool:
        if b.w is None or b.w.strip() == "":
            raise Exception("No ID found: " + str(b.x()))
        return self.data_callbacks.instance.is_in_library(title=b.w.strip())

    def _strict_test(self, b, attr: Optional[TrackAttribute], strict: Optional[Union[str, 'Composer']]) -> bool:
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

    def _is_blacklisted(self, b) -> bool:
        from library_data.blacklist import Blacklist
        item = Blacklist.get_violation_item(b.n)
        if item is not None:
            logger.warning(f"Blacklisted: {item.string} ({b.n})")
            return True
        item = Blacklist.get_violation_item(b.d)
        if item is not None:
            logger.warning(f"Blacklisted: {item.string}\n{b.d}")
            return True
        return False

    def _is_compilation(self, b) -> bool:
        """
        Detect compilation albums/playlists that are typically bad choices for single track selection.
        Example: "50 Most Beautiful X"
        """
        if not hasattr(b, 'n') or b.n is None:
            return False
        
        name = b.n.lower()
        description = b.d.lower() if hasattr(b, 'd') and b.d else ""
        
        # Compilation patterns to detect
        compilation_patterns = [
            # Number + "Most" patterns (e.g., "50 Most Beautiful", "100 Most")
            r'\d+\s+most\s+(beautiful|greatest|best|popular|famous|essential)',
            # "Best of" patterns
            r'best\s+of\s+',
            # "Essential" patterns
            r'essential\s+(classical|music|collection)',
            # "Greatest Hits" patterns
            r'greatest\s+hits',
            # "Collection" patterns (when it's clearly a compilation)
            r'(the\s+)?(complete|definitive|ultimate|premium)\s+collection',
            # "Top X" patterns
            r'top\s+\d+',
            # "Ultimate" patterns
            r'ultimate\s+(collection|anthology|best)',
            # "Anthology" patterns
            r'anthology',
            # "Compilation" patterns
            r'compilation',
            # "Various Artists" or similar
            r'various\s+artists',
        ]
        
        # Check name and description for compilation patterns
        text_to_check = f"{name} {description}".lower()
        for pattern in compilation_patterns:
            if re.search(pattern, text_to_check, re.IGNORECASE):
                logger.warning(f"Detected compilation by pattern /{pattern}/: {b.n}")
                return True
        
        return False

    def delayed(self, b, attr: Optional[TrackAttribute], s: str, b1=None) -> None:
        thread = Utils.start_thread(self._delayed, use_asyncio=False, args=[b, attr, s, b1])
        ExtensionManager.DELAYED_THREADS.append(thread)

    def _delayed(self, b, attr: Optional[TrackAttribute], s: str, b1=None, sleep: bool = True) -> None:
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

        try:
            f, b = self._a(b, b1)
            self._append(b, f, attr, s)
            PlaybackConfig.assign_extension(f)
            if self.ui_callbacks is not None:
                self.ui_callbacks.update_extension_status(_("Extension \"{0}\" ready").format(b.n))
                # TODO update ExtensionsWindow as well if it's open
            ExtensionManager.extension_thread_delayed_complete = True
        except Exception as e:
            logger.error(f"Extension delayed processing failed: {e}")
            self._append(b, None, attr, s, str(e))
            ExtensionManager.extension_thread_delayed_complete = True
            raise e

    def _a(self, b, b1=None) -> tuple[str, Any]:
        a = b.da(g=config.directories[0])
        e1 = " Destination: "
        logger.warning(f"extending delayed: {a}")
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
            logger.warning("F was not found" if _f is None else "F was found but invalid: " + _f)
            if _e is None or not os.path.exists(_e):
                logger.warning("E was not found" if _e is None else "E was found but invalid: " + _e)
                close_match = self.check_dir_for_close_match(_e)
                if close_match is not None:
                    _f = close_match
                elif b1 is not None:
                    logger.info(f"Primary option failed, trying backup: {b1.n}")
                    return self._a(b1)  # Try backup, no backup parameter on this call
                else:
                    ExtensionManager.extension_thread_delayed_complete = True
                    raise Exception(f"No output found {b}")
            else:
                _f = _e
        
        # Clean emoji from filename if present
        if Utils.contains_emoji(_f):
            dirname = os.path.dirname(_f)
            basename = os.path.basename(_f)
            cleaned_basename = Utils.clean_emoji(basename)
            new_path = os.path.join(dirname, cleaned_basename)
            try:
                os.rename(_f, new_path)
                _f = new_path
            except Exception as e:
                logger.error(f"Failed to rename file to remove emoji: {e}")
        return _f, b

    def _m(self, q: str, t: str) -> Dict[str, float]:
        q_lower = q.lower()
        t_lower = t.lower()
        
        metrics = {}
        
        # 1. Substring containment (most important)
        if q_lower in t_lower:
            metrics['substring_match'] = len(q) / len(t)
        else:
            metrics['substring_match'] = 0.0
        
        # 2. Word overlap
        q_words = set(q_lower.split())
        t_words = set(t_lower.split())
        common_words = q_words.intersection(t_words)
        metrics['word_overlap'] = len(common_words) / len(q_words) if q_words else 0.0
        
        # 3. Levenshtein distance (normalized)
        levenshtein_dist = Utils.string_distance(q, t)
        max_len = max(len(q), len(t))
        metrics['levenshtein_similarity'] = 1.0 - (levenshtein_dist / max_len) if max_len > 0 else 0.0
        
        # 4. Overall quality score (weighted combination)
        metrics['overall_quality'] = (
            metrics['substring_match'] * 0.5 +      # Most important
            metrics['word_overlap'] * 0.3 +          # Important
            metrics['levenshtein_similarity'] * 0.2  # Less important
        )
        
        return metrics

    def _append(self, b, f: Optional[str], attr: Optional[TrackAttribute], s: str, exception: Optional[str] = None):
        obj = dict(b.u)
        obj["filename"] = f
        obj["date"] = datetime.datetime.now().isoformat()
        obj["strategy"] = ExtensionManager.strategy.name
        obj["track_attr"] = attr.name if attr is not None else "<unknown>"
        obj["search_query"] = s
        
        # Calculate quality metrics if we have a valid result
        if exception is None and hasattr(b, 'n') and b.n:
            quality_metrics = self._m(s, b.n)
            obj.update(quality_metrics)
        else:
            # Set default values for failed extensions
            obj.update({
                'substring_match': 0.0,
                'word_overlap': 0.0,
                'levenshtein_similarity': 0.0,
                'overall_quality': 0.0
            })
        
        obj["failed"] = exception is not None
        obj["exception"] = exception
        ExtensionManager.extensions.append(obj)

    def check_dir_for_close_match(self, t: Optional[str]) -> Optional[str]:
        if t is None or t.strip() == "":
            return None
        _dir = os.path.abspath(config.directories[0])
        for f in os.listdir(_dir):
            filepath = os.path.join(_dir, f)
            if os.path.isfile(filepath) and Utils.is_similar_strings(filepath, t, True):
                logger.info(f"Found close match: {f}")
                return filepath
        return None

    def s(self, q, x=1):
        logger.info(f"s: {q}")
        return LibraryExtender.isyMOLB_(q, m=x)

    @staticmethod
    def get_extension_detailsfor_track(media_track: Optional['MediaTrack'] = None) -> Optional[Dict[str, Any]]:
        if media_track is None:
            return None
        try:
            filepath = media_track.filepath
            for extension in ExtensionManager.extensions:
                if extension["filename"] == filepath:
                    return extension
        except Exception as e:
            logger.error(f"Error getting extension details for {filepath}: {e}")
        logger.error(f"No extension details found for {filepath}")
        return None
