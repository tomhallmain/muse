"""Tests for LibraryData.get_all_tracks(rescan=True) keeping cached track details."""

import pytest

import library_data.library_data as library_data_module
from library_data.library_data import LibraryData


class _CountingTrack:
    """Stands in for MediaTrack, recording which files were read."""

    reads = []

    def __init__(self, filepath):
        self.filepath = filepath
        _CountingTrack.reads.append(filepath)

    @staticmethod
    def write_errors_to_file():
        pass


@pytest.fixture
def library(tmp_path, monkeypatch):
    _CountingTrack.reads = []
    monkeypatch.setattr(library_data_module, "MediaTrack", _CountingTrack)
    monkeypatch.setattr(library_data_module, "reset_store", lambda: None)
    monkeypatch.setattr(library_data_module.config, "get_all_directories", lambda: [str(tmp_path)])

    def add(name):
        path = tmp_path / name
        path.write_bytes(b"")
        return str(path)
    return add


def _paths():
    return sorted(track.filepath for track in LibraryData.all_tracks)


@pytest.mark.unit
class TestRescan:
    def test_a_file_present_before_and_after_keeps_its_cached_details(self, library):
        kept = library("kept.mp3")
        LibraryData.get_all_tracks()
        cached = LibraryData.MEDIA_TRACK_CACHE[kept]

        LibraryData.get_all_tracks(rescan=True)

        assert LibraryData.MEDIA_TRACK_CACHE[kept] is cached
        assert _CountingTrack.reads == [kept]

    def test_a_new_file_is_read_and_listed(self, library):
        kept = library("kept.mp3")
        LibraryData.get_all_tracks()
        added = library("added.mp3")

        LibraryData.get_all_tracks(rescan=True)

        assert _paths() == sorted([kept, added])
        assert _CountingTrack.reads == [kept, added]

    def test_a_removed_file_is_no_longer_listed(self, library, tmp_path):
        kept = library("kept.mp3")
        removed = library("removed.mp3")
        LibraryData.get_all_tracks()
        (tmp_path / "removed.mp3").unlink()

        LibraryData.get_all_tracks(rescan=True)

        assert _paths() == [kept]
        assert removed not in _paths()

    def test_without_rescan_a_new_file_is_not_picked_up(self, library):
        kept = library("kept.mp3")
        LibraryData.get_all_tracks()
        library("added.mp3")

        LibraryData.get_all_tracks()

        assert _paths() == [kept]
