"""Unit tests for library_data/works_data.py's WorksData DAO.

Runs against the isolated in-memory DB provided by the autouse
``isolated_singletons`` fixture (tests/conftest.py) -- never the real
muse_library.db.
"""

import pytest

from library_data.composer import Composer, composers_data
from library_data.work import Work
from library_data.works_data import works_data


def _saved_composer(name="Test Composer for Works"):
    composer = Composer(id=None, name=name)
    success, error = composers_data.save_composer(composer)
    assert success, error
    return composer


def _insert_media_track(filepath):
    """matched_track_filepath is a real FK onto media_tracks(filepath) -- a
    match can only ever point at a track row that actually exists."""
    import library_data.works_data as works_data_mod

    conn = works_data_mod.get_connection()
    conn.execute(
        "INSERT INTO media_tracks (filepath, scanned_at) VALUES (?, 0)", (filepath,)
    )
    conn.commit()


@pytest.mark.unit
class TestSaveAndFetchWorks:
    def test_no_works_for_an_unknown_composer(self):
        assert works_data.get_works_for_composer(999999) == []

    def test_none_composer_id_returns_empty(self):
        assert works_data.get_works_for_composer(None) == []

    def test_saved_works_are_fetched_back(self):
        composer = _saved_composer()
        works_data.save_works(composer.id, [
            Work("Symphony No. 5", composer.name, catalogue_number="Op. 67", date="1808"),
            Work("Symphony No. 6", composer.name, catalogue_number="Op. 68"),
        ])

        fetched = works_data.get_works_for_composer(composer.id)

        assert {w.name for w in fetched} == {"Symphony No. 5", "Symphony No. 6"}
        by_name = {w.name: w for w in fetched}
        assert by_name["Symphony No. 5"].catalogue_number == "Op. 67"
        assert by_name["Symphony No. 5"].date == "1808"
        assert by_name["Symphony No. 5"].composer == composer.name

    def test_works_are_scoped_to_their_composer(self):
        a = _saved_composer("Composer A for Works")
        b = _saved_composer("Composer B for Works")
        works_data.save_works(a.id, [Work("Only A's Work", a.name)])

        assert works_data.get_works_for_composer(b.id) == []


@pytest.mark.unit
class TestSaveWorksIsUpsert:
    def test_resaving_the_same_work_does_not_duplicate_it(self):
        composer = _saved_composer()
        works_data.save_works(composer.id, [Work("Symphony No. 5", composer.name)])
        works_data.save_works(composer.id, [Work("Symphony No. 5", composer.name, date="1808")])

        fetched = works_data.get_works_for_composer(composer.id)

        assert len(fetched) == 1
        assert fetched[0].date == "1808"

    def test_resaving_does_not_clear_an_existing_track_match(self):
        """A re-ingest must not throw away a match found separately by the
        extension/UI matching pass -- save_works only ever adds/updates
        catalogue_number/date/source, never matched_track_filepath."""
        composer = _saved_composer()
        _insert_media_track("/music/beethoven5.mp3")
        works_data.save_works(composer.id, [Work("Symphony No. 5", composer.name)])
        [work] = works_data.get_works_for_composer(composer.id)
        works_data.set_matched_track(work.id, "/music/beethoven5.mp3")

        works_data.save_works(composer.id, [Work("Symphony No. 5", composer.name, date="1808")])

        [refetched] = works_data.get_works_for_composer(composer.id)
        assert refetched.matched_track_filepath == "/music/beethoven5.mp3"
        assert refetched.date == "1808"


@pytest.mark.unit
class TestSetMatchedTrack:
    def test_sets_the_match(self):
        composer = _saved_composer()
        _insert_media_track("/music/beethoven5.mp3")
        works_data.save_works(composer.id, [Work("Symphony No. 5", composer.name)])
        [work] = works_data.get_works_for_composer(composer.id)

        works_data.set_matched_track(work.id, "/music/beethoven5.mp3")

        [refetched] = works_data.get_works_for_composer(composer.id)
        assert refetched.matched_track_filepath == "/music/beethoven5.mp3"

    def test_can_clear_the_match(self):
        composer = _saved_composer()
        _insert_media_track("/music/beethoven5.mp3")
        works_data.save_works(composer.id, [Work("Symphony No. 5", composer.name)])
        [work] = works_data.get_works_for_composer(composer.id)
        works_data.set_matched_track(work.id, "/music/beethoven5.mp3")

        works_data.set_matched_track(work.id, None)

        [refetched] = works_data.get_works_for_composer(composer.id)
        assert refetched.matched_track_filepath is None

    def test_setting_the_match_to_a_nonexistent_track_does_not_raise(self):
        """The FK is real (matched_track_filepath references media_tracks); a
        bad filepath must fail closed, not crash the caller."""
        composer = _saved_composer()
        works_data.save_works(composer.id, [Work("Symphony No. 5", composer.name)])
        [work] = works_data.get_works_for_composer(composer.id)

        works_data.set_matched_track(work.id, "/music/does-not-exist.mp3")

        [refetched] = works_data.get_works_for_composer(composer.id)
        assert refetched.matched_track_filepath is None


@pytest.mark.unit
class TestComposerDeletionCascades:
    def test_deleting_a_composer_removes_its_works(self):
        composer = _saved_composer()
        works_data.save_works(composer.id, [Work("Symphony No. 5", composer.name)])

        success, error = composers_data.delete_composer(composer)

        assert success, error
        assert works_data.get_works_for_composer(composer.id) == []
