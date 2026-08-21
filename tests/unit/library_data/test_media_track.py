"""Unit tests for catalogue and main-artist derivation on library_data.media_track.MediaTrack."""

import pytest

from library_data.media_track import MediaTrack
from utils.config import config


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


@pytest.mark.parametrize("albumartist,artist,prefer_last,expected", [
    # albumartist wins whenever it names a real artist
    ("Herbert von Karajan", "Berlin Philharmonic; Herbert von Karajan", False, "Herbert von Karajan"),
    ("Miles Davis", None, False, "Miles Davis"),
    ("  Miles Davis  ", "Someone Else", False, "Miles Davis"),
    # placeholder albumartist values fall through to the artist tag
    ("Various Artists", "Miles Davis", False, "Miles Davis"),
    ("various", "Miles Davis", False, "Miles Davis"),
    ("VA", "Miles Davis", False, "Miles Davis"),
    ("Unknown", "Miles Davis", False, "Miles Davis"),
    ("", "Miles Davis", False, "Miles Davis"),
    # a placeholder with a label suffix is matched as a substring
    ("Various Artists - Some Label", "Miles Davis", False, "Miles Davis"),
    # but a short placeholder must never match as a substring: "va" is inside "Ravel"
    ("Ravel", "Miles Davis", False, "Ravel"),
    # albumartist is only trusted when it names a single credit
    ("Gershwin, Whiteman & Bargy", "Gershwin", False, "Gershwin"),
    ("Karajan feat. Mutter", "Karajan", False, "Karajan"),
    # a label catalogue reference is not an artist
    ("ZZGR: 2960118", "Johnny Guarnieri", False, "Johnny Guarnieri"),
    # featured credits are stripped
    (None, "Berlin Philharmonic feat. Anne-Sophie Mutter", False, "Berlin Philharmonic"),
    (None, "Karajan ft. Mutter", False, "Karajan"),
    (None, "Karajan featuring Mutter", False, "Karajan"),
    (None, "Karajan with Mutter", False, "Karajan"),
    (None, "Karajan, feat. Mutter", False, "Karajan"),
    # a marker must be a whole word, not a prefix of a longer one
    (None, "Feathers", False, "Feathers"),
    (None, "Withering Look", False, "Withering Look"),
    (None, "Ftero", False, "Ftero"),
    # combined credits split on the configured preference
    (None, "Herbert von Karajan; Berlin Philharmonic", False, "Herbert von Karajan"),
    (None, "Herbert von Karajan; Berlin Philharmonic", True, "Berlin Philharmonic"),
    (None, "Berlin Philharmonic, Herbert von Karajan", True, "Herbert von Karajan"),
    (None, "A & B", False, "A"),
    (None, "A / B", True, "B"),
    # "and" is not a separator: it is usually part of one name
    (None, "Fletcher Henderson and His Orchestra", False, "Fletcher Henderson and His Orchestra"),
    (None, "Fletcher Henderson and His Orchestra", True, "Fletcher Henderson and His Orchestra"),
    (None, "Gold And Black Aces", False, "Gold And Black Aces"),
    # featured credits are stripped before the split
    (None, "Berlin Philharmonic, Karajan feat. Mutter", True, "Karajan"),
    # nothing to resolve
    (None, "Solo Artist", False, "Solo Artist"),
    (None, "  Padded  ", False, "Padded"),
    (None, None, False, None),
    (None, "", False, ""),
])
def test_derive_main_artist(albumartist, artist, prefer_last, expected):
    assert MediaTrack._derive_main_artist(albumartist, artist, prefer_last_segment=prefer_last) == expected


def test_get_main_artist_caches_on_instance():
    track = MediaTrack.__new__(MediaTrack)
    track.albumartist = None
    track.artist = "Berlin Philharmonic feat. Anne-Sophie Mutter"
    track.main_artist = None

    first = track.get_main_artist()
    assert first == "Berlin Philharmonic"
    assert track.get_main_artist() == first


def test_get_main_artist_handles_no_artist_fields():
    track = MediaTrack.__new__(MediaTrack)
    track.albumartist = None
    track.artist = None
    track.main_artist = None
    assert track.get_main_artist() == ""


def test_get_main_artist_follows_the_config_preference(monkeypatch):
    monkeypatch.setattr(config, "main_artist_prefers_last_segment", True)
    track = MediaTrack.__new__(MediaTrack)
    track.albumartist = None
    track.artist = "Berlin Philharmonic; Herbert von Karajan"
    track.main_artist = None
    assert track.get_main_artist() == "Herbert von Karajan"


def test_from_db_row_track_does_not_crash_on_first_get_main_artist():
    row = {
        "filepath": "/music/artist/album/track.mp3",
        "parent_filepath": None,
        "title": "Track",
        "tracktitle": None,
        "artist": "Berlin Philharmonic; Herbert von Karajan",
        "albumartist": None,
        "album": "Some Album",
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
    assert track.main_artist is None
    assert track.get_main_artist() == "Berlin Philharmonic"
