"""Tests for utils/media_file_tools.py.

Everything runs on files under tmp_path or on stand-in tag objects; no test reads
the configured library directories.
"""

import importlib
import os

import pytest

import utils.media_file_tools as mf


class _Picture:
    def __init__(self, data, type=0):
        self.data = data
        self.type = type


class _ID3Frame:
    def __init__(self, *text):
        self.text = list(text)


class _ID3Tags(dict):
    """Stand-in for mutagen's ID3: dict lookups plus getall()."""

    def __init__(self, frames, pictures=()):
        super().__init__(frames)
        self._pictures = list(pictures)

    def getall(self, name):
        return self._pictures if name == "APIC" else []


class _Audio:
    def __init__(self, tags=None, pictures=None):
        self.tags = tags
        if pictures is not None:
            self.pictures = pictures


def _touch(path, content=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


@pytest.mark.unit
class TestCollectFiles:
    def test_matches_extensions_case_insensitively_and_skips_appledouble(self, tmp_path):
        library = tmp_path / "library"
        _touch(library / "a.m4p")
        _touch(library / "B.M4P")
        _touch(library / "._a.m4p")
        _touch(library / "c.m4a")
        found, skipped = mf.collect_files([str(library)], [".m4p"])
        assert [os.path.basename(p) for p in found] == ["B.M4P", "a.m4p"]
        assert skipped == 1

    def test_recurse_controls_subfolders(self, tmp_path):
        library = tmp_path / "library"
        _touch(library / "top.mp3")
        _touch(library / "album" / "deep.mp3")
        assert len(mf.collect_files([str(library)], [".mp3"])[0]) == 2
        assert len(mf.collect_files([str(library)], [".mp3"], recurse=False)[0]) == 1


@pytest.mark.unit
class TestMoveAside:
    def test_a_taken_name_is_numbered(self, tmp_path):
        target_dir = tmp_path / "aside"
        _touch(target_dir / "song.m4p", b"existing")
        source = _touch(tmp_path / "song.m4p", b"new")
        destination = mf.move_aside(str(source), str(target_dir))
        assert destination.endswith("song__1.m4p")
        assert not source.exists()
        assert (target_dir / "song.m4p").read_bytes() == b"existing"
        assert (target_dir / "song__1.m4p").read_bytes() == b"new"


@pytest.mark.unit
class TestFirstText:
    def test_mp4_keys(self):
        assert mf.first_text({"\xa9nam": ["Gloria"]}, "title") == "Gloria"

    def test_id3_frames(self):
        tags = _ID3Tags({"TALB": _ID3Frame("Vivaldi: Gloria")})
        assert mf.first_text(tags, "album") == "Vivaldi: Gloria"

    def test_vorbis_keys(self):
        assert mf.first_text({"artist": ["Academy of Ancient Music"]}, "artist") == \
            "Academy of Ancient Music"

    def test_absent_or_empty_values_give_an_empty_string(self):
        assert mf.first_text({"\xa9nam": [], "title": ["  "]}, "title") == ""


@pytest.mark.unit
class TestPictureFrom:
    def test_flac_prefers_the_front_cover(self):
        audio = _Audio(tags={}, pictures=[_Picture(b"back", type=4), _Picture(b"front", type=3)])
        assert mf.picture_from(audio) == b"front"

    def test_id3_reads_frames_whatever_their_description(self):
        audio = _Audio(tags=_ID3Tags({}, pictures=[_Picture(b"cover")]))
        assert mf.picture_from(audio) == b"cover"

    def test_mp4_cover_atom(self):
        assert mf.picture_from(_Audio(tags={"covr": [b"mp4cover"]})) == b"mp4cover"

    @pytest.mark.parametrize("audio", [None, _Audio(tags=None), _Audio(tags={})])
    def test_no_artwork(self, audio):
        assert mf.picture_from(audio) is None


@pytest.mark.unit
def test_configured_directories_keeps_only_existing_ones(tmp_path, monkeypatch):
    config = importlib.import_module("utils.config").config
    monkeypatch.setattr(config, "directories", [str(tmp_path), str(tmp_path / "missing"), ""])
    assert mf.configured_directories() == [str(tmp_path)]
