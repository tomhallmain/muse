"""Tests for per-track play counts (library_data/play_counts.py) and their path propagation."""

import datetime
import os
from types import SimpleNamespace

import pytest

from library_data import play_counts
from utils import filepath_update

T1 = datetime.datetime(2026, 1, 1, 12, 0)
T2 = datetime.datetime(2026, 2, 1, 12, 0)
T3 = datetime.datetime(2026, 3, 1, 12, 0)


def _track(filepath, artist="An Artist", album="An Album", title="A Title", tracknumber=3):
    return SimpleNamespace(filepath=filepath, artist=artist, album=album, title=title,
                           tracknumber=tracknumber)


def _row(filepath):
    return play_counts.get_connection().execute(
        "SELECT * FROM track_plays WHERE kind = ? AND key = ?", (play_counts.FILE, filepath)
    ).fetchone()


@pytest.fixture
def threshold(monkeypatch):
    def set_threshold(ratio=0.5, cap=0):
        monkeypatch.setattr(play_counts.config, "play_count_threshold_ratio", ratio, raising=False)
        monkeypatch.setattr(play_counts.config, "play_count_threshold_cap_seconds", cap, raising=False)
    set_threshold()
    return set_threshold


@pytest.mark.unit
class TestCountsAsPlay:
    def test_below_the_ratio_does_not_count(self, threshold):
        assert not play_counts.counts_as_play(99.5, 200.0)

    def test_at_the_ratio_counts(self, threshold):
        assert play_counts.counts_as_play(100.0, 200.0)

    def test_the_cap_counts_a_long_track_early(self, threshold):
        threshold(cap=240)
        assert play_counts.counts_as_play(240.0, 3600.0)
        assert not play_counts.counts_as_play(239.5, 3600.0)

    def test_a_zero_cap_is_no_cap(self, threshold):
        threshold(cap=0)
        assert not play_counts.counts_as_play(240.0, 3600.0)

    @pytest.mark.parametrize("length", [None, 0.0, -1.0])
    def test_an_unknown_length_never_counts(self, threshold, length):
        assert not play_counts.counts_as_play(500.0, length)

    def test_nothing_heard_never_counts(self, threshold):
        threshold(ratio=0.0)
        assert not play_counts.counts_as_play(0.0, 200.0)


@pytest.mark.unit
class TestRecordPlay:
    def test_a_first_play_creates_the_row(self):
        play_counts.record_play(_track("/m/a.mp3"), when=T1)
        info = play_counts.get_play_info("/m/a.mp3")
        assert (info.play_count, info.first_played, info.last_played) == (1, T1, T1)

    def test_a_later_play_increments_and_moves_only_last_played(self):
        play_counts.record_play(_track("/m/a.mp3"), when=T1)
        play_counts.record_play(_track("/m/a.mp3"), when=T2)
        info = play_counts.get_play_info("/m/a.mp3")
        assert (info.play_count, info.first_played, info.last_played) == (2, T1, T2)

    def test_the_tag_snapshot_follows_the_latest_play(self):
        play_counts.record_play(_track("/m/a.mp3", title="Old"), when=T1)
        play_counts.record_play(_track("/m/a.mp3", title="New", tracknumber=-1), when=T2)
        row = _row("/m/a.mp3")
        assert (row["artist"], row["album"], row["title"], row["tracknumber"]) == (
            "An Artist", "An Album", "New", None)

    def test_a_track_without_a_path_is_ignored(self):
        play_counts.record_play(_track(""))
        assert play_counts.get_play_counts() == {}

    def test_an_uncounted_file_has_no_info(self):
        assert play_counts.get_play_info("/m/never.mp3") is None

    def test_bulk_counts(self):
        play_counts.record_play(_track("/m/a.mp3"))
        play_counts.record_play(_track("/m/a.mp3"))
        play_counts.record_play(_track("/m/b.mp3"))
        assert play_counts.get_play_counts() == {"/m/a.mp3": 2, "/m/b.mp3": 1}


@pytest.mark.unit
class TestRekeyAndDelete:
    def test_a_rename_moves_the_row(self):
        play_counts.record_play(_track("/m/a.mp3"), when=T1)
        play_counts.rekey_files({"/m/a.mp3": "/m/b.mp3"})
        assert play_counts.get_play_info("/m/a.mp3") is None
        assert play_counts.get_play_info("/m/b.mp3").play_count == 1

    def test_a_rename_onto_an_existing_row_merges(self):
        play_counts.record_play(_track("/m/a.mp3", title="Source"), when=T2)
        play_counts.record_play(_track("/m/a.mp3", title="Source"), when=T3)
        play_counts.record_play(_track("/m/b.mp3", title="Target"), when=T1)

        play_counts.rekey_files({"/m/a.mp3": "/m/b.mp3"})

        info = play_counts.get_play_info("/m/b.mp3")
        assert (info.play_count, info.first_played, info.last_played) == (3, T1, T3)
        assert _row("/m/b.mp3")["title"] == "Source"
        assert play_counts.get_play_info("/m/a.mp3") is None

    def test_delete_removes_only_the_named_rows(self):
        play_counts.record_play(_track("/m/a.mp3"))
        play_counts.record_play(_track("/m/b.mp3"))
        play_counts.delete_files(["/m/a.mp3"])
        assert play_counts.get_play_counts() == {"/m/b.mp3": 1}


@pytest.mark.unit
class TestPropagation:
    """Through utils.filepath_update, using OS-native paths as playback records them."""

    def test_file_rename(self, tmp_path):
        old, new = str(tmp_path / "a.mp3"), str(tmp_path / "b.mp3")
        play_counts.record_play(_track(old))
        filepath_update._plays_file(old, new)
        assert play_counts.get_play_counts() == {new: 1}

    def test_directory_rename_remaps_nested_files_like_the_track_cache(self, tmp_path):
        old_dir, new_dir = str(tmp_path / "Artist"), str(tmp_path / "Renamed")
        nested = os.path.join(old_dir, "Album", "01.mp3")
        outside = str(tmp_path / "Other" / "02.mp3")
        play_counts.record_play(_track(nested))
        play_counts.record_play(_track(outside))

        filepath_update._plays_directory(old_dir, new_dir)

        expected = filepath_update._remap_under(old_dir, new_dir, nested)
        assert expected == os.path.join(new_dir, "Album", "01.mp3")
        assert play_counts.get_play_counts() == {expected: 1, outside: 1}

    def test_file_delete(self, tmp_path):
        path = str(tmp_path / "a.mp3")
        play_counts.record_play(_track(path))
        filepath_update._plays_file_delete(path)
        assert play_counts.get_play_counts() == {}

    def test_directory_delete_removes_the_subtree_only(self, tmp_path):
        inside = os.path.join(str(tmp_path / "Album"), "01.mp3")
        outside = str(tmp_path / "Other" / "02.mp3")
        play_counts.record_play(_track(inside))
        play_counts.record_play(_track(outside))
        filepath_update._plays_directory_delete(str(tmp_path / "Album"))
        assert play_counts.get_play_counts() == {outside: 1}

    def test_the_public_rename_entry_point_includes_play_counts(self, tmp_path):
        old, new = str(tmp_path / "a.mp3"), str(tmp_path / "b.mp3")
        play_counts.record_play(_track(old))
        filepath_update.propagate_file_rename(old, new)
        assert play_counts.get_play_counts() == {new: 1}
