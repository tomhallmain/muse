"""
Tests for utils/path_move.py (gap #8 — Windows/cross-volume edge cases).

All tests run on the host OS.  Platform-specific behaviour (case-insensitive
comparison on Windows) is skipped unless running on Windows.
"""

import os

import pytest

from utils.path_move import destination_occupied, move_on_disk, paths_equivalent


class TestDestinationOccupied:
    def test_false_when_destination_does_not_exist(self, tmp_path):
        src = tmp_path / "a.mp3"
        src.touch()
        assert not destination_occupied(str(src), str(tmp_path / "b.mp3"))

    def test_true_when_different_file_exists_at_dst(self, tmp_path):
        src = tmp_path / "a.mp3"
        dst = tmp_path / "b.mp3"
        src.touch()
        dst.touch()
        assert destination_occupied(str(src), str(dst))

    def test_false_when_src_and_dst_are_the_same_path(self, tmp_path):
        p = tmp_path / "a.mp3"
        p.touch()
        assert not destination_occupied(str(p), str(p))


class TestPathsEquivalent:
    def test_same_path_is_equivalent(self, tmp_path):
        p = str(tmp_path / "a.mp3")
        assert paths_equivalent(p, p)

    def test_different_paths_are_not_equivalent(self, tmp_path):
        assert not paths_equivalent(
            str(tmp_path / "a.mp3"), str(tmp_path / "b.mp3")
        )

    @pytest.mark.skipif(os.name != "nt", reason="Case-insensitivity is Windows-only")
    def test_case_only_difference_is_equivalent_on_windows(self, tmp_path):
        assert paths_equivalent(str(tmp_path / "A.MP3"), str(tmp_path / "a.mp3"))


class TestMoveOnDisk:
    def test_same_volume_moves_file_on_disk(self, tmp_path):
        src = tmp_path / "src.mp3"
        dst = tmp_path / "dst.mp3"
        src.write_bytes(b"audio")

        result = move_on_disk(str(src), str(dst))

        assert result == str(dst)
        assert dst.exists()
        assert not src.exists()

    def test_same_volume_dispatches_to_os_rename(self, tmp_path, monkeypatch):
        import utils.path_move as pm

        src = tmp_path / "src.mp3"
        src.write_bytes(b"audio")
        dst = tmp_path / "dst.mp3"
        calls = []
        monkeypatch.setattr(pm, "same_volume", lambda a, b: True)
        monkeypatch.setattr(pm.os, "rename", lambda s, d: calls.append((s, d)))

        move_on_disk(str(src), str(dst))

        assert len(calls) == 1
        assert calls[0] == (str(src), str(dst))

    def test_cross_volume_dispatches_to_shutil_move(self, tmp_path, monkeypatch):
        import utils.path_move as pm

        src = tmp_path / "src.mp3"
        src.write_bytes(b"audio")
        dst = tmp_path / "dst.mp3"
        calls = []
        monkeypatch.setattr(pm, "same_volume", lambda a, b: False)
        monkeypatch.setattr(pm.shutil, "move", lambda s, d: calls.append((s, d)) or d)

        move_on_disk(str(src), str(dst))

        assert len(calls) == 1
