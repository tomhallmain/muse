"""
Read-only Last.fm Web Services client.

Uses GET requests with an API key only (no user session). Suitable for browsing
public profiles: library tracks/albums/artists, loved tracks, and profile info.

API reference: https://www.last.fm/api
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Union

import requests

from utils.config import config
from utils.logging_setup import get_logger

logger = get_logger(__name__)

API_ROOT = "https://ws.audioscrobbler.com/2.0/"
DEFAULT_USER_AGENT = "tomhallmain-Muse-App/1.0"
DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 1000
DEFAULT_PAGE_DELAY_SECONDS = 0.25

# Last.fm method names are picky; keep canonical spelling but allow tolerant callers.
_METHOD_ALIASES: dict[str, str] = {
    "user.getinfo": "user.getInfo",
    "user.getrecenttracks": "user.getRecentTracks",
    "user.gettoptracks": "user.getTopTracks",
    "user.gettopalbums": "user.getTopAlbums",
    "user.gettopartists": "user.getTopArtists",
    "user.getlovedtracks": "user.getLovedTracks",
    "library.getartists": "library.getArtists",
}


class LastFmAPIError(Exception):
    """Raised when the Last.fm API returns an error or the response is invalid."""

    def __init__(self, message: str, code: Optional[int] = None):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class LastFmPagination:
    user: str
    page: int
    per_page: int
    total_pages: int
    total: int


@dataclass(frozen=True)
class LastFmUser:
    name: str
    url: str
    country: Optional[str] = None
    playcount: Optional[int] = None
    artist_count: Optional[int] = None
    album_count: Optional[int] = None
    track_count: Optional[int] = None
    image_url: Optional[str] = None
    registered_unixtime: Optional[int] = None


@dataclass(frozen=True)
class LastFmLibraryArtist:
    name: str
    playcount: int
    rank: Optional[int] = None
    url: Optional[str] = None
    mbid: Optional[str] = None
    tagcount: Optional[int] = None
    image_url: Optional[str] = None


@dataclass(frozen=True)
class LastFmLibraryAlbum:
    name: str
    artist: str
    playcount: int
    url: Optional[str] = None
    mbid: Optional[str] = None
    tagcount: Optional[int] = None
    image_url: Optional[str] = None


@dataclass(frozen=True)
class LastFmLibraryTrack:
    name: str
    artist: str
    playcount: int
    album: Optional[str] = None
    url: Optional[str] = None
    mbid: Optional[str] = None
    tagcount: Optional[int] = None
    image_url: Optional[str] = None
    rank: Optional[int] = None


@dataclass
class LastFmLibraryArtistsPage:
    pagination: LastFmPagination
    artists: List[LastFmLibraryArtist] = field(default_factory=list)


@dataclass
class LastFmLibraryAlbumsPage:
    pagination: LastFmPagination
    albums: List[LastFmLibraryAlbum] = field(default_factory=list)


@dataclass
class LastFmLibraryTracksPage:
    pagination: LastFmPagination
    tracks: List[LastFmLibraryTrack] = field(default_factory=list)


@dataclass
class LastFmLovedTracksPage:
    pagination: LastFmPagination
    tracks: List[LastFmLibraryTrack] = field(default_factory=list)


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("#text") or value.get("name")
    return str(value)


def _int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _image_url(images: Any, preferred_sizes: Sequence[str] = ("extralarge", "large", "medium", "small")) -> Optional[str]:
    for item in _as_list(images):
        if not isinstance(item, dict):
            continue
        if item.get("size") in preferred_sizes:
            url = _text(item)
            if url:
                return url
    for item in _as_list(images):
        if isinstance(item, dict):
            url = _text(item)
            if url:
                return url
    return None


def _artist_name(artist: Any) -> str:
    if isinstance(artist, dict):
        return _text(artist.get("name")) or ""
    return _text(artist) or ""


def _parse_pagination(attr: Dict[str, Any], default_user: str) -> LastFmPagination:
    return LastFmPagination(
        user=attr.get("user", default_user),
        page=_int(attr.get("page"), 1),
        per_page=_int(attr.get("perPage") or attr.get("perpage"), DEFAULT_PAGE_LIMIT),
        total_pages=_int(attr.get("totalPages") or attr.get("totalpages"), 1),
        total=_int(attr.get("total"), 0),
    )


class LastFmReadAPI:
    """
    Read-only Last.fm API client for public user libraries.

    Configure ``lastfm_api_key`` in ``config.json``. Apply for a key at
    https://www.last.fm/api/account/create
    """

    def __init__(self, api_key: Optional[str] = None, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self.api_key = api_key if api_key is not None else config.lastfm_api_key
        self.user_agent = user_agent
        self._session = requests.Session()
        self._session.headers["User-Agent"] = user_agent

    def _call(self, method: str, **params: Any) -> Dict[str, Any]:
        if not self.api_key:
            raise LastFmAPIError(
                "No Last.fm API key configured. Set lastfm_api_key in config.json."
            )

        method = (method or "").strip()
        method = _METHOD_ALIASES.get(method.lower(), method)

        query = {
            "method": method,
            "api_key": self.api_key,
            "format": "json",
        }
        for key, value in params.items():
            if value is not None:
                query[key] = value

        try:
            response = self._session.get(API_ROOT, params=query, timeout=30)
        except requests.RequestException as exc:
            logger.error("Last.fm request failed for %s: %s", method, exc)
            raise LastFmAPIError(str(exc)) from exc

        try:
            payload = response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict) and "error" in payload:
            err_code = payload.get("error")
            raise LastFmAPIError(
                payload.get("message", "Unknown Last.fm API error"),
                code=int(err_code) if err_code is not None else None,
            )

        if response.status_code >= 400:
            snippet = (response.text or "").strip()
            if len(snippet) > 300:
                snippet = snippet[:300] + "..."
            raise LastFmAPIError(
                f"HTTP {response.status_code} for {method}. Response: {snippet}"
            )

        if not isinstance(payload, dict):
            raise LastFmAPIError(f"Invalid JSON from Last.fm ({method})")

        return payload

    def get_user_info(self, username: str) -> LastFmUser:
        """Profile metadata for a public user (``user.getInfo``)."""
        payload = self._call("user.getInfo", user=username)
        user = payload.get("user") or {}
        counts = user.get("counts") or {}
        registered = user.get("registered") or {}
        return LastFmUser(
            name=_text(user.get("name")) or username,
            url=_text(user.get("url")) or "",
            country=_text(user.get("country")),
            playcount=_int(user.get("playcount"), 0) or None,
            artist_count=_int(counts.get("artists"), 0) or None,
            album_count=_int(counts.get("albums"), 0) or None,
            track_count=_int(counts.get("tracks"), 0) or None,
            image_url=_image_url(user.get("image")),
            registered_unixtime=_int(registered.get("unixtime"), 0) or None,
        )

    def get_library_artists(
        self,
        username: str,
        page: int = 1,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> LastFmLibraryArtistsPage:
        """Paginated artists in a user's library (``library.getArtists``)."""
        payload = self._call(
            "library.getArtists",
            user=username,
            page=page,
            limit=self._clamp_limit(limit),
        )
        root = payload.get("artists") or {}
        attr = root.get("@attr") or {}
        artists: List[LastFmLibraryArtist] = []
        for item in _as_list(root.get("artist")):
            if not isinstance(item, dict):
                continue
            artists.append(
                LastFmLibraryArtist(
                    name=_text(item.get("name")) or "",
                    playcount=_int(item.get("playcount")),
                    rank=_int((item.get("@attr") or {}).get("rank"), 0) or _int(item.get("rank"), 0) or None,
                    url=_text(item.get("url")),
                    mbid=_text(item.get("mbid")) or None,
                    tagcount=_int(item.get("tagcount"), 0) or None,
                    image_url=_image_url(item.get("image")),
                )
            )
        return LastFmLibraryArtistsPage(
            pagination=_parse_pagination(attr, username),
            artists=artists,
        )

    def get_library_albums(
        self,
        username: str,
        page: int = 1,
        limit: int = DEFAULT_PAGE_LIMIT,
        period: str = "overall",
    ) -> LastFmLibraryAlbumsPage:
        """Paginated top albums for a user (``user.getTopAlbums``)."""
        payload = self._call(
            "user.getTopAlbums",
            user=username,
            page=page,
            limit=self._clamp_limit(limit),
            period=period,
        )
        root = payload.get("topalbums") or {}
        attr = root.get("@attr") or {}
        albums: List[LastFmLibraryAlbum] = []
        for item in _as_list(root.get("album")):
            if not isinstance(item, dict):
                continue
            albums.append(
                LastFmLibraryAlbum(
                    name=_text(item.get("name")) or "",
                    artist=_artist_name(item.get("artist")),
                    playcount=_int(item.get("playcount")),
                    url=_text(item.get("url")),
                    mbid=_text(item.get("mbid")) or None,
                    tagcount=None,
                    image_url=_image_url(item.get("image")),
                )
            )
        return LastFmLibraryAlbumsPage(
            pagination=_parse_pagination(attr, username),
            albums=albums,
        )

    def get_library_tracks(
        self,
        username: str,
        page: int = 1,
        limit: int = DEFAULT_PAGE_LIMIT,
        period: str = "overall",
    ) -> LastFmLibraryTracksPage:
        """Paginated top tracks for a user (``user.getTopTracks``)."""
        payload = self._call(
            "user.getTopTracks",
            user=username,
            page=page,
            limit=self._clamp_limit(limit),
            period=period,
        )
        root = payload.get("toptracks") or {}
        attr = root.get("@attr") or {}
        tracks: List[LastFmLibraryTrack] = []
        for item in _as_list(root.get("track")):
            if not isinstance(item, dict):
                continue
            tracks.append(
                LastFmLibraryTrack(
                    name=_text(item.get("name")) or "",
                    artist=_artist_name(item.get("artist")),
                    playcount=_int(item.get("playcount")),
                    album=None,
                    url=_text(item.get("url")),
                    mbid=_text(item.get("mbid")) or None,
                    tagcount=None,
                    image_url=_image_url(item.get("image")),
                    rank=_int((item.get("@attr") or {}).get("rank"), 0) or None,
                )
            )
        return LastFmLibraryTracksPage(
            pagination=_parse_pagination(attr, username),
            tracks=tracks,
        )

    def get_loved_tracks(
        self,
        username: str,
        page: int = 1,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> LastFmLovedTracksPage:
        """Tracks the user has loved (``user.getLovedTracks``), public profiles only."""
        payload = self._call(
            "user.getLovedTracks",
            user=username,
            page=page,
            limit=self._clamp_limit(limit),
        )
        root = payload.get("lovedtracks") or {}
        attr = root.get("@attr") or {}
        tracks: List[LastFmLibraryTrack] = []
        for item in _as_list(root.get("track")):
            if not isinstance(item, dict):
                continue
            tracks.append(self._parse_library_track(item))
        return LastFmLovedTracksPage(
            pagination=_parse_pagination(attr, username),
            tracks=tracks,
        )

    def iter_library_tracks(
        self,
        username: str,
        limit: int = DEFAULT_PAGE_LIMIT,
        period: str = "overall",
        max_pages: Optional[int] = None,
        page_delay_seconds: float = DEFAULT_PAGE_DELAY_SECONDS,
    ) -> Iterator[LastFmLibraryTrack]:
        """Yield top tracks for a user, paging through ``user.getTopTracks``."""
        yield from self._iter_pages(
            fetch=lambda page: self.get_library_tracks(
                username, page=page, limit=limit, period=period
            ),
            items_attr="tracks",
            max_pages=max_pages,
            page_delay_seconds=page_delay_seconds,
        )

    def iter_library_albums(
        self,
        username: str,
        limit: int = DEFAULT_PAGE_LIMIT,
        period: str = "overall",
        max_pages: Optional[int] = None,
        page_delay_seconds: float = DEFAULT_PAGE_DELAY_SECONDS,
    ) -> Iterator[LastFmLibraryAlbum]:
        """Yield top albums for a user, paging through ``user.getTopAlbums``."""
        yield from self._iter_pages(
            fetch=lambda page: self.get_library_albums(
                username, page=page, limit=limit, period=period
            ),
            items_attr="albums",
            max_pages=max_pages,
            page_delay_seconds=page_delay_seconds,
        )

    def iter_library_artists(
        self,
        username: str,
        limit: int = DEFAULT_PAGE_LIMIT,
        max_pages: Optional[int] = None,
        page_delay_seconds: float = DEFAULT_PAGE_DELAY_SECONDS,
    ) -> Iterator[LastFmLibraryArtist]:
        """Yield every artist in a user's library."""
        yield from self._iter_pages(
            fetch=lambda page: self.get_library_artists(username, page=page, limit=limit),
            items_attr="artists",
            max_pages=max_pages,
            page_delay_seconds=page_delay_seconds,
        )

    @staticmethod
    def _clamp_limit(limit: int) -> int:
        return max(1, min(int(limit), MAX_PAGE_LIMIT))

    @staticmethod
    def _parse_library_track(item: Dict[str, Any]) -> LastFmLibraryTrack:
        attr = item.get("@attr") or {}
        return LastFmLibraryTrack(
            name=_text(item.get("name")) or "",
            artist=_artist_name(item.get("artist")),
            playcount=_int(item.get("playcount")),
            album=_text(item.get("album")) or None,
            url=_text(item.get("url")),
            mbid=_text(item.get("mbid")) or None,
            tagcount=_int(item.get("tagcount"), 0) or None,
            image_url=_image_url(item.get("image")),
            rank=_int(attr.get("rank"), 0) or None,
        )

    def _iter_pages(
        self,
        fetch: Any,
        items_attr: str,
        max_pages: Optional[int],
        page_delay_seconds: float,
    ) -> Iterator[Any]:
        page = 1
        pages_fetched = 0
        while True:
            result = fetch(page)
            for item in getattr(result, items_attr):
                yield item

            pages_fetched += 1
            pagination = result.pagination
            if page >= pagination.total_pages:
                break
            if max_pages is not None and pages_fetched >= max_pages:
                break
            page += 1
            if page_delay_seconds > 0:
                time.sleep(page_delay_seconds)


_LASTFM_CACHE_FILE = Path(__file__).resolve().parent.parent / "configs" / "lastfm_cache.json.gz"
_lastfm_cache_instance: Optional[LastFmLibraryCache] = None


def get_lastfm_cache() -> LastFmLibraryCache:
    """Return the process-wide singleton Last.fm library cache (lazily loaded)."""
    global _lastfm_cache_instance
    if _lastfm_cache_instance is None:
        _lastfm_cache_instance = LastFmLibraryCache()
    return _lastfm_cache_instance


class LastFmLibraryCache:
    """
    Persistent cache of Last.fm library data keyed by username.

    Backed by the lfm_tracks and lfm_scopes tables in configs/muse_library.db.
    set_scope() writes and commits immediately; save() is a no-op retained for
    interface compatibility.

    The path argument is retained for backward compatibility but unused.
    """

    # Fields retained per item type (image URLs and tag counts omitted).
    _TRACK_FIELDS  = ("name", "artist", "playcount", "album", "mbid", "rank")
    _ALBUM_FIELDS  = ("name", "artist", "playcount", "mbid")
    _ARTIST_FIELDS = ("name", "playcount", "mbid", "rank")

    _SCOPE_FIELDS: Dict[str, tuple] = {
        "tracks":  _TRACK_FIELDS,
        "albums":  _ALBUM_FIELDS,
        "artists": _ARTIST_FIELDS,
    }

    def __init__(self, path: Path = _LASTFM_CACHE_FILE) -> None:  # noqa: ARG002
        pass

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get_scope(self, username: str, scope: str) -> Optional[List[Dict[str, Any]]]:
        """Return cached items for *username* / *scope*, or None if never fetched."""
        from utils.db import get_connection
        conn = get_connection()
        sentinel = conn.execute(
            "SELECT 1 FROM lfm_scopes WHERE username=? AND scope=?",
            (username.lower(), scope),
        ).fetchone()
        if sentinel is None:
            return None
        rows = conn.execute(
            "SELECT name, artist, playcount, album, mbid, rank "
            "FROM lfm_tracks WHERE username=? AND scope=? ORDER BY rank ASC NULLS LAST",
            (username.lower(), scope),
        ).fetchall()
        fields = self._SCOPE_FIELDS.get(scope, self._TRACK_FIELDS)
        return [{f: row[f] for f in fields} for row in rows]

    def set_scope(self, username: str, scope: str, items: List[Dict[str, Any]]) -> None:
        from utils.db import get_connection
        conn = get_connection()
        key = username.lower()
        now = time.time()
        conn.execute(
            "INSERT OR REPLACE INTO lfm_scopes (username, scope, fetched_at) VALUES (?, ?, ?)",
            (key, scope, now),
        )
        conn.execute(
            "DELETE FROM lfm_tracks WHERE username=? AND scope=?", (key, scope)
        )
        if items:
            conn.executemany(
                """INSERT OR REPLACE INTO lfm_tracks
                   (username, scope, mbid, name, artist, playcount, rank, album, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        key,
                        scope,
                        item.get("mbid") or "",
                        item.get("name", ""),
                        item.get("artist") or "",
                        item.get("playcount") or 0,
                        item.get("rank"),
                        item.get("album"),
                        now,
                    )
                    for item in items
                ],
            )
        conn.commit()

    def fetched_at(self, username: str, scope: str) -> Optional[float]:
        from utils.db import get_connection
        row = get_connection().execute(
            "SELECT fetched_at FROM lfm_scopes WHERE username=? AND scope=?",
            (username.lower(), scope),
        ).fetchone()
        return row[0] if row else None

    def save(self) -> None:
        """No-op — writes are committed immediately in set_scope()."""

    # ------------------------------------------------------------------
    # Serialisation helpers (unchanged from gzip implementation)
    # ------------------------------------------------------------------

    @classmethod
    def serialise_tracks(cls, tracks: List[LastFmLibraryTrack]) -> List[Dict[str, Any]]:
        return [
            {f: getattr(t, f if f != "name" else "name", None) for f in cls._TRACK_FIELDS}
            for t in tracks
        ]

    @classmethod
    def serialise_albums(cls, albums: List[LastFmLibraryAlbum]) -> List[Dict[str, Any]]:
        return [{f: getattr(a, f, None) for f in cls._ALBUM_FIELDS} for a in albums]

    @classmethod
    def serialise_artists(cls, artists: List[LastFmLibraryArtist]) -> List[Dict[str, Any]]:
        return [{f: getattr(a, f, None) for f in cls._ARTIST_FIELDS} for a in artists]


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m extensions.lastfm_api <lastfm_username>")
        sys.exit(1)

    client = LastFmReadAPI()
    target_user = sys.argv[1]
    info = client.get_user_info(target_user)
    print(f"User: {info.name} ({info.url})")
    print(
        f"Library counts — artists: {info.artist_count}, "
        f"albums: {info.album_count}, tracks: {info.track_count}"
    )

    page = client.get_library_tracks(target_user, limit=5)
    print(
        f"\nFirst page of library tracks ({page.pagination.page}/"
        f"{page.pagination.total_pages}, {page.pagination.total} total):"
    )
    for track in page.tracks:
        print(f"  {track.playcount:>6}  {track.artist} — {track.name}")
