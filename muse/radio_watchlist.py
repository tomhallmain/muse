"""Radio station watch-list and auto-switch service.

Persists a list of WatchEntry objects in ``app_info_cache`` under
``radio_watchlist``.  A background service opens one ICY metadata poll thread
per unique station UUID. A "match" entry switches playback
(``app_actions.start_play_callback``) when the StreamTitle matches its
criteria; a "novel" entry never switches on its own, and instead asks the UI to
suggest titles that muse.radio_novelty judges new to the listener.
"""

import dataclasses
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from utils.app_info_cache import app_info_cache
from utils.config import config
from utils.logging_setup import get_logger

logger = get_logger(__name__)

_CACHE_KEY = "radio_watchlist"

MODE_MATCH = "match"
MODE_NOVEL = "novel"


@dataclass
class WatchEntry:
    """Describes one station/track combination to watch for."""

    label: str
    station_uuid: str
    station_name: str = ""   # stored at add-time so no extra API call is needed
    match_artist: str = ""   # substring match, case-insensitive
    match_title: str = ""    # substring match, case-insensitive
    match_any: str = ""      # matched against the full raw StreamTitle string

    enabled: bool = True
    mode: str = MODE_MATCH
    # "novel" mode only: "auto", "yes" or "no" -- whether the station is treated
    # as classical, which weakens the new-artist signal.
    classical: str = "auto"
    # "novel" mode only: optional {"weights": {signal: weight}, "threshold": n}
    # overriding muse.radio_novelty's defaults.
    novelty: Dict[str, Any] = field(default_factory=dict)

    def is_active(self) -> bool:
        """True when the entry is enabled and has something to act on.

        A "match" entry needs at least one non-empty criterion; a "novel"
        entry needs none.
        """
        if self.mode == MODE_NOVEL:
            return self.enabled
        return self.enabled and bool(self.match_any or self.match_artist or self.match_title)

    def matches(self, artist: str, title: str) -> bool:
        """Return True when the ICY artist/title satisfies this entry's criteria.

        ``match_any`` is tried first: if set, the criterion must appear anywhere
        in ``"artist - title"``.  Otherwise all non-empty ``match_artist`` /
        ``match_title`` fields must match.
        """
        if self.mode != MODE_MATCH or not self.is_active():
            return False
        if self.match_any:
            raw = f"{artist} - {title}".lower()
            return self.match_any.lower() in raw
        artist_ok = not self.match_artist or self.match_artist.lower() in artist.lower()
        title_ok = not self.match_title or self.match_title.lower() in title.lower()
        return artist_ok and title_ok

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "WatchEntry":
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


# ── Persistence ────────────────────────────────────────────────────────────────

def load_entries() -> list:
    raw = app_info_cache.get(_CACHE_KEY, [])
    entries = []
    for d in raw:
        try:
            entries.append(WatchEntry.from_dict(d))
        except Exception as exc:
            logger.warning("Skipping malformed watchlist entry: %s", exc)
    return entries


def save_entries(entries: list) -> None:
    app_info_cache.set(_CACHE_KEY, [e.to_dict() for e in entries])


# ── Service ────────────────────────────────────────────────────────────────────

class WatchlistService:
    """Background service that polls watched stations for matching tracks.

    One daemon thread per unique ``station_uuid`` is started on ``start()``.
    All threads are stopped cleanly on ``stop()``/``reload()``.
    """

    def __init__(self) -> None:
        self._app_actions: Optional[Any] = None
        self._stop_events: dict = {}   # uuid → threading.Event
        self._threads: dict = {}       # uuid → threading.Thread
        self._cooldowns: dict = {}     # (uuid, label) → monotonic time of last trigger
        self._stations: dict = {}      # uuid → station dict from Radio Browser
        self._novelty = None           # built on first use; see _get_novelty
        self._lock = threading.Lock()

    # ── Public lifecycle ──────────────────────────────────────────────────────

    def start(self, app_actions) -> None:
        """Start polling threads if ``radio_watchlist_enabled`` is set."""
        if not config.radio_watchlist_enabled:
            logger.debug("Radio watch-list is disabled; not starting")
            return
        self._app_actions = app_actions
        self._launch_threads()

    def stop(self) -> None:
        """Signal all threads to exit and wait briefly for them to finish."""
        for ev in self._stop_events.values():
            ev.set()
        for t in self._threads.values():
            if t.is_alive():
                t.join(timeout=2.0)
        self._stop_events.clear()
        self._threads.clear()

    def reload(self, app_actions=None) -> None:
        """Restart the service with the current watch-list (e.g. after UI changes)."""
        if app_actions is not None:
            self._app_actions = app_actions
        self.stop()
        if config.radio_watchlist_enabled:
            self._launch_threads()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _launch_threads(self) -> None:
        entries = load_entries()
        uuid_entries: dict = {}
        for entry in entries:
            if entry.is_active() and entry.station_uuid:
                uuid_entries.setdefault(entry.station_uuid, []).append(entry)

        max_stations = config.radio_watchlist_max_stations
        for uuid in list(uuid_entries)[:max_stations]:
            self._start_poll_thread(uuid, uuid_entries[uuid])

    def _start_poll_thread(self, uuid: str, entries: list) -> None:
        stop = threading.Event()
        self._stop_events[uuid] = stop

        def run() -> None:
            station = self._resolve_station(uuid)
            if station:
                self._stations[uuid] = station
            url = self._station_url(station)
            if not url:
                logger.warning(
                    "Cannot resolve stream URL for watchlist station %s; "
                    "this poll thread will not start",
                    uuid,
                )
                return
            try:
                from extensions.icy_metadata import poll_icy_metadata
                poll_icy_metadata(
                    url,
                    stop,
                    lambda artist, title: self._on_title_change(
                        uuid, entries, artist, title
                    ),
                )
            except Exception:
                logger.exception("Watchlist ICY poll thread failed for station %s", uuid)

        t = threading.Thread(
            target=run,
            name=f"watchlist-{uuid[:8]}",
            daemon=True,
        )
        self._threads[uuid] = t
        t.start()

    @staticmethod
    def _resolve_station(uuid: str) -> Optional[dict]:
        try:
            from extensions.radio_browser import get_station_by_uuid
            return get_station_by_uuid(uuid)
        except Exception as exc:
            logger.warning("Could not look up watchlist station %s: %s", uuid, exc)
        return None

    @staticmethod
    def _station_url(station: Optional[dict]) -> str:
        if not station:
            return ""
        try:
            from extensions.radio_browser import resolve_stream_url
            raw = station.get("url_resolved") or station.get("url") or ""
            return resolve_stream_url(raw) if raw else ""
        except Exception as exc:
            logger.warning("Could not resolve URL for watchlist station: %s", exc)
        return ""

    def _get_novelty(self):
        if self._novelty is None:
            from muse.radio_novelty import build_evaluator
            self._novelty = build_evaluator()
        return self._novelty

    def _on_title_change(
        self,
        uuid: str,
        entries: list,
        artist: str,
        title: str,
    ) -> None:
        """Called from the ICY thread when StreamTitle changes on a watched station."""
        novel = [e for e in entries if e.mode == MODE_NOVEL and e.is_active()]
        if novel:
            self._on_novel_title_change(uuid, novel[0], artist, title)

        now = time.monotonic()
        cooldown_secs = config.radio_watchlist_cooldown_minutes * 60.0

        for entry in entries:
            if not entry.matches(artist, title):
                continue

            key = (uuid, entry.label)
            with self._lock:
                last = self._cooldowns.get(key, 0.0)
                if now - last < cooldown_secs:
                    logger.debug(
                        "Watchlist match suppressed by cooldown: %s", entry.label
                    )
                    continue
                self._cooldowns[key] = now

            logger.info(
                "Watchlist match: '%s — %s' → entry '%s'",
                artist,
                title,
                entry.label,
            )

            if self._is_already_playing(uuid):
                logger.debug(
                    "Already playing station %s; no playback switch needed", uuid
                )
                continue

            self._switch_to_station(uuid, entry, artist, title)

    def _on_novel_title_change(self, uuid: str, entry: "WatchEntry", artist: str, title: str) -> None:
        """Tell the UI the station moved on, then suggest the new title if it is novel."""
        if self._app_actions is None:
            return
        try:
            from muse.radio_novelty import StationInfo
            station = self._stations.get(uuid) or {}
            info = StationInfo(
                uuid=uuid,
                name=station.get("name") or entry.station_name or entry.label,
                tags=station.get("tags") or "",
            )
            self._app_actions.radio_station_title_changed(uuid)
            suggestion = self._get_novelty().evaluate(entry, info, artist, title)
            if suggestion is None or self._is_already_playing(uuid):
                return
            logger.info("Radio suggestion: '%s - %s' on %s (%s)",
                        artist, title, info.name, ", ".join(suggestion.signals))
            self._app_actions.show_radio_suggestion(suggestion)
        except Exception:
            logger.exception("Novelty check failed for watchlist station %s", uuid)

    def switch_to_suggestion(self, suggestion: Any) -> None:
        """Switch playback to a suggested station, off the calling (UI) thread.

        The station lookup is a network call, and start_play_callback accepts
        calls from any thread.
        """
        threading.Thread(
            target=self._play_station,
            args=(suggestion.station_uuid, suggestion.station_name,
                  suggestion.artist, suggestion.title),
            name=f"watchlist-switch-{suggestion.station_uuid[:8]}",
            daemon=True,
        ).start()

    def _is_already_playing(self, uuid: str) -> bool:
        try:
            if self._app_actions is not None:
                current = self._app_actions.get_current_track()
                if current and getattr(current, "station_uuid", None) == uuid:
                    return True
        except Exception:
            pass
        return False

    def _switch_to_station(
        self,
        uuid: str,
        entry: "WatchEntry",
        artist: str,
        title: str,
    ) -> None:
        self._play_station(uuid, entry.station_name or entry.label, artist, title)

    def _play_station(self, uuid: str, fallback_name: str, artist: str, title: str) -> None:
        try:
            from extensions.radio_browser import get_station_by_uuid, resolve_stream_url
            from library_data.network_media_track import NetworkMediaTrack

            station = get_station_by_uuid(uuid)
            if not station:
                logger.warning(
                    "No station data returned for watchlist UUID %s; cannot switch",
                    uuid,
                )
                return
            raw_url = station.get("url_resolved") or station.get("url") or ""
            url = resolve_stream_url(raw_url) if raw_url else ""
            if not url:
                return

            track = NetworkMediaTrack(
                url=url,
                name=station.get("name") or fallback_name,
                station_uuid=uuid,
                codec=station.get("codec") or "",
                bitrate=int(station.get("bitrate") or 0),
                tags=station.get("tags") or "",
                country=station.get("countrycode") or station.get("country") or "",
            )
            track.update_from_icy(artist, title)

            if self._app_actions is not None:
                self._app_actions.start_play_callback(track=track)
        except Exception:
            logger.exception(
                "Failed to switch playback to watchlist station %s", uuid
            )


# Module-level singleton used by app_qt.py
watchlist_service = WatchlistService()
