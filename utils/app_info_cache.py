import datetime
import json
import os
import shutil
import threading

from lib.position_data_qt import PositionData
from utils.app_paths import cache_dir
from utils.encryptor import encrypt_data_to_file, decrypt_data_from_file, stored_keys_need_unavailable_oqs
from utils.globals import AppInfo
from utils.logging_setup import get_logger
from utils.runner_app_config import RunnerAppConfig

logger = get_logger(__name__)


class AppInfoCache:
    INFO_KEY = "info"
    HISTORY_KEY = "history"
    DIRECTORIES_KEY = "directories"
    TRACKERS_KEY = "trackers"
    MAX_HISTORY_ENTRIES = 50
    NUM_BACKUPS = 4  # Number of backup files to maintain

    def __init__(self):
        self._lock = threading.RLock()
        self._cache = {AppInfoCache.INFO_KEY: {}, AppInfoCache.HISTORY_KEY: [], AppInfoCache.DIRECTORIES_KEY: {}}
        self._cache_loc = os.path.join(cache_dir(), "app_info_cache.enc")
        self._json_loc = os.path.join(cache_dir(), "app_info_cache.json")
        # Plaintext saves while the encrypted cache cannot be read (quantum keys
        # without OQS). load() never migrates this file into the encrypted
        # cache: it holds only what was saved since then, and would replace
        # the encrypted cache's contents. Kept for manual recovery.
        self._no_oqs_json_loc = os.path.join(cache_dir(), "app_info_cache.no_oqs.json")
        self._encrypted_cache_unreadable = False
        self.load()
        self.validate()

    def wipe_instance(self):
        with self._lock:
            self._cache = {AppInfoCache.INFO_KEY: {}, AppInfoCache.HISTORY_KEY: [], AppInfoCache.DIRECTORIES_KEY: {}}

    def store(self):
        """Persist cache to encrypted file. Returns True on success, False if encrypted store failed but JSON fallback succeeded. Raises on encoding or JSON fallback failure."""
        with self._lock:
            try:
                cache_data = json.dumps(self._cache).encode('utf-8')
            except Exception as e:
                raise Exception(f"Error compiling application cache: {e}")

            if self._encrypted_cache_unreadable:
                # Encrypting fails the same way loading did; go straight to the fallback.
                json_loc = self._no_oqs_json_loc
            else:
                json_loc = self._json_loc
                try:
                    encrypt_data_to_file(
                        cache_data,
                        AppInfo.SERVICE_NAME,
                        AppInfo.APP_IDENTIFIER,
                        self._cache_loc,
                    )
                    self._remove_superseded_json()
                    return True  # Encryption successful
                except Exception as e:
                    logger.error(f"Error encrypting cache: {e}")

            try:
                with open(json_loc, "w", encoding="utf-8") as f:
                    json.dump(self._cache, f)
                return False  # Encryption failed, but JSON fallback succeeded
            except Exception as e:
                raise Exception(f"Error storing application cache: {e}")

    def _remove_superseded_json(self):
        """Delete the plaintext fallback once an encrypted save holds the same
        data; left in place, load() would prefer it over newer encrypted saves."""
        if os.path.exists(self._json_loc):
            try:
                os.remove(self._json_loc)
                logger.info(f"Removed {self._json_loc}: superseded by the encrypted cache")
            except OSError as e:
                logger.error(f"Could not remove superseded {self._json_loc}: {e}")

    def _try_load_cache_from_file(self, path):
        """Attempt to load and decrypt the cache from the given file path. Raises on failure."""
        encrypted_data = decrypt_data_from_file(
            path,
            AppInfo.SERVICE_NAME,
            AppInfo.APP_IDENTIFIER
        )
        return json.loads(encrypted_data.decode('utf-8'))

    def load(self):
        with self._lock:
            try:
                if os.path.exists(self._json_loc):
                    logger.info(f"Detected JSON-format application cache, will attempt migration to encrypted store")
                    with open(self._json_loc, "r", encoding="utf-8") as f:
                        self._cache = json.load(f)
                    if self.store():
                        logger.info(f"Migrated application cache from {self._json_loc} to encrypted store")
                    else:
                        logger.warning("Encrypted store of application cache failed; keeping JSON cache file")
                    return

                # Try encrypted cache and backups in order
                cache_paths = [self._cache_loc] + self._get_backup_paths()
                any_exist = any(os.path.exists(path) for path in cache_paths)
                if not any_exist:
                    logger.info(f"No cache file found at {self._cache_loc}, creating new cache")
                    return

                for path in cache_paths:
                    if os.path.exists(path):
                        try:
                            self._cache = self._try_load_cache_from_file(path)
                            # Only shift backups if we loaded from the main file
                            if path == self._cache_loc:
                                message = f"Loaded cache from {self._cache_loc}"
                                rotated_count = self._rotate_backups()
                                if rotated_count > 0:
                                    message += f", rotated {rotated_count} backups"
                                logger.info(message)
                            else:
                                logger.warning(f"Loaded cache from backup: {path}")
                            return
                        except Exception as e:
                            logger.error(f"Failed to load cache from {path}: {e}")
                            continue
                # If we get here, all attempts failed (but at least one file existed)
                if stored_keys_need_unavailable_oqs(AppInfo.SERVICE_NAME, AppInfo.APP_IDENTIFIER):
                    self._start_without_encrypted_cache()
                    return
                raise Exception(f"Failed to load cache from all locations: {cache_paths}")
            except FileNotFoundError:
                pass

    def _start_without_encrypted_cache(self):
        """Continue from the last no-OQS session's saves, or from an empty cache,
        leaving the encrypted cache and its backups untouched for a process
        with OQS."""
        self._encrypted_cache_unreadable = True
        logger.warning(
            f"{self._cache_loc} is encrypted with quantum (OQS) keys and this build has no OQS "
            f"(build with --with-oqs to read it). Starting without it; it is left untouched, "
            f"and this session's changes are saved to {self._no_oqs_json_loc} only."
        )
        if os.path.exists(self._no_oqs_json_loc):
            try:
                with open(self._no_oqs_json_loc, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
                logger.info(f"Loaded cache from {self._no_oqs_json_loc}")
            except (OSError, ValueError) as e:
                logger.error(f"Could not read {self._no_oqs_json_loc}, starting empty: {e}")

    def validate(self):
        with self._lock:
            pass

    def _get_history(self) -> list:
        """Get history list. Must be called from within a locked context."""
        if AppInfoCache.HISTORY_KEY not in self._cache:
            self._cache[AppInfoCache.HISTORY_KEY] = {}
        return self._cache[AppInfoCache.HISTORY_KEY]

    def _get_directory_info(self):
        """Get directory info dict. Must be called from within a locked context."""
        if AppInfoCache.DIRECTORIES_KEY not in self._cache:
            self._cache[AppInfoCache.DIRECTORIES_KEY] = {}
        return self._cache[AppInfoCache.DIRECTORIES_KEY]

    def _get_trackers(self) -> dict:
        """Get trackers dict. Must be called from within a locked context."""
        if AppInfoCache.TRACKERS_KEY not in self._cache:
            self._cache[AppInfoCache.TRACKERS_KEY] = {}
        return self._cache[AppInfoCache.TRACKERS_KEY]

    def set(self, key, value):
        with self._lock:
            if AppInfoCache.INFO_KEY not in self._cache:
                self._cache[AppInfoCache.INFO_KEY] = {}
            self._cache[AppInfoCache.INFO_KEY][key] = value

    def get(self, key, default_val=None):
        with self._lock:
            if AppInfoCache.INFO_KEY not in self._cache or key not in self._cache[AppInfoCache.INFO_KEY]:
                return default_val
            return self._cache[AppInfoCache.INFO_KEY][key]

    def set_display_position(self, master, geometry=None):
        """Store the main window's display position and size.

        Pass ``geometry`` to save that instead of the window's current one --
        e.g. its last known non-maximized geometry.
        """
        self.set("display_position", PositionData.from_master(master, geometry=geometry).to_dict())

    def set_virtual_screen_info(self, master):
        """Store the virtual screen information."""
        try:
            self.set("virtual_screen_info", PositionData.from_master_virtual_screen(master).to_dict())
        except Exception as e:
            logger.warning(f"Failed to store virtual screen info: {e}")

    def get_virtual_screen_info(self):
        """Get the cached virtual screen info, returns None if not set or invalid."""
        virtual_screen_data = self.get("virtual_screen_info")
        if not virtual_screen_data:
            return None
        return PositionData.from_dict(virtual_screen_data)

    def get_display_position(self):
        """Get the cached display position, returns None if not set or invalid."""
        position_data = self.get("display_position")
        if not position_data:
            return None
        return PositionData.from_dict(position_data)

    def set_history(self, runner_config):
        with self._lock:
            history = self._get_history()
            if len(history) > 0 and runner_config == RunnerAppConfig.from_dict(history[0]):
                return False
            config_dict = runner_config.to_dict()
            history.insert(0, config_dict)
            # Remove the oldest entry from history if over the limit of entries
            while len(history) >= AppInfoCache.MAX_HISTORY_ENTRIES:
                history = history[0:-1]
            return True

    def get_last_history_index(self):
        with self._lock:
            history = self._get_history()
            return len(history) - 1

    def get_history(self, _idx=0):
        with self._lock:
            history = self._get_history()
            if _idx >= len(history):
                raise Exception("Invalid history index " + str(_idx))
            return history[_idx]

    def get_history_latest(self):
        with self._lock:
            history = self._get_history()
            if len(history) == 0:
                return RunnerAppConfig()
            return RunnerAppConfig.from_dict(history[0])

    def set_directory(self, directory, key, value):
        with self._lock:
            directory = AppInfoCache.normalize_directory_key(directory)
            if directory is None or directory.strip() == "":
                raise Exception(f"Invalid directory provided to app_info_cache.set(). key={key} value={value}")
            directory_info = self._get_directory_info()
            if directory not in directory_info:
                directory_info[directory] = {}
            directory_info[directory][key] = value

    def get_directory(self, directory, key, default_val=None):
        with self._lock:
            directory = AppInfoCache.normalize_directory_key(directory)
            directory_info = self._get_directory_info()
            if directory not in directory_info or key not in directory_info[directory]:
                return default_val
            return directory_info[directory][key]

    def get_tracker(self, tracker):
        with self._lock:
            trackers = self._get_trackers()
            if tracker not in trackers:
                trackers[tracker] = {"count": 0, "last": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
            return trackers[tracker]

    def increment_tracker(self, tracker):
        with self._lock:
            tracker = self.get_tracker(tracker)
            now = datetime.datetime.now()
            last_track = datetime.datetime.strptime(tracker["last"], "%Y-%m-%d %H:%M")
            if now.year <= last_track.year and now.month <= last_track.month and now.day <= last_track.day:
                tracker["count"] += 1
            else:
                tracker["count"] = 1
            tracker["last"] = now.strftime("%Y-%m-%d %H:%M")
            hours_since_last = (now - last_track).total_seconds()/3600
            return int(tracker["count"]), float(hours_since_last)

    @staticmethod
    def normalize_directory_key(directory):
        return os.path.normpath(os.path.abspath(directory))

    def export_as_json(self, json_path=None):
        """Export the current cache as a JSON file (not encrypted)."""
        if json_path is None:
            json_path = self._json_loc
        with self._lock:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        return json_path

    def _get_backup_paths(self):
        """Get list of backup file paths in order of preference"""
        backup_paths = []
        for i in range(1, AppInfoCache.NUM_BACKUPS + 1):
            index = "" if i == 1 else f"{i}"
            path = f"{self._cache_loc}.bak{index}"
            backup_paths.append(path)
        return backup_paths

    def _rotate_backups(self):
        """Rotate backup files: move each backup to the next position, oldest gets overwritten"""
        backup_paths = self._get_backup_paths()
        rotated_count = 0
        
        # Remove the oldest backup if it exists
        if os.path.exists(backup_paths[-1]):
            os.remove(backup_paths[-1])
        
        # Shift backups: move each backup to the next position
        for i in range(len(backup_paths) - 1, 0, -1):
            if os.path.exists(backup_paths[i - 1]):
                shutil.copy2(backup_paths[i - 1], backup_paths[i])
                rotated_count += 1
        
        # Copy main cache to first backup position
        shutil.copy2(self._cache_loc, backup_paths[0])
        
        return rotated_count

app_info_cache = AppInfoCache()
