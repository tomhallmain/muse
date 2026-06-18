"""Unit tests for extensions.radio_browser."""

import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _load_radio_browser():
    """Load radio_browser via importlib, stubbing only utils.logging_setup."""
    if "utils.logging_setup" not in sys.modules:
        stub = types.ModuleType("utils.logging_setup")
        stub.get_logger = lambda name: MagicMock()
        sys.modules["utils.logging_setup"] = stub
    if "utils" not in sys.modules:
        sys.modules["utils"] = types.ModuleType("utils")

    # Ensure the extensions namespace exists as a plain namespace package so
    # importlib can register the module without needing the real __init__.py.
    if "extensions" not in sys.modules:
        ns = types.ModuleType("extensions")
        ns.__path__ = [str(_ROOT / "extensions")]
        sys.modules["extensions"] = ns

    spec = importlib.util.spec_from_file_location(
        "extensions.radio_browser", _ROOT / "extensions" / "radio_browser.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["extensions.radio_browser"] = mod
    # Also attach as an attribute so patch() string lookup works if needed.
    sys.modules["extensions"].radio_browser = mod  # type: ignore[attr-defined]
    spec.loader.exec_module(mod)
    return mod


rb = _load_radio_browser()


# Reset module-level server cache before every test so they don't interfere.
import pytest

@pytest.fixture(autouse=True)
def reset_cached_server():
    rb._cached_server = ""
    yield
    rb._cached_server = ""


def _mock_response(data):
    """Return a context-manager mock that yields JSON-encoded *data*."""
    body = json.dumps(data).encode()
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ── Server resolution ─────────────────────────────────────────────────────────

def test_resolve_server_uses_dns():
    servers = [{"name": "test.api.example.com"}]
    with patch.object(rb.request, "urlopen", return_value=_mock_response(servers)):
        server = rb._resolve_server()
    assert server == "https://test.api.example.com"
    assert rb._cached_server == server


def test_resolve_server_cached_on_second_call():
    rb._cached_server = "https://cached.example.com"
    with patch.object(rb.request, "urlopen") as mock_open:
        server = rb._resolve_server()
    mock_open.assert_not_called()
    assert server == "https://cached.example.com"


def test_resolve_server_fallback_on_error():
    with patch.object(rb.request, "urlopen", side_effect=Exception("timeout")):
        server = rb._resolve_server()
    assert "radio-browser.info" in server


# ── search_stations ───────────────────────────────────────────────────────────

def test_search_stations_returns_list():
    rb._cached_server = "https://test.example.com"
    payload = [
        {
            "stationuuid": "abc",
            "name": "Jazz FM",
            "url_resolved": "http://stream.example.com",
            "codec": "MP3",
            "bitrate": 128,
            "country": "DE",
            "tags": "jazz",
            "votes": 42,
        }
    ]
    with patch.object(rb.request, "urlopen", return_value=_mock_response(payload)):
        results = rb.search_stations(query="jazz")
    assert isinstance(results, list)
    assert len(results) == 1
    assert results[0]["name"] == "Jazz FM"


def test_search_stations_passes_query_params():
    rb._cached_server = "https://test.example.com"
    captured_url = []

    def fake_urlopen(req, timeout=None):
        captured_url.append(req.full_url)
        return _mock_response([])

    with patch.object(rb.request, "urlopen", side_effect=fake_urlopen):
        rb.search_stations(query="Bach", tags="classical", country="AT", limit=25)

    assert len(captured_url) == 1
    url = captured_url[0]
    assert "name=Bach" in url
    assert "tag=classical" in url
    assert "country=AT" in url
    assert "limit=25" in url


# ── resolve_stream_url ────────────────────────────────────────────────────────

def test_resolve_stream_url_passthrough_for_non_playlist():
    url = "http://stream.example.com/radio"
    assert rb.resolve_stream_url(url) == url


def test_resolve_stream_url_m3u():
    m3u_content = b"#EXTM3U\nhttp://actual.stream.example.com/audio\n"
    resp = MagicMock()
    resp.read.return_value = m3u_content
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    with patch.object(rb.request, "urlopen", return_value=resp):
        result = rb.resolve_stream_url("http://example.com/playlist.m3u")
    assert result == "http://actual.stream.example.com/audio"


def test_resolve_stream_url_pls():
    pls_content = b"[playlist]\nFile1=http://pls.stream.example.com/\nTitle1=Radio\n"
    resp = MagicMock()
    resp.read.return_value = pls_content
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    with patch.object(rb.request, "urlopen", return_value=resp):
        result = rb.resolve_stream_url("http://example.com/radio.pls")
    assert result == "http://pls.stream.example.com/"


def test_resolve_stream_url_returns_original_on_fetch_error():
    url = "http://example.com/playlist.m3u8"
    with patch.object(rb.request, "urlopen", side_effect=Exception("timeout")):
        result = rb.resolve_stream_url(url)
    assert result == url


def test_resolve_stream_url_query_params_ignored_for_extension_check():
    url = "http://stream.example.com/listen?format=mp3"
    assert rb.resolve_stream_url(url) == url
