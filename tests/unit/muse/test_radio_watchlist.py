"""Unit tests for muse.radio_watchlist."""

import importlib.util
import sys
import threading
import time
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


def _load_watchlist():
    """Load muse.radio_watchlist with minimal stubs."""
    for mod in ["utils.logging_setup", "utils.logging"]:
        if mod not in sys.modules:
            stub = types.ModuleType(mod)
            stub.get_logger = lambda name: MagicMock()
            sys.modules[mod] = stub

    if "utils" not in sys.modules:
        _stub("utils")

    # Stub app_info_cache
    if "utils.app_info_cache" not in sys.modules:
        cache_stub = _stub("utils.app_info_cache")
        _store = {}
        cache = MagicMock()
        cache.get = lambda k, d=None: _store.get(k, d)
        cache.set = lambda k, v: _store.update({k: v})
        cache_stub.app_info_cache = cache

    # Stub config with watchlist-specific defaults
    if "utils.config" not in sys.modules:
        config_stub = _stub("utils.config")
        cfg = MagicMock()
        cfg.radio_watchlist_enabled = True
        cfg.radio_watchlist_cooldown_minutes = 30
        cfg.radio_watchlist_max_stations = 10
        config_stub.config = cfg

    if "muse" not in sys.modules:
        _stub("muse")

    spec = importlib.util.spec_from_file_location(
        "muse.radio_watchlist", _ROOT / "muse" / "radio_watchlist.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["muse.radio_watchlist"] = mod
    spec.loader.exec_module(mod)
    return mod


wl = _load_watchlist()
WatchEntry = wl.WatchEntry
WatchlistService = wl.WatchlistService


# ── WatchEntry.matches ────────────────────────────────────────────────────────

def test_matches_artist_substring():
    entry = WatchEntry(label="Bach", station_uuid="x", match_artist="bach")
    assert entry.matches("J.S. Bach", "Cello Suite No.1") is True


def test_matches_artist_case_insensitive():
    entry = WatchEntry(label="Bach", station_uuid="x", match_artist="BACH")
    assert entry.matches("bach", "something") is True


def test_no_match_wrong_artist():
    entry = WatchEntry(label="Bach", station_uuid="x", match_artist="beethoven")
    assert entry.matches("Bach", "Symphony") is False


def test_matches_title_substring():
    entry = WatchEntry(label="Suite", station_uuid="x", match_title="cello suite")
    assert entry.matches("Bach", "Cello Suite No.1") is True


def test_matches_both_artist_and_title():
    entry = WatchEntry(
        label="Bach Suites",
        station_uuid="x",
        match_artist="bach",
        match_title="suite",
    )
    assert entry.matches("J.S. Bach", "Suite No.1 in G major") is True


def test_requires_both_when_both_set():
    entry = WatchEntry(
        label="Bach Suites",
        station_uuid="x",
        match_artist="bach",
        match_title="symphony",
    )
    # title doesn't match
    assert entry.matches("Bach", "Cello Suite") is False


def test_matches_match_any():
    entry = WatchEntry(label="Classical", station_uuid="x", match_any="classic")
    assert entry.matches("Vienna Orchestra", "Classical Music") is True


def test_match_any_against_full_string():
    entry = WatchEntry(label="Test", station_uuid="x", match_any="bach - suite")
    assert entry.matches("Bach", "Suite No.1") is True


def test_no_match_empty_criteria():
    # Entry with no criteria is not active → never matches
    entry = WatchEntry(label="Empty", station_uuid="x")
    assert entry.matches("Bach", "Anything") is False


def test_disabled_entry_never_matches():
    entry = WatchEntry(
        label="Disabled", station_uuid="x", match_artist="bach", enabled=False
    )
    assert entry.matches("Bach", "Suite") is False


# ── WatchEntry serialisation ──────────────────────────────────────────────────

def test_round_trip_to_from_dict():
    original = WatchEntry(
        label="Test",
        station_uuid="abc123",
        station_name="Test Radio",
        match_artist="bach",
        match_title="suite",
        match_any="",
        enabled=True,
    )
    recovered = WatchEntry.from_dict(original.to_dict())
    assert recovered == original


def test_from_dict_ignores_unknown_keys():
    d = {"label": "L", "station_uuid": "u", "future_field": "x"}
    entry = WatchEntry.from_dict(d)
    assert entry.label == "L"
    assert not hasattr(entry, "future_field")


# ── WatchlistService cooldown ─────────────────────────────────────────────────

def _make_service():
    svc = WatchlistService()
    svc._app_actions = MagicMock()
    svc._app_actions.get_current_track.return_value = None
    return svc


def test_cooldown_suppresses_retrigger():
    svc = _make_service()
    entry = WatchEntry(label="Bach", station_uuid="uuid1", match_artist="bach")

    # Fake _switch_to_station so it doesn't hit the network
    switch_calls = []
    svc._switch_to_station = lambda *a: switch_calls.append(a)

    svc._on_title_change("uuid1", [entry], "Bach", "Cello Suite")
    svc._on_title_change("uuid1", [entry], "Bach", "Cello Suite")

    assert len(switch_calls) == 1, "Second call within cooldown should be suppressed"


def test_cooldown_allows_after_expiry():
    svc = _make_service()
    entry = WatchEntry(label="Bach", station_uuid="uuid1", match_artist="bach")
    switch_calls = []
    svc._switch_to_station = lambda *a: switch_calls.append(a)

    svc._on_title_change("uuid1", [entry], "Bach", "Cello Suite")

    # Force cooldown to expire by backdating the recorded time
    key = ("uuid1", "Bach")
    with svc._lock:
        svc._cooldowns[key] = time.monotonic() - 99999.0

    svc._on_title_change("uuid1", [entry], "Bach", "Allemande")

    assert len(switch_calls) == 2, "Call after cooldown expiry should fire"


def test_no_switch_when_already_on_station():
    svc = _make_service()
    entry = WatchEntry(label="Bach", station_uuid="uuid1", match_artist="bach")

    current = MagicMock()
    current.station_uuid = "uuid1"
    svc._app_actions.get_current_track.return_value = current

    switch_calls = []
    svc._switch_to_station = lambda *a: switch_calls.append(a)

    svc._on_title_change("uuid1", [entry], "Bach", "Suite")

    assert switch_calls == [], "Should not switch when already on the matching station"


# ── WatchlistService thread deduplication ─────────────────────────────────────

def test_duplicate_station_uuids_start_one_thread():
    """Two entries sharing the same UUID must share one poll thread."""
    svc = _make_service()

    entry_a = WatchEntry(label="A", station_uuid="same-uuid", match_artist="bach")
    entry_b = WatchEntry(label="B", station_uuid="same-uuid", match_title="suite")

    wl.save_entries([entry_a, entry_b])

    started_uuids = []

    def fake_start_poll(uuid, entries):
        started_uuids.append(uuid)
        ev = threading.Event()
        svc._stop_events[uuid] = ev
        t = threading.Thread(target=lambda: ev.wait(), daemon=True)
        svc._threads[uuid] = t
        t.start()

    svc._start_poll_thread = fake_start_poll
    svc._launch_threads()
    svc.stop()

    assert started_uuids.count("same-uuid") == 1, (
        f"Expected one thread for 'same-uuid', got {started_uuids.count('same-uuid')}"
    )


def test_max_stations_cap():
    """Service honours radio_watchlist_max_stations."""
    svc = _make_service()

    # Override config cap to 2
    original = wl.config.radio_watchlist_max_stations
    wl.config.radio_watchlist_max_stations = 2

    entries = [
        WatchEntry(label=str(i), station_uuid=f"uuid{i}", match_artist="bach")
        for i in range(5)
    ]
    wl.save_entries(entries)

    started_uuids = []

    def fake_start_poll(uuid, _entries):
        started_uuids.append(uuid)
        svc._stop_events[uuid] = threading.Event()
        svc._threads[uuid] = threading.Thread(
            target=lambda: None, daemon=True
        )

    svc._start_poll_thread = fake_start_poll
    svc._launch_threads()

    wl.config.radio_watchlist_max_stations = original

    assert len(started_uuids) <= 2, (
        f"Expected at most 2 threads, started {len(started_uuids)}"
    )
