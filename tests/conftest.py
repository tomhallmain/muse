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
    _is_extended: bool = False

    def get_genre(self):
        return self._genre

    def get_form(self):
        return self._form

    def get_instrument(self):
        return self._instrument


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

    PlaybackConfig.open_configs.clear()
    PlaybackConfigMaster.open_configs.clear()
    PlaybackStateManager.reset()


def _patch_app_info_cache_singleton(monkeypatch, cache_instance) -> None:
    """Patch the app_info_cache singleton everywhere tests may hold a reference.

    ``utils/__init__.py`` does ``from utils.app_info_cache import app_info_cache``,
    which binds the instance onto the ``utils`` package as ``utils.app_info_cache``.
    That shadows the real submodule, so ``import utils.app_info_cache as x`` returns
    the singleton, not the module — never use ``x.AppInfoCache()`` in that case.
    """
    import utils

    cache_module = importlib.import_module("utils.app_info_cache")
    monkeypatch.setattr(cache_module, "app_info_cache", cache_instance)
    monkeypatch.setattr(utils, "app_info_cache", cache_instance)

    for module_name in (
        "muse.playlist",
        "library_data.library_data",
        "muse.prompter",
        "muse.schedules_manager",
    ):
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        if hasattr(module, "app_info_cache"):
            monkeypatch.setattr(module, "app_info_cache", cache_instance)


def _patch_config_singleton(monkeypatch, config_instance) -> None:
    """Patch the config singleton (same package shadowing issue as app_info_cache)."""
    import utils

    config_module = importlib.import_module("utils.config")
    monkeypatch.setattr(config_module, "config", config_instance)
    monkeypatch.setattr(utils, "config", config_instance)

    for module_name in (
        "muse.playlist",
        "muse.muse",
        "muse.playback",
        "muse.dj_persona",
        "library_data.library_data",
    ):
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        if hasattr(module, "config"):
            monkeypatch.setattr(module, "config", config_instance)


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
    """Point app singletons at a fresh per-test temp directory."""
    cache_dir = tmp_path / "cache"
    configs_dir = tmp_path / "configs"
    cache_dir.mkdir()
    configs_dir.mkdir()
    if os.path.isfile(_config_example_src):
        shutil.copy(_config_example_src, configs_dir / "config.json")

    monkeypatch.setenv("MUSE_CACHE_DIR", str(cache_dir))
    monkeypatch.setenv("MUSE_CONFIGS_DIR", str(configs_dir))

    from utils.app_info_cache import AppInfoCache

    new_cache = AppInfoCache()
    _patch_app_info_cache_singleton(monkeypatch, new_cache)

    config_module = importlib.import_module("utils.config")
    _patch_config_singleton(monkeypatch, config_module.Config())

    import muse.muse_memory as mm

    new_memory = mm.MuseMemory()
    _patch_muse_memory_singleton(monkeypatch, new_memory)

    _reset_library_caches()
    _reset_playlist_history()


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
            title="Symphony No. 5 - I",
            album="Beethoven: Symphony No. 5",
            artist="Berlin Philharmonic",
            composer="Beethoven",
            _genre="Classical",
            _form="Symphony",
            _instrument="Orchestra",
        ),
        MockMediaTrack(
            filepath="track2.mp3",
            title="Symphony No. 5 - II",
            album="Beethoven: Symphony No. 5",
            artist="Berlin Philharmonic",
            composer="Beethoven",
            _genre="Classical",
            _form="Symphony",
            _instrument="Orchestra",
        ),
        MockMediaTrack(
            filepath="track3.mp3",
            title="The Four Seasons - Spring",
            album="Vivaldi: The Four Seasons",
            artist="Academy of St Martin",
            composer="Vivaldi",
            _genre="Classical",
            _form="Concerto",
            _instrument="Violin",
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
