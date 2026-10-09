"""Resolve on-disk cache file locations (``MUSE_CACHE_DIR`` overrides them for tests)."""

import os

from utils.app_paths import cache_dir


def resolve_cache_file(filename: str) -> str:
    """Return the absolute path of a cache file in the user cache dir."""
    return os.path.join(cache_dir(), filename)
