"""Unit tests for the embedding tier of muse/track_affinity.py.

Vectors are supplied directly rather than computed, so the similarity arithmetic
and the decline paths are what is under test -- not the model. The stub replaces
``embed_texts`` in this module's own namespace, which is the seam the caller
actually reads; patching a method on a class reached by a deferred import does
not take, and the test then silently runs against whatever is really installed.
"""

import pytest

from muse.track_affinity import (
    ATTRIBUTE_SIGNAL_WEIGHT,
    EMBEDDING_SIGNAL_WEIGHT,
    LLM_SIGNAL_WEIGHT,
    AffinityReference,
    blend_affinity,
    cosine_similarity,
    embedding_group_scores,
)


def _reference(**values):
    reference = AffinityReference()
    for attribute, value in values.items():
        reference.add(attribute, value)
    return reference


def _vectors(monkeypatch, vectors):
    """Stand in for the model, returning fixed vectors for whatever is asked."""
    monkeypatch.setattr("muse.track_affinity.embed_texts", lambda texts: vectors)


@pytest.mark.unit
class TestCosineSimilarity:
    def test_identical_vectors_score_one(self):
        assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)

    def test_magnitude_does_not_matter(self):
        """Only direction carries meaning, so an unnormalised vector is fine."""
        assert cosine_similarity([1.0, 0.0], [7.0, 0.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors_score_zero(self):
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposed_vectors_score_minus_one(self):
        assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_mismatched_lengths_cannot_be_compared(self):
        assert cosine_similarity([1.0, 0.0], [1.0]) is None

    def test_empty_and_zero_vectors_cannot_be_compared(self):
        assert cosine_similarity([], [1.0]) is None
        assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) is None


@pytest.mark.unit
class TestEmbedTexts:
    @pytest.fixture(autouse=True)
    def reset_module_state(self):
        """The loaded model and the "gave up" flag are module-level, so they have
        to be cleared or one test's outcome decides the next one's."""
        import muse.track_affinity as module

        before = (module._embedder, module._embedder_unavailable)
        module._embedder, module._embedder_unavailable = None, False
        yield
        module._embedder, module._embedder_unavailable = before

    def test_a_missing_package_reads_as_no_vectors(self, monkeypatch):
        import muse.track_affinity as module

        monkeypatch.setattr(module, "_get_embedder", lambda: None)

        assert module.embed_texts(["anything"]) is None

    def test_an_absent_package_is_not_an_error(self, monkeypatch):
        """A None entry in sys.modules is what an unimportable package looks
        like, and is how this reads on a machine without the optional install."""
        import sys

        import muse.track_affinity as module

        monkeypatch.setitem(sys.modules, "sentence_transformers", None)

        assert module._get_embedder() is None

    def test_giving_up_is_remembered(self, monkeypatch):
        """Retrying an absent package on every grouping change would pay the
        import cost forever."""
        import sys

        import muse.track_affinity as module

        monkeypatch.setitem(sys.modules, "sentence_transformers", None)
        module._get_embedder()

        assert module._embedder_unavailable is True
        # The flag alone now decides, so a package appearing later is not picked
        # up until the next run -- which is the trade for not retrying forever.
        monkeypatch.undo()
        assert module._get_embedder() is None

    def test_a_model_that_raises_reads_as_no_vectors(self, monkeypatch):
        import muse.track_affinity as module

        class _Broken:
            def encode(self, _texts):
                raise RuntimeError("out of memory")

        monkeypatch.setattr(module, "_get_embedder", lambda: _Broken())

        assert module.embed_texts(["anything"]) is None

    def test_vectors_come_back_as_plain_lists(self, monkeypatch):
        """The model returns arrays; cosine_similarity walks plain sequences."""
        import muse.track_affinity as module

        class _Model:
            def encode(self, texts):
                return [(1.0, 0.0) for _ in texts]

        monkeypatch.setattr(module, "_get_embedder", lambda: _Model())

        assert module.embed_texts(["a", "b"]) == [[1.0, 0.0], [1.0, 0.0]]


@pytest.mark.unit
class TestEmbeddingGroupScores:
    def test_scores_are_keyed_by_group_value(self, monkeypatch):
        # Reference vector, then one per candidate: identical, then orthogonal.
        _vectors(monkeypatch, [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]])

        scores = embedding_group_scores(_reference(composer="Mozart"), ["Haydn", "Coltrane"])

        assert scores["Haydn"] == pytest.approx(1.0)
        assert scores["Coltrane"] == pytest.approx(0.0)

    def test_opposed_vectors_are_floored_at_zero(self, monkeypatch):
        """Being opposed carries no more meaning here than being unrelated."""
        _vectors(monkeypatch, [[1.0, 0.0], [-1.0, 0.0]])

        assert embedding_group_scores(_reference(composer="Mozart"), ["Haydn"])["Haydn"] == 0.0

    def test_an_unavailable_model_means_the_tier_is_off(self, monkeypatch):
        """sentence-transformers is optional, so its absence has to read as one
        signal declining rather than as an error."""
        _vectors(monkeypatch, None)

        assert embedding_group_scores(_reference(composer="Mozart"), ["Haydn"]) is None

    def test_no_reference_means_nothing_to_measure_against(self, monkeypatch):
        _vectors(monkeypatch, [[1.0], [1.0]])

        assert embedding_group_scores(AffinityReference(), ["Haydn"]) is None
        assert embedding_group_scores(None, ["Haydn"]) is None

    def test_no_candidates_means_no_call(self, monkeypatch):
        _vectors(monkeypatch, [[1.0]])

        assert embedding_group_scores(_reference(composer="Mozart"), []) is None
        assert embedding_group_scores(_reference(composer="Mozart"), ["", None]) is None

    def test_a_short_answer_is_declined(self, monkeypatch):
        """One vector back for two candidates plus the reference is unusable."""
        _vectors(monkeypatch, [[1.0, 0.0], [1.0, 0.0]])

        assert embedding_group_scores(_reference(composer="Mozart"),
                                      ["Haydn", "Coltrane"]) is None

    def test_uncomparable_vectors_are_declined(self, monkeypatch):
        _vectors(monkeypatch, [[1.0, 0.0], [1.0]])

        assert embedding_group_scores(_reference(composer="Mozart"), ["Haydn"]) is None

    def test_a_raising_model_is_declined_rather_than_propagated(self, monkeypatch):
        def _raise(_texts):
            raise RuntimeError("model went away")

        monkeypatch.setattr("muse.track_affinity.embed_texts", _raise)

        assert embedding_group_scores(_reference(composer="Mozart"), ["Haydn"]) is None

    def test_the_attribute_labels_the_candidates(self, monkeypatch):
        """A bare value gives the model nothing to place; the attribute says what
        kind of thing it is looking at."""
        asked = []
        monkeypatch.setattr("muse.track_affinity.embed_texts",
                            lambda texts: asked.append(list(texts)) or [[1.0], [1.0]])

        embedding_group_scores(_reference(composer="Mozart"), ["Haydn"], attribute="composer")

        assert asked[0][1] == "composer: Haydn"


@pytest.mark.unit
class TestBlendWithThreeSignals:
    def test_all_three_are_normalised_over_their_weights(self):
        expected = (1.0 * ATTRIBUTE_SIGNAL_WEIGHT + 0.0 * LLM_SIGNAL_WEIGHT
                    + 0.0 * EMBEDDING_SIGNAL_WEIGHT) / (
            ATTRIBUTE_SIGNAL_WEIGHT + LLM_SIGNAL_WEIGHT + EMBEDDING_SIGNAL_WEIGHT)

        assert blend_affinity(1.0, 0.0, 0.0) == pytest.approx(expected)

    def test_a_missing_signal_costs_nothing(self):
        """Absent must not mean zero, or having no embedding model would drag
        every score down."""
        assert blend_affinity(1.0, 1.0, None) == pytest.approx(1.0)
        assert blend_affinity(1.0, None, None) == pytest.approx(1.0)

    def test_embeddings_alone_still_blend(self):
        expected = ATTRIBUTE_SIGNAL_WEIGHT / (ATTRIBUTE_SIGNAL_WEIGHT + EMBEDDING_SIGNAL_WEIGHT)

        assert blend_affinity(1.0, None, 0.0) == pytest.approx(expected)

    def test_embeddings_weigh_less_than_the_chat_model(self):
        """Similarity over a short label nudges; it does not decide."""
        assert EMBEDDING_SIGNAL_WEIGHT < LLM_SIGNAL_WEIGHT

    def test_agreement_across_all_signals_preserves_the_score(self):
        assert blend_affinity(1.0, 1.0, 1.0) == pytest.approx(1.0)
        assert blend_affinity(0.0, 0.0, 0.0) == pytest.approx(0.0)
