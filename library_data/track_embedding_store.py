"""Library-wide vectors per search field, so a search can return tracks whose
text never literally contains the query.

The ranking signal in LibraryDataSearch scores the tracks the substring filter
already returned. This is the other half: which tracks that filter never looked
at are worth returning at all. That inverts the cost -- the work scales with the
library rather than with one page of results -- so these vectors are built once
and kept, where the ranking ones are built per search and thrown away.

Everything lives in one compressed-free .npz beside the other caches: one matrix
per field plus a JSON blob holding the model name and, per field, the filepath
and text hash behind each row. Not the database, because bulk float data does
not belong in a schema and staying out of it means no migration; not the media
track cache, because that is rewritten whole and would then pay for the vectors
on every write. The hash is of the exact text a row was built from, so an edited
tag or a renamed file re-encodes that row alone. The model name is stored with
them because vectors from two models cannot be compared, so a model change has
to discard the archive rather than silently mix them.

Values are embedded bare, without the "field: " label the ranking path applies.
There the label is constant across one sort and cancels out; here it would sit
in every row of a library-wide comparison and compress the very range of
similarities the cutoff has to discriminate on.
"""

import hashlib
import json
import os
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from utils.cache_paths import resolve_cache_file
from utils.config import config
from utils.logging_setup import get_logger
from utils.translations import I18N

_ = I18N._

logger = get_logger(__name__)

try:
    import numpy as np
except Exception as e:
    np = None
    logger.info(f"Semantic search recall is unavailable without numpy: {e}")

STORE_FILENAME = "app_track_embeddings.npz"

# Fields whose values are distinct enough per track to be worth a row each.
DEFAULT_SEMANTIC_FIELDS = ("title", "artist", "album")

# How many candidates one query may contribute, before the cutoffs below.
DEFAULT_TOP_K = 25

# The working cutoff: a candidate is kept while it stays within this much of the
# best candidate for the same query. Relative because the cosine scale shifts
# from query to query, so one fixed threshold is either too tight or too loose
# depending on what was typed.
DEFAULT_RELATIVE_FLOOR = 0.15

# The sanity gate under the relative floor, not the working cutoff. Without it a
# query with no neighbours at all still returns its least-bad ones, since every
# score sits within the margin of a bad best score.
DEFAULT_MIN_SCORE = 0.25

ENCODE_BATCH_SIZE = 512

# Encoding time between saves. The build thread is a daemon, so it dies with the
# application, and a first build over a large library is long enough to be caught
# mid-way. Measured in time rather than rows because a save rewrites the whole
# archive: against this much work the rewrite is noise, whatever the library size
# or the machine.
CHECKPOINT_SECONDS = 120


# Deferred the way the other readers of track_affinity reach it: importing muse
# pulls in the playback package, and loading the model pulls in torch.
def _model_name() -> str:
    from muse.track_affinity import EMBED_MODEL_NAME
    return EMBED_MODEL_NAME


def _model() -> Any:
    from muse.track_affinity import embedding_model
    return embedding_model()


def semantic_recall_enabled() -> bool:
    return bool(getattr(config, "search_enable_semantic_recall", True))


def semantic_fields() -> Tuple[str, ...]:
    configured = getattr(config, "search_semantic_fields", None)
    if isinstance(configured, (list, tuple)):
        fields = tuple(str(f).strip().lower() for f in configured if str(f).strip())
        if fields:
            return fields
    return DEFAULT_SEMANTIC_FIELDS


def _config_number(name: str, default, cast):
    value = getattr(config, name, None)
    try:
        return cast(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def top_k() -> int:
    return max(1, _config_number("search_semantic_top_k", DEFAULT_TOP_K, int))


def relative_floor() -> float:
    return _config_number("search_semantic_relative_floor", DEFAULT_RELATIVE_FLOOR, float)


def min_score() -> float:
    return _config_number("search_semantic_min_score", DEFAULT_MIN_SCORE, float)


def track_text(track: Any, track_attr: str) -> str:
    """One track's value for a field, or "" where it has none."""
    value = getattr(track, track_attr, None)
    if callable(value):
        value = value()
    return str(value).strip() if value else ""


def _text_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


class TrackEmbeddingStore:
    """Every field's vectors, in one archive.

    Reads are cheap and always answer with whatever is currently built, so a
    search never waits on encoding. Building happens on its own thread and swaps
    the finished matrix in at the end.
    """

    def __init__(self):
        self._state_lock = threading.Lock()
        self._build_lock = threading.Lock()
        self._loaded = False
        self._matrices: Dict[str, Any] = {}
        self._paths: Dict[str, List[str]] = {}
        self._hashes: Dict[str, List[str]] = {}
        self._building: Set[str] = set()
        self._checked_track_count: Dict[str, int] = {}

    @property
    def path(self) -> str:
        return resolve_cache_file(STORE_FILENAME)

    def _clear_locked(self) -> None:
        self._matrices = {}
        self._paths = {}
        self._hashes = {}

    def _load_locked(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if np is None:
            return
        try:
            if not os.path.isfile(self.path):
                return
            with np.load(self.path) as archive:
                if "meta" not in archive:
                    return
                meta = json.loads(bytes(archive["meta"]).decode("utf-8"))
                model_name = _model_name()
                if meta.get("model") != model_name:
                    logger.info(f"Discarding the search index, it was built with "
                                f"{meta.get('model')} and the model is now {model_name}")
                    return
                for field, entries in (meta.get("fields") or {}).items():
                    key = f"vectors_{field}"
                    if key not in archive:
                        continue
                    matrix = archive[key]
                    if matrix.ndim != 2 or matrix.shape[0] != len(entries):
                        logger.warning(f"Dropping {field} from the search index, "
                                       f"{matrix.shape[0]} rows against {len(entries)} entries")
                        continue
                    self._matrices[field] = matrix.astype(np.float32, copy=False)
                    self._paths[field] = [entry[0] for entry in entries]
                    self._hashes[field] = [entry[1] for entry in entries]
            logger.info("Loaded search index: "
                        + ", ".join(f"{field} {len(paths)}"
                                    for field, paths in self._paths.items()))
        except Exception as e:
            logger.warning(f"Could not read the search index, it will be rebuilt: {e}")
            self._clear_locked()

    def _write_locked(self) -> None:
        try:
            meta = {
                "model": _model_name(),
                "fields": {field: [[path, digest] for path, digest
                                   in zip(self._paths[field], self._hashes[field])]
                           for field in self._matrices},
            }
            payload = {f"vectors_{field}": matrix for field, matrix in self._matrices.items()}
            # As bytes rather than an object entry, so the archive never needs
            # pickle to be read back.
            payload["meta"] = np.frombuffer(json.dumps(meta).encode("utf-8"), dtype=np.uint8)
            np.savez(self.path, **payload)
        except Exception as e:
            logger.warning(f"Could not write the search index, it will be rebuilt next time: {e}")

    def reset(self) -> None:
        """Make every field re-check itself against the library on next use."""
        with self._state_lock:
            self._checked_track_count = {}

    def ensure_built(self, field: str, tracks, track_attr: str, status_callback=None) -> None:
        """Start a build if the library has moved on. Returns without waiting.

        A search that runs while this is still encoding simply gets whatever is
        already built, which is the whole point of not blocking on it.
        """
        if np is None or not tracks:
            return
        with self._state_lock:
            if field in self._building or self._checked_track_count.get(field) == len(tracks):
                return
            self._building.add(field)
        from utils.utils import Utils

        def build_thread():
            try:
                self.build(field, tracks, track_attr, status_callback=status_callback)
            finally:
                with self._state_lock:
                    self._building.discard(field)

        Utils.start_thread(build_thread, use_asyncio=False)

    def build(self, field: str, tracks, track_attr: str, status_callback=None) -> bool:
        """Bring *field* level with *tracks*, encoding only what is missing or stale.

        Never raises. Encoding happens outside the state lock, so queries keep
        answering from the previous matrix while a rebuild is in progress.
        """
        if np is None:
            return False
        with self._build_lock:
            try:
                with self._state_lock:
                    self._load_locked()
                    known = {path: (row, digest) for row, (path, digest)
                             in enumerate(zip(self._paths.get(field, []),
                                              self._hashes.get(field, [])))}
                    matrix = self._matrices.get(field)

                wanted: List[Tuple[str, str, str]] = []
                seen = set()
                for track in tracks:
                    filepath = str(track.filepath)
                    if filepath in seen:
                        continue
                    seen.add(filepath)
                    text = track_text(track, track_attr)
                    if text:
                        wanted.append((filepath, text, _text_hash(text)))

                rows: List[Any] = []
                stale: List[int] = []
                for position, (filepath, _text, digest) in enumerate(wanted):
                    found = known.get(filepath)
                    if found is not None and found[1] == digest and matrix is not None:
                        rows.append(matrix[found[0]])
                    else:
                        rows.append(None)
                        stale.append(position)

                if not stale and len(wanted) == len(known):
                    with self._state_lock:
                        self._checked_track_count[field] = len(tracks)
                    return True

                if stale:
                    model = _model()
                    if model is None:
                        return False
                    logger.info(f"Encoding {len(stale)} {field} values for the search index")
                    last_checkpoint = time.monotonic()
                    for start in range(0, len(stale), ENCODE_BATCH_SIZE):
                        chunk = stale[start:start + ENCODE_BATCH_SIZE]
                        encoded = model.encode([wanted[position][1] for position in chunk],
                                               convert_to_numpy=True,
                                               normalize_embeddings=True,
                                               show_progress_bar=False)
                        encoded = np.asarray(encoded, dtype=np.float32)
                        for slot, position in enumerate(chunk):
                            rows[position] = encoded[slot]
                        if status_callback:
                            try:
                                status_callback(_("Building search index... ({0}/{1})").format(
                                    min(start + ENCODE_BATCH_SIZE, len(stale)), len(stale)))
                            except Exception as e:
                                logger.error(f"Error in search index status callback: {e}")
                        if time.monotonic() - last_checkpoint >= CHECKPOINT_SECONDS:
                            self._install(field, wanted, rows, len(tracks), partial=True)
                            last_checkpoint = time.monotonic()

                self._install(field, wanted, rows, len(tracks))
                logger.info(f"Search index for {field} holds {len(wanted)} vectors")
                return True
            except Exception as e:
                logger.warning(f"Could not build the {field} search index, "
                               f"searches stay literal: {e}")
                return False

    def _install(self, field: str, wanted: List[Tuple[str, str, str]], rows: List[Any],
                 track_count: int, partial: bool = False) -> None:
        """Put the finished rows in place and save.

        A partial save is what lets an interrupted build resume rather than start
        over: what is written is always a valid index over a subset of the
        library, and the next build encodes the rows that are missing from it.
        """
        resolved = [position for position, row in enumerate(rows) if row is not None]
        if partial and not resolved:
            return
        with self._state_lock:
            # An explicit empty matrix rather than none at all: every track
            # having lost its value for this field is a real state, and it has
            # to round-trip as "nothing indexed".
            self._matrices[field] = (np.vstack([rows[position] for position in resolved])
                                     .astype(np.float32) if resolved
                                     else np.zeros((0, 1), dtype=np.float32))
            self._paths[field] = [wanted[position][0] for position in resolved]
            self._hashes[field] = [wanted[position][2] for position in resolved]
            if not partial:
                self._checked_track_count[field] = track_count
            self._write_locked()

    def query(self, field: str, text: str) -> List[Tuple[str, float]]:
        """Filepaths closest to *text*, best first, after both cutoffs.

        Never raises. An empty list means the index has nothing to add, which is
        also what an absent model or an unbuilt field gives.
        """
        if np is None or not text:
            return []
        try:
            with self._state_lock:
                self._load_locked()
                matrix = self._matrices.get(field)
                paths = list(self._paths.get(field, []))
            if matrix is None or not paths:
                return []
            model = _model()
            if model is None:
                return []
            vector = model.encode([text], convert_to_numpy=True,
                                  normalize_embeddings=True, show_progress_bar=False)
            vector = np.asarray(vector, dtype=np.float32).reshape(-1)
            if vector.shape[0] != matrix.shape[1]:
                logger.warning(f"The {field} search index has {matrix.shape[1]}-wide rows "
                               f"against a {vector.shape[0]}-wide query, discarding it")
                return []
            scores = matrix @ vector
            wanted = min(top_k(), scores.shape[0])
            best = np.argpartition(-scores, wanted - 1)[:wanted]
            best = best[np.argsort(-scores[best])]
            cutoff = max(float(scores[best[0]]) - relative_floor(), min_score())
            return [(paths[row], float(scores[row])) for row in best
                    if float(scores[row]) >= cutoff]
        except Exception as e:
            logger.warning(f"Could not query the {field} search index, "
                           f"the search stays literal: {e}")
            return []


_store: Optional[TrackEmbeddingStore] = None
_store_lock = threading.Lock()


def get_store() -> TrackEmbeddingStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = TrackEmbeddingStore()
        return _store


def reset_store() -> None:
    """Make the store re-check itself against the library on next use."""
    get_store().reset()
