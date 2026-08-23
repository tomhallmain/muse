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
