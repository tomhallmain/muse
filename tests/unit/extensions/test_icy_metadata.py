"""Unit tests for extensions.icy_metadata."""

import importlib.util
import io
import sys
import threading
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _load_icy_metadata():
    """Load icy_metadata via importlib, stubbing only utils.logging_setup."""
    if "utils.logging_setup" not in sys.modules:
        stub = types.ModuleType("utils.logging_setup")
        stub.get_logger = lambda name: MagicMock()
        sys.modules["utils.logging_setup"] = stub
    if "utils" not in sys.modules:
        sys.modules["utils"] = types.ModuleType("utils")

    if "extensions" not in sys.modules:
        ns = types.ModuleType("extensions")
        ns.__path__ = [str(_ROOT / "extensions")]
        sys.modules["extensions"] = ns

    spec = importlib.util.spec_from_file_location(
        "extensions.icy_metadata", _ROOT / "extensions" / "icy_metadata.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["extensions.icy_metadata"] = mod
    spec.loader.exec_module(mod)
    return mod


icy = _load_icy_metadata()

parse_stream_title = icy.parse_stream_title
poll_icy_metadata = icy.poll_icy_metadata


# ── Helpers ───────────────────────────────────────────────────────────────────

class _FakeResp:
    """Minimal HTTP response that reads from a BytesIO buffer."""

    def __init__(self, headers: dict, body: bytes):
        self._headers = {k.lower(): v for k, v in headers.items()}
        self._body = io.BytesIO(body)

    def getheader(self, name: str):
        return self._headers.get(name.lower())

    def read(self, n: int = -1) -> bytes:
        return self._body.read(n)


def _icy_body(metaint: int, *titles: str) -> bytes:
    """Build an ICY stream body: metaint audio bytes + metadata block per title."""
    buf = bytearray()
    for title in titles:
        buf.extend(b"\x00" * metaint)
        meta = f"StreamTitle='{title}';"
        meta_bytes = meta.encode("utf-8")
        length = (len(meta_bytes) + 15) // 16
        padded = meta_bytes + b"\x00" * (length * 16 - len(meta_bytes))
        buf.append(length)
        buf.extend(padded)
    return bytes(buf)


def _mock_conn(metaint: int, *titles: str):
    """Return a mock HTTPConnection whose response carries the given ICY titles."""
    resp = _FakeResp({"icy-metaint": str(metaint)}, _icy_body(metaint, *titles))
    conn = MagicMock()
    conn.getresponse.return_value = resp
    return conn


# ── parse_stream_title ────────────────────────────────────────────────────────

def test_parse_artist_title():
    assert parse_stream_title("Adele - Hello") == ("Adele", "Hello")


def test_parse_title_only():
    assert parse_stream_title("Station Jingle") == ("", "Station Jingle")


def test_parse_empty_string():
    assert parse_stream_title("") == ("", "")


def test_parse_whitespace_only():
    assert parse_stream_title("   ") == ("", "")


def test_parse_multiple_dashes_splits_on_first():
    # "J.S. Bach - Suite No.1 - BWV 1007" → ("J.S. Bach", "Suite No.1 - BWV 1007")
    assert parse_stream_title("J.S. Bach - Suite No.1 - BWV 1007") == (
        "J.S. Bach",
        "Suite No.1 - BWV 1007",
    )


def test_parse_strips_whitespace():
    assert parse_stream_title("  Artist  -  Title  ") == ("Artist", "Title")


# ── poll_icy_metadata — no ICY header ────────────────────────────────────────

def test_poll_returns_when_no_metaint_header():
    """Function returns immediately when station has no icy-metaint header."""
    resp = _FakeResp({}, b"")
    conn = MagicMock()
    conn.getresponse.return_value = resp

    called = []
    stop = threading.Event()
    with patch.object(icy.http.client, "HTTPConnection", return_value=conn):
        poll_icy_metadata("http://stream.example.com/", stop, lambda *a: called.append(a))

    assert called == []


# ── poll_icy_metadata — title change callback ─────────────────────────────────

def test_poll_calls_on_title_change():
    """on_title_change is called with (artist, title) when StreamTitle changes."""
    received = []
    stop = threading.Event()

    def on_change(artist, title):
        received.append((artist, title))
        stop.set()

    conn = _mock_conn(4, "Artist - Song")
    with patch.object(icy.http.client, "HTTPConnection", return_value=conn):
        poll_icy_metadata("http://stream.example.com/", stop, on_change)

    assert received == [("Artist", "Song")]


def test_poll_multiple_titles_fires_each_change():
    """Callback fires once per distinct StreamTitle in the body."""
    received = []
    stop = threading.Event()
    titles_to_send = ["Alpha - One", "Beta - Two", "Gamma - Three"]
    expected = [("Alpha", "One"), ("Beta", "Two"), ("Gamma", "Three")]

    def on_change(artist, title):
        received.append((artist, title))
        if len(received) == len(expected):
            stop.set()

    conn = _mock_conn(4, *titles_to_send)
    with patch.object(icy.http.client, "HTTPConnection", return_value=conn):
        poll_icy_metadata("http://stream.example.com/", stop, on_change)

    assert received == expected


def test_poll_no_duplicate_callback_for_same_title():
    """Repeated identical StreamTitle blocks do not re-fire the callback."""
    received = []
    stop = threading.Event()

    def on_change(artist, title):
        received.append((artist, title))
        if len(received) == 1:
            stop.set()

    # Same title twice — only the first should fire
    conn = _mock_conn(4, "Artist - Song", "Artist - Song")
    with patch.object(icy.http.client, "HTTPConnection", return_value=conn):
        poll_icy_metadata("http://stream.example.com/", stop, on_change)

    assert len(received) == 1


def test_poll_skips_empty_metadata_blocks():
    """Empty StreamTitle (metadata block with no content) is silently skipped."""
    received = []
    stop = threading.Event()

    # Build a body with an empty metadata block followed by a real one
    metaint = 4
    audio = b"\x00" * metaint
    # Empty metadata: length byte = 0
    empty_block = audio + bytes([0])
    # Real metadata block
    meta_str = "StreamTitle='Artist - Song';"
    meta_bytes = meta_str.encode()
    length = (len(meta_bytes) + 15) // 16
    padded = meta_bytes + b"\x00" * (length * 16 - len(meta_bytes))
    real_block = audio + bytes([length]) + padded

    body = empty_block + real_block

    resp = _FakeResp({"icy-metaint": str(metaint)}, body)
    conn = MagicMock()
    conn.getresponse.return_value = resp

    def on_change(artist, title):
        received.append((artist, title))
        stop.set()

    with patch.object(icy.http.client, "HTTPConnection", return_value=conn):
        poll_icy_metadata("http://stream.example.com/", stop, on_change)

    assert received == [("Artist", "Song")]


# ── poll_icy_metadata — reconnect on error ────────────────────────────────────

def test_poll_reconnects_on_connection_error():
    """A connection error causes a retry; second connection delivers metadata."""
    received = []
    stop = threading.Event()
    call_count = [0]

    def make_conn(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            bad = MagicMock()
            bad.request.side_effect = ConnectionError("refused")
            return bad
        # Second attempt: deliver one title then let the body run out naturally
        def on_change(artist, title):
            received.append((artist, title))
            stop.set()

        return _mock_conn(4, "Reconnect - Track")

    def on_change(artist, title):
        received.append((artist, title))
        stop.set()

    with patch.object(icy.http.client, "HTTPConnection", side_effect=make_conn):
        with patch.object(icy, "_RECONNECT_BASE_DELAY", 0.0):
            poll_icy_metadata("http://stream.example.com/", stop, on_change)

    assert call_count[0] == 2
    assert received == [("Reconnect", "Track")]


# ── poll_icy_metadata — stop event ────────────────────────────────────────────

def test_poll_stops_when_event_set_before_call():
    """If stop_event is already set, the function returns without connecting."""
    stop = threading.Event()
    stop.set()

    conn = MagicMock()
    with patch.object(icy.http.client, "HTTPConnection", return_value=conn):
        poll_icy_metadata("http://stream.example.com/", stop, lambda *a: None)

    conn.request.assert_not_called()
