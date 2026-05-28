"""
Read-only MusicBrainz Web Service client.

Used to cross-reference MBIDs returned by the Last.fm API to retrieve
composer, lyricist, arranger, and other credited roles.

No API key is required. MusicBrainz asks that clients:
  - Identify themselves with a descriptive User-Agent header.
  - Stay within 1 request per second (unauthenticated).

Composer credits in MusicBrainz live on Works, not Recordings. The lookup
path is: Recording MBID → linked Work(s) → Work's artist relations.

API reference: https://musicbrainz.org/doc/MusicBrainz_API
"""

from __future__ import annotations

import gzip
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

from utils.logging_setup import get_logger

logger = get_logger(__name__)

API_ROOT = "https://musicbrainz.org/ws/2/"
DEFAULT_USER_AGENT = "tomhallmain-Muse-App/1.0"

_CACHE_FILE = Path(__file__).resolve().parent.parent / "configs" / "musicbrainz_cache.json.gz"
MIN_REQUEST_INTERVAL = 1.05  # MusicBrainz rate limit: 1 req/sec unauthenticated

# Relation types that represent composition credit on a Work.
COMPOSITION_RELATION_TYPES = frozenset({
    "composer",
    "lyricist",
    "writer",
    "arranger",
    "orchestrator",
})


class MusicBrainzError(Exception):
    """Raised when the MusicBrainz API returns an error or the response is invalid."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class MusicBrainzArtist:
    name: str
    mbid: str
    sort_name: Optional[str] = None
    disambiguation: Optional[str] = None


@dataclass(frozen=True)
class MusicBrainzRelation:
    relation_type: str
    artist: MusicBrainzArtist
    attributes: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MusicBrainzWork:
    mbid: str
    title: str
    relations: Tuple[MusicBrainzRelation, ...]

    @property
    def composers(self) -> List[MusicBrainzArtist]:
        return [r.artist for r in self.relations if r.relation_type == "composer"]

    @property
    def composition_credits(self) -> Dict[str, List[MusicBrainzArtist]]:
        """All composition-related artist credits, keyed by relation type."""
        result: Dict[str, List[MusicBrainzArtist]] = {}
        for r in self.relations:
            if r.relation_type in COMPOSITION_RELATION_TYPES:
                result.setdefault(r.relation_type, []).append(r.artist)
        return result


@dataclass(frozen=True)
class MusicBrainzRecording:
    mbid: str
    title: str
    work_mbids: Tuple[str, ...]


class MusicBrainzCache:
    """
    Persistent, session-independent cache mapping recording MBIDs to enriched
    composition data (composer, lyricist, arranger, etc.).

    Stored as gzip-compressed JSON so the file stays small even with thousands
    of entries. Load on construction; call ``save()`` explicitly after batching
    new lookups.
    """

    def __init__(self, path: Path = _CACHE_FILE) -> None:
        self._path = path
        self._data: Optional[Dict[str, Dict[str, Any]]] = None  # None ⇒ not yet loaded
        self._dirty = False

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get(self, recording_mbid: str) -> Optional[Dict[str, Any]]:
        self._ensure_loaded()
        return self._data.get(recording_mbid)

    def set(self, recording_mbid: str, record: Dict[str, Any]) -> None:
        self._ensure_loaded()
        self._data[recording_mbid] = record
        self._dirty = True

    def __contains__(self, recording_mbid: str) -> bool:
        self._ensure_loaded()
        return recording_mbid in self._data

    def save(self) -> None:
        if not self._dirty:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(self._path, "wt", encoding="utf-8") as fh:
                json.dump(self._data, fh, ensure_ascii=False, separators=(",", ":"))
            self._dirty = False
            logger.debug("MusicBrainz cache saved (%d entries) to %s", len(self._data), self._path)
        except OSError as exc:
            logger.error("Could not save MusicBrainz cache to %s: %s", self._path, exc)

    @property
    def size(self) -> int:
        self._ensure_loaded()
        return len(self._data)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._data is not None:
            return
        self._data = {}
        if not self._path.exists():
            return
        try:
            with gzip.open(self._path, "rt", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                self._data = loaded
                logger.debug("MusicBrainz cache loaded (%d entries) from %s", len(self._data), self._path)
        except Exception as exc:
            logger.warning("Could not load MusicBrainz cache from %s: %s", self._path, exc)
            self._data = {}


_mb_cache_instance: Optional[MusicBrainzCache] = None


def get_mb_cache() -> MusicBrainzCache:
    """Return the process-wide singleton MusicBrainz recording cache (lazily loaded)."""
    global _mb_cache_instance
    if _mb_cache_instance is None:
        _mb_cache_instance = MusicBrainzCache()
    return _mb_cache_instance


class MusicBrainzReadAPI:
    """
    Read-only MusicBrainz API client.

    No API key required. Enforces a 1 req/sec rate limit and caches all
    fetched recordings, works, and artists for the lifetime of the instance.
    """

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": user_agent,
            "Accept": "application/json",
        })
        self._last_request_at: float = 0.0
        self._recording_cache: Dict[str, MusicBrainzRecording] = {}
        self._work_cache: Dict[str, MusicBrainzWork] = {}
        self._artist_cache: Dict[str, MusicBrainzArtist] = {}

    def _call(self, endpoint: str, **params: Any) -> Dict[str, Any]:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)

        params["fmt"] = "json"
        try:
            response = self._session.get(f"{API_ROOT}{endpoint}", params=params, timeout=30)
        except requests.RequestException as exc:
            logger.error("MusicBrainz request failed (%s): %s", endpoint, exc)
            raise MusicBrainzError(str(exc)) from exc
        finally:
            self._last_request_at = time.monotonic()

        if response.status_code == 404:
            raise MusicBrainzError(f"Not found: {endpoint}", status_code=404)
        if response.status_code == 503:
            raise MusicBrainzError("Rate limited by MusicBrainz (503)", status_code=503)
        if response.status_code >= 400:
            raise MusicBrainzError(
                f"HTTP {response.status_code} for {endpoint}", status_code=response.status_code
            )

        try:
            payload = response.json()
        except ValueError:
            raise MusicBrainzError(f"Invalid JSON from MusicBrainz ({endpoint})")

        if isinstance(payload, dict) and "error" in payload:
            raise MusicBrainzError(payload["error"])

        return payload

    def get_recording(self, mbid: str) -> MusicBrainzRecording:
        """Fetch a recording by MBID, including links to its associated works."""
        if mbid in self._recording_cache:
            return self._recording_cache[mbid]
        payload = self._call(f"recording/{mbid}", inc="work-rels")
        recording = self._parse_recording(mbid, payload)
        self._recording_cache[mbid] = recording
        return recording

    def get_work(self, mbid: str) -> MusicBrainzWork:
        """Fetch a work by MBID, including all artist relations (composer, lyricist, etc.)."""
        if mbid in self._work_cache:
            return self._work_cache[mbid]
        payload = self._call(f"work/{mbid}", inc="artist-rels")
        work = self._parse_work(mbid, payload)
        self._work_cache[mbid] = work
        return work

    def get_artist(self, mbid: str) -> MusicBrainzArtist:
        """Fetch an artist by MBID."""
        if mbid in self._artist_cache:
            return self._artist_cache[mbid]
        payload = self._call(f"artist/{mbid}")
        artist = MusicBrainzArtist(
            name=payload.get("name") or "",
            mbid=payload.get("id") or mbid,
            sort_name=payload.get("sort-name") or None,
            disambiguation=payload.get("disambiguation") or None,
        )
        self._artist_cache[mbid] = artist
        return artist

    def get_composers(self, recording_mbid: str) -> List[MusicBrainzArtist]:
        """
        Return the composer(s) for a recording, resolving through its linked work(s).
        Returns an empty list if the MBID is unknown or no composer credit exists.
        """
        credits = self.get_composition_credits(recording_mbid)
        return credits.get("composer", [])

    def get_composition_credits(self, recording_mbid: str) -> Dict[str, List[MusicBrainzArtist]]:
        """
        Return all composition-related credits for a recording (composer, lyricist,
        arranger, orchestrator, writer), resolving through its linked work(s).
        Returns an empty dict if the MBID is unknown or no credits exist.
        """
        try:
            recording = self.get_recording(recording_mbid)
        except MusicBrainzError as exc:
            logger.warning("Could not fetch recording %s: %s", recording_mbid, exc)
            return {}

        combined: Dict[str, List[MusicBrainzArtist]] = {}
        for work_mbid in recording.work_mbids:
            try:
                work = self.get_work(work_mbid)
                for role, artists in work.composition_credits.items():
                    combined.setdefault(role, []).extend(artists)
            except MusicBrainzError as exc:
                logger.warning("Could not fetch work %s: %s", work_mbid, exc)

        return combined

    def enrich_recordings(
        self,
        mbids: List[str],
        cache: MusicBrainzCache,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """
        Resolve composition credits for every recording MBID not already in
        *cache*, storing normalised records back into *cache* and persisting
        to disk when done.

        Each cache record has the shape::

            {
                "mb_title":    str,          # canonical MusicBrainz recording title
                "composer":    [str, ...],
                "lyricist":    [str, ...],
                "arranger":    [str, ...],
                "orchestrator":[str, ...],
                "writer":      [str, ...],
            }

        *progress_callback* is called with ``(completed, total)`` after each
        MBID is resolved (cached or not), where *total* is the number of
        uncached MBIDs that needed network requests.
        """
        uncached = [m for m in mbids if m and m not in cache]
        total = len(uncached)
        for i, mbid in enumerate(uncached):
            try:
                credits = self.get_composition_credits(mbid)
                recording = self._recording_cache.get(mbid)
                cache.set(mbid, {
                    "mb_title": recording.title if recording else "",
                    "composer": [a.name for a in credits.get("composer", [])],
                    "lyricist": [a.name for a in credits.get("lyricist", [])],
                    "arranger": [a.name for a in credits.get("arranger", [])],
                    "orchestrator": [a.name for a in credits.get("orchestrator", [])],
                    "writer": [a.name for a in credits.get("writer", [])],
                })
            except MusicBrainzError as exc:
                logger.warning("Skipping recording %s during enrichment: %s", mbid, exc)
                cache.set(mbid, {
                    "mb_title": "",
                    "composer": [],
                    "lyricist": [],
                    "arranger": [],
                    "orchestrator": [],
                    "writer": [],
                })
            if progress_callback:
                progress_callback(i + 1, total)
        cache.save()

    @staticmethod
    def _parse_recording(mbid: str, payload: Dict[str, Any]) -> MusicBrainzRecording:
        work_mbids = []
        for rel in payload.get("relations") or []:
            if rel.get("target-type") == "work":
                work = rel.get("work") or {}
                work_id = work.get("id")
                if work_id:
                    work_mbids.append(work_id)
        return MusicBrainzRecording(
            mbid=payload.get("id") or mbid,
            title=payload.get("title") or "",
            work_mbids=tuple(work_mbids),
        )

    @staticmethod
    def _parse_work(mbid: str, payload: Dict[str, Any]) -> MusicBrainzWork:
        relations = []
        for rel in payload.get("relations") or []:
            if rel.get("target-type") != "artist":
                continue
            artist_data = rel.get("artist") or {}
            artist_mbid = artist_data.get("id") or ""
            if not artist_mbid:
                continue
            relations.append(MusicBrainzRelation(
                relation_type=rel.get("type") or "unknown",
                artist=MusicBrainzArtist(
                    name=artist_data.get("name") or "",
                    mbid=artist_mbid,
                    sort_name=artist_data.get("sort-name") or None,
                    disambiguation=artist_data.get("disambiguation") or None,
                ),
                attributes=tuple(rel.get("attributes") or []),
            ))
        return MusicBrainzWork(
            mbid=payload.get("id") or mbid,
            title=payload.get("title") or "",
            relations=tuple(relations),
        )


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m extensions.musicbrainz_api <recording-mbid>")
        sys.exit(1)

    client = MusicBrainzReadAPI()
    recording_mbid = sys.argv[1]
    credits = client.get_composition_credits(recording_mbid)

    if not credits:
        print(f"No composition credits found for recording {recording_mbid}.")
        sys.exit(0)

    print(f"Composition credits for recording {recording_mbid}:")
    for role, artists in sorted(credits.items()):
        for artist in artists:
            disambig = f" ({artist.disambiguation})" if artist.disambiguation else ""
            print(f"  {role:<16} {artist.name}{disambig}")
