import datetime
import os
import random
import re
import subprocess
import threading
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Union

from extensions.llm import LLM, LLMResponseException
from extensions.library_extender import LibraryExtender
from extensions.soup_utils import SoupUtils
from muse.playback_config_master import PlaybackConfigMaster
from muse.prompter import Prompter
from muse.track_affinity import cosine_similarity, current_favorites_profile, embed_texts
from utils.app_info_cache import app_info_cache
from utils.config import config
from utils.globals import TrackAttribute, ExtensionStrategy, MediaFileType
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
    # These were class constants that could only be changed by editing this file;
    # they now read from config, defaulting to the values that used to be here.
    extension_thread: Optional[Any] = None

    # Cancellation signal for the current generation of extension threads. Each
    # thread captures it on entry and start_extensions_thread installs a
    # replacement rather than clearing it, so a stopped thread stays stopped.
    stop_event: threading.Event = threading.Event()
    current_download_process: Optional[Any] = None
    THREAD_JOIN_TIMEOUT_SECONDS: float = 5.0
    FAVORITE_BIAS_CHANCE: float = 0.5

    # Candidate currently selected and waiting out its pre-download delay, if any.
    # Dict shape: {"id": str, "title": str, "rejected": bool, "raw": dict,
    # "attr": Optional[TrackAttribute], "search_query": str}
    pending_candidate: Optional[Dict[str, Any]] = None
    # Persisted rejection records; rejected_ids is a derived O(1) lookup set.
    rejected_extensions: List[Dict[str, Any]] = []
    # IDs (LibraryExtender `.w`) the user has explicitly rejected before download;
    # excluded from future selection via _bad_option/_is_rejected.
    rejected_ids: set = set()

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
        ExtensionManager.rejected_extensions = list(app_info_cache.get("rejected_extensions", []))
        repaired = ExtensionManager._repair_corrupted_rejected_ids()
        migrated = ExtensionManager._migrate_legacy_rejected_ids()
        if migrated or repaired:
            # Persist so this doesn't get re-migrated on every future load.
            ExtensionManager.store_extensions()
        ExtensionManager._recompute_rejected_ids()

    @staticmethod
    def _repair_corrupted_rejected_ids() -> bool:
        from extensions.library_extender import q23
        repaired = False
        for r in ExtensionManager.rejected_extensions:
            id_val = r.get("id")
            if isinstance(id_val, dict):
                r["id"] = id_val.get(q23) or str(id_val)
                repaired = True
        return repaired

    @staticmethod
    def _migrate_legacy_rejected_ids() -> bool:
        """Wrap bare IDs from the old rejected_extension_ids key into placeholder records. Returns whether anything changed."""
        legacy_ids = app_info_cache.get("rejected_extension_ids", [])
        if not legacy_ids:
            return False
        existing_ids = {r["id"] for r in ExtensionManager.rejected_extensions}
        migrated = False
        for old_id in legacy_ids:
            if old_id not in existing_ids:
                ExtensionManager.rejected_extensions.append({
                    "id": old_id,
                    "snippet": {"title": ""},
                    "date": "",
                    "track_attr": "",
                    "search_query": "",
                })
                existing_ids.add(old_id)
                migrated = True
        return migrated

    @staticmethod
    def _recompute_rejected_ids() -> None:
        ExtensionManager.rejected_ids = {r["id"] for r in ExtensionManager.rejected_extensions}

    @staticmethod
    def _trim_extension_history() -> None:
        """Drop the oldest entries once the history passes its configured cap.

        The cap was a declared-but-never-read constant, so the history grew
        without bound. Entries are appended chronologically, so the oldest sit
        at the front. A cap of 0 keeps everything.
        """
        max_length = config.get_int("extension_history_max_length", 100000)
        excess = len(ExtensionManager.extensions) - max_length
        if max_length > 0 and excess > 0:
            del ExtensionManager.extensions[:excess]
            logger.info(f"Trimmed {excess} oldest extension history entries (cap {max_length})")

    @staticmethod
    def store_extensions() -> None:
        ExtensionManager._trim_extension_history()
        app_info_cache.set("extensions", list(ExtensionManager.extensions))
        app_info_cache.set("extension_strategy", ExtensionManager.strategy.name)
        app_info_cache.set("rejected_extensions", list(ExtensionManager.rejected_extensions))

    @staticmethod
    def reject_pending_candidate() -> bool:
        """Reject the extension candidate currently waiting to be downloaded.

        Marks it excluded from future selection and signals the waiting
        ``_delayed`` thread to skip the download. Does not start a new
        extension job -- the regular recurring extension cycle already
        picks up the next candidate on its own schedule.

        Returns True if there was a pending candidate to reject.
        """
        pending = ExtensionManager.pending_candidate
        if pending is None:
            return False
        obj = dict(pending["raw"])
        obj["id"] = pending["id"]
        obj["date"] = datetime.datetime.now().isoformat()
        obj["track_attr"] = pending["attr"].name if pending["attr"] is not None else "<unknown>"
        obj["search_query"] = pending["search_query"]
        ExtensionManager.rejected_extensions.append(obj)
        ExtensionManager._recompute_rejected_ids()
        pending["rejected"] = True
        ExtensionManager.store_extensions()
        return True

    @staticmethod
    def reject_extension(extension: Dict[str, Any]) -> bool:
        from extensions.library_extender import q20, q23
        id_val = extension.get(q20, {}).get(q23)
        if not id_val or id_val in ExtensionManager.rejected_ids:
            return False
        obj = dict(extension)
        obj["id"] = id_val
        obj["date"] = datetime.datetime.now().isoformat()
        ExtensionManager.rejected_extensions.append(obj)
        ExtensionManager._recompute_rejected_ids()
        ExtensionManager.store_extensions()
        return True

    @staticmethod
    def remove_rejection(rejection: Dict[str, Any]) -> bool:
        """Remove a rejection record, making its candidate eligible again. Returns True if found."""
        if rejection not in ExtensionManager.rejected_extensions:
            return False
        ExtensionManager.rejected_extensions.remove(rejection)
        ExtensionManager._recompute_rejected_ids()
        ExtensionManager.store_extensions()
        return True

    def __init__(self, ui_callbacks: Optional[Any], data_callbacks: Optional[Any]) -> None:
        from utils.config import config
        self.llm = LLM.from_config(config, state_key="extension_manager")
        self.prompter = Prompter()
        wait_min, wait_max = config.get_int_range("extension_cycle_wait_minutes", 60, 90)
        self.extension_wait_min: int = wait_min
        self.extension_wait_expected_max: int = wait_max
        self.ui_callbacks = ui_callbacks
        self.data_callbacks = data_callbacks

    def start_extensions_thread(self, initial_sleep: bool = True, overwrite_cache: bool = False, voice: Optional[Any] = None) -> None:
        logger.info('Starting extensions thread')
        if ExtensionManager.extension_thread is not None and ExtensionManager.extension_thread.is_alive():
            logger.info('Extension thread already running')
            return
        ExtensionManager.stop_event = threading.Event()
        ExtensionManager.extension_thread = Utils.start_thread(self._run_extensions, use_asyncio=False, args=(initial_sleep, voice))

    @staticmethod
    def _terminate_download_process() -> bool:
        process = ExtensionManager.current_download_process
        if process is None or process.poll() is not None:
            return False
        logger.info("Terminating in-flight extension download")
        try:
            process.terminate()
            try:
                process.wait(timeout=ExtensionManager.THREAD_JOIN_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                logger.warning("Download process ignored terminate; killing it")
                process.kill()
                process.wait(timeout=ExtensionManager.THREAD_JOIN_TIMEOUT_SECONDS)
        except Exception as e:
            logger.warning(f"Error terminating download process: {e}")
            return False
        finally:
            ExtensionManager.current_download_process = None
        return True

    def reset_extension(self, restart_thread: bool = True) -> None:
        """Reset the extension system, optionally restarting the thread."""
        try:
            ExtensionManager.EXTENSION_QUEUE.cancel()
            ExtensionManager.stop_event.set()
            self._terminate_download_process()
            timeout = ExtensionManager.THREAD_JOIN_TIMEOUT_SECONDS
            closed_one_thread = False

            # Clean up main extension thread
            if ExtensionManager.extension_thread is not None and ExtensionManager.extension_thread.is_alive():
                ExtensionManager.extension_thread.join(timeout=timeout)
                if ExtensionManager.extension_thread.is_alive():
                    # Blocked in an uninterruptible call; its event stays set, so
                    # it exits at its next checkpoint and starts no new work.
                    logger.warning(f"Extension thread still blocked after {timeout}s")
                closed_one_thread = True
            ExtensionManager.extension_thread = None

            # Clean up delayed threads
            for thread in ExtensionManager.DELAYED_THREADS:
                if thread.is_alive():
                    thread.join(timeout=timeout)
                    if thread.is_alive():
                        logger.warning(f"Delayed thread still blocked after {timeout}s")
                    closed_one_thread = True

            ExtensionManager.DELAYED_THREADS = []
            if closed_one_thread:
                logger.info("Reset extension thread.")
            if restart_thread:
                self.start_extensions_thread()
        except Exception as e:
            logger.error(f"Error during extension reset: {str(e)}")
            # Ensure we don't leave the system in an inconsistent state
            ExtensionManager.extension_thread = None
            ExtensionManager.DELAYED_THREADS = []

    def get_extension_sleep_time(self, min_value: int, max_value: int) -> int:
        current_track = PlaybackConfigMaster.get_playing_track()
        if current_track is not None and current_track.get_track_length() > max_value:
            length = int(current_track.get_track_length())
            min_value += length
            max_value += length
            logger.info(f"Increased extension sleep time for long track, "
                        f"new range: {min_value/60:.1f}min-{max_value/60:.1f}min")
        return random.randint(min_value, max_value)

    def _run_extensions(self, initial_sleep: bool = True, voice: Optional[Any] = None) -> None:
        stop_event = ExtensionManager.stop_event
        if initial_sleep:
            sleep_time_seconds = random.randint(200, 1200)
            check_cadence = 150
            while not stop_event.is_set() and sleep_time_seconds > 0:
                sleep_time_seconds -= check_cadence
                if sleep_time_seconds <= 0:
                    break
                if self.ui_callbacks is not None:
                    self.ui_callbacks.update_extension_status(_("Extension thread waiting for {0} minutes").format(round(float(sleep_time_seconds) / 60)))
                if Utils.long_wait(stop_event, check_cadence, "extension: startup delay", total=sleep_time_seconds, print_cadence=180):
                    break
            if stop_event.is_set():
                logger.info("Extension thread stopped during startup delay")
                return
            logger.info("Extension thread woke up")
        while not stop_event.is_set():
            self._extend_by_random_attr(voice)
            # Re-check: the call above does work the event cannot interrupt.
            if stop_event.is_set():
                break
            ExtensionManager.extension_thread_delayed_complete = False
            sleep_time_minutes = int(self.get_extension_sleep_time(
                self.extension_wait_min * 60, self.extension_wait_expected_max * 60) / 60)
            check_cadence = 1
            while not stop_event.is_set() and sleep_time_minutes > 0:
                sleep_time_minutes -= check_cadence
                if sleep_time_minutes <= 0:
                    break
                if ExtensionManager.extension_thread_delayed_complete and self.ui_callbacks is not None:
                    self.ui_callbacks.update_extension_status(_("Extension thread waiting for {0} minutes").format(sleep_time_minutes))
                if Utils.long_wait(stop_event, check_cadence * 60, "extension: idle between cycles", total=sleep_time_minutes * 60, print_cadence=180):
                    break
        logger.info("Extension thread exiting")

    def _favored_value(self, attr: TrackAttribute) -> Optional[str]:
        # Bias new material toward what the listener favorites, but only part of
        # the time -- always drawing from a handful of favored values would keep
        # returning to the same few and stop turning up anything new.
        if random.random() >= ExtensionManager.FAVORITE_BIAS_CHANCE:
            return None
        attribute_favorites = current_favorites_profile().get(attr.value)
        values = attribute_favorites.names() if attribute_favorites else []
        return random.choice(values) if values else None

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
        value = self._favored_value(attr) or extendible_attrs[attr]()

        logger.info(f'Extending by random {attr}: {value}')
        if voice is not None:
            muse_to_say = _("Coming up soon, we'll be listening to a new track from the {0} {1}.").format(attr.get_translation(), value)
            voice.prepare_to_say(muse_to_say, save_for_last=True)
        self.extend(value=value, attr=attr, strict=True)

    def _extend(self, value: str = "", attr: Optional[TrackAttribute] = None, strict: bool = False) -> None:
        stop_event = ExtensionManager.stop_event
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
            if Utils.long_wait(stop_event, 300, "extension thread job wait"):
                self.EXTENSION_QUEUE.job_running = False
                return
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
        self._simple("track title: \"" + title + "\"", attr=TrackAttribute.TITLE, strict=(title if strict else None), entity=title)

    def extend_by_album(self, album: str, strict: bool = False) -> None:
        self._simple("album title: \"" + album + "\"", attr=TrackAttribute.ALBUM, strict=(album if strict else None), entity=album)

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
        obj = self.data_callbacks.instance.artists.get_data(artist)
        self._simple(query, attr=TrackAttribute.ARTIST, strict=(artist if strict else None), entity=obj or artist)

    def extend_by_composer(self, composer_name: str) -> None:
        composer = self.data_callbacks.instance.composers.get_data(composer_name)
        self._simple("music composed by " + composer_name, attr=TrackAttribute.COMPOSER, strict=composer, entity=composer or composer_name)

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
        obj = self.data_callbacks.instance.genres.get_data(genre)
        self._simple(query, attr=TrackAttribute.GENRE, strict=(genre if strict else None), entity=obj or genre)

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
        obj = self.data_callbacks.instance.instruments.get_data(instrument)
        self._simple(query, attr=TrackAttribute.INSTRUMENT, strict=(instrument if strict else None), entity=obj or instrument)

    def _simple(self, q: str, m: int = 6, depth: int = 0, attr: Optional[TrackAttribute] = None, strict: Optional[Union[str, 'Composer']] = None, entity: Optional[Any] = None) -> None:
        r = self.s(q, m)
        if ExtensionManager.stop_event.is_set():
            logger.info("Extension search discarded, stop requested")
            return
        if r is not None and r.i():
            a = r.o()
            for i in a:
                i.n = SoupUtils.clean_html(i.n)
                i.d = SoupUtils.clean_html(i.d)
            score_with_llm = (
                getattr(config, "extension_enable_llm_scoring", True)
                and self.llm.get_failure_count() == 0
            )
            scores = self._llm_score_options(q, a) if score_with_llm else None
            score_with_embedding = getattr(config, "extension_enable_embedding_scoring", True)
            embedding_scores = self._embedding_score_options(q, a) if score_with_embedding else None
            for idx, i in enumerate(a):
                i.m = self._m(q, i.n, llm_score=(scores.get(idx) if scores else None),
                              embedding_score=(embedding_scores.get(idx) if embedding_scores else None))
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
                self._simple(q, m=m*2, depth=depth+1, attr=attr, strict=strict, entity=entity)
                return
            b = opts[0]
            b1 = opts[1] if len(opts) > 1 else None
            logger.warning(f"Selected option: {b.n} - {b.x()}")
            if b1:
                logger.info(f"Backup option: {b1.n} - {b1.x()}")
            logger.info(b.d)
            self.delayed(b, attr, s=q, b1=b1, entity=entity)
        else:
            if r is None:
                logger.warning("Tracking too many requests.")
            else:
                logger.warning(f'No results found for "{q}"')

    def _bad_option(self, b, strict: bool = False, attr: Optional[TrackAttribute] = None) -> bool:
        if b is None:
            return True
        if b.y:
            logger.info(f"Skipping unresolved option: {b.n}")
            return True
        min_seconds, max_seconds = config.get_int_range("extension_track_duration_seconds", 120, 10800)
        return (b.xfgi(min_seconds)
                or b.xfgj(max_seconds)
                or self.is_in_library(b)
                or (strict and self._strict_test(b, attr, strict))
                or self._is_blacklisted(b)
                or self._is_rejected(b)
                or self._is_skipped_emoji_title(b)
                or self._is_compilation(b)
                or self._not_music(b))

    @staticmethod
    def _is_skipped_emoji_title(b) -> bool:
        """Emoji titles are skipped unless the user opts into keeping them.

        This replaced a fixed 95% skip chance; a toggle is easier to reason
        about, and off means the same thing the old rate almost always did.
        """
        if getattr(config, "extension_allow_emoji_titles", False):
            return False
        return Utils.contains_emoji(b.n)

    def _is_rejected(self, b) -> bool:
        if b.w in ExtensionManager.rejected_ids:
            logger.info(f"Skipping previously-rejected candidate: {b.n}")
            return True
        return False

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
        return self._do_check(b, compilation_patterns)
    
    def _not_music(self, b) -> bool:
        # Not music patterns to detect
        patterns = [
            r'biography',
            r'(^|\W)RPG',
        ]
        return self._do_check(b, patterns)

    def _do_check(self, b, patterns: List[str], only_n: bool = False) -> bool:
        if not hasattr(b, 'n') or b.n is None:
            return False
        n = b.n.lower()
        d = b.d.lower() if hasattr(b, 'd') and b.d else ""
        text_to_check = n if only_n else f"{n} | {d}"
        for pattern in patterns:
            if re.search(pattern, text_to_check, re.IGNORECASE):
                return True
        return False

    def delayed(self, b, attr: Optional[TrackAttribute], s: str, b1=None, entity: Optional[Any] = None) -> None:
        thread = Utils.start_thread(self._delayed, use_asyncio=False, args=[b, attr, s, b1, True, entity])
        ExtensionManager.DELAYED_THREADS.append(thread)

    def _delayed(self, b, attr: Optional[TrackAttribute], s: str, b1=None, sleep: bool = True, entity: Optional[Any] = None) -> None:
        stop_event = ExtensionManager.stop_event
        if sleep:
            ExtensionManager.pending_candidate = {
                "id": b.w,
                "title": b.n,
                "rejected": False,
                "raw": dict(b.u),
                "attr": attr,
                "search_query": s,
            }
            review_min, review_max = config.get_int_range("extension_pending_review_seconds", 1000, 2000)
            time_seconds = self.get_extension_sleep_time(review_min, review_max)
            check_cadence = 150
            while not stop_event.is_set() and time_seconds > 0:
                if ExtensionManager.pending_candidate.get("rejected"):
                    break
                time_seconds -= check_cadence
                if time_seconds <= 0:
                    break
                if self.ui_callbacks is not None:
                    self.ui_callbacks.update_extension_status(_("Extension \"{0}\" waiting for {1} minutes").format(SoupUtils.clean_html(b.n), round(float(time_seconds) / 60)))
                if Utils.long_wait(stop_event, check_cadence, f"extension: pre-download delay", total=time_seconds, print_cadence=180):
                    break

            if stop_event.is_set():
                logger.info(f"Extension candidate abandoned, stop requested: {b.n}")
                ExtensionManager.pending_candidate = None
                ExtensionManager.extension_thread_delayed_complete = True
                return

            if ExtensionManager.pending_candidate.get("rejected"):
                logger.info(f"Extension candidate rejected before download: {b.n}")
                if self.ui_callbacks is not None:
                    self.ui_callbacks.update_extension_status(_("Extension \"{0}\" rejected").format(SoupUtils.clean_html(b.n)))
                ExtensionManager.pending_candidate = None
                ExtensionManager.extension_thread_delayed_complete = True
                return
            ExtensionManager.pending_candidate = None

        if self.ui_callbacks is not None:
            self.ui_callbacks.update_extension_status(_("Fetching extension \"{0}\"").format(SoupUtils.clean_html(b.n)))
        try:
            f, b = self._a(b, b1)

            if config.embed_extension_artwork and f:
                from extensions.extension_filer import embed_artwork_from_sidecar
                embed_artwork_from_sidecar(f)

            # Extract entity display name and aliases for rename and auto-filing
            _aliases: list = []
            _name: Optional[str] = None
            if entity:
                if isinstance(entity, str):
                    _aliases, _name = [entity], entity
                else:
                    _aliases = getattr(entity, 'indicators', None) or getattr(entity, 'transliterations', None) or []
                    _name = getattr(entity, 'name', str(entity))
                    if not _aliases:
                        _aliases = [_name]

            # Prefix filename with entity name when it isn't already present
            if _name and f:
                _bn = os.path.basename(f)
                if not any(a.lower() in _bn.lower() for a in _aliases):
                    _n = os.path.join(os.path.dirname(f), _name + " - " + _bn)
                    try:
                        os.rename(f, _n)
                        f = _n
                    except Exception as e:
                        logger.error(f"Failed to rename: {e}")

            # Auto-file into genre/artist/album subdirectory
            if not config.auto_file_extensions:
                logger.info("Auto-filing skipped: auto_file_extensions is disabled")
            elif not f:
                logger.warning("Auto-filing skipped: no downloaded file path was produced")
            else:
                from extensions.extension_filer import file_extension
                filed = file_extension(f, attr, _name, entity, b.n, llm=self.llm)
                if filed:
                    f = filed
                else:
                    logger.warning("Auto-filing returned no path; file remains at %s", f)

            self._append(b, f, attr, s)
            PlaybackConfigMaster.assign_extension(f)
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
        a = b.da(g=config.directories[0], t=config.embed_extension_artwork)
        e1 = " Destination: "
        logger.warning(f"extending delayed: {a}")
        e = "[download]"
        p = subprocess.Popen(a, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        ExtensionManager.current_download_process = p
        try:
            o, __ = p.communicate()
        finally:
            ExtensionManager.current_download_process = None
        if ExtensionManager.stop_event.is_set():
            logger.info("Extension download stopped")
            raise Exception("Extension download stopped")
        f = "[ExtractAudio]"
        _e = None
        _f = None
        for line in o.split("\n"):
            print(line)
            if line.startswith(e + e1):
                _e = line[len(e + e1):]
            if line.startswith(f + e1):
                _f = line[len(f + e1):]
        if _f is None or not self._exists_with_retry(_f):
            logger.warning("F was not found" if _f is None else "F was found but invalid: " + _f)
            if _e is None or not self._exists_with_retry(_e):
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

    @staticmethod
    def _exists_with_retry(path: Optional[str], attempts: int = 5, delay_seconds: float = 0.5) -> bool:
        if not path:
            return False
        for attempt in range(attempts):
            if os.path.exists(path):
                return True
            if attempt < attempts - 1:
                time.sleep(delay_seconds)
        return False

    @staticmethod
    def _j(title: str) -> float:
        """
        Partial demerits for titles that often indicate sloppy or off-topic uploads
        (uniform letter casing, social-style '@' for 'at', stray punctuation between words).
        Emoji is handled separately in _bad_option.
        """
        if not title or not title.strip():
            return 0.0
        penalty = 0.0
        letters = [c for c in title if c.isalpha()]
        if len(letters) >= 3:
            if all(c.islower() for c in letters):
                penalty += 0.08
            elif all(c.isupper() for c in letters):
                penalty += 0.08
        # Spaced '@' as in "artist @ venue" (not email-like local@domain.tld)
        if re.search(r"\s@\s", title):
            penalty += 0.07
        # Other symbols standing alone between whitespace (not typical prose punctuation)
        standalone = re.findall(r"(^|\s)([#*%$^~=<>+|\\`])($|\s)", title)
        penalty += min(0.12, 0.04 * len(standalone))
        return min(penalty, 0.25)

    def _llm_score_options(self, q: str, a: List[Any]) -> Optional[Dict[int, float]]:
        """Score all candidates 0.0-1.0 via one LLM call. Never raises; returns None on any failure, so callers fall back to mechanical `_m()` weighting."""
        try:
            prompt = self.prompter.get_prompt("score_search_results")
            prompt = prompt.replace("QUERY", q)
            candidates_text = "\n".join(f"{idx}: {cand.n}" for idx, cand in enumerate(a))
            prompt = prompt.replace("CANDIDATES", candidates_text)
            result = self.llm.generate_json_get_value(prompt, "scores")
            if result is None or not isinstance(result.response, dict) or len(result.response) != len(a):
                return None
            scores: Dict[int, float] = {}
            for key, value in result.response.items():
                idx = int(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    return None
                score = float(value)
                if idx not in range(len(a)) or not (0.0 <= score <= 1.0):
                    return None
                scores[idx] = score
            return scores if len(scores) == len(a) else None
        except (LLMResponseException, ValueError, TypeError) as e:
            logger.warning(f"LLM scoring of search results failed, falling back to mechanical quality only: {e}")
            return None

    def _embedding_score_options(self, q: str, a: List[Any]) -> Optional[Dict[int, float]]:
        """Score all candidates 0.0-1.0 by embedding similarity to the query.

        Runs locally via sentence-transformers rather than through Ollama, so it
        fails independently of the chat-model scoring above. Never raises;
        returns None when the embedding model is unavailable or gives an
        unusable result, so callers fall back to mechanical `_m()` weighting.
        """
        try:
            texts = [q] + [cand.n for cand in a]
            vectors = embed_texts(texts)
        except Exception as e:
            logger.warning(f"Embedding scoring of search results failed, falling back to mechanical quality only: {e}")
            return None
        if not vectors or len(vectors) != len(texts):
            return None
        scores: Dict[int, float] = {}
        for idx, vector in enumerate(vectors[1:]):
            similarity = cosine_similarity(vectors[0], vector)
            if similarity is None:
                return None
            # Opposed vectors carry no more meaning here than unrelated ones.
            scores[idx] = max(0.0, min(1.0, similarity))
        return scores

    def _m(self, q: str, t: str, llm_score: Optional[float] = None,
           embedding_score: Optional[float] = None) -> Dict[str, float]:
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
        
        # 3. String distance (normalized)
        l_dist = Utils.string_distance(q, t)
        max_len = max(len(q), len(t))
        metrics['string_similarity'] = 1.0 - (l_dist / max_len) if max_len > 0 else 0.0
        
        # 4. Overall quality score (weighted combination). Each optional model
        # signal is a minority slice of the total weight, never the whole of
        # it, and embedding_score gets a smaller slice than llm_score: it is
        # the weaker judge of relevance, but fails independently of the LLM.
        if llm_score is not None:
            metrics['llm_score'] = llm_score
        if embedding_score is not None:
            metrics['embedding_score'] = embedding_score
        if llm_score is not None and embedding_score is not None:
            base = (
                metrics['substring_match'] * 0.30 +
                metrics['word_overlap'] * 0.20 +
                metrics['string_similarity'] * 0.10 +
                llm_score * 0.25 +
                embedding_score * 0.15
            )
        elif llm_score is not None:
            base = (
                metrics['substring_match'] * 0.35 +
                metrics['word_overlap'] * 0.25 +
                metrics['string_similarity'] * 0.15 +
                llm_score * 0.25
            )
        elif embedding_score is not None:
            base = (
                metrics['substring_match'] * 0.40 +
                metrics['word_overlap'] * 0.25 +
                metrics['string_similarity'] * 0.15 +
                embedding_score * 0.20
            )
        else:
            base = (
                metrics['substring_match'] * 0.5 +      # Most important
                metrics['word_overlap'] * 0.3 +         # Important
                metrics['string_similarity'] * 0.2      # Less important
            )
        metrics["presentation_penalty"] = ExtensionManager._j(t)
        metrics["overall_quality"] = max(0.0, min(1.0, base - metrics["presentation_penalty"]))
        
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
                'string_similarity': 0.0,
                'presentation_penalty': 0.0,
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
            if not MediaFileType.is_media_filetype(f):
                continue
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
