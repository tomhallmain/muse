"""Unit tests for library_data/work.py's Work value object."""

import pytest

from library_data.work import Work


@pytest.mark.unit
class TestWorkEquality:
    def test_same_composer_and_name_are_equal(self):
        assert Work("Symphony No. 5", "Beethoven") == Work("Symphony No. 5", "Beethoven")

    def test_different_name_is_not_equal(self):
        assert Work("Symphony No. 5", "Beethoven") != Work("Symphony No. 6", "Beethoven")

    def test_different_composer_is_not_equal(self):
        assert Work("Symphony No. 5", "Beethoven") != Work("Symphony No. 5", "Mozart")

    def test_catalogue_number_and_date_do_not_affect_identity(self):
        """A re-ingest that fills in a catalogue number/date must not read as a
        new, different work -- composer.py:53's UNIQUE(composer_id, name)
        constraint depends on this matching Work's own notion of identity."""
        a = Work("Symphony No. 5", "Beethoven", catalogue_number="Op. 67", date="1808")
        b = Work("Symphony No. 5", "Beethoven")

        assert a == b
        assert hash(a) == hash(b)

    def test_not_equal_to_a_non_work(self):
        assert Work("Symphony No. 5", "Beethoven") != "Symphony No. 5"


@pytest.mark.unit
class TestWorkSerialization:
    def test_round_trips_through_dict(self):
        work = Work("Symphony No. 5", "Beethoven", date="1808", catalogue_number="Op. 67",
                    source="imslp", matched_track_filepath="/music/beethoven5.mp3", id=3)

        restored = Work.from_dict(work.to_dict())

        assert restored.id == 3
        assert restored.name == "Symphony No. 5"
        assert restored.composer == "Beethoven"
        assert restored.date == "1808"
        assert restored.catalogue_number == "Op. 67"
        assert restored.source == "imslp"
        assert restored.matched_track_filepath == "/music/beethoven5.mp3"
        assert restored == work

    def test_from_dict_tolerates_missing_optional_fields(self):
        work = Work.from_dict({"name": "Symphony No. 5", "composer": "Beethoven"})

        assert work.date is None
        assert work.catalogue_number is None
        assert work.source is None
        assert work.matched_track_filepath is None
        assert work.id is None

    def test_to_dict_is_json_serializable(self):
        """Composer.to_json() hands this straight to json.dumps (indirectly, via
        scripts/export_composers_example.py) -- it must not contain Work objects."""
        import json

        json.dumps(Work("Symphony No. 5", "Beethoven").to_dict())


@pytest.mark.unit
class TestCatalogueKeys:
    @pytest.mark.parametrize("text,expected", [
        ("Cello Suite No.1 in G, BWV 1007 - I. Prélude", {("bwv", "1007", None)}),
        ("Suite BWV1007", {("bwv", "1007", None)}),
        ("Eine kleine Nachtmusik KV 525", {("k", "525", None)}),
        ("Serenade K. 525", {("k", "525", None)}),
        ("Piano Sonata Hob. XVI:52", {("hob", "xvi 52", None)}),
        ("Sonata in B-flat, D. 960", {("d", "960", None)}),
        ("Étude Op. 10, No. 3", {("op", "10", "3")}),
        ("Symphony No. 5, Opus 67", {("op", "67", None)}),
    ])
    def test_references_are_found_and_normalised(self, text, expected):
        assert Work.catalogue_keys(text) == expected

    @pytest.mark.parametrize("text", ["Kind of Blue", "Opera Arias", "Concerto in D 2 movements", "", None])
    def test_ordinary_words_are_not_references(self, text):
        assert Work.catalogue_keys(text) == set()


@pytest.mark.unit
class TestMatchesTitle:
    def test_catalogue_numbers_match_across_spellings(self):
        work = Work("Serenade No. 13", "Mozart", catalogue_number="K. 525")
        assert work.matches_title("Eine kleine Nachtmusik, KV525: I. Allegro")

    def test_a_different_catalogue_number_does_not_match_even_with_the_same_name(self):
        work = Work("Cello Suite No. 1", "Bach", catalogue_number="BWV 1007")
        assert not work.matches_title("Cello Suite No. 1, BWV 1008")

    def test_a_numbered_piece_matches_its_collection(self):
        assert Work("Études", "Chopin", catalogue_number="Op. 10").matches_title("Étude Op. 10 No. 3")

    def test_different_numbers_in_one_opus_do_not_match(self):
        work = Work("Étude in E major", "Chopin", catalogue_number="Op. 10 No. 3")
        assert not work.matches_title("Étude Op. 10 No. 12")

    def test_without_catalogue_numbers_the_whole_name_must_appear(self):
        work = Work("Les Soli", "Lajtha")
        assert work.matches_title("\"Les Soli\" Symphony for Strings, Harp and Percussion")
        assert not work.matches_title("Solo Pieces")

    def test_a_short_generic_name_never_matches_by_name(self):
        assert not Work("Suite", "Bach").matches_title("Suite in G")
