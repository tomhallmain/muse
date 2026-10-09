"""Where Muse's files live.

Per-user data sits in one app data dir, ``%APPDATA%\\muse`` on Windows and
``~/.local/share/muse`` elsewhere (``MUSE_APP_DATA_DIR`` overrides it), holding
``configs/`` (config.json, the library DB, legacy library data under
``configs/library_data/``), ``cache/``, ``logs/`` and ``tts_output/``.
``MUSE_CONFIGS_DIR`` and ``MUSE_CACHE_DIR`` relocate a single subdir. Bundled
read-only files resolve through ``resource_path``. Files at legacy repo locations
move in when each dir is first resolved, never overwriting, and not while any
override is set. No ``utils`` imports at load time: the logger resolves its
directory here, and every ``utils`` module may import this one.
"""

import fnmatch
import glob
import os
import shutil
import sys
import threading

APP_DIR_NAME = "muse"

# The repo checkout, or the folder a compiled build runs from; the build
# places bundled files at the same relative paths.
RESOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Where earlier versions wrote user files. In a build it holds only bundled
# files, which the migration skips.
REPO_ROOT = RESOURCE_ROOT
# Nuitka defines __compiled__ in every module it compiles.
IS_BUILD = "__compiled__" in globals()

_OVERRIDE_VARS = ("MUSE_APP_DATA_DIR", "MUSE_CONFIGS_DIR", "MUSE_CACHE_DIR")

# Files in library_data/data that stay there; every other file is user data.
_SHIPPED_LIBRARY_DATA = ("*_example.json", "blacklist_default.enc", "data_fixes.json")

# (pattern relative to REPO_ROOT, subdir of the cache dir or "" for its root)
_LEGACY_CACHE_PATTERNS = (
    ("app_info_cache.enc*", ""),
    ("app_info_cache.json", ""),
    ("app_media_track_cache*", ""),
    ("app_directories_cache*", ""),
    ("app_track_embeddings*", ""),
    ("muse_memory", ""),
    ("temp_llm_prompt_response_history_*.json", ""),
    (os.path.join("extensions", "library_ext_q_dict.json"), ""),
    (os.path.join("library_data", "wiki", "*"), "wiki"),
    (os.path.join("assets", "spinning_record_videos", "*"), "spinning_record_videos"),
)

_migrated = set()
_migrate_lock = threading.Lock()


def _logger():
    from utils.logging_setup import get_logger
    return get_logger(__name__)


def resource_path(*parts: str) -> str:
    """Absolute path of a bundled, read-only file: locale, prompts, assets, templates."""
    return os.path.join(RESOURCE_ROOT, *parts)


def app_data_dir() -> str:
    """Root of the per-user app data directory (not created here)."""
    override = os.environ.get("MUSE_APP_DATA_DIR")
    if override:
        return override
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    else:
        base = os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, APP_DIR_NAME)


def configs_dir() -> str:
    """User configs, the library DB and network lookup caches; created on first use."""
    path = os.environ.get("MUSE_CONFIGS_DIR") or os.path.join(app_data_dir(), "configs")
    os.makedirs(path, exist_ok=True)
    _migrate_once("configs", _migrate_configs, path)
    return path


def user_library_data_dir() -> str:
    """User working copies of library metadata (artists.json, blacklist.json, ...)."""
    path = os.path.join(configs_dir(), "library_data")
    os.makedirs(path, exist_ok=True)
    return path


def cache_dir() -> str:
    """Caches the app can rebuild or re-download; created on first use."""
    path = os.environ.get("MUSE_CACHE_DIR") or os.path.join(app_data_dir(), "cache")
    os.makedirs(path, exist_ok=True)
    _migrate_once("cache", _migrate_cache, path)
    return path


def logs_dir() -> str:
    """Log files; created on first use."""
    path = os.path.join(app_data_dir(), "logs")
    os.makedirs(path, exist_ok=True)
    return path


def tts_output_dir() -> str:
    """Generated speech, including the recordings kept for replay; created on first use."""
    path = os.path.join(app_data_dir(), "tts_output")
    os.makedirs(path, exist_ok=True)
    _migrate_once("tts_output", _migrate_tts_output, path)
    return path


def _migrate_once(key: str, migrate, target: str) -> None:
    with _migrate_lock:
        if key in _migrated:
            return
        _migrated.add(key)
        # Under an override the target is a scratch or test dir, and the repo's
        # files must stay where they are.
        if any(os.environ.get(var) for var in _OVERRIDE_VARS):
            return
        try:
            migrate(target)
        except Exception as e:
            _logger().error(f"Moving legacy files into {target} failed: {e}")


def _move(src: str, dest_dir: str) -> None:
    """Move *src* into *dest_dir* unless an entry of that name exists there."""
    dest = os.path.join(dest_dir, os.path.basename(src))
    if os.path.lexists(dest):
        _logger().warning(f"Not moving {src}: {dest} already exists")
        return
    os.makedirs(dest_dir, exist_ok=True)
    shutil.move(src, dest)
    _logger().info(f"Moved {src} to {dest}")


def _move_matches(pattern: str, dest_dir: str) -> None:
    for src in sorted(glob.glob(os.path.join(REPO_ROOT, pattern))):
        try:
            _move(src, dest_dir)
        except OSError as e:
            _logger().error(f"Could not move {src} to {dest_dir}: {e}")


def _migrate_configs(target: str) -> None:
    legacy_configs = os.path.join(REPO_ROOT, "configs")
    if os.path.isdir(legacy_configs):
        for name in sorted(os.listdir(legacy_configs)):
            _move_matches(os.path.join("configs", glob.escape(name)), target)
    legacy_data = os.path.join(REPO_ROOT, "library_data", "data")
    if os.path.isdir(legacy_data):
        for name in sorted(os.listdir(legacy_data)):
            if any(fnmatch.fnmatch(name, p) for p in _SHIPPED_LIBRARY_DATA):
                continue
            _move_matches(os.path.join("library_data", "data", glob.escape(name)),
                          os.path.join(target, "library_data"))


def _migrate_cache(target: str) -> None:
    for pattern, subdir in _LEGACY_CACHE_PATTERNS:
        _move_matches(pattern, os.path.join(target, subdir) if subdir else target)


def _migrate_tts_output(target: str) -> None:
    _move_matches(os.path.join("tts_output", "*"), target)

