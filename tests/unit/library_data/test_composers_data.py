"""Unit tests for composer indicator matching against track metadata."""

import pytest

from library_data.composer import Composer, ComposersData, ComposersDataSearch
from library_data.work import Work
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


@pytest.mark.unit
class TestComposerWorksRoundTrip:
    """Works moved from a bare-name column on composers to their own table
    (library_data/works_data.py) -- this covers the save/reload path staying
    intact through that move."""

    def test_saved_works_survive_a_reload(self):
        data = ComposersData()
        composer = Composer(id=None, name="Round Trip Test Composer")
        composer.add_work("Test Symphony")
        success, error = data.save_composer(composer)
        assert success, error

        data.reload()
        reloaded = data.get_data("Round Trip Test Composer")

        assert reloaded is not None
        assert [w.name for w in reloaded.works] == ["Test Symphony"]
        assert reloaded.works[0].composer == "Round Trip Test Composer"

    def test_to_json_serializes_works_as_plain_dicts(self):
        """Composer.to_json() feeds json.dumps (scripts/export_composers_example.py)
        -- it must never hand back raw Work objects."""
        import json

        composer = Composer(id=1, name="JSON Test Composer",
                            works=[Work("Test Symphony", "JSON Test Composer", catalogue_number="Op. 1")])

        json.dumps(composer.to_json())

    def test_from_json_reconstructs_work_objects(self):
        composer = Composer(id=1, name="JSON Test Composer",
                            works=[Work("Test Symphony", "JSON Test Composer", catalogue_number="Op. 1")])

        restored = Composer.from_json(composer.to_json())

        assert len(restored.works) == 1
        assert isinstance(restored.works[0], Work)
        assert restored.works[0].catalogue_number == "Op. 1"
