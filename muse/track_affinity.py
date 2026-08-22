"""Scoring how strongly a track relates to some reference.

The reference is whatever context applies -- a seed track, a search query, the
listener's favorites, or a combination -- so one score serves playlist ordering,
mid-playback resorting and extension search rather than each growing its own
notion of similarity.

Three signals, in order of what they cost. Attribute overlap is a dictionary
comparison per track and answers on its own. On top of it, one chat-model call
and one embedding call per grouping change buy the judgement that two different
composers are close to each other, which overlap cannot express. Both are
optional and blended rather than substituted, so neither can override what the
tags state as fact and either can be absent.

The same score also runs in reverse. Measured against what has recently *played*
rather than against what was asked for, it says what the listener has had enough
of, and that pushes material back instead of pulling it forward. Attraction and
repulsion are separate because only repulsion is safe to re-seed from what is
playing: attraction would compound until the playlist narrowed to one composer,
where repulsion decays as soon as the material stops.

Everything is applied to a bounded window of upcoming tracks, never to the
library, so nothing here needs precomputing or persisting.
"""

import math
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from utils.globals import TrackAttribute
from utils.logging_setup import get_logger

logger = get_logger(__name__)

# Attribute name -> how to read it off a MediaTrack. A "get_" prefix marks a
# method, matching how PlaylistSortType.getter_name_mapping() spells the same
# distinction.
TRACK_VALUE_GETTERS: Dict[str, str] = {
    "composer": "composer",
    "artist": "get_main_artist",
    "album": "album",
    "genre": "get_genre",
    "form": "get_form",
    "instrument": "get_instrument",
    "catalogue": "get_catalogue",
}

# Starting weights only. Which attributes matter is a matter of taste, so these
# are overridable per call rather than fixed here.
DEFAULT_ATTRIBUTE_WEIGHTS: Dict[str, float] = {
    "composer": 1.0,
    "artist": 0.8,
    "form": 0.6,
    "instrument": 0.5,
    "genre": 0.4,
    "album": 0.3,
    "catalogue": 0.3,
}

# A search field that is not one attribute but any of them.
_ALL_FIELDS_KEY = "all"

# Whether upcoming tracks are ordered at all. One preference for the whole
# application rather than per playlist: this is a matter of listening taste, not
# a property of any particular playlist. On or off, with no "prefer varied"
# state -- inverting the intent reference would push away from what was searched
# for, which is not what anyone asked for. Keeping things fresh is what
# saturation below does, against what was heard.
AFFINITY_OFF = "off"
AFFINITY_ON = "on"
AFFINITY_PREFERENCES = (AFFINITY_OFF, AFFINITY_ON)

# Active by default, so the ordering works without being configured first. An
# unset or unrecognised value reads as this rather than as off, which also keeps
# a config written before the setting existed -- or holding one of the states
# this replaced -- on the working behaviour.
DEFAULT_AFFINITY_PREFERENCE = AFFINITY_ON

# How hard fully-saturated material is pushed back, relative to the blended
# attraction score it is subtracted from.
SATURATION_WEIGHT = 0.5

# Listening time at which a value counts as over-heard. Roughly one long track,
# or a few ordinary ones, which is about when a listener would start to notice.
SATURATION_SECONDS_THRESHOLD = 600

# Saturation fades rather than latching: material heard an hour and a half ago
# weighs half what it did.
SATURATION_HALF_LIFE_SECONDS = 5400

# Saturation reads the plain artist tag rather than the resolved main artist,
# which is derived lazily and only for the shuffle that needs it. Recording every
# track would force that work whatever the listener is playing; the containment
# matching in _matches() still relates the two.
_SATURATION_GETTERS: Dict[str, str] = dict(TRACK_VALUE_GETTERS, artist="artist")

# How many upcoming tracks reordering may touch: roughly two to three hours of
# listening, past which the order will have been re-evaluated anyway. A stand-in
# until the playlist window can say how much it actually displays.
DEFAULT_AFFINITY_WINDOW = 40

# Attribute overlap answers "is this the same composer" exactly, but cannot say
# that two different composers are close to each other. The other two signals buy
# that judgement. All three are blended rather than substituted, so a bad or
# eccentric score cannot override what the tags state as fact, and the blend is
# normalised over whichever signals are actually present.
ATTRIBUTE_SIGNAL_WEIGHT = 1.0
LLM_SIGNAL_WEIGHT = 1.0
# Lower than the other two: embedding similarity is measured over a short label,
# and its scores sit in a narrow band, so it nudges rather than decides.
EMBEDDING_SIGNAL_WEIGHT = 0.6

# Small, CPU-fast, and runs in this process. Deliberately not the chat model and
# deliberately not routed through Ollama: a listener who has the daemon turned
# off would otherwise lose both of the signals above at once, when the whole
# point of having two is that they fail separately.
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"

# Short on purpose. This runs while music is playing and only ever improves an
# order that is already valid, so waiting is never worth it.
LLM_AFFINITY_TIMEOUT_SECONDS = 20

# One prompt has to hold every candidate, and groups past this add cost without
# affecting what plays soonest.
MAX_LLM_SCORED_GROUPS = 40

# What the model is asked to score against, longest-lived signals first.
_REFERENCE_DESCRIPTION_ORDER = ("composer", "artist", "form", "instrument",
                                "genre", "album", "catalogue")


def affinity_preference() -> str:
    from utils.config import config
    value = getattr(config, "affinity_preference", None)
    if isinstance(value, str):
        value = value.strip().lower()
        if value in AFFINITY_PREFERENCES:
            return value
    return DEFAULT_AFFINITY_PREFERENCE


def affinity_enabled() -> bool:
    return affinity_preference() == AFFINITY_ON


def _track_value(track: Any, attribute: str,
                 getters: Optional[Dict[str, str]] = None) -> Optional[str]:
    getter = (getters or TRACK_VALUE_GETTERS).get(attribute)
    if getter is None:
        return None
    try:
        value = getattr(track, getter, None)
        if callable(value):
            value = value()
    except Exception:
        return None
    if value is None:
        return None
    value = str(value).strip().lower()
    return value or None


def _matches(value: str, wanted: Set[str]) -> bool:
    if value in wanted:
        return True
    # Containment either way: a query says "mozart" where the tag says "wolfgang
    # amadeus mozart", and a seed track's full value may sit inside a longer one.
    return any(w in value or value in w for w in wanted)


@dataclass
class AffinityReference:
    """What a track is being compared against: attribute name -> wanted values."""

    values: Dict[str, Set[str]] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not any(self.values.values())

    def add(self, attribute: str, value: Optional[str]) -> None:
        if not value:
            return
        cleaned = str(value).strip().lower()
        if cleaned:
            self.values.setdefault(attribute, set()).add(cleaned)

    def merge(self, other: 'AffinityReference') -> 'AffinityReference':
        """Combine two references; neither is modified."""
        merged = AffinityReference({k: set(v) for k, v in self.values.items()})
        for attribute, wanted in other.values.items():
            merged.values.setdefault(attribute, set()).update(wanted)
        return merged

    @classmethod
    def from_track(cls, track: Any) -> 'AffinityReference':
        reference = cls()
        for attribute in TRACK_VALUE_GETTERS:
            reference.add(attribute, _track_value(track, attribute))
        return reference

    @classmethod
    def from_search_query(cls, search_query: Optional[Dict[str, Any]]) -> 'AffinityReference':
        """Build from a PlaylistDescriptor search_query.

        Only the positive terms are used. Negative terms have already excluded
        their tracks from the result set, so they cannot affect ordering within it.
        An "all" field applies to every attribute, since that is what it searched.
        """
        reference = cls()
        if not search_query:
            return reference
        from library_data.library_data import LibraryDataSearch

        for key, raw in search_query.items():
            if not isinstance(raw, str) or not raw.strip():
                continue
            positive, _negative = LibraryDataSearch._parse_terms(raw)
            if key == _ALL_FIELDS_KEY:
                for attribute in TRACK_VALUE_GETTERS:
                    for term in positive:
                        reference.add(attribute, term)
            elif key in TRACK_VALUE_GETTERS:
                for term in positive:
                    reference.add(key, term)
        return reference

    @classmethod
    def from_favorites_profile(cls, profile: Dict[str, List[str]]) -> 'AffinityReference':
        reference = cls()
        for attribute, favorite_values in profile.items():
            for value in favorite_values:
                reference.add(attribute, value)
        return reference


def saturation_applies(descriptor: Any) -> bool:
    """Whether recently-heard material should be pushed back for this playlist.

    Only where the listener stated no preference: pressing play, or a playlist
    sourced from directories. A search says what was wanted, and answering it
    with less of that would be perverse. A track-based playlist is not reordered
    at all.

    No descriptor is the plain press-play case -- the attribute is only ever set
    for a saved playlist -- and takes the same treatment as a directory one.
    """
    if descriptor is None:
        return True
    try:
        return not (descriptor.is_track_based() or descriptor.is_search_based())
    except Exception as e:
        logger.warning(f"Could not read the playlist descriptor, leaving saturation off: {e}")
        return False


# attribute -> value -> [seconds heard, when last heard]. Process-wide: this is
# what the listener has been hearing, not a property of any one playlist.
_listening_log: Dict[str, Dict[str, List[float]]] = {}


def clear_listening_log() -> None:
    _listening_log.clear()


def record_listening(track: Any, seconds: Optional[float] = None) -> None:
    """Add a track's length to the running total for each of its attribute values.

    Counted when the track starts rather than when it ends, so a skipped track
    still counts in full. That errs towards freshness, which is the direction
    this exists to serve.
    """
    try:
        if seconds is None:
            seconds = float(track.get_track_length() or 0.0)
        if seconds <= 0:
            return
        now = time.time()
        for attribute in _SATURATION_GETTERS:
            value = _track_value(track, attribute, getters=_SATURATION_GETTERS)
            if not value:
                continue
            entry = _listening_log.setdefault(attribute, {}).get(value)
            if entry is None:
                _listening_log[attribute][value] = [seconds, now]
            else:
                entry[0] = _decayed(entry[0], entry[1], now) + seconds
                entry[1] = now
    except Exception as e:
        logger.warning(f"Could not record listening time: {e}")


def _decayed(seconds: float, last_heard: float, now: float) -> float:
    elapsed = max(0.0, now - last_heard)
    if SATURATION_HALF_LIFE_SECONDS <= 0:
        return seconds
    return seconds * (0.5 ** (elapsed / SATURATION_HALF_LIFE_SECONDS))


def saturation_reference() -> Optional[AffinityReference]:
    """What the listener has had enough of, or None if nothing has crossed the line.

    Only values past the threshold are included, which is what makes this a
    threshold rather than a gradient: below it nothing is pushed anywhere, and a
    mild repulsion is never applied to everything at once.
    """
    if not _listening_log:
        return None
    now = time.time()
    reference = AffinityReference()
    for attribute, values in _listening_log.items():
        for value, (seconds, last_heard) in list(values.items()):
            if _decayed(seconds, last_heard, now) >= SATURATION_SECONDS_THRESHOLD:
                reference.add(attribute, value)
    return None if reference.is_empty() else reference


def affinity(track: Any, reference: Optional[AffinityReference],
             weights: Optional[Dict[str, float]] = None) -> float:
    """How strongly track matches reference, 0.0 to 1.0.

    Normalised by the weight of the attributes the reference actually carries, so
    a reference naming only a composer is not penalised for saying nothing about
    instrument.
    """
    if reference is None or reference.is_empty():
        return 0.0
    if weights is None:
        weights = DEFAULT_ATTRIBUTE_WEIGHTS

    considered = 0.0
    matched = 0.0
    for attribute, wanted in reference.values.items():
        if not wanted:
            continue
        weight = weights.get(attribute, 0.0)
        if weight <= 0:
            continue
        considered += weight
        value = _track_value(track, attribute)
        if value and _matches(value, wanted):
            matched += weight
    if considered <= 0:
        return 0.0
    return matched / considered


def blend_affinity(attribute_score: float, llm_score: Optional[float] = None,
                   embedding_score: Optional[float] = None) -> float:
    """Combine the attribute score with whichever model signals are available.

    Weights are normalised over the signals actually present, so a missing one
    costs nothing rather than counting as a zero. With neither model signal this
    is the attribute score unchanged, letting every caller blend unconditionally
    while tier 1 still stands on its own.
    """
    total = ATTRIBUTE_SIGNAL_WEIGHT
    weighted = attribute_score * ATTRIBUTE_SIGNAL_WEIGHT
    if llm_score is not None:
        total += LLM_SIGNAL_WEIGHT
        weighted += llm_score * LLM_SIGNAL_WEIGHT
    if embedding_score is not None:
        total += EMBEDDING_SIGNAL_WEIGHT
        weighted += embedding_score * EMBEDDING_SIGNAL_WEIGHT
    return weighted / total if total > 0 else attribute_score


def reference_description(reference: Optional[AffinityReference]) -> str:
    """The reference as a phrase to put in a prompt. Empty if there is nothing to say."""
    if reference is None or reference.is_empty():
        return ""
    parts = []
    for attribute in _REFERENCE_DESCRIPTION_ORDER:
        wanted = reference.values.get(attribute)
        if wanted:
            parts.append(f"{attribute}: {', '.join(sorted(wanted))}")
    return "; ".join(parts)


def llm_group_scores(reference: Optional[AffinityReference], group_values: List[str],
                     llm: Any = None) -> Optional[Dict[str, float]]:
    """Score each group against the reference in one model call, keyed by group value.

    Keyed by value rather than by position so the result stays usable after the
    window has moved on, which it will have by the time a slow call returns.

    Never raises. Returns None whenever the model is unavailable, slow, or
    answers with anything other than a full set of valid scores -- the caller
    then has attribute overlap alone, which is a complete answer by itself.
    """
    candidates = [v for v in group_values if v]
    if reference is None or reference.is_empty() or not candidates:
        return None
    candidates = candidates[:MAX_LLM_SCORED_GROUPS]
    if len(group_values) > MAX_LLM_SCORED_GROUPS:
        logger.info(f"Scoring only the first {MAX_LLM_SCORED_GROUPS} of {len(group_values)} groups")

    try:
        from extensions.llm import LLM
        from muse.prompter import Prompter

        if llm is None:
            # Its own failure state: scoring going quiet must not count towards
            # taking the DJ's generation offline, nor the other way round.
            llm = LLM.from_config(state_key="track_affinity")
        if llm.is_failing():
            logger.info("Skipping affinity scoring, the model has been failing")
            return None

        prompt = Prompter().get_prompt("score_track_affinity")
        prompt = prompt.replace("REFERENCE", reference_description(reference))
        prompt = prompt.replace(
            "CANDIDATES", "\n".join(f"{i}: {v}" for i, v in enumerate(candidates)))
        result = llm.generate_json_get_value(prompt, "scores",
                                             timeout=LLM_AFFINITY_TIMEOUT_SECONDS)
    except Exception as e:
        logger.warning(f"Affinity scoring call failed, using attribute overlap alone: {e}")
        return None

    if result is None or not isinstance(result.response, dict) or len(result.response) != len(candidates):
        return None
    scores: Dict[str, float] = {}
    try:
        for key, value in result.response.items():
            index = int(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return None
            score = float(value)
            if index not in range(len(candidates)) or not (0.0 <= score <= 1.0):
                return None
            scores[candidates[index]] = score
    except (TypeError, ValueError) as e:
        logger.warning(f"Affinity scoring returned an unusable response: {e}")
        return None
    return scores if len(scores) == len(set(candidates)) else None


_embedder: Any = None
_embedder_unavailable = False


def _get_embedder() -> Any:
    """The sentence-transformer model, loaded once, or None if it cannot be had.

    sentence-transformers is optional: without it this tier is simply off, the
    same as any other signal that declines. The import is deferred because it
    pulls in torch, and the first load fetches model weights, so this must only
    ever be reached from the background scoring pass.
    """
    global _embedder, _embedder_unavailable
    if _embedder is not None or _embedder_unavailable:
        return _embedder
    try:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer(EMBED_MODEL_NAME)
        logger.info(f"Loaded embedding model {EMBED_MODEL_NAME} for affinity scoring")
    except Exception as e:
        # Remembered, so a missing package is not re-attempted on every grouping change.
        _embedder_unavailable = True
        logger.info(f"Embedding affinity is unavailable, the other signals still apply: {e}")
    return _embedder


def embed_texts(texts: List[str]) -> Optional[List[List[float]]]:
    """Vectors for *texts*, or None if the model is unavailable or fails."""
    model = _get_embedder()
    if model is None:
        return None
    try:
        return [list(vector) for vector in model.encode(texts)]
    except Exception as e:
        logger.warning(f"Embedding failed: {e}")
        return None


def cosine_similarity(left: List[float], right: List[float]) -> Optional[float]:
    """Cosine of the angle between two vectors, or None if they cannot be compared.

    Written out rather than taken from numpy: the window holds a few dozen
    vectors, so this is a few thousand multiplications, and it keeps an array
    library off the playback thread.
    """
    if not left or not right or len(left) != len(right):
        return None
    dot = 0.0
    left_sq = 0.0
    right_sq = 0.0
    for a, b in zip(left, right):
        dot += a * b
        left_sq += a * a
        right_sq += b * b
    if left_sq <= 0.0 or right_sq <= 0.0:
        return None
    return dot / math.sqrt(left_sq * right_sq)


def embedding_group_scores(reference: Optional[AffinityReference], group_values: List[str],
                           attribute: str = "") -> Optional[Dict[str, float]]:
    """Score each group by embedding similarity to the reference, keyed by group value.

    Catches relatedness that exact-match overlap misses -- a differing spelling,
    or a form that is close without being the same word. Vectors are computed on
    demand for the window and discarded; nothing is precomputed or stored.

    Never raises. Returns None when the model is unavailable or gives back
    anything unusable, leaving the ordering to the other signals.
    """
    candidates = [v for v in group_values if v]
    if reference is None or reference.is_empty() or not candidates:
        return None
    candidates = candidates[:MAX_LLM_SCORED_GROUPS]

    description = reference_description(reference)
    if not description:
        return None
    prefix = f"{attribute}: " if attribute else ""
    texts = [description] + [f"{prefix}{value}" for value in candidates]

    try:
        vectors = embed_texts(texts)
    except Exception as e:
        logger.warning(f"Embedding scoring failed, leaving the ordering to the other signals: {e}")
        return None
    if not vectors or len(vectors) != len(texts):
        return None

    scores: Dict[str, float] = {}
    for value, vector in zip(candidates, vectors[1:]):
        similarity = cosine_similarity(vectors[0], vector)
        if similarity is None:
            return None
        # Opposed vectors carry no more meaning here than unrelated ones.
        scores[value] = max(0.0, min(1.0, similarity))
    return scores or None


def reference_for(descriptor: Any = None, start_track: Any = None) -> Optional[AffinityReference]:
    """The reference a playlist should be ordered against, or None for no reordering.

    Sources are tried in order of how specifically they state an intent. A search
    query and a chosen start track are both explicit and combine; favorites are a
    standing preference and only apply when neither is present, since merging
    them into a search would let a favorite outscore what was actually searched
    for.

    Never raises: any failure here means the playlist keeps the order it already
    had, which is the behaviour from before this existed.
    """
    try:
        if not affinity_enabled():
            return None
        if descriptor is not None and not descriptor.allows_resort():
            # The listener named every track, so the order is already their decision.
            return None

        reference = AffinityReference()
        search_query = getattr(descriptor, "search_query", None) if descriptor is not None else None
        if search_query:
            reference = reference.merge(AffinityReference.from_search_query(search_query))
        if start_track is not None:
            reference = reference.merge(AffinityReference.from_track(start_track))
        if reference.is_empty():
            reference = AffinityReference.from_favorites_profile(current_favorites_profile())
        return None if reference.is_empty() else reference
    except Exception as e:
        logger.warning(f"Could not build an affinity reference, leaving playlist order alone: {e}")
        return None


def current_favorites_profile(top_n: int = 5) -> Dict[str, List[str]]:
    """The stored favorites as a profile. Empty if they are unreadable."""
    try:
        from utils.app_info_cache import app_info_cache
        return favorites_profile(app_info_cache.get("favorites", []), top_n=top_n)
    except Exception as e:
        logger.warning(f"Could not read favorites: {e}")
        return {}


def favorites_profile(raw_favorites: Optional[List[Any]], top_n: int = 5) -> Dict[str, List[str]]:
    """The listener's most-favorited values per attribute, commonest first.

    Small enough to hand to a prompt verbatim and usable directly as a reference,
    which raw favorites are not -- they are mostly duplication, and encoding them
    wholesale would spend tokens without conveying more.
    """
    if not raw_favorites:
        return {}
    from library_data.favorite import Favorite

    counters: Dict[str, Counter] = {}
    for raw in raw_favorites:
        if not isinstance(raw, dict):
            continue
        try:
            favorite = Favorite.from_dict(raw)
        except Exception:
            continue
        attribute = favorite.attribute
        if not isinstance(attribute, TrackAttribute):
            continue
        name = attribute.value
        if name not in TRACK_VALUE_GETTERS:
            continue
        value = (favorite.value or "").strip()
        if value:
            counters.setdefault(name, Counter())[value] += 1

    return {
        name: [value for value, _count in counter.most_common(top_n)]
        for name, counter in counters.items()
    }
