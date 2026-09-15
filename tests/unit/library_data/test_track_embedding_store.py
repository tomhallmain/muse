"""Unit tests for the persisted vector store behind semantic recall.

The model is stubbed with a fixed text-to-vector table, so what is under test is
the incremental build, the on-disk round trip, the two cutoffs and the decline
paths -- not the model. Both seams are patched in this module's own namespace,
which is where the deferred imports read them.

Skipped wholesale without numpy, which is what the module itself does: the store
is inert there and every caller falls back to literal search.

User data isolation: MUSE_CACHE_DIR is redirected per test, so the archive is
written under pytest's tmp_path and never beside the real caches. Tracks are
in-memory stubs and no filesystem path below is ever opened as a media file.
"""

from types import SimpleNamespace

import pytest

np = pytest.importorskip("numpy")

from library_data import track_embedding_store
from library_data.track_embedding_store import STORE_FILENAME, TrackEmbeddingStore
from utils.config import config

MODEL_NAME = "test-model"

# Unit vectors on a circle: the angle between two texts is what their cosine
# similarity comes out as, so the table below states relatedness directly.
VECTORS = {
    "beethoven": (1.0, 0.0),
    "beethoven sonata": (0.995, 0.0998),      # ~0.995 to "beethoven"
    "beethovn": (0.98, 0.199),                # ~0.980, a misspelling
    "beethoven quartet": (0.94, 0.342),       # ~0.940
    "brahms": (0.6, 0.8),                     # ~0.600, same domain, different composer
    "tractor maintenance": (0.0, 1.0),        # 0.0, unrelated
}


class _FakeModel:
    """Returns the table's vectors and records what it was asked to encode."""

    def __init__(self):
        self.encoded = []

    def encode(self, texts, convert_to_numpy=False, normalize_embeddings=False,
               show_progress_bar=False):
        self.encoded.extend(texts)
        rows = []
        for text in texts:
            if text not in VECTORS:
                raise AssertionError(f"unexpected text encoded: {text!r}")
            vector = np.array(VECTORS[text], dtype=np.float32)
            rows.append(vector / np.linalg.norm(vector))
        return np.vstack(rows)


def _track(filepath, title, artist=""):
    return SimpleNamespace(filepath=filepath, searchable_title=title,
                           searchable_artist=artist)


@pytest.fixture
def model(monkeypatch, tmp_path):
    monkeypatch.setenv("MUSE_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(track_embedding_store, "_model_name", lambda: MODEL_NAME)
    fake = _FakeModel()
    monkeypatch.setattr(track_embedding_store, "_model", lambda: fake)
    monkeypatch.setattr(config, "search_semantic_top_k", 25, raising=False)
    monkeypatch.setattr(config, "search_semantic_relative_floor", 0.15, raising=False)
    monkeypatch.setattr(config, "search_semantic_min_score", 0.25, raising=False)
    return fake


def _store_files(cache_dir):
    """Every file the store wrote, by name. Other things share the cache
    directory, so this asks what this feature left rather than what is there."""
    return sorted(path.name for path in cache_dir.glob("app_track_embeddings*"))


def _built(model, titles):
    """A store holding one title row per entry, keyed by a synthetic path."""
    tracks = [_track(f"/synthetic/{i}.mp3", title) for i, title in enumerate(titles)]
    store = TrackEmbeddingStore()
    assert store.build("title", tracks, "searchable_title") is True
    return store, tracks


@pytest.mark.unit
class TestBuild:
    def test_a_build_writes_one_archive(self, model, tmp_path):
        _store, _tracks = _built(model, ["beethoven sonata", "brahms"])

        assert _store_files(tmp_path) == [STORE_FILENAME]
        assert sorted(model.encoded) == ["beethoven sonata", "brahms"]

    def test_every_field_shares_the_one_archive(self, model, tmp_path):
        tracks = [_track("/synthetic/0.mp3", "beethoven sonata", artist="brahms")]
        store = TrackEmbeddingStore()

        assert store.build("title", tracks, "searchable_title") is True
        assert store.build("artist", tracks, "searchable_artist") is True

        assert _store_files(tmp_path) == [STORE_FILENAME]
        reopened = TrackEmbeddingStore()
        assert [path for path, _score in reopened.query("title", "beethoven")] == ["/synthetic/0.mp3"]
        assert [path for path, _score in reopened.query("artist", "brahms")] == ["/synthetic/0.mp3"]

    def test_a_rebuild_encodes_nothing_when_the_library_has_not_moved(self, model):
        store, tracks = _built(model, ["beethoven sonata", "brahms"])
        model.encoded.clear()

        assert store.build("title", tracks, "searchable_title") is True

        assert model.encoded == []

    def test_only_the_changed_row_is_re_encoded(self, model):
        """The stored hash is of the exact text, so an edited tag costs one row."""
        store, tracks = _built(model, ["beethoven sonata", "brahms"])
        model.encoded.clear()
        tracks[1].searchable_title = "beethoven quartet"

        assert store.build("title", tracks, "searchable_title") is True

        assert model.encoded == ["beethoven quartet"]

    def test_a_removed_track_leaves_the_index(self, model):
        store, tracks = _built(model, ["beethoven sonata", "tractor maintenance"])
        assert [path for path, _score
                in store.query("title", "tractor maintenance")] == ["/synthetic/1.mp3"]
        model.encoded.clear()

        assert store.build("title", tracks[:1], "searchable_title") is True

        assert store.query("title", "tractor maintenance") == []
        assert model.encoded == ["tractor maintenance"], "the rebuild should encode nothing"

    def test_a_track_with_no_value_is_not_indexed(self, model):
        tracks = [_track("/synthetic/0.mp3", "beethoven sonata"),
                  _track("/synthetic/1.mp3", "")]
        store = TrackEmbeddingStore()

        assert store.build("title", tracks, "searchable_title") is True

        assert model.encoded == ["beethoven sonata"]

    def test_a_missing_model_leaves_the_field_unbuilt(self, monkeypatch, model):
        monkeypatch.setattr(track_embedding_store, "_model", lambda: None)
        tracks = [_track("/synthetic/0.mp3", "beethoven sonata")]
        store = TrackEmbeddingStore()

        assert store.build("title", tracks, "searchable_title") is False
        assert store.query("title", "beethoven") == []

    def test_a_raising_model_is_contained(self, monkeypatch, model):
        class _Raises:
            def encode(self, *args, **kwargs):
                raise RuntimeError("no model")

        monkeypatch.setattr(track_embedding_store, "_model", lambda: _Raises())
        tracks = [_track("/synthetic/0.mp3", "beethoven sonata")]
        store = TrackEmbeddingStore()

        assert store.build("title", tracks, "searchable_title") is False

    def test_an_interrupted_build_resumes_from_its_checkpoint(self, monkeypatch, model):
        """The build thread is a daemon and dies with the application, so a long
        first build has to leave behind what it already finished."""
        monkeypatch.setattr(track_embedding_store, "ENCODE_BATCH_SIZE", 1)
        monkeypatch.setattr(track_embedding_store, "CHECKPOINT_SECONDS", 0)
        tracks = [_track("/synthetic/0.mp3", "beethoven sonata"),
                  _track("/synthetic/1.mp3", "brahms")]

        class _FailsAfterTheFirstBatch:
            def __init__(self):
                self.calls = 0

            def encode(self, texts, **kwargs):
                self.calls += 1
                if self.calls > 1:
                    raise RuntimeError("interrupted")
                return model.encode(texts, **kwargs)

        monkeypatch.setattr(track_embedding_store, "_model", lambda: _FailsAfterTheFirstBatch())
        assert TrackEmbeddingStore().build("title", tracks, "searchable_title") is False

        model.encoded.clear()
        monkeypatch.setattr(track_embedding_store, "_model", lambda: model)

        assert TrackEmbeddingStore().build("title", tracks, "searchable_title") is True

        assert model.encoded == ["brahms"], "the finished row should not be encoded again"


@pytest.mark.unit
class TestPersistence:
    def test_a_fresh_store_reads_what_the_last_one_wrote(self, model):
        _store, _tracks = _built(model, ["beethoven sonata", "brahms"])
        model.encoded.clear()

        reopened = TrackEmbeddingStore()
        matches = reopened.query("title", "beethoven")

        assert [path for path, _score in matches] == ["/synthetic/0.mp3"]
        assert model.encoded == ["beethoven"], "only the query should need encoding"

    def test_the_archive_reads_back_without_pickle(self, model, tmp_path):
        """np.load defaults to refusing pickled objects, so the metadata has to
        be plain bytes rather than an object entry."""
        _store, _tracks = _built(model, ["beethoven sonata"])

        with np.load(tmp_path / STORE_FILENAME, allow_pickle=False) as archive:
            assert sorted(archive.files) == ["meta", "vectors_title"]

    def test_a_model_change_discards_the_stored_vectors(self, monkeypatch, model):
        """Vectors from two models are not comparable, so they cannot be mixed."""
        _store, _tracks = _built(model, ["beethoven sonata"])
        monkeypatch.setattr(track_embedding_store, "_model_name", lambda: "some-other-model")

        assert TrackEmbeddingStore().query("title", "beethoven") == []

    def test_a_dimension_mismatch_is_discarded(self, monkeypatch, model):
        _store, _tracks = _built(model, ["beethoven sonata"])

        class _WiderModel:
            def encode(self, texts, **kwargs):
                return np.ones((len(texts), 5), dtype=np.float32)

        monkeypatch.setattr(track_embedding_store, "_model", lambda: _WiderModel())

        assert TrackEmbeddingStore().query("title", "beethoven") == []

    def test_an_unreadable_archive_is_discarded(self, model, tmp_path):
        _store, _tracks = _built(model, ["beethoven sonata"])
        (tmp_path / STORE_FILENAME).write_bytes(b"not an archive")

        assert TrackEmbeddingStore().query("title", "beethoven") == []


@pytest.mark.unit
class TestCutoffs:
    def test_the_closest_candidate_comes_first(self, model):
        store, _tracks = _built(model, ["beethoven quartet", "beethovn", "beethoven sonata"])

        matches = store.query("title", "beethoven")

        assert [path for path, _score in matches] == [
            "/synthetic/2.mp3", "/synthetic/1.mp3", "/synthetic/0.mp3"]

    def test_the_relative_floor_drops_the_distant_ones(self, model):
        """brahms sits 0.4 below the best hit, past the 0.15 margin."""
        store, _tracks = _built(model, ["beethoven sonata", "brahms"])

        matches = store.query("title", "beethoven")

        assert [path for path, _score in matches] == ["/synthetic/0.mp3"]

    def test_a_widened_floor_admits_them(self, monkeypatch, model):
        monkeypatch.setattr(config, "search_semantic_relative_floor", 0.5, raising=False)
        store, _tracks = _built(model, ["beethoven sonata", "brahms"])

        assert len(store.query("title", "beethoven")) == 2

    def test_nothing_comes_back_when_nothing_is_close(self, model):
        """The margin alone would still return the least-bad candidate, since
        every score sits within it of a bad best score."""
        store, _tracks = _built(model, ["tractor maintenance"])

        assert store.query("title", "beethoven") == []

    def test_top_k_caps_what_one_query_contributes(self, monkeypatch, model):
        monkeypatch.setattr(config, "search_semantic_top_k", 2, raising=False)
        store, _tracks = _built(model, ["beethoven quartet", "beethovn", "beethoven sonata"])

        matches = store.query("title", "beethoven")

        assert [path for path, _score in matches] == ["/synthetic/2.mp3", "/synthetic/1.mp3"]


@pytest.mark.unit
class TestDeclinePaths:
    def test_an_unbuilt_field_has_nothing_to_add(self, model):
        store, _tracks = _built(model, ["beethoven sonata"])

        assert store.query("composer", "beethoven") == []

    def test_an_empty_store_has_nothing_to_add(self, model):
        assert TrackEmbeddingStore().query("title", "beethoven") == []

    def test_an_empty_query_has_nothing_to_ask(self, model):
        store, _tracks = _built(model, ["beethoven sonata"])
        model.encoded.clear()

        assert store.query("title", "") == []
        assert model.encoded == []

    def test_a_failing_query_leaves_the_search_literal(self, monkeypatch, model):
        store, _tracks = _built(model, ["beethoven sonata"])

        class _Raises:
            def encode(self, *args, **kwargs):
                raise RuntimeError("no model")

        monkeypatch.setattr(track_embedding_store, "_model", lambda: _Raises())

        assert store.query("title", "beethoven") == []
