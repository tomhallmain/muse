"""Unit tests for NameOps word-boundary matching."""

import pytest

from utils.name_ops import NameOps


@pytest.mark.unit
class TestContainsOnWordBoundary:
    @pytest.mark.parametrize("text,value", [
        ("Amalia Catharina, Countess of Erbach", "Bach"),
        ("Anton Adam Bachschmid", "Bach"),
        ("Caspar Joseph Brambach", "Bach"),
        ("Bartholomäus Gesius", "Barth"),
        ("Christian Heinemeyer", "Meyer"),
        ("Achille Simonetti", "Simon"),
    ])
    def test_rejects_indicator_inside_a_longer_word(self, text, value):
        """A plain substring test matched all of these; a boundary test must not."""
        assert not NameOps.contains_on_word_boundary(text, value)

    @pytest.mark.parametrize("text,value", [
        ("Johann Sebastian Bach", "Bach"),
        ("Bach, J. S. - Cantata BWV 140", "Bach"),
        ("Toccata and Fugue in D minor (Bach)", "Bach"),
        ("J.S. Bach: Mass in B minor", "Bach"),
        ("Erik Meyer-Helmund", "Meyer"),
        ("Symphony by Müller", "Müller"),
        ("BWV 1043", "BWV"),
    ])
    def test_matches_indicator_delimited_by_non_word_characters(self, text, value):
        assert NameOps.contains_on_word_boundary(text, value)

    @pytest.mark.parametrize("text,value", [
        ("Adolf Müller Sr. - Overture", "Müller Sr."),
        ("Prelude B.W.V. 846", "B.W.V."),
    ])
    def test_indicators_holding_regex_metacharacters_match(self, text, value):
        assert NameOps.contains_on_word_boundary(text, value)

    def test_regex_metacharacters_are_matched_literally(self):
        # '.' is a literal here, not "any character" -- a regex implementation
        # without escaping would match this.
        assert not NameOps.contains_on_word_boundary("Prelude BxWxVx 846", "B.W.V.")

    def test_later_occurrence_still_matches_after_an_embedded_one(self):
        # First "Bach" is inside Bachschmid; the standalone one after it counts.
        assert NameOps.contains_on_word_boundary("Bachschmid arr. Bach", "Bach")

    @pytest.mark.parametrize("text,value", [("", "Bach"), ("Bach", ""), ("", "")])
    def test_empty_inputs_do_not_match(self, text, value):
        assert not NameOps.contains_on_word_boundary(text, value)
