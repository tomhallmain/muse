"""Unit tests for composer indicator matching against track metadata."""

import pytest

from library_data.composer import ComposersData, ComposersDataSearch
from tests.conftest import MockMediaTrack


def _track(title, album="", artist="", composer=None):
    return MockMediaTrack(
        filepath="/tmp/muse_test_track.mp3",
        title=title,
        album=album,
        artist=artist,
        composer=composer,
        _genre="",
        _form="",
        _instrument="",
        _catalogue="",
    )


@pytest.mark.unit
class TestComposerIndicatorMatching:
    def test_short_indicator_does_not_match_inside_a_longer_name(self):
        """"Bach" must not attach to Erbach, which merely ends in those letters."""
        data = ComposersData()
        matches = data.get_composers(_track("Amalia Catharina, Countess of Erbach - Aria"))
        assert "Amalia Catharina, Countess of Erbach" in matches
        assert "Johann Sebastian Bach" not in matches

    def test_short_indicator_does_not_match_a_longer_surname(self):
        data = ComposersData()
        matches = data.get_composers(_track("Anton Adam Bachschmid - Concerto in D"))
        assert "Anton Adam Bachschmid" in matches
        assert "Johann Sebastian Bach" not in matches

    def test_indicator_still_matches_on_a_word_boundary(self):
        data = ComposersData()
        matches = data.get_composers(_track("Johann Sebastian Bach - Toccata and Fugue"))
        assert "Johann Sebastian Bach" in matches

    def test_indicator_matches_when_followed_by_punctuation(self):
        data = ComposersData()
        matches = data.get_composers(_track("Bach: Mass in B minor"))
        assert "Johann Sebastian Bach" in matches

    def test_matching_applies_to_the_composer_tag(self):
        data = ComposersData()
        matches = data.get_composers(_track("Concerto in D", composer="Bachschmid"))
        assert "Johann Sebastian Bach" not in matches


@pytest.mark.unit
class TestComposersDataSearch:
    def test_query_with_regex_special_characters_does_not_raise(self):
        """The search term is escaped; an unescaped '[' is an invalid pattern."""
        data = ComposersData()
        search = ComposersDataSearch(composer="bach [")
        data.do_search(search)
        assert search.get_results() == []

    def test_search_finds_composer_by_indicator(self):
        data = ComposersData()
        search = ComposersDataSearch(composer="beethoven")
        data.do_search(search)
        assert "Ludwig van Beethoven" in [c.name for c in search.get_results()]
