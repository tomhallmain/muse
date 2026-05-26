"""
Read-only Last.fm Web Services client.

Uses GET requests with an API key only (no user session). Suitable for browsing
public profiles: library tracks/albums/artists, loved tracks, and profile info.

API reference: https://www.last.fm/api
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
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
        artist: Optional[str] = None,
    ) -> LastFmLibraryAlbumsPage:
        """Paginated albums in a user's library (``library.getAlbums``)."""
        try:
            payload = self._call(
                "library.getAlbums",
                user=username,
                page=page,
                limit=self._clamp_limit(limit),
                artist=artist,
            )
            root = payload.get("albums") or {}
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
                        tagcount=_int(item.get("tagcount"), 0) or None,
                        image_url=_image_url(item.get("image")),
                    )
                )
            return LastFmLibraryAlbumsPage(
                pagination=_parse_pagination(attr, username),
                albums=albums,
            )
        except LastFmAPIError as exc:
            logger.warning(
                "library.getAlbums unavailable, falling back to user.getTopAlbums: %s",
                exc,
            )
            return self._get_top_albums_fallback(
                username=username,
                page=page,
                limit=limit,
            )

    def get_library_tracks(
        self,
        username: str,
        page: int = 1,
        limit: int = DEFAULT_PAGE_LIMIT,
        artist: Optional[str] = None,
        album: Optional[str] = None,
    ) -> LastFmLibraryTracksPage:
        """Paginated tracks in a user's library (``library.getTracks``)."""
        try:
            payload = self._call(
                "library.getTracks",
                user=username,
                page=page,
                limit=self._clamp_limit(limit),
                artist=artist,
                album=album,
            )
            root = payload.get("tracks") or {}
            attr = root.get("@attr") or {}
            tracks: List[LastFmLibraryTrack] = []
            for item in _as_list(root.get("track")):
                if not isinstance(item, dict):
                    continue
                tracks.append(self._parse_library_track(item))
            return LastFmLibraryTracksPage(
                pagination=_parse_pagination(attr, username),
                tracks=tracks,
            )
        except LastFmAPIError as exc:
            logger.warning(
                "library.getTracks unavailable, falling back to user.getRecentTracks: %s",
                exc,
            )
            return self._get_recent_tracks_fallback(
                username=username,
                page=page,
                limit=limit,
            )

    def _get_top_albums_fallback(
        self,
        username: str,
        page: int,
        limit: int,
    ) -> LastFmLibraryAlbumsPage:
        payload = self._call(
            "user.getTopAlbums",
            user=username,
            page=page,
            limit=self._clamp_limit(limit),
            period="overall",
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

    def _get_recent_tracks_fallback(
        self,
        username: str,
        page: int,
        limit: int,
    ) -> LastFmLibraryTracksPage:
        payload = self._call(
            "user.getRecentTracks",
            user=username,
            page=page,
            limit=min(self._clamp_limit(limit), 200),
            extended=1,
        )
        root = payload.get("recenttracks") or {}
        attr = root.get("@attr") or {}
        tracks: List[LastFmLibraryTrack] = []
        for item in _as_list(root.get("track")):
            if not isinstance(item, dict):
                continue
            tracks.append(
                LastFmLibraryTrack(
                    name=_text(item.get("name")) or "",
                    artist=_artist_name(item.get("artist")),
                    playcount=0,
                    album=_text(item.get("album")) or None,
                    url=_text(item.get("url")),
                    mbid=_text(item.get("mbid")) or None,
                    tagcount=None,
                    image_url=_image_url(item.get("image")),
                    rank=None,
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
        artist: Optional[str] = None,
        album: Optional[str] = None,
        max_pages: Optional[int] = None,
        page_delay_seconds: float = DEFAULT_PAGE_DELAY_SECONDS,
    ) -> Iterator[LastFmLibraryTrack]:
        """Yield every track in a user's library, paging through ``library.getTracks``."""
        yield from self._iter_pages(
            fetch=lambda page: self.get_library_tracks(
                username, page=page, limit=limit, artist=artist, album=album
            ),
            items_attr="tracks",
            max_pages=max_pages,
            page_delay_seconds=page_delay_seconds,
        )

    def iter_library_albums(
        self,
        username: str,
        limit: int = DEFAULT_PAGE_LIMIT,
        artist: Optional[str] = None,
        max_pages: Optional[int] = None,
        page_delay_seconds: float = DEFAULT_PAGE_DELAY_SECONDS,
    ) -> Iterator[LastFmLibraryAlbum]:
        """Yield every album in a user's library."""
        yield from self._iter_pages(
            fetch=lambda page: self.get_library_albums(
                username, page=page, limit=limit, artist=artist
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
