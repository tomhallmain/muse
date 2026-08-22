"""Unit tests for the model-scoring tier of muse/track_affinity.py.

The tier exists to buy judgement attribute overlap cannot express -- that two
different composers are close to each other. Most of what is checked here is
that it declines cleanly, since it must never be worse than not running.
"""

from types import SimpleNamespace

import pytest

from muse.track_affinity import (
    ATTRIBUTE_SIGNAL_WEIGHT,
    LLM_SIGNAL_WEIGHT,
    MAX_LLM_SCORED_GROUPS,
    AffinityReference,
    blend_affinity,
    llm_group_scores,
    reference_description,
)


def _reference(**values):
    reference = AffinityReference()
    for attribute, value in values.items():
        reference.add(attribute, value)
    return reference


def _llm(response, failing=False):
    return SimpleNamespace(
        is_failing=lambda: failing,
        generate_json_get_value=lambda *a, **k: (
            None if response is None else SimpleNamespace(response=response)),
    )


def _raising_llm(exception):
    def _raise(*_a, **_k):
        raise exception

    return SimpleNamespace(is_failing=lambda: False, generate_json_get_value=_raise)


@pytest.mark.unit
class TestBlendAffinity:
    def test_no_model_score_leaves_the_attribute_score_alone(self):
        assert blend_affinity(0.75, None) == pytest.approx(0.75)

    def test_scores_are_blended_not_replaced(self):
        """A bad or eccentric model score must not override what the tags state."""
        blended = blend_affinity(1.0, 0.0)
        expected = ATTRIBUTE_SIGNAL_WEIGHT / (ATTRIBUTE_SIGNAL_WEIGHT + LLM_SIGNAL_WEIGHT)

        assert blended == pytest.approx(expected)
        assert 0.0 < blended < 1.0

    def test_agreement_preserves_the_score(self):
        assert blend_affinity(1.0, 1.0) == pytest.approx(1.0)
        assert blend_affinity(0.0, 0.0) == pytest.approx(0.0)

    def test_a_model_score_can_lift_an_unrelated_attribute_score(self):
        """The whole point: a different composer the model judges close."""
        assert blend_affinity(0.0, 1.0) > 0.0


@pytest.mark.unit
class TestReferenceDescription:
    def test_empty_reference_says_nothing(self):
        assert reference_description(None) == ""
        assert reference_description(AffinityReference()) == ""

    def test_attributes_are_named_with_their_values(self):
        # AffinityReference stores values lowercased for matching.
        assert reference_description(_reference(composer="Mozart")) == "composer: mozart"

    def test_longest_lived_signals_come_first(self):
        text = reference_description(_reference(genre="Classical", composer="Mozart"))

        assert text.index("composer") < text.index("genre")

    def test_multiple_values_are_listed(self):
        reference = _reference(composer="Mozart")
        reference.add("composer", "Haydn")

        assert reference_description(reference) == "composer: haydn, mozart"


@pytest.mark.unit
class TestLlmGroupScores:
    def test_scores_are_keyed_by_group_value(self):
        """Keyed by value rather than position, so the result survives the window
        moving on before a slow call returns."""
        scores = llm_group_scores(_reference(composer="Mozart"), ["Haydn", "Coltrane"],
                                  llm=_llm({"0": 0.9, "1": 0.1}))

        assert scores == {"Haydn": 0.9, "Coltrane": 0.1}

    def test_a_failing_model_is_not_called(self):
        assert llm_group_scores(_reference(composer="Mozart"), ["Haydn"],
                                llm=_llm({"0": 0.9}, failing=True)) is None

    def test_no_reference_means_nothing_to_score_against(self):
        assert llm_group_scores(AffinityReference(), ["Haydn"], llm=_llm({"0": 0.9})) is None
        assert llm_group_scores(None, ["Haydn"], llm=_llm({"0": 0.9})) is None

    def test_no_candidates_means_no_call(self):
        assert llm_group_scores(_reference(composer="Mozart"), [], llm=_llm({})) is None
        assert llm_group_scores(_reference(composer="Mozart"), ["", None], llm=_llm({})) is None

    def test_no_response_is_declined(self):
        assert llm_group_scores(_reference(composer="Mozart"), ["Haydn"], llm=_llm(None)) is None

    def test_a_partial_answer_is_declined(self):
        """Half the groups scored would silently reorder against a mix of scored
        and unscored, so the whole answer is dropped."""
        assert llm_group_scores(_reference(composer="Mozart"), ["Haydn", "Coltrane"],
                                llm=_llm({"0": 0.9})) is None

    def test_scores_outside_the_range_are_declined(self):
        assert llm_group_scores(_reference(composer="Mozart"), ["Haydn"],
                                llm=_llm({"0": 1.4})) is None

    def test_an_index_that_names_no_candidate_is_declined(self):
        assert llm_group_scores(_reference(composer="Mozart"), ["Haydn"],
                                llm=_llm({"7": 0.9})) is None

    @pytest.mark.parametrize("value", [True, "0.9", None, [0.9]])
    def test_non_numeric_scores_are_declined(self, value):
        """True would otherwise pass as 1.0, since bool is an int."""
        assert llm_group_scores(_reference(composer="Mozart"), ["Haydn"],
                                llm=_llm({"0": value})) is None

    def test_a_non_dict_response_is_declined(self):
        assert llm_group_scores(_reference(composer="Mozart"), ["Haydn"],
                                llm=_llm([0.9])) is None

    def test_a_non_numeric_key_is_declined(self):
        assert llm_group_scores(_reference(composer="Mozart"), ["Haydn"],
                                llm=_llm({"first": 0.9})) is None

    def test_a_raising_model_is_declined_rather_than_propagated(self):
        assert llm_group_scores(_reference(composer="Mozart"), ["Haydn"],
                                llm=_raising_llm(RuntimeError("ollama is not running"))) is None

    def test_more_groups_than_fit_are_truncated_not_refused(self):
        candidates = [f"Composer{i}" for i in range(MAX_LLM_SCORED_GROUPS + 10)]
        response = {str(i): 0.5 for i in range(MAX_LLM_SCORED_GROUPS)}

        scores = llm_group_scores(_reference(composer="Mozart"), candidates,
                                  llm=_llm(response))

        assert len(scores) == MAX_LLM_SCORED_GROUPS
        assert candidates[MAX_LLM_SCORED_GROUPS] not in scores
