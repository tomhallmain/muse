"""Unit tests for library_data.network_media_track.NetworkMediaTrack."""

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


def _load_nmt():
    """Load NetworkMediaTrack with minimal stubs to avoid pulling in the full app."""
    # Stub out heavy dependencies
    for mod in [
        "music_tag", "pymediainfo", "vlc", "ffmpeg",
        "utils.ffmpeg_handler", "utils.utils", "utils.config",
        "utils.app_info_cache",
    ]:
        if mod not in sys.modules:
            sys.modules[mod] = MagicMock()

    if "utils" not in sys.modules:
        _stub("utils")
    if "utils.logging_setup" not in sys.modules:
        ls = _stub("utils.logging_setup")
        ls.get_logger = lambda name: MagicMock()
    if "utils.translations" not in sys.modules:
        t = _stub("utils.translations")
        t.I18N = MagicMock()
        t.I18N._ = lambda s: s

    # Stub library_data.media_track just enough
    if "library_data" not in sys.modules:
        _stub("library_data")
    if "library_data.media_track" not in sys.modules:
        mt = _stub("library_data.media_track")

        class _FakeMediaTrack:
            def is_stream(self):
                return False

        mt.MediaTrack = _FakeMediaTrack

    spec = importlib.util.spec_from_file_location(
        "library_data.network_media_track",
        _ROOT / "library_data" / "network_media_track.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["library_data.network_media_track"] = mod
    spec.loader.exec_module(mod)
    return mod


_nmt_mod = _load_nmt()
NetworkMediaTrack = _nmt_mod.NetworkMediaTrack

_URL = "http://stream.example.com/radio"
_NAME = "Example Radio"


def _make(**kwargs):
    defaults = {"url": _URL, "name": _NAME}
    defaults.update(kwargs)
    return NetworkMediaTrack(**defaults)


# ── Basic construction ────────────────────────────────────────────────────────

def test_filepath_is_url():
    t = _make()
    assert t.filepath == _URL


def test_title_is_name():
    t = _make()
    assert t.title == _NAME


def test_station_metadata_stored():
    t = _make(station_uuid="abc123", codec="MP3", bitrate=128, tags="jazz", country="DE")
    assert t.station_uuid == "abc123"
    assert t.stream_codec == "MP3"
    assert t.stream_bitrate == 128
    assert t.genre == "jazz"
    assert t.country == "DE"


# ── is_invalid ────────────────────────────────────────────────────────────────

def test_is_invalid_false_for_http_url():
    assert _make().is_invalid() is False


def test_is_invalid_true_for_empty_url():
    t = NetworkMediaTrack(url="", name="X")
    assert t.is_invalid() is True


def test_is_invalid_true_for_non_http_url():
    t = NetworkMediaTrack(url="ftp://nope.example.com", name="X")
    assert t.is_invalid() is True


# ── is_stream ─────────────────────────────────────────────────────────────────

def test_is_stream_true():
    assert _make().is_stream() is True


def test_is_stream_flag_attribute():
    assert _make()._is_stream is True


# ── track length / video ──────────────────────────────────────────────────────

def test_get_track_length_negative():
    assert _make().get_track_length() == -1.0


def test_get_is_video_false():
    assert _make().get_is_video() is False


# ── parent filepath ───────────────────────────────────────────────────────────

def test_get_parent_filepath_returns_url():
    assert _make().get_parent_filepath() == _URL


# ── album artwork / volume ────────────────────────────────────────────────────

def test_get_album_artwork_none():
    assert _make().get_album_artwork() is None


def test_get_volume_returns_defaults():
    mean, peak = _make().get_volume()
    assert mean == -9999.0
    assert peak == -9999.0


# ── equality / hash ───────────────────────────────────────────────────────────

def test_eq_same_url():
    a = _make()
    b = _make()
    assert a == b


def test_eq_different_url():
    a = _make(url="http://a.example.com/")
    b = _make(url="http://b.example.com/")
    assert a != b


def test_hash_consistent():
    t = _make()
    assert hash(t) == hash(t)


def test_hash_equal_objects_match():
    a = _make()
    b = _make()
    assert hash(a) == hash(b)


def test_str_contains_name_and_url():
    s = str(_make())
    assert _NAME in s
    assert _URL in s
