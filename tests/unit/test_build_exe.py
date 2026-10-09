"""Tests for the helpers in build_exe.py, imported without running a build."""

import json
import os

import pytest

import build_exe

_OVERRIDES = ("MUSE_APP_DATA_DIR", "MUSE_CONFIGS_DIR", "MUSE_CACHE_DIR")


@pytest.fixture
def no_overrides(monkeypatch):
    for var in _OVERRIDES:
        monkeypatch.delenv(var, raising=False)


def _coqui_checkout(path):
    (path / "TTS").mkdir(parents=True)
    (path / "TTS" / "__init__.py").write_text("", encoding="utf-8")
    return path


@pytest.mark.unit
class TestPopOption:
    def test_removes_and_returns_the_value(self):
        args = ["--jobs=4", "--coqui-path=C:/x=y", "--show-scons"]
        assert build_exe._pop_option(args, "--coqui-path") == "C:/x=y"
        assert args == ["--jobs=4", "--show-scons"]

    def test_absent_option_returns_none(self):
        args = ["--jobs=4"]
        assert build_exe._pop_option(args, "--coqui-path") is None
        assert args == ["--jobs=4"]

    def test_a_flag_without_a_value_is_not_matched(self):
        args = ["--coqui-path"]
        assert build_exe._pop_option(args, "--coqui-path") is None


@pytest.mark.unit
class TestUserConfigPath:
    def test_configs_dir_override(self, monkeypatch, tmp_path, no_overrides):
        (tmp_path / "config.json").write_text("{}", encoding="utf-8")
        monkeypatch.setenv("MUSE_CONFIGS_DIR", str(tmp_path))
        assert build_exe._user_config_path() == os.path.join(str(tmp_path), "config.json")

    def test_app_data_dir_override(self, monkeypatch, tmp_path, no_overrides):
        (tmp_path / "configs").mkdir()
        (tmp_path / "configs" / "config.json").write_text("{}", encoding="utf-8")
        monkeypatch.setenv("MUSE_APP_DATA_DIR", str(tmp_path))
        assert build_exe._user_config_path() == os.path.join(str(tmp_path), "configs", "config.json")

    def test_windows_default_is_under_appdata(self, monkeypatch, tmp_path, no_overrides):
        configs = tmp_path / "Roaming" / "muse" / "configs"
        configs.mkdir(parents=True)
        (configs / "config.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(build_exe.sys, "platform", "win32")
        monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
        assert build_exe._user_config_path() == str(configs / "config.json")

    def test_falls_back_to_the_repo_configs_until_migrated(self, monkeypatch, tmp_path, no_overrides):
        monkeypatch.setenv("MUSE_CONFIGS_DIR", str(tmp_path / "empty"))
        monkeypatch.setattr(build_exe, "REPO_ROOT", str(tmp_path / "repo"))
        assert build_exe._user_config_path() == os.path.join(str(tmp_path / "repo"), "configs", "config.json")


@pytest.mark.unit
class TestCoquiLocation:
    def test_command_line_wins(self, monkeypatch, tmp_path):
        checkout = _coqui_checkout(tmp_path / "coqui")

        def not_called():
            raise AssertionError("config.json read although --coqui-path was given")

        monkeypatch.setattr(build_exe, "_user_config_path", not_called)
        assert build_exe._coqui_location(str(checkout)) == os.path.abspath(str(checkout))

    def test_from_config_with_home_placeholder(self, monkeypatch, tmp_path):
        checkout = _coqui_checkout(tmp_path / "coqui")
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"coqui_tts_location": "{HOME}/coqui"}), encoding="utf-8")
        monkeypatch.setattr(build_exe, "_user_config_path", lambda: str(config))
        monkeypatch.setattr(build_exe.os.path, "expanduser", lambda p: str(tmp_path) if p == "~" else p)
        assert build_exe._coqui_location(None) == os.path.abspath(str(checkout))

    def test_dir_without_tts_package_exits(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            build_exe._coqui_location(str(tmp_path))
        assert "Coqui TTS checkout not found" in str(exc.value)
        assert "--coqui-path" in str(exc.value)

    def test_unset_in_config_exits(self, monkeypatch, tmp_path):
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"coqui_tts_location": ""}), encoding="utf-8")
        monkeypatch.setattr(build_exe, "_user_config_path", lambda: str(config))
        with pytest.raises(SystemExit) as exc:
            build_exe._coqui_location(None)
        assert "not set" in str(exc.value)

    def test_unreadable_config_exits(self, monkeypatch, tmp_path):
        monkeypatch.setattr(build_exe, "_user_config_path", lambda: str(tmp_path / "missing.json"))
        with pytest.raises(SystemExit):
            build_exe._coqui_location(None)


@pytest.mark.unit
class TestAssetsFiles:
    def test_lists_assets_without_generated_clips(self, monkeypatch, tmp_path):
        for relpath in ("assets/icon.png", "assets/sub/x.png", "assets/spinning_record_videos/clip.mp4"):
            path = tmp_path / relpath
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"")
        monkeypatch.setattr(build_exe, "REPO_ROOT", str(tmp_path))
        assert build_exe._assets_files() == sorted([
            os.path.join("assets", "icon.png"),
            os.path.join("assets", "sub", "x.png"),
        ])
