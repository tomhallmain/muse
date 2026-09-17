"""Tests for ExtensionManager's post-download output resolution fallback
(extensions/extension_manager.py: check_dir_for_close_match, _exists_with_retry).

Regression coverage for a stray, never-embedded thumbnail jpg with a
near-identical filename to the just downloaded audio file being matched by
check_dir_for_close_match and treated as the extension's output.
"""

import os

import pytest

import extensions.extension_manager as extension_manager_mod
from extensions.extension_manager import ExtensionManager

# The jpg carries a fullwidth colon the audio file does not, the one-character
# difference that made the two names near-identical.
_AUDIO_NAME = "Example Composer (c.1500) [Work] Some Long Movement Title - Kyrie [0123456789A].m4a"
_STRAY_JPG_NAME = "Example Composer (c.1500)： [Work] Some Long Movement Title - Kyrie [0123456789A].jpg"


def _manager():
    return ExtensionManager.__new__(ExtensionManager)


@pytest.mark.unit
class TestCheckDirForCloseMatch:
    def test_does_not_match_a_near_identical_image_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(extension_manager_mod.config, "directories", [str(tmp_path)])
        (tmp_path / _STRAY_JPG_NAME).write_bytes(b"not audio")

        result = _manager().check_dir_for_close_match(str(tmp_path / _AUDIO_NAME))

        assert result is None

    def test_prefers_audio_file_over_near_identical_image(self, tmp_path, monkeypatch):
        monkeypatch.setattr(extension_manager_mod.config, "directories", [str(tmp_path)])
        (tmp_path / _STRAY_JPG_NAME).write_bytes(b"not audio")
        actual_audio = tmp_path / _AUDIO_NAME.replace("0123456789A", "0123456789B")
        actual_audio.write_bytes(b"audio bytes")

        result = _manager().check_dir_for_close_match(str(tmp_path / _AUDIO_NAME))

        assert result == str(actual_audio)

    def test_no_files_in_directory_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(extension_manager_mod.config, "directories", [str(tmp_path)])

        assert _manager().check_dir_for_close_match(str(tmp_path / _AUDIO_NAME)) is None

    def test_blank_target_returns_none(self):
        assert _manager().check_dir_for_close_match("") is None
        assert _manager().check_dir_for_close_match(None) is None

    def test_matches_when_target_carries_pre_extraction_extension(self, tmp_path, monkeypatch):
        monkeypatch.setattr(extension_manager_mod.config, "directories", [str(tmp_path)])
        stem = "Example Artist - Another Long Track Title For Matching [0123456789C]"
        actual_audio = tmp_path / (stem + ".opus")
        actual_audio.write_bytes(b"audio bytes")

        result = _manager().check_dir_for_close_match(str(tmp_path / (stem + ".webm")))

        assert result == str(actual_audio)

    def test_matches_target_reported_under_a_different_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr(extension_manager_mod.config, "directories", [str(tmp_path)])
        actual_audio = tmp_path / _AUDIO_NAME
        actual_audio.write_bytes(b"audio bytes")

        result = _manager().check_dir_for_close_match(
            os.path.join("C:\\some\\other\\deeply\\nested\\dir", _AUDIO_NAME))

        assert result == str(actual_audio)

    def test_unrelated_filename_is_not_matched(self, tmp_path, monkeypatch):
        monkeypatch.setattr(extension_manager_mod.config, "directories", [str(tmp_path)])
        (tmp_path / "Totally Different Song [zzz999QQQ_].opus").write_bytes(b"audio bytes")

        result = _manager().check_dir_for_close_match(str(tmp_path / "Some Track Title [abc123XYZ_].opus"))

        assert result is None


@pytest.mark.unit
class TestExistsWithRetry:
    def test_missing_path_returns_false(self):
        assert ExtensionManager._exists_with_retry(None) is False
        assert ExtensionManager._exists_with_retry("") is False

    def test_existing_file_returns_true_immediately(self, tmp_path):
        f = tmp_path / "present.m4a"
        f.write_bytes(b"data")

        assert ExtensionManager._exists_with_retry(str(f)) is True

    def test_retries_until_file_appears(self, tmp_path, monkeypatch):
        monkeypatch.setattr(extension_manager_mod.time, "sleep", lambda *_: None)
        target = str(tmp_path / "delayed.m4a")
        real_exists = os.path.exists
        calls = {"n": 0}

        def flaky_exists(path):
            if path == target:
                calls["n"] += 1
                return calls["n"] >= 3
            return real_exists(path)

        monkeypatch.setattr(extension_manager_mod.os.path, "exists", flaky_exists)

        assert ExtensionManager._exists_with_retry(target, attempts=5, delay_seconds=0.01) is True
        assert calls["n"] == 3

    def test_gives_up_after_attempts_exhausted(self, tmp_path, monkeypatch):
        monkeypatch.setattr(extension_manager_mod.time, "sleep", lambda *_: None)
        missing = str(tmp_path / "never.m4a")

        assert ExtensionManager._exists_with_retry(missing, attempts=3, delay_seconds=0.01) is False
