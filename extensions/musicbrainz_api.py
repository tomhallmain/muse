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
    genres: Tuple[str, ...] = field(default_factory=tuple)

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
    artist_credit: str = ""  # full credited performer string, e.g. "Rattle & Berliner Philharmoniker"
    genres: Tuple[str, ...] = field(default_factory=tuple)


class MusicBrainzCache:
    """
    Persistent cache mapping recording MBIDs to enriched composition data.

    Backed by the mb_recordings table in configs/muse_library.db.  Each
    set() call executes the INSERT but does not commit; call save() to flush
    a batch of writes.  The path argument is retained for backward compatibility
    but unused.

    Multi-valued fields (mb_genres, composer, lyricist, arranger, orchestrator,
    writer) are stored as "; "-delimited strings in the DB and returned as
    lists — callers see the same interface as the former gzip implementation.
    """

    _MULTI_VALUE_FIELDS = ("mb_genres", "composer", "lyricist", "arranger", "orchestrator", "writer")

    def __init__(self, path: Path = _CACHE_FILE) -> None:  # noqa: ARG002
        pass

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get(self, recording_mbid: str) -> Optional[Dict[str, Any]]:
        from utils.db import get_connection, delim_to_list
        row = get_connection().execute(
            "SELECT mb_title, mb_artist, mb_genres, composer, lyricist, "
            "arranger, orchestrator, writer FROM mb_recordings WHERE mbid=?",
            (recording_mbid,),
        ).fetchone()
        if row is None:
            return None
        record = dict(row)
        for field in self._MULTI_VALUE_FIELDS:
            record[field] = delim_to_list(record[field])
        return record

    def set(self, recording_mbid: str, record: Dict[str, Any]) -> None:
        import time
        from utils.db import get_connection, list_to_delim
        get_connection().execute(
            """INSERT OR REPLACE INTO mb_recordings
               (mbid, mb_title, mb_artist, mb_genres, composer,
                lyricist, arranger, orchestrator, writer, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                recording_mbid,
                record.get("mb_title", ""),
                record.get("mb_artist", ""),
                list_to_delim(record.get("mb_genres", [])),
                list_to_delim(record.get("composer", [])),
                list_to_delim(record.get("lyricist", [])),
                list_to_delim(record.get("arranger", [])),
                list_to_delim(record.get("orchestrator", [])),
                list_to_delim(record.get("writer", [])),
                time.time(),
            ),
        )

    def __contains__(self, recording_mbid: str) -> bool:
        from utils.db import get_connection
        row = get_connection().execute(
            "SELECT 1 FROM mb_recordings WHERE mbid=? LIMIT 1",
            (recording_mbid,),
        ).fetchone()
        return row is not None

    def save(self) -> None:
        """Commit any pending batch writes to the database."""
        from utils.db import get_connection
        get_connection().commit()
        logger.debug("MusicBrainz cache committed")

    @property
    def size(self) -> int:
        from utils.db import get_connection
        return get_connection().execute(
            "SELECT COUNT(*) FROM mb_recordings"
        ).fetchone()[0]


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
        """Fetch a recording by MBID, including links to its associated works.

        ``work-level-rels`` causes MB to embed each linked work's own relations
        inline, so a single request returns both the recording's performer credits
        and the works' composition credits.  The parsed works are pre-populated
        into ``_work_cache``; subsequent ``get_work`` calls for those MBIDs will
        be cache hits and require no additional network request.
        """
        if mbid in self._recording_cache:
            return self._recording_cache[mbid]
        payload = self._call(
            f"recording/{mbid}",
            inc="work-rels+artist-credits+genres+work-level-rels",
        )
        recording = self._parse_recording(mbid, payload)
        self._recording_cache[mbid] = recording
        # Pre-populate work cache from inline work-level-rels data so
        # get_composition_credits doesn't need separate work requests.
        for rel in payload.get("relations") or []:
            if rel.get("target-type") == "work":
                work_data = rel.get("work") or {}
                work_id = work_data.get("id")
                if work_id and work_id not in self._work_cache:
                    self._work_cache[work_id] = self._parse_work(work_id, work_data)
        return recording

    def get_work(self, mbid: str) -> MusicBrainzWork:
        """Fetch a work by MBID, including artist relations and genres."""
        if mbid in self._work_cache:
            return self._work_cache[mbid]
        payload = self._call(f"work/{mbid}", inc="artist-rels+genres")
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
                "mb_artist":   str,          # credited performer string
                "mb_genres":   [str, ...],   # recording genres then work genres, deduped
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
                # Merge genres: recording-level first, then each linked work's genres.
                # Recording genres tend to describe the performance; work genres tend
                # to describe the form/style (especially for classical).  Both are
                # valuable, so we keep both, deduplicated, in that order.
                seen_genres: set = set()
                merged_genres: list = []
                for g in (recording.genres if recording else ()):
                    if g not in seen_genres:
                        merged_genres.append(g)
                        seen_genres.add(g)
                for work_mbid in (recording.work_mbids if recording else ()):
                    work = self._work_cache.get(work_mbid)
                    if work:
                        for g in work.genres:
                            if g not in seen_genres:
                                merged_genres.append(g)
                                seen_genres.add(g)
                cache.set(mbid, {
                    "mb_title": recording.title if recording else "",
                    "mb_artist": recording.artist_credit if recording else "",
                    "mb_genres": merged_genres,
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
                    "mb_artist": "",
                    "mb_genres": [],
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

        # Build the full credited performer string by concatenating each credit's
        # name and its join-phrase (e.g. " & ", ", ") exactly as MB intends.
        credit_parts = []
        for entry in payload.get("artist-credit") or []:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name") or (entry.get("artist") or {}).get("name") or ""
            if name:
                credit_parts.append(name + (entry.get("joinphrase") or ""))
        artist_credit = "".join(credit_parts)

        genres = tuple(
            g["name"]
            for g in sorted(payload.get("genres") or [], key=lambda g: -g.get("count", 0))
            if isinstance(g, dict) and g.get("name")
        )
        return MusicBrainzRecording(
            mbid=payload.get("id") or mbid,
            title=payload.get("title") or "",
            work_mbids=tuple(work_mbids),
            artist_credit=artist_credit,
            genres=genres,
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
        genres = tuple(
            g["name"]
            for g in sorted(payload.get("genres") or [], key=lambda g: -g.get("count", 0))
            if isinstance(g, dict) and g.get("name")
        )
        return MusicBrainzWork(
            mbid=payload.get("id") or mbid,
            title=payload.get("title") or "",
            relations=tuple(relations),
            genres=genres,
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
