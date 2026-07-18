"""Unit tests for catalogue derivation on library_data.media_track.MediaTrack."""

import pytest

from library_data.media_track import MediaTrack


@pytest.mark.parametrize("album,expected", [
    ("Beethoven Sonatas Vol. 1", "Beethoven Sonatas"),
    ("Beethoven Sonatas Vol 2", "Beethoven Sonatas"),
    ("Beethoven Sonatas Volume 3", "Beethoven Sonatas"),
    ("Beethoven Sonatas Vols. 1-2", "Beethoven Sonatas"),
    ("Beethoven Sonatas: Vol. 1", "Beethoven Sonatas"),
    ("Sinfonías Volumen 1", "Sinfonías"),
    ("Klavierwerke Bd. 2", "Klavierwerke"),
    ("Симфонии Том 1", "Симфонии"),
    ("Time Out", "Time Out"),
    ("Volcano Nights", "Volcano Nights"),
    ("Vol. 1", "Vol. 1"),
    (None, None),
    ("", ""),
])
def test_derive_catalogue(album, expected):
    assert MediaTrack._derive_catalogue(album) == expected


def test_get_catalogue_caches_on_instance():
    track = MediaTrack.__new__(MediaTrack)
    track.album = "Beethoven Sonatas Vol. 1"
    track.catalogue = None

    first = track.get_catalogue()
    assert first == "Beethoven Sonatas"

    # Mutate album after first computation; cached value should not change.
    track.album = "Something Else Vol. 9"
    assert track.get_catalogue() == first


def test_get_catalogue_handles_no_album():
    track = MediaTrack.__new__(MediaTrack)
    track.album = None
    track.catalogue = None
    assert track.get_catalogue() == ""


def test_from_db_row_track_does_not_crash_on_first_get_catalogue():
    row = {
        "filepath": "/music/artist/album/track.mp3",
        "parent_filepath": None,
        "title": "Track",
        "tracktitle": None,
        "artist": "Some Artist",
        "albumartist": None,
        "album": "Some Album Vol. 4",
        "composer": None,
        "tracknumber": None,
        "totaltracks": None,
        "discnumber": None,
        "totaldiscs": None,
        "genre": None,
        "year": None,
        "compilation": 0,
        "compilation_name": None,
        "mean_volume": None,
        "max_volume": None,
        "length": None,
        "form": None,
        "instrument": None,
        "is_video": None,
    }
    track = MediaTrack.from_db_row(row)
    assert track.catalogue is None
    assert track.get_catalogue() == "Some Album"
