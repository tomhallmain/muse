"""Tests for re-reading a single cached track from its file."""

import pytest

import library_data.library_data as library_data_module
from library_data.library_data import LibraryData
from library_data.media_track import MediaTrack


@pytest.fixture
def track(audio_library_media_tracks):
    return audio_library_media_tracks[0]


@pytest.mark.unit
class TestReloadFromFile:
    def test_cached_values_are_replaced_in_place(self, track):
        from_file = MediaTrack(track.filepath).title
        track.title = "Stale Title"
        same_object = track

        track.reload_from_file()

        assert track is same_object
        assert track.title == from_file

    def test_values_the_file_no_longer_has_are_dropped(self, track):
        track.stale_attribute = "left over"
        track.reload_from_file()
        assert not hasattr(track, "stale_attribute")

    def test_the_extension_flag_is_kept(self, track):
        track.set_is_extended(True)
        track.reload_from_file()
        assert track._is_extended is True

    def test_a_missing_file_raises_and_leaves_the_track_alone(self, track, tmp_path):
        track.filepath = str(tmp_path / "gone.mp3")
        track.title = "Kept Title"
        with pytest.raises(FileNotFoundError):
            track.reload_from_file()
        assert track.title == "Kept Title"


@pytest.mark.unit
class TestReloadTrack:
    def test_a_distinct_cached_object_for_the_path_is_reloaded_too(self, track, monkeypatch):
        monkeypatch.setattr(library_data_module, "reset_store", lambda: None)
        from_file = MediaTrack(track.filepath).title
        other = MediaTrack(track.filepath)
        other.title = "Stale Title"
        LibraryData.MEDIA_TRACK_CACHE[track.filepath] = other

        LibraryData.reload_track(track)

        assert other.title == from_file

    def test_the_embedding_store_is_told_to_recheck(self, track, monkeypatch):
        calls = []
        monkeypatch.setattr(library_data_module, "reset_store", lambda: calls.append(True))
        LibraryData.reload_track(track)
        assert calls == [True]
