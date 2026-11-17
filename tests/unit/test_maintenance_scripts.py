"""Tests for scripts/find_replaced_tracks.py and scripts/repair_album_artwork.py.

The scripts are loaded from their files. Every test hands them paths under
tmp_path. None lets them fall back to the configured library directories, which
the example config points at a real folder in the user's home.
"""

import importlib.util
import os
import sys

import pytest

from utils.translations import I18N

_ = I18N._

_SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            "scripts")


@pytest.fixture
def load_script(monkeypatch):
    """Load a script as a module. Loading changes into the repo root, so the cwd is restored after."""
    monkeypatch.chdir(os.getcwd())

    def load(name):
        spec = importlib.util.spec_from_file_location(
            f"muse_script_{name}", os.path.join(_SCRIPTS_DIR, name + ".py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    return load


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


@pytest.mark.unit
class TestFindReplacedTracks:
    @pytest.fixture
    def script(self, load_script, monkeypatch):
        module = load_script("find_replaced_tracks")

        def refuse():
            raise AssertionError("the configured library directories must not be read")
        monkeypatch.setattr(module.mf, "configured_directories", refuse)
        return module

    @staticmethod
    def _entry(script, path, duration=100.0, has_artwork=False):
        entry = script.Entry(str(path))
        entry.duration = duration
        entry.title = "Gloria"
        entry.has_artwork = has_artwork
        entry.tag_count = 5
        return entry

    def test_classify_sorts_each_source_by_its_counterpart(self, script, tmp_path):
        album, other = tmp_path / "album", tmp_path / "other"
        sources = [
            self._entry(script, album / "a.m4p"),
            self._entry(script, album / "b.m4p", has_artwork=True),
            self._entry(script, album / "c.m4p", duration=100.0),
            self._entry(script, album / "d.m4p"),
            self._entry(script, album / "e.m4p"),
        ]
        targets = [
            self._entry(script, album / "a.m4a", has_artwork=True),
            self._entry(script, album / "b.m4a"),
            self._entry(script, album / "c.m4a", duration=150.0),
            # Same name, different folder: a different track.
            self._entry(script, other / "e.m4a", has_artwork=True),
        ]
        groups = script.classify(sources, targets)
        names = {key: [os.path.basename(item[0].path if isinstance(item, tuple) else item.path)
                       for item in items]
                 for key, items in groups.items()}
        assert names["replaced"] == ["a.m4p"]
        assert names["transferable"] == ["b.m4p"]
        assert names["mismatched"] == ["c.m4p"]
        assert names["unmatched"] == ["d.m4p", "e.m4p"]

    def test_differing_tags_are_a_mismatch(self, script, tmp_path):
        source = self._entry(script, tmp_path / "a.m4p")
        target = self._entry(script, tmp_path / "a.m4a", has_artwork=True)
        target.title = "Magnificat"
        groups = script.classify([source], [target])
        assert [how for _s, _t, how in groups["mismatched"]] == ["tags differ"]

    def test_an_empty_directory_lists_nothing_and_touches_nothing(self, script, tmp_path,
                                                                   monkeypatch, capsys):
        library = tmp_path / "library"
        library.mkdir()
        monkeypatch.setattr(sys, "argv", ["find_replaced_tracks.py", "--dir", str(library)])
        assert script.main() == 0
        assert "Nothing to do." in capsys.readouterr().out
        assert list(library.iterdir()) == []


@pytest.mark.unit
class TestRepairAlbumArtwork:
    @pytest.fixture
    def script(self, load_script):
        return load_script("repair_album_artwork")

    def test_titles_come_from_the_update_metadata_log_line(self, script, tmp_path):
        log = tmp_path / "muse.log"
        logged = _("Successfully updated metadata for {0}").format("Song [abcdefghijk]")
        log.write_text(f"2026-11-17 10:00:00 - INFO - {logged}\n"
                       "2026-11-17 10:00:01 - INFO - Something else\n", encoding="utf-8")
        assert script.parse_updated_titles(str(log)) == ["Song [abcdefghijk]"]

    def test_index_by_video_id_counts_media_files_only(self, script, tmp_path):
        root = tmp_path / "library"
        track = _touch(root / "Song [abcdefghijk].m4a")
        _touch(root / "Song [abcdefghijk].jpg")      # sidecar thumbnail
        _touch(root / "._Song [abcdefghijk].m4a")    # AppleDouble companion
        nested = _touch(root / "album" / "Other [bcdefghijkl].mp3")
        assert script.index_by_video_id(str(root)) == {"abcdefghijk": [str(track)]}
        assert script.index_by_video_id(str(root), recurse=True) == {
            "abcdefghijk": [str(track)],
            "bcdefghijkl": [str(nested)],
        }
