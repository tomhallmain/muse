"""Unit tests for catalogue and main-artist derivation on library_data.media_track.MediaTrack."""

import types

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
        "album_from_metadata": 1,
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
        "album_from_metadata": 1,
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


@pytest.mark.parametrize("data,expected", [
    (b'\x89PNG\r\n\x1a\n' + b'rest', ".png"),
    (b'RIFF' + b'\x00\x00\x00\x00' + b'WEBP' + b'rest', ".webp"),
    (b'GIF89a' + b'rest', ".gif"),
    (b'\xff\xd8\xff' + b'rest', ".jpg"),
    (b'', ".jpg"),
    (None, ".jpg"),
])
def test_artwork_extension(data, expected):
    """The temp file was previously always named .jpg regardless of content."""
    assert MediaTrack.artwork_extension(data) == expected


def test_artwork_quality_of_nothing_is_zero():
    assert MediaTrack.artwork_quality(None) == (0, 0)
    assert MediaTrack.artwork_quality(b"") == (0, 0)


def test_artwork_quality_falls_back_to_byte_length_when_undecodable():
    data = b"not a decodable image"
    assert MediaTrack.artwork_quality(data) == (0, len(data))


def test_artwork_quality_uses_pixel_area_when_decodable():
    pytest.importorskip("PIL")
    import io
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (20, 10), (255, 0, 0)).save(buf, format="PNG")
    data = buf.getvalue()

    assert MediaTrack.artwork_quality(data) == (200, len(data))


@pytest.mark.parametrize("candidate,existing,expected,note", [
    ((1000 * 1000, 90000), (600 * 600, 40000), True, "600 -> 1000 is 2.78x area"),
    ((600 * 600, 40000), (500 * 500, 30000), False, "500 -> 600 is only 1.44x area"),
    ((1500 * 1500, 200000), (1400 * 1400, 190000), False, "1400 -> 1500 is 1.15x area"),
    ((500 * 500, 30000), (0, 0), True, "receiving track has no artwork"),
    ((500 * 500, 30000), (500 * 500, 30000), False, "identical artwork is never rewritten"),
    ((0, 48000), (0, 30000), True, "no dimensions: 60% more bytes"),
    ((0, 35000), (0, 30000), False, "no dimensions: only 17% more bytes"),
    ((500 * 500, 48000), (0, 30000), True, "only one measurable: compare bytes"),
    ((0, 0), (500 * 500, 30000), False, "nothing never replaces something"),
])
def test_artwork_is_improvement(candidate, existing, expected, note):
    assert MediaTrack.artwork_is_improvement(candidate, existing) is expected, note


# ---------------------------------------------------------------------------
# load_embedded_artwork
# ---------------------------------------------------------------------------

class _FakeArtwork:
    def __init__(self, data):
        self.data = data


class _FakeArtworkItem:
    def __init__(self, data):
        self.first = _FakeArtwork(data) if data else None


class _FakeMusicTagFile:
    def __init__(self, data):
        self._data = data

    def __getitem__(self, key):
        return _FakeArtworkItem(self._data if key == "artwork" else None)


class _FakePicture:
    """Stands in for a mutagen ID3 APIC frame. Type 3 is the front cover."""

    def __init__(self, data, picture_type=0):
        self.data = data
        self.type = picture_type


class _FakeMutagenFile:
    def __init__(self, tags):
        self.tags = tags


def _reader_track(monkeypatch, music_tag_data=None, tags=None, music_tag_available=True):
    """A MediaTrack whose two artwork readers are replaced by fakes."""
    import library_data.media_track as media_track_mod
    monkeypatch.setattr(media_track_mod, "MUSIC_TAG_AVAILABLE", music_tag_available)
    monkeypatch.setattr(
        media_track_mod, "music_tag",
        types.SimpleNamespace(load_file=lambda path: _FakeMusicTagFile(music_tag_data)),
        raising=False)
    monkeypatch.setattr(
        media_track_mod, "File",
        lambda path: _FakeMutagenFile({} if tags is None else tags),
        raising=False)
    track = MediaTrack.__new__(MediaTrack)
    track.filepath = "/music/artist/album/track.mp3"
    track.artwork = None
    track.is_video = False
    return track


@pytest.mark.unit
class TestLoadEmbeddedArtwork:
    def test_music_tag_is_read_first(self, monkeypatch):
        track = _reader_track(monkeypatch, music_tag_data=b"from-music-tag",
                              tags={"APIC:0": _FakePicture(b"from-mutagen")})
        assert track.load_embedded_artwork() == b"from-music-tag"

    def test_falls_back_to_mutagen_when_music_tag_finds_nothing(self, monkeypatch):
        track = _reader_track(monkeypatch, music_tag_data=None,
                              tags={"APIC:0": _FakePicture(b"from-mutagen")})
        assert track.load_embedded_artwork() == b"from-mutagen"

    def test_described_picture_frame_is_found(self, monkeypatch):
        """Regression: ID3 keys a picture frame by 'APIC:' plus its description, so
        matching the bare key found only a frame described by the empty string --
        missing both the index descriptions music_tag writes and a tagger's own."""
        track = _reader_track(monkeypatch, music_tag_available=False,
                              tags={"APIC:0": _FakePicture(b"described")})
        assert track.load_embedded_artwork() == b"described"

    def test_front_cover_is_preferred_among_several_pictures(self, monkeypatch):
        track = _reader_track(monkeypatch, music_tag_available=False, tags={
            "APIC:back": _FakePicture(b"back", picture_type=4),
            "APIC:front": _FakePicture(b"front", picture_type=3),
        })
        assert track.load_embedded_artwork() == b"front"

    def test_none_when_no_tag_carries_a_picture(self, monkeypatch):
        track = _reader_track(monkeypatch, tags={"TIT2": object()})
        assert track.load_embedded_artwork() is None

    def test_cached_artwork_is_not_re_read(self, monkeypatch):
        track = _reader_track(monkeypatch, music_tag_data=b"from-file")
        track.artwork = b"cached"
        assert track.load_embedded_artwork() == b"cached"
