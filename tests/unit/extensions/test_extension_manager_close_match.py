"""Tests for ExtensionManager's post-download output resolution fallback
(extensions/extension_manager.py: check_dir_for_close_match, _exists_with_retry).

Regression coverage for catastrophic_extension_timing_error.log: a stray,
never-embedded thumbnail jpg with a near-identical filename to the just
downloaded audio file was matched by check_dir_for_close_match and treated
as the extension's output.
"""

import os

import pytest

import extensions.extension_manager as extension_manager_mod
from extensions.extension_manager import ExtensionManager

# Real filenames from the incident log (colon variant is the stray leftover jpg).
_M4A_NAME = "Mathieu Gascongne (c.1510) [Missa] Mijn herte altijt heeft verlanghen - Kyrie [B-y2mGSORmY].m4a"
_STRAY_JPG_NAME = "Mathieu Gascongne (c.1510)： [Missa] Mijn herte altijt heeft verlanghen - Kyrie [B-y2mGSORmY].jpg"


def _manager():
    return ExtensionManager.__new__(ExtensionManager)


@pytest.mark.unit
class TestCheckDirForCloseMatch:
    def test_does_not_match_a_near_identical_image_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(extension_manager_mod.config, "directories", [str(tmp_path)])
        (tmp_path / _STRAY_JPG_NAME).write_bytes(b"not audio")

        result = _manager().check_dir_for_close_match(str(tmp_path / _M4A_NAME))

        assert result is None

    def test_prefers_audio_file_over_near_identical_image(self, tmp_path, monkeypatch):
        monkeypatch.setattr(extension_manager_mod.config, "directories", [str(tmp_path)])
        (tmp_path / _STRAY_JPG_NAME).write_bytes(b"not audio")
        actual_audio = tmp_path / _M4A_NAME.replace("B-y2mGSORmY", "B-y2mGSORmZ")
        actual_audio.write_bytes(b"audio bytes")

        result = _manager().check_dir_for_close_match(str(tmp_path / _M4A_NAME))

        assert result == str(actual_audio)

    def test_no_files_in_directory_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(extension_manager_mod.config, "directories", [str(tmp_path)])

        assert _manager().check_dir_for_close_match(str(tmp_path / _M4A_NAME)) is None

    def test_blank_target_returns_none(self):
        assert _manager().check_dir_for_close_match("") is None
        assert _manager().check_dir_for_close_match(None) is None


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
