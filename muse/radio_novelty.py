"""Deciding whether a title playing on a watched station is new to the listener.

Gates can only rule a title out; signals add weight towards "new". A title is
suggested when it passes every gate and its signal weights reach the
threshold. A title isn't required: stations often send only part of a
StreamTitle, and a new composer or artist is novelty on its own.

The library and "heard before" lookups are passed in, so the rules can be
tested without a library, a database or a network.
"""

import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional, Set

from utils.logging_setup import get_logger

logger = get_logger(__name__)

SIGNAL_TITLE = "new_title"
SIGNAL_COMPOSER = "new_composer"
SIGNAL_ARTIST = "new_artist"
SIGNAL_STATION = "new_to_station"

DEFAULT_WEIGHTS: Dict[str, float] = {
    SIGNAL_TITLE: 1.0,
    SIGNAL_COMPOSER: 1.0,
    SIGNAL_ARTIST: 1.0,
    SIGNAL_STATION: 0.3,
}
# On a classical station the StreamTitle "artist" is usually a performer,
# ensemble or conductor, and a new recording of known repertoire is not what
# "new to me" means there; composer novelty carries that instead.
CLASSICAL_ARTIST_WEIGHT = 0.3
DEFAULT_THRESHOLD = 1.0

CLASSICAL_AUTO = "auto"
CLASSICAL_YES = "yes"
CLASSICAL_NO = "no"
# Auto-detection from observed titles: classical once at least this share of
# the last _CLASSICAL_WINDOW titles named a composer, given enough titles.
_CLASSICAL_WINDOW = 20
_CLASSICAL_MIN_SAMPLES = 5
_CLASSICAL_SHARE = 0.5

_SEEN_TITLES_CACHE_KEY = "radio_seen_titles"
# Separators between several names in one StreamTitle artist field.
_ARTIST_SPLIT = re.compile(r"\s*(?:,|;|/|&|\+|\bfeat\b\.?|\bft\b\.?)\s*", re.IGNORECASE)


def _fold(text: Optional[str]) -> str:
    from library_data.play_counts import fold
    return fold(text)


def _stream_key(artist: Optional[str], title: Optional[str]) -> Optional[str]:
    from library_data.play_counts import stream_key
    return stream_key(artist, title)


def _names_overlap(a: str, b: str) -> bool:
    """Whether two folded names refer to the same person: equal, or one is the
    other's whole words ("bach" and "johann sebastian bach")."""
    if not a or not b:
        return False
    return a == b or f" {a} " in f" {b} " or f" {b} " in f" {a} "


def split_artists(artist: Optional[str]) -> List[str]:
    """The folded individual names in a StreamTitle artist field."""
    return [f for f in (_fold(part) for part in _ARTIST_SPLIT.split(artist or "")) if f]


@dataclass
class StationInfo:
    uuid: str
    name: str = ""
    tags: str = ""


@dataclass
class Suggestion:
    station_uuid: str
    station_name: str
    artist: str
    title: str
    key: str
    signals: List[str]
    score: float


class LibraryIndex:
    """What the library already holds, for the library gate and the signals.

    Built from the tracks' own values and rebuilt when the track list changes.
    """

    def __init__(self, tracks_source: Callable[[], List[Any]],
                 infer_composers: Callable[[str, str], List[str]]):
        self._tracks_source = tracks_source
        self._infer_composers = infer_composers
        self._lock = threading.Lock()
        self._built_for: Optional[tuple] = None
        self._titles: Dict[str, Set[str]] = {}
        self._names: Set[str] = set()
        self._composers: Set[str] = set()

    def _ensure_built(self) -> None:
        tracks = self._tracks_source() or []
        signature = (id(tracks), len(tracks))
        with self._lock:
            if self._built_for == signature:
                return
            titles: Dict[str, Set[str]] = {}
            names: Set[str] = set()
            composers: Set[str] = set()
            for track in tracks:
                track_names = set()
                for value in (getattr(track, "artist", None), getattr(track, "albumartist", None)):
                    track_names.update(split_artists(value))
                for composer in split_artists(getattr(track, "composer", None)):
                    composers.add(composer)
                    track_names.add(composer)
                names.update(track_names)
                for title in (getattr(track, "title", None), getattr(track, "tracktitle", None)):
                    folded = _fold(title)
                    if folded:
                        titles.setdefault(folded, set()).update(track_names)
            self._titles, self._names, self._composers = titles, names, composers
            self._built_for = signature

    def is_empty(self) -> bool:
        self._ensure_built()
        return not self._titles and not self._names

    def has_title(self, artist: str, title: str) -> bool:
        """Whether the library has this title, by this artist when one is given."""
        self._ensure_built()
        folded = _fold(title)
        if folded not in self._titles:
            return False
        artists = split_artists(artist)
        owners = self._titles[folded]
        if not artists or not owners:
            return True
        return any(_names_overlap(a, owner) for a in artists for owner in owners)

    def has_name(self, name: str) -> bool:
        """Whether a folded artist or composer name is known to the library."""
        self._ensure_built()
        if name in self._names:
            return True
        return any(_names_overlap(name, known) for known in self._names)

    def has_composer(self, composer_name: str) -> bool:
        self._ensure_built()
        folded = _fold(composer_name)
        return any(_names_overlap(folded, known) for known in self._composers)

    def infer_composers(self, artist: str, title: str) -> List[str]:
        try:
            return list(self._infer_composers(artist or "", title or ""))
        except Exception as e:
            logger.warning(f"Composer inference failed for '{artist} - {title}': {e}")
            return []


class _StationState:
    def __init__(self, first_seen: float, titles: Iterable[str], bound: int):
        self.first_seen = first_seen
        self.titles: Deque[str] = deque(titles, maxlen=bound)
        self.title_set: Set[str] = set(self.titles)
        # Whether each recent title named a composer, for classical auto-detection.
        self.composer_hits: Deque[bool] = deque(maxlen=_CLASSICAL_WINDOW)

    def add_title(self, key: str) -> None:
        if key in self.title_set:
            return
        if len(self.titles) == self.titles.maxlen:
            self.title_set.discard(self.titles[0])
        self.titles.append(key)
        self.title_set.add(key)


class NoveltyEvaluator:
    """Applies the gates and signals to each title change on a novel watch entry.

    Keeps per-station state (titles seen, for the "new to station" signal and
    classical detection) persisted in app_info_cache, and the suggestion
    cooldowns in memory.
    """

    def __init__(self, library: LibraryIndex, heard: Callable[[str, str], bool],
                 cache: Any = None, clock: Callable[[], float] = time.time):
        self._library = library
        self._heard = heard
        self._cache = cache
        self._clock = clock
        self._lock = threading.Lock()
        self._stations: Dict[str, _StationState] = {}
        self._last_suggested: Dict[tuple, float] = {}
        self._last_any_suggestion = 0.0
        self._load_stations()

    # ── Settings ───────────────────────────────────────────────────────────────

    @staticmethod
    def _config():
        from utils.config import config
        return config

    def _weights(self, entry: Any, classical: bool) -> Dict[str, float]:
        weights = dict(DEFAULT_WEIGHTS)
        if classical:
            weights[SIGNAL_ARTIST] = CLASSICAL_ARTIST_WEIGHT
        overrides = (getattr(entry, "novelty", None) or {}).get("weights") or {}
        weights.update({k: float(v) for k, v in overrides.items() if k in weights})
        return weights

    @staticmethod
    def _threshold(entry: Any) -> float:
        value = (getattr(entry, "novelty", None) or {}).get("threshold")
        return float(value) if value else DEFAULT_THRESHOLD

    # ── Station state ──────────────────────────────────────────────────────────

    def _load_stations(self) -> None:
        if self._cache is None:
            return
        bound = int(self._config().radio_novelty_seen_titles_per_station)
        stored = self._cache.get(_SEEN_TITLES_CACHE_KEY, {}) or {}
        for uuid, record in stored.items():
            try:
                self._stations[uuid] = _StationState(float(record["first_seen"]), record.get("titles", []), bound)
            except Exception as e:
                logger.warning(f"Skipping malformed seen-titles record for station {uuid}: {e}")

    def _save_stations(self) -> None:
        if self._cache is None:
            return
        self._cache.set(_SEEN_TITLES_CACHE_KEY, {
            uuid: {"first_seen": state.first_seen, "titles": list(state.titles)}
            for uuid, state in self._stations.items()
        })

    def _station(self, uuid: str) -> _StationState:
        state = self._stations.get(uuid)
        if state is None:
            bound = int(self._config().radio_novelty_seen_titles_per_station)
            state = _StationState(self._clock(), [], bound)
            self._stations[uuid] = state
        return state

    def is_classical(self, entry: Any, station: StationInfo) -> bool:
        """The entry's own setting, else the station's tags, else its observed titles."""
        setting = getattr(entry, "classical", CLASSICAL_AUTO) or CLASSICAL_AUTO
        if setting == CLASSICAL_YES:
            return True
        if setting == CLASSICAL_NO:
            return False
        tag_words = {_fold(tag) for tag in self._config().radio_novelty_classical_tags}
        station_tags = {_fold(tag) for tag in (station.tags or "").split(",")}
        if tag_words & station_tags:
            return True
        with self._lock:
            state = self._stations.get(station.uuid)
            hits = list(state.composer_hits) if state else []
        return len(hits) >= _CLASSICAL_MIN_SAMPLES and sum(hits) / len(hits) >= _CLASSICAL_SHARE

    # ── Gates ──────────────────────────────────────────────────────────────────

    def is_non_track(self, artist: str, title: str, station_name: str) -> bool:
        combined = _fold(f"{artist} {title}")
        if len(combined) < 3:
            return True
        station = _fold(station_name)
        if station and _fold(title) and (_fold(title) == station or station in _fold(title)):
            return True
        padded = f" {combined} "
        for pattern in self._config().radio_novelty_non_track_patterns:
            folded = _fold(pattern)
            if folded and f" {folded} " in padded:
                return True
        try:
            from library_data.blacklist import Blacklist
            if Blacklist.get_violation_item(f"{artist} - {title}") is not None:
                return True
        except Exception as e:
            logger.warning(f"Blacklist check skipped for radio title: {e}")
        return False

    # ── Evaluation ─────────────────────────────────────────────────────────────

    def evaluate(self, entry: Any, station: StationInfo, artist: str, title: str) -> Optional[Suggestion]:
        """A suggestion for this title change, or None. Never raises."""
        try:
            return self._evaluate(entry, station, artist or "", title or "")
        except Exception as e:
            logger.error(f"Novelty evaluation failed for '{artist} - {title}': {e}")
            return None

    def _evaluate(self, entry: Any, station: StationInfo, artist: str, title: str) -> Optional[Suggestion]:
        if self.is_non_track(artist, title, station.name):
            return None
        # Until the library has loaded, everything would look new.
        if self._library.is_empty():
            return None
        key = _stream_key(artist, title) or f"artist: {_fold(artist)}"
        composers = self._library.infer_composers(artist, title)
        now = self._clock()
        warmup = float(self._config().radio_novelty_warmup_minutes) * 60.0

        with self._lock:
            state = self._station(station.uuid)
            seen_before = key in state.title_set
            warmed_up = now - state.first_seen >= warmup
            state.add_title(key)
            state.composer_hits.append(bool(composers))
            self._save_stations()

        has_title = bool(_fold(title))
        if has_title and self._heard(artist, title):
            return None
        if has_title and self._library.has_title(artist, title):
            return None

        classical = self.is_classical(entry, station)
        weights = self._weights(entry, classical)
        signals: List[str] = []
        if has_title:
            signals.append(SIGNAL_TITLE)
        if composers and not any(self._library.has_composer(c) for c in composers):
            signals.append(SIGNAL_COMPOSER)
        artists = split_artists(artist)
        composer_names = {_fold(c) for c in composers}
        if artists and not any(self._library.has_name(a) or any(_names_overlap(a, c) for c in composer_names)
                               for a in artists):
            signals.append(SIGNAL_ARTIST)
        if not seen_before and warmed_up:
            signals.append(SIGNAL_STATION)
        score = sum(weights[s] for s in signals)
        if score < self._threshold(entry):
            return None

        per_title_gap = float(self._config().radio_watchlist_cooldown_minutes) * 60.0
        any_gap = float(self._config().radio_novelty_suggestion_cooldown_minutes) * 60.0
        with self._lock:
            last_for_title = self._last_suggested.get((station.uuid, key))
            if last_for_title is not None and now - last_for_title < per_title_gap:
                return None
            if self._last_any_suggestion and now - self._last_any_suggestion < any_gap:
                return None
            self._last_suggested[(station.uuid, key)] = now
            self._last_any_suggestion = now

        return Suggestion(station.uuid, station.name, artist, title, key, signals, score)


def build_evaluator() -> NoveltyEvaluator:
    """An evaluator wired to the live library, play counts and app_info_cache."""
    from types import SimpleNamespace

    from library_data import play_counts
    from library_data.composer import composers_data
    from library_data.library_data import LibraryData
    from utils.app_info_cache import app_info_cache

    def infer(artist: str, title: str) -> List[str]:
        pseudo = SimpleNamespace(title=title, album=None, artist=artist or None,
                                 composer=None, filepath="")
        return composers_data.get_composers(pseudo)

    library = LibraryIndex(lambda: LibraryData.all_tracks, infer)
    return NoveltyEvaluator(library, play_counts.is_stream_title_heard, cache=app_info_cache)
