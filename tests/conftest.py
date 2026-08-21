"""
Root conftest for the Muse test suite.

Env vars must be set at module load time — before app singletons import — because
``app_info_cache``, ``config``, and ``muse_memory`` are created on first import.
Nested conftest files mirror the same bootstrap for alternate collection orders.
"""

import importlib
import importlib.util
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

import pytest

# ---------------------------------------------------------------------------
# Project root on sys.path (see also pythonpath / importmode in pytest.ini)
# ---------------------------------------------------------------------------
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# ---------------------------------------------------------------------------
# Bootstrap temp cache/config before any utils/muse singleton import
# ---------------------------------------------------------------------------
_bootstrap_spec = importlib.util.spec_from_file_location(
    "muse_tests_bootstrap_env",
    os.path.join(os.path.dirname(__file__), "bootstrap_env.py"),
)
_bootstrap_mod = importlib.util.module_from_spec(_bootstrap_spec)
_bootstrap_spec.loader.exec_module(_bootstrap_mod)
_bootstrap_mod.apply()

_config_example_src = os.path.join(_project_root, "configs", "config_example.json")

from utils.globals import HistoryType, PlaylistSortType


@dataclass
class MockMediaTrack:
    """Mock MediaTrack for testing."""
    filepath: str
    title: str
    album: str
    artist: str
    composer: str
    _genre: str
    _form: str
    _instrument: str
    _catalogue: str
    _is_extended: bool = False
    _is_stream: bool = False
    _main_artist: str = ""

    def get_genre(self):
        return self._genre

    def get_form(self):
        return self._form

    def get_instrument(self):
        return self._instrument

    def get_catalogue(self):
        return self._catalogue

    def get_main_artist(self):
        return self._main_artist or self.artist

    def get_parent_filepath(self):
        return self.filepath

    def is_invalid(self):
        return False

    def get_track_length(self):
        return 120.0

    def get_is_video(self):
        return False

    def get_volume(self):
        return (-20.0, -10.0)

    def is_stream(self) -> bool:
        return self._is_stream


@dataclass
class MockDataCallbacks:
    """Mock data callbacks for testing."""
    def __init__(self, tracks=None):
        self.tracks = tracks or []
        self.track_dict = {track.filepath: track for track in self.tracks}

    def get_track(self, track_id: str) -> Optional[dict]:
        return self.track_dict.get(track_id)

    def get_all_tracks(self) -> List[dict]:
        return self.tracks

    def get_all_filepaths(self, directories: List[str], overwrite: bool = False) -> List[str]:
        return [str(Path(__file__).parent / "fixtures" / "sample_100KB.mp3")]


class MockArgs:
    """Mock command line arguments for testing."""

    def __init__(self):
        self.enable_preparation = True
        self.enable_dynamic_volume = True
        self.enable_long_track_splitting = False
        self.long_track_splitting_time_cutoff_minutes = 20
        self.total = -1
        self.playlist_sort_type = PlaylistSortType.RANDOM
        self.directories = None
        self.overwrite = False
        self.track = None
        self.placeholder = False
        self.use_system_language_for_all_topics = False


def _reset_library_caches() -> None:
    import library_data.library_data as library_data

    library_data.LibraryData.DIRECTORIES_CACHE = {}
    library_data.LibraryData.MEDIA_TRACK_CACHE = {}
    library_data.LibraryData._directory_cache_loaded = False


def _reset_playlist_history() -> None:
    from muse.playlist import Playlist

    for history_type in HistoryType:
        setattr(Playlist, history_type.value, [])


def _reset_playback_state() -> None:
    from muse.playback_config import PlaybackConfig
    from muse.playback_config_master import PlaybackConfigMaster
    from muse.playback_state import PlaybackStateManager
    from muse.muse_spot_profile import MuseSpotProfile

    PlaybackConfig.open_configs.clear()
    PlaybackConfigMaster.open_configs.clear()
    PlaybackStateManager.reset()
    MuseSpotProfile.clear_session()


# ---------------------------------------------------------------------------
# DB isolation helpers
# ---------------------------------------------------------------------------

_db_template_conn = None


def _get_db_template_conn():
    """Build the seeded reference database once for the whole session.

    Uses the same schema as the real DB but skips the legacy-JSON migration
    and gzip-cache imports to avoid slow I/O and real-file dependencies.
    """
    global _db_template_conn
    if _db_template_conn is not None:
        return _db_template_conn

    import sqlite3

    from utils.db import (
        _create_schema,
        _seed_artists,
        _seed_composers,
        _seed_forms,
        _seed_genres,
        _seed_instruments,
        _set_meta,
    )

    conn = sqlite3.connect(":memory:")
    _create_schema(conn)
    _seed_forms(conn)
    _seed_genres(conn)
    _seed_instruments(conn)
    _seed_composers(conn)
    _seed_artists(conn)
    _set_meta(conn, "seeded", "1")
    conn.commit()
    _db_template_conn = conn
    return _db_template_conn


def _make_isolated_db_conn():
    """Return a fresh in-memory SQLite database, page-copied from the template.

    Re-running the seed per test costs ~28ms (parsing a 2.5 MB composers JSON
    and inserting several thousand rows); copying the already-seeded template
    costs well under a millisecond. The copy is a fully independent database,
    so per-test isolation is unchanged.
    """
    import sqlite3

    conn = sqlite3.connect(":memory:")
    _get_db_template_conn().backup(conn)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _patch_db_connection_singleton(monkeypatch, conn) -> None:
    """Redirect get_connection() to *conn* for all known call sites.

    Patches the utils.db module (for callers that import inside functions)
    and the five library_data modules that bind ``get_connection`` at module
    load time via a top-level ``from utils.db import get_connection``.
    When ``reload_metadata_singletons`` later creates fresh ArtistsData() /
    ComposersData() / FormsData() / GenresData() / InstrumentsData() instances
    those constructors will use the isolated connection.
    """
    import utils.db as db_mod

    monkeypatch.setattr(db_mod, "get_connection", lambda: conn)
    monkeypatch.setattr(db_mod, "_connection", conn)

    for module_name in (
        "library_data.artist",
        "library_data.composer",
        "library_data.form",
        "library_data.genre",
        "library_data.instrument",
    ):
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        if hasattr(module, "get_connection"):
            monkeypatch.setattr(module, "get_connection", lambda c=conn: c)


def repoint_singleton_bindings(monkeypatch, attr_name, old_obj, new_obj) -> None:
    """Repoint every module-level binding of *old_obj* to *new_obj*.

    A module doing ``from utils.config import config`` at import time holds its
    own reference to the singleton, so patching the source module alone leaves
    that binding stale and the module keeps reading the un-isolated instance --
    which is never reset between tests, so its values leak into whatever runs
    next. That surfaces as a test passing for the wrong reason, not as an error.

    Sweeping sys.modules replaces the per-module list this used to need, which
    silently went out of date whenever a module adopted the import style. The
    identity check touches only bindings to the exact old object, and modules
    imported later reach the new object through the already-patched source
    module. Test modules are swept too, so a module-level import in a test file
    no longer writes to a different object than the code under test reads.

    Two things it cannot reach: a reference copied onto an instance attribute
    (``self.config = config``), which needs its owner rebuilt; and a module
    imported for the first time *during* a test, which binds that test's
    instance -- monkeypatch never set that binding, so it survives teardown and
    later sweeps no longer recognise it. The second only bites a module reached
    exclusively by a lazy import; anything a test module imports at the top is
    already in sys.modules before the first sweep runs.
    """
    for module in list(sys.modules.values()):
        try:
            if getattr(module, attr_name, None) is old_obj:
                monkeypatch.setattr(module, attr_name, new_obj)
        except Exception:
            continue


def _patch_muse_memory_singleton(monkeypatch, memory_instance) -> None:
    import muse.muse as muse_mod
    import muse.muse_memory as muse_memory_mod
    import utils.persistent_data_manager as pdm

    monkeypatch.setattr(muse_memory_mod, "muse_memory", memory_instance)
    monkeypatch.setattr(muse_mod, "muse_memory", memory_instance)
    monkeypatch.setattr(pdm, "muse_memory", memory_instance)


@pytest.fixture(autouse=True)
def bypass_password(monkeypatch):
    """Never prompt for passwords or touch the OS credential store (Weidr-style)."""
    from tests.utils.auth_test_bypass import install_password_bypass

    install_password_bypass(monkeypatch)


@pytest.fixture(autouse=True)
def isolated_singletons(tmp_path, monkeypatch):
    """Point app singletons at a fresh per-test temp directory.

    Also redirects the SQLite DB connection to an isolated in-memory database
    so tests never touch the real muse_library.db on disk.  The in-memory DB
    is seeded from the example JSON files (same as a fresh production install)
    but skips the slow legacy-JSON and gzip-cache migrations.

    The DB patch is applied before the other singletons are (re)constructed so
    that any singleton whose __init__ calls get_connection() picks up the
    isolated connection.  In particular, when the UI conftest's
    ``isolated_metadata_files`` later calls ``reload_metadata_singletons()``,
    the new ArtistsData / FormsData / GenresData / InstrumentsData instances
    will load from the in-memory DB rather than the real one.
    """
    cache_dir = tmp_path / "cache"
    configs_dir = tmp_path / "configs"
    cache_dir.mkdir()
    configs_dir.mkdir()
    if os.path.isfile(_config_example_src):
        shutil.copy(_config_example_src, configs_dir / "config.json")

    monkeypatch.setenv("MUSE_CACHE_DIR", str(cache_dir))
    monkeypatch.setenv("MUSE_CONFIGS_DIR", str(configs_dir))

    # --- DB isolation (must come before singleton construction below) ---
    isolated_db_conn = _make_isolated_db_conn()
    _patch_db_connection_singleton(monkeypatch, isolated_db_conn)

    # importlib rather than `import utils.app_info_cache as x`: utils/__init__.py
    # binds the *instance* onto the package under that same name, so the plain
    # import statement hands back the singleton instead of the module.
    cache_module = importlib.import_module("utils.app_info_cache")
    old_cache = cache_module.app_info_cache
    new_cache = cache_module.AppInfoCache()
    repoint_singleton_bindings(monkeypatch, "app_info_cache", old_cache, new_cache)

    config_module = importlib.import_module("utils.config")
    old_config = config_module.config
    config_instance = config_module.Config()
    repoint_singleton_bindings(monkeypatch, "config", old_config, config_instance)
    # Rebuild composers_data (DB-backed; must use the isolated in-memory connection)
    # rather than whatever the module-level singleton loaded at import time.
    try:
        import library_data.composer as _composer_mod
        monkeypatch.setattr(
            _composer_mod, "composers_data", _composer_mod.ComposersData()
        )
    except Exception:
        pass
    # Same for forms_data (DB-backed; must use the isolated in-memory connection).
    try:
        import library_data.form as _form_mod
        _fresh_forms = _form_mod.FormsData()
        monkeypatch.setattr(_form_mod, "forms_data", _fresh_forms)
        try:
            import ui_qt.forms_window as _forms_window_mod
            if hasattr(_forms_window_mod, "forms_data"):
                monkeypatch.setattr(_forms_window_mod, "forms_data", _fresh_forms)
        except Exception:
            pass
    except Exception:
        pass
    # Same for genre_data (DB-backed; must use the isolated in-memory connection).
    try:
        import library_data.genre as _genre_mod
        _fresh_genres = _genre_mod.GenresData()
        monkeypatch.setattr(_genre_mod, "genre_data", _fresh_genres)
        try:
            import ui_qt.genres_window as _genres_window_mod
            if hasattr(_genres_window_mod, "genre_data"):
                monkeypatch.setattr(_genres_window_mod, "genre_data", _fresh_genres)
        except Exception:
            pass
    except Exception:
        pass
    # Same for artists_data (DB-backed; must use the isolated in-memory connection).
    try:
        import library_data.artist as _artist_mod
        _fresh_artists = _artist_mod.ArtistsData()
        monkeypatch.setattr(_artist_mod, "artists_data", _fresh_artists)
        try:
            import ui_qt.artists_window as _artists_window_mod
            if hasattr(_artists_window_mod, "artists_data"):
                monkeypatch.setattr(_artists_window_mod, "artists_data", _fresh_artists)
        except Exception:
            pass
    except Exception:
        pass
    # Same for instruments_data (DB-backed; must use the isolated in-memory connection).
    try:
        import library_data.instrument as _instrument_mod
        _fresh_instruments = _instrument_mod.InstrumentsData()
        monkeypatch.setattr(_instrument_mod, "instruments_data", _fresh_instruments)
        try:
            import ui_qt.instruments_window as _instruments_window_mod
            if hasattr(_instruments_window_mod, "instruments_data"):
                monkeypatch.setattr(_instruments_window_mod, "instruments_data", _fresh_instruments)
        except Exception:
            pass
    except Exception:
        pass

    import muse.muse_memory as mm

    new_memory = mm.MuseMemory()
    _patch_muse_memory_singleton(monkeypatch, new_memory)

    _reset_library_caches()
    _reset_playlist_history()

    yield

    isolated_db_conn.close()


@pytest.fixture
def app_info_cache(isolated_singletons):
    """The isolated app_info_cache singleton for this test.

    ``repoint_singleton_bindings`` also fixes up a module-level import in a test
    file, so this is not the only way to reach the isolated instance -- but it
    states the dependency instead of relying on the sweep, and it stays correct
    for the cases the sweep documents as out of reach.
    """
    from utils.app_info_cache import app_info_cache as isolated_instance

    return isolated_instance


@pytest.fixture(autouse=True)
def reset_app_globals():
    """Reset mutable class-level state between tests."""
    _reset_playback_state()
    _reset_library_caches()
    _reset_playlist_history()
    yield
    _reset_playback_state()
    _reset_library_caches()
    _reset_playlist_history()


@pytest.fixture
def mock_args():
    return MockArgs()


@pytest.fixture
def mock_tracks():
    return [
        MockMediaTrack(
            filepath="track1.mp3",
            title="Piano Sonata in C Minor",
            album="Beethoven: Piano Sonatas",
            artist="Berlin Philharmonic",
            composer="Beethoven",
            _genre="Classical",
            _form="Symphony",
            _instrument="Orchestra",
            _catalogue="Beethoven: Piano Sonatas",
        ),
        MockMediaTrack(
            filepath="track2.mp3",
            title="Piano Sonata in F Minor",
            album="Beethoven: Piano Sonatas",
            artist="Berlin Philharmonic",
            composer="Beethoven",
            _genre="Classical",
            _form="Symphony",
            _instrument="Orchestra",
            _catalogue="Beethoven: Piano Sonatas",
        ),
        MockMediaTrack(
            filepath="track3.mp3",
            title="Opera Excerpt I",
            album="Vivaldi Operas Vol. 1",
            artist="Academy of St Martin",
            composer="Vivaldi",
            _genre="Classical",
            _form="Concerto",
            _instrument="Violin",
            _catalogue="Vivaldi Operas",
        ),
        MockMediaTrack(
            filepath="track4.mp3",
            title="Take Five",
            album="Time Out",
            artist="Dave Brubeck",
            composer="Paul Desmond",
            _genre="Jazz",
            _form="Jazz Standard",
            _instrument="Piano",
            _catalogue="Time Out",
        ),
        MockMediaTrack(
            filepath="track5.mp3",
            title="Blue Rondo à la Turk",
            album="Time Out",
            artist="Dave Brubeck",
            composer="Dave Brubeck",
            _genre="Jazz",
            _form="Jazz Standard",
            _instrument="Piano",
            _catalogue="Time Out",
        ),
        MockMediaTrack(
            filepath="track6.mp3",
            title="Stairway to Heaven",
            album="Led Zeppelin IV",
            artist="Led Zeppelin",
            composer="Page/Plant",
            _genre="Rock",
            _form="Rock Song",
            _instrument="Guitar",
            _catalogue="Led Zeppelin IV",
        ),
        MockMediaTrack(
            filepath="track7.mp3",
            title="Opera Excerpt II",
            album="Vivaldi Operas Vol. 2",
            artist="Academy of St Martin",
            composer="Vivaldi",
            _genre="Classical",
            _form="Concerto",
            _instrument="Violin",
            _catalogue="Vivaldi Operas",
        ),
    ]


@pytest.fixture
def mock_data_callbacks(mock_tracks):
    return MockDataCallbacks(mock_tracks)


@pytest.fixture
def test_data_dir():
    return Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def audio_library_dir():
    """Tagged MP3 library (100+ tracks); generated on first use if missing."""
    from tests.fixtures.audio_fixtures import ensure_audio_library, ffmpeg_available

    if not ffmpeg_available():
        pytest.skip("ffmpeg not on PATH — cannot generate audio fixtures")
    return ensure_audio_library()


@pytest.fixture(scope="session")
def audio_library_manifest(audio_library_dir):
    from tests.fixtures.audio_fixtures import read_manifest

    return read_manifest()


@pytest.fixture
def audio_library_media_tracks(audio_library_dir):
    from tests.fixtures.audio_fixtures import load_media_tracks

    return load_media_tracks()


@pytest.fixture
def audio_library_callbacks(audio_library_dir):
    from tests.fixtures.audio_fixtures import build_fixture_callbacks

    return build_fixture_callbacks()


@pytest.fixture
def sample_audio_file(test_data_dir):
    from tests.fixtures.audio_fixtures import ensure_legacy_samples, ffmpeg_available

    if not ffmpeg_available():
        pytest.skip("ffmpeg not on PATH — cannot generate audio fixtures")
    ensure_legacy_samples()
    return test_data_dir / "sample_100KB.mp3"


@pytest.fixture
def temp_dir(tmp_path):
    return tmp_path


def pytest_sessionfinish(session, exitstatus):
    """Remove disposable TTS artifacts left in tts_output by integration tests."""
    from tts.output_cleanup import cleanup_default_output_directory

    cleanup_default_output_directory()


# Directory name under tests/ == the marker every test beneath it carries.
LAYER_MARKERS = ("unit", "integration", "ui")


def pytest_collection_modifyitems(items):
    """Apply the layer marker (unit / integration / ui) to every test by location.

    pytest reads ``pytestmark`` only at module and class scope, so a marker
    cannot be declared once per directory in a conftest.  Without this hook the
    documented ``-m unit`` / ``-m integration`` / ``-m ui`` selections quietly
    run only the modules that happen to decorate themselves, which is easy to
    get wrong when adding a file and impossible to notice from the output.
    """
    tests_root = Path(__file__).parent
    for item in items:
        try:
            parts = Path(str(item.path)).relative_to(tests_root).parts
        except ValueError:
            continue
        if parts and parts[0] in LAYER_MARKERS:
            item.add_marker(getattr(pytest.mark, parts[0]))
