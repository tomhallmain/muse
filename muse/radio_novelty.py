"""Deciding whether a title playing on a watched station is new to the listener.

Gates can only rule a title out; signals add weight towards "new". A title is
suggested when it passes every gate and its signal weights reach the
threshold. A title isn't required: stations often send only part of a
StreamTitle, and a new composer or artist is novelty on its own.

The library, "heard before" and affinity lookups are passed in, so the rules
can be tested without a library, a database, a model or a network.
"""

import datetime
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
SIGNAL_WORK = "new_work"
SIGNAL_AFFINITY = "close_to_taste"

DEFAULT_WEIGHTS: Dict[str, float] = {
    SIGNAL_TITLE: 1.0,
    SIGNAL_COMPOSER: 1.0,
    SIGNAL_ARTIST: 1.0,
    SIGNAL_STATION: 0.3,
    SIGNAL_WORK: 1.0,
    # Graded: this weight times the affinity score (0 to 1), not all or nothing.
    SIGNAL_AFFINITY: 1.0,
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
_SUPPRESSED_CACHE_KEY = "radio_suppressed_suggestions"
# Separators between several names in one StreamTitle artist field.
_ARTIST_SPLIT = re.compile(r"\s*(?:,|;|/|&|\+|\bfeat\b\.?|\bft\b\.?)\s*", re.IGNORECASE)


def _fold(text: Optional[str]) -> str:
    from utils.name_ops import NameOps
    return NameOps.fold(text)


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
    # The composer's work this title was matched to, for SIGNAL_WORK.
    work_name: str = ""


class LibraryIndex:
    """What the library already holds, for the library gate and the signals.

    Built from the tracks' own values and rebuilt when the track list changes.
    """

    def __init__(self, tracks_source: Callable[[], List[Any]],
                 infer_composers: Callable[[str, str], List[str]],
                 works_for: Optional[Callable[[str], List[Any]]] = None):
        self._tracks_source = tracks_source
        self._infer_composers = infer_composers
        self._works_for = works_for
        self._lock = threading.Lock()
        self._built_for: Optional[tuple] = None
        self._titles: Dict[str, Set[str]] = {}
        self._names: Set[str] = set()
        self._composers: Set[str] = set()
        # Folded composer -> the raw titles of that composer's library tracks.
        self._titles_by_composer: Dict[str, List[str]] = {}

    def _ensure_built(self) -> None:
        tracks = self._tracks_source() or []
        signature = (id(tracks), len(tracks))
        with self._lock:
            if self._built_for == signature:
                return
            titles: Dict[str, Set[str]] = {}
            names: Set[str] = set()
            composers: Set[str] = set()
            titles_by_composer: Dict[str, List[str]] = {}
            for track in tracks:
                track_names = set()
                for value in (getattr(track, "artist", None), getattr(track, "albumartist", None)):
                    track_names.update(split_artists(value))
                track_titles = [t for t in (getattr(track, "title", None), getattr(track, "tracktitle", None)) if t]
                for composer in split_artists(getattr(track, "composer", None)):
                    composers.add(composer)
                    track_names.add(composer)
                    titles_by_composer.setdefault(composer, []).extend(track_titles)
                names.update(track_names)
                for title in track_titles:
                    folded = _fold(title)
                    if folded:
                        titles.setdefault(folded, set()).update(track_names)
            self._titles, self._names, self._composers = titles, names, composers
            self._titles_by_composer = titles_by_composer
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

    def match_work(self, composer_name: str, title: str) -> Optional[tuple]:
        """(work, in_library) for the composer's work this title names, or None.

        in_library is true if any matching work is linked to a library track or
        named by one of the composer's library tracks, so a title that could be
        either of two works counts as known if one of them is.
        """
        if self._works_for is None:
            return None
        try:
            works = list(self._works_for(composer_name) or [])
        except Exception as e:
            logger.warning(f"Could not read works for {composer_name}: {e}")
            return None
        matched = [w for w in works if w.matches_title(title)]
        if not matched:
            return None
        self._ensure_built()
        folded = _fold(composer_name)
        library_titles = [t for composer, titles in self._titles_by_composer.items()
                          if _names_overlap(folded, composer) for t in titles]
        for work in matched:
            if getattr(work, "matched_track_filepath", None) or any(work.matches_title(t) for t in library_titles):
                return work, True
        return matched[0], False

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
                 cache: Any = None, clock: Callable[[], float] = time.time,
                 affinity: Optional[Callable[[str], Optional[float]]] = None):
        self._library = library
        self._heard = heard
        self._cache = cache
        self._clock = clock
        self._affinity = affinity
        self._lock = threading.Lock()
        self._stations: Dict[str, _StationState] = {}
        self._last_suggested: Dict[tuple, float] = {}
        self._last_any_suggestion = 0.0
        # key -> {"label": "artist - title", "date": ISO timestamp}
        self._suppressed: Dict[str, Dict[str, str]] = {}
        self._load_stations()
        self._load_suppressed()

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

    def _load_suppressed(self) -> None:
        if self._cache is None:
            return
        stored = self._cache.get(_SUPPRESSED_CACHE_KEY, {}) or {}
        self._suppressed = {k: dict(v) for k, v in stored.items() if isinstance(v, dict)}

    def _save_suppressed(self) -> None:
        if self._cache is not None:
            self._cache.set(_SUPPRESSED_CACHE_KEY, dict(self._suppressed))

    # ── Suppression ("don't suggest this again") ──────────────────────────────

    def suppress(self, suggestion: Suggestion) -> None:
        label = " - ".join(part for part in (suggestion.artist, suggestion.title) if part)
        with self._lock:
            self._suppressed[suggestion.key] = {
                "label": label, "date": datetime.datetime.now().isoformat(),
            }
            self._save_suppressed()

    def suppressed_count(self) -> int:
        with self._lock:
            return len(self._suppressed)

    def clear_suppressed(self) -> None:
        with self._lock:
            self._suppressed = {}
            self._save_suppressed()

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
        # With nothing in the library, everything would look new.
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
            if key in self._suppressed:
                return None

        has_title = bool(_fold(title))
        if has_title and self._heard(artist, title):
            return None
        new_work = None
        if has_title:
            for composer in composers:
                if not self._library.has_composer(composer):
                    continue
                match = self._library.match_work(composer, title)
                if match is None:
                    continue
                work, in_library = match
                # A work the library has is not new, however differently the
                # station spells its title.
                if in_library:
                    return None
                new_work = work
                break
        if has_title and new_work is None and self._library.has_title(artist, title):
            return None

        classical = self.is_classical(entry, station)
        weights = self._weights(entry, classical)
        signals: List[str] = []
        if new_work is not None:
            signals.append(SIGNAL_WORK)
        elif has_title:
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
        threshold = self._threshold(entry)
        # The affinity score costs a model run, so it is computed only when its
        # largest possible contribution would reach the threshold.
        affinity_weight = weights[SIGNAL_AFFINITY]
        if (score < threshold and self._affinity is not None and affinity_weight > 0
                and score + affinity_weight >= threshold):
            value = self._affinity(_affinity_text(artist, title, composers))
            if value:
                score += affinity_weight * value
                signals.append(SIGNAL_AFFINITY)
        if score < threshold:
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

        return Suggestion(station.uuid, station.name, artist, title, key, signals, score,
                          work_name=new_work.name if new_work is not None else "")


def _unit(value: float) -> float:
    """Clamped to 0..1: an opposed vector means no more than an unrelated one."""
    return max(0.0, min(1.0, value))


def _affinity_text(artist: str, title: str, composers: List[str]) -> str:
    """The title in the "attribute: value" form reference descriptions use."""
    parts = []
    if composers:
        parts.append(f"composer: {', '.join(composers)}")
    if artist:
        parts.append(f"artist: {artist}")
    if title:
        parts.append(f"title: {title}")
    return "; ".join(parts)


class AffinityScorer:
    """How close a title is to the listener's taste without being familiar.

    relevance x (1 - familiarity), each an embedding similarity clamped to
    0..1: relevance against the favorites profile, familiarity against the
    most-played values. So something near what the listener likes, but unlike
    what they already play most, scores highest. None when there are no
    favorites, the model is unavailable, or affinity is turned off.
    """

    REFRESH_SECONDS = 1800.0

    def __init__(self, relevance_text: Callable[[], str], familiarity_text: Callable[[], str],
                 embed: Callable[[List[str]], Optional[List[List[float]]]],
                 similarity: Callable[[List[float], List[float]], Optional[float]],
                 enabled: Callable[[], bool] = lambda: True,
                 clock: Callable[[], float] = time.monotonic):
        self._relevance_text = relevance_text
        self._familiarity_text = familiarity_text
        self._embed = embed
        self._similarity = similarity
        self._enabled = enabled
        self._clock = clock
        self._lock = threading.Lock()
        self._built_at: Optional[float] = None
        self._relevance_vector: Optional[List[float]] = None
        self._familiarity_vector: Optional[List[float]] = None

    def _references(self) -> Optional[List[float]]:
        """The relevance vector, rebuilding both references when they are stale."""
        with self._lock:
            now = self._clock()
            if self._built_at is None or now - self._built_at >= self.REFRESH_SECONDS:
                self._built_at = now
                self._relevance_vector = self._familiarity_vector = None
                relevance = self._relevance_text()
                if relevance:
                    familiarity = self._familiarity_text()
                    texts = [relevance] + ([familiarity] if familiarity else [])
                    vectors = self._embed(texts)
                    if vectors and len(vectors) == len(texts):
                        self._relevance_vector = vectors[0]
                        self._familiarity_vector = vectors[1] if familiarity else None
            return self._relevance_vector

    def __call__(self, text: str) -> Optional[float]:
        try:
            if not text or not self._enabled():
                return None
            relevance_vector = self._references()
            if relevance_vector is None:
                return None
            vectors = self._embed([text])
            if not vectors:
                return None
            relevance = self._similarity(vectors[0], relevance_vector)
            if relevance is None:
                return None
            familiarity = 0.0
            if self._familiarity_vector is not None:
                familiarity = self._similarity(vectors[0], self._familiarity_vector) or 0.0
            return _unit(relevance) * (1.0 - _unit(familiarity))
        except Exception as e:
            logger.warning(f"Affinity scoring of a radio title failed: {e}")
            return None


def _most_played_description(top_n: int = 5) -> str:
    """The most-played values per attribute, weighted by play count, as a description."""
    from library_data import play_counts
    from library_data.library_data import LibraryData
    from muse.track_affinity import AffinityReference, reference_description

    totals: Dict[str, Dict[str, int]] = {}
    for filepath, count in play_counts.get_play_counts().items():
        track = LibraryData.MEDIA_TRACK_CACHE.get(filepath)
        if track is None:
            continue
        for attribute, values in AffinityReference.from_track(track).values.items():
            for value in values:
                bucket = totals.setdefault(attribute, {})
                bucket[value] = bucket.get(value, 0) + count
    reference = AffinityReference()
    for attribute, counts in totals.items():
        for value, _count in sorted(counts.items(), key=lambda kv: -kv[1])[:top_n]:
            reference.add(attribute, value)
    return reference_description(reference)


def _favorites_description() -> str:
    from muse.track_affinity import AffinityReference, current_favorites_profile, reference_description
    return reference_description(AffinityReference.from_favorites_profile(current_favorites_profile()))


def build_evaluator() -> NoveltyEvaluator:
    """An evaluator wired to the live library, play counts and app_info_cache."""
    from types import SimpleNamespace

    from library_data import play_counts
    from library_data.composer import composers_data
    from library_data.library_data import LibraryData
    from utils.app_info_cache import app_info_cache

    from muse.track_affinity import affinity_enabled, cosine_similarity, embed_texts

    def infer(artist: str, title: str) -> List[str]:
        pseudo = SimpleNamespace(title=title, album=None, artist=artist or None,
                                 composer=None, filepath="")
        return composers_data.get_composers(pseudo)

    def works_for(composer_name: str) -> List[Any]:
        composer = composers_data.get_data(composer_name)
        return list(getattr(composer, "works", None) or [])

    # get_all_tracks rather than the all_tracks list itself: playback reads tracks
    # one at a time and never fills that list, so it can still be empty here.
    library = LibraryIndex(LibraryData.get_all_tracks, infer, works_for)
    affinity = AffinityScorer(_favorites_description, _most_played_description,
                              embed_texts, cosine_similarity, enabled=affinity_enabled)
    return NoveltyEvaluator(library, play_counts.is_stream_title_heard, cache=app_info_cache,
                            affinity=affinity)
