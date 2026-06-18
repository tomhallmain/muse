"""Radio Browser API client (https://www.radio-browser.info/).

DNS-based server discovery, station search, and playlist URL resolution.
All state is module-level and cached for the process lifetime.
"""

import json
import random
from urllib import request
from urllib.error import URLError
from urllib.parse import urlencode

from utils.logging_setup import get_logger

logger = get_logger(__name__)

_USER_AGENT = "Muse/1.0"
_DISCOVERY_URL = "https://all.api.radio-browser.info/json/servers"
_cached_server: str = ""


def _resolve_server() -> str:
    global _cached_server
    if _cached_server:
        return _cached_server
    try:
        req = request.Request(_DISCOVERY_URL, headers={"User-Agent": _USER_AGENT})
        with request.urlopen(req, timeout=5) as resp:
            servers = json.loads(resp.read().decode())
            host = random.choice(servers)["name"]
            _cached_server = f"https://{host}"
            logger.debug("Radio Browser server resolved: %s", _cached_server)
    except Exception as exc:
        logger.warning("Radio Browser DNS discovery failed, using fallback: %s", exc)
        _cached_server = "https://de1.api.radio-browser.info"
    return _cached_server


def _api_get(path: str, params: dict | None = None) -> list:
    global _cached_server
    server = _resolve_server()
    url = f"{server}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    req = request.Request(
        url,
        headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except URLError:
        _cached_server = ""  # force re-resolution on next call
        raise


def search_stations(
    query: str = "",
    tags: str = "",
    country: str = "",
    limit: int = 50,
) -> list[dict]:
    """Search the Radio Browser catalogue.

    Returns a list of station dicts; each contains at minimum:
    ``stationuuid``, ``name``, ``url_resolved``, ``codec``, ``bitrate``,
    ``country``, ``tags``, ``votes``.
    """
    params: dict = {
        "limit": limit,
        "hidebroken": "true",
        "order": "votes",
        "reverse": "true",
    }
    if query:
        params["name"] = query
    if tags:
        params["tag"] = tags
    if country:
        params["country"] = country
    return _api_get("/json/stations/search", params)


def get_station_by_uuid(uuid: str) -> "dict | None":
    """Return the Radio Browser station dict for *uuid*, or ``None`` if not found."""
    try:
        results = _api_get(f"/json/stations/byuuid/{uuid}")
        return results[0] if results else None
    except Exception as exc:
        logger.warning("Failed to fetch station by UUID %s: %s", uuid, exc)
        return None


def resolve_stream_url(url: str) -> str:
    """Return the direct stream URL, following m3u/pls/xspf playlists if needed."""
    base = url.lower().split("?")[0]
    if not any(base.endswith(ext) for ext in (".m3u", ".m3u8", ".pls", ".xspf")):
        return url
    try:
        req = request.Request(url, headers={"User-Agent": _USER_AGENT})
        with request.urlopen(req, timeout=5) as resp:
            content = resp.read().decode("utf-8", errors="replace")
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("http"):
                return line
            # .pls format: File1=http://...
            if "=" in line:
                val = line.split("=", 1)[1].strip()
                if val.startswith("http"):
                    return val
    except Exception as exc:
        logger.warning("Failed to resolve playlist URL %s: %s", url, exc)
    return url
