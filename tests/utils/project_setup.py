"""Project path setup and library data initialisation for test scripts.

Usage from any test script::

    from tests.utils.project_setup import ensure_project_root, load_library_data

    ensure_project_root()          # adds project root to sys.path
    library_data = load_library_data()  # loads caches and returns LibraryData
"""

import os
import sys


_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def ensure_project_root():
    """Insert the project root into ``sys.path`` if it is not already there."""
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)


def get_project_root() -> str:
    return _PROJECT_ROOT


def load_library_data():
    """Load directory / media-track / recently-played caches and return a
    fresh ``LibraryData`` instance.  Prints progress to stdout."""
    ensure_project_root()
    from library_data.library_data import LibraryData
    from muse.playlist import Playlist

    print("Loading caches...")
    LibraryData.load_directory_cache()
    LibraryData.load_media_track_cache()
    Playlist.load_recently_played_lists()
    return LibraryData()
