"""Tests for the helpers in build_exe.py, imported without running a build."""

import json
import os

import pytest

import build_exe

@pytest.fixture
def no_overrides(monkeypatch):
    """Unset the two overrides _user_config_path reads. It only computes a
    path and checks it exists; MUSE_CACHE_DIR, which also places the key
    store, stays set."""
    for var in ("MUSE_APP_DATA_DIR", "MUSE_CONFIGS_DIR"):
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
        configs = tmp_path / "my_configs"
        configs.mkdir()
        (configs / "config.json").write_text("{}", encoding="utf-8")
        monkeypatch.setenv("MUSE_CONFIGS_DIR", str(configs))
        assert build_exe._user_config_path() == os.path.join(str(configs), "config.json")

    def test_app_data_dir_override(self, monkeypatch, tmp_path, no_overrides):
        # A subdir: the root conftest already creates tmp_path/configs.
        app_data = tmp_path / "app_data"
        (app_data / "configs").mkdir(parents=True)
        (app_data / "configs" / "config.json").write_text("{}", encoding="utf-8")
        monkeypatch.setenv("MUSE_APP_DATA_DIR", str(app_data))
        assert build_exe._user_config_path() == os.path.join(str(app_data), "configs", "config.json")

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


@pytest.mark.unit
class TestAppVersion:
    def test_reads_the_version_file(self):
        import re

        assert re.fullmatch(r"\d+(\.\d+){0,3}", build_exe._app_version())

    def test_strips_the_line_end(self, monkeypatch, tmp_path):
        (tmp_path / build_exe.VERSION_FILE).write_text("1.2.3\n", encoding="utf-8")
        monkeypatch.setattr(build_exe, "REPO_ROOT", str(tmp_path))
        assert build_exe._app_version() == "1.2.3"

    @pytest.mark.parametrize("bad", ["1.0.0-beta", "1.2.3.4.5", "v1", ""])
    def test_rejects_what_windows_version_information_cannot_hold(self, monkeypatch, tmp_path, bad):
        (tmp_path / build_exe.VERSION_FILE).write_text(bad + "\n", encoding="utf-8")
        monkeypatch.setattr(build_exe, "REPO_ROOT", str(tmp_path))
        with pytest.raises(SystemExit):
            build_exe._app_version()

    def test_the_version_file_is_bundled(self):
        args = build_exe._nuitka_args("Muse.exe", "1.2.3", "20261009-095251")
        assert f"--include-data-files={build_exe.VERSION_FILE}={build_exe.VERSION_FILE}" in args


@pytest.mark.unit
class TestLockHas:
    @pytest.mark.parametrize("line", [
        "liboqs-python==0.12.0",
        "liboqs_python @ git+https://github.com/open-quantum-safe/liboqs-python.git@abc",
        "LibOQS.Python>=0.12",
    ])
    def test_finds_a_pinned_distribution(self, tmp_path, line):
        lock = tmp_path / "lock.txt"
        lock.write_text(f"numpy==2.0.2\n{line}\n", encoding="utf-8")
        assert build_exe._lock_has(str(lock), "liboqs-python")

    def test_absent_distribution(self, tmp_path):
        lock = tmp_path / "lock.txt"
        lock.write_text("numpy==2.0.2\nliboqs==1.0\n", encoding="utf-8")
        assert not build_exe._lock_has(str(lock), "liboqs-python")


@pytest.mark.unit
class TestTransformersVersionCheck:
    def test_matching_release_is_quiet(self, caplog):
        with caplog.at_level("INFO", logger="build_exe"):
            build_exe._check_transformers_version({"transformers": "4.45.2"})
        assert caplog.records == []

    def test_other_release_warns(self, caplog):
        with caplog.at_level("INFO", logger="build_exe"):
            build_exe._check_transformers_version({"transformers": "4.46.0"})
        assert [r.levelname for r in caplog.records] == ["WARNING"]
        assert "4.46.0" in caplog.messages[0]

    def test_absent_transformers_is_quiet(self, caplog):
        with caplog.at_level("INFO", logger="build_exe"):
            build_exe._check_transformers_version({"transformers": None})
        assert caplog.records == []


@pytest.mark.unit
class TestGitCommit:
    def _git(self, tmp_path, head):
        git = tmp_path / ".git"
        git.mkdir()
        (git / "HEAD").write_text(head + "\n", encoding="utf-8")
        return git

    def test_detached_head(self, tmp_path):
        self._git(tmp_path, "abc123")
        assert build_exe._git_commit(str(tmp_path)) == "abc123"

    def test_branch_ref_file(self, tmp_path):
        git = self._git(tmp_path, "ref: refs/heads/dev")
        (git / "refs" / "heads").mkdir(parents=True)
        (git / "refs" / "heads" / "dev").write_text("def456\n", encoding="utf-8")
        assert build_exe._git_commit(str(tmp_path)) == "def456"

    def test_packed_ref(self, tmp_path):
        git = self._git(tmp_path, "ref: refs/heads/main")
        (git / "packed-refs").write_text(
            "# pack-refs with: peeled fully-peeled sorted\n0a1b2c refs/heads/main\n", encoding="utf-8")
        assert build_exe._git_commit(str(tmp_path)) == "0a1b2c"

    def test_not_a_checkout(self, tmp_path):
        assert build_exe._git_commit(str(tmp_path)) == ""


@pytest.mark.unit
class TestBuildInfo:
    def test_environment_versions_come_from_the_interpreter(self):
        import sys

        environment = build_exe._environment_versions(sys.executable)
        assert environment["python"] == sys.version.split()[0]
        assert set(environment["packages"]) == set(build_exe.RECORDED_DISTRIBUTIONS)

    def test_written_build_info(self, monkeypatch, tmp_path):
        # Stubbed so the test runs no git in the real checkout.
        monkeypatch.setattr(build_exe, "_version_module", lambda: {
            "read_git_commit": lambda checkout: "",
            "source_state": lambda repo: {"commit": "abc123", "tree": "fed987", "changes": ""},
        })
        monkeypatch.setattr(build_exe, "BUILD_DIR", str(tmp_path))
        monkeypatch.setattr(build_exe, "BUILD_INFO_PATH", str(tmp_path / "build_info.json"))
        environment = {"python": "3.10.14", "packages": {"PySide6": "6.11.2", "torch": None}}
        build_exe._write_build_info("1.2.3", "20261009-095251", environment, str(tmp_path / "coqui"),
                                    with_oqs=True)
        info = json.loads((tmp_path / "build_info.json").read_text(encoding="utf-8"))
        assert info == {
            "version": "1.2.3",
            "build_id": "20261009-095251",
            "with_oqs": True,
            "python": "3.10.14",
            "packages": {"PySide6": "6.11.2"},
            "coqui_commit": "unknown",
            "source": {"repo": build_exe.REPO_ROOT, "commit": "abc123", "tree": "fed987", "changes": ""},
        }

    def test_nuitka_args_carry_version_and_build_info(self):
        args = build_exe._nuitka_args("Muse.exe", "1.2.3", "20261009-095251")
        assert "--product-version=1.2.3" in args
        assert "--file-version=1.2.3" in args
        assert "--file-description=Muse media player, build 20261009-095251" in args
        assert f"--include-data-files={build_exe.BUILD_INFO_PATH}=build_info.json" in args


@pytest.mark.unit
class TestMemoryWait:
    @staticmethod
    def _no_tool(monkeypatch, tools=None):
        """No variable, *tools* ({command: path}) as what shutil.which finds."""
        monkeypatch.delenv(build_exe.MEMORY_WAIT_PLUGIN_ENV, raising=False)
        monkeypatch.setattr(build_exe.shutil, "which", lambda name: (tools or {}).get(name))

    def test_the_variable_names_the_plugin(self, monkeypatch, tmp_path):
        plugin = tmp_path / "memory_wait_plugin.py"
        plugin.write_text("", encoding="utf-8")
        self._no_tool(monkeypatch)
        monkeypatch.setenv(build_exe.MEMORY_WAIT_PLUGIN_ENV, str(plugin))
        assert build_exe._memory_wait_plugin() == str(plugin)

    def test_an_installed_tool_names_the_plugin(self, monkeypatch, tmp_path):
        import subprocess

        plugin = tmp_path / "memory_wait_plugin.py"
        plugin.write_text("", encoding="utf-8")
        self._no_tool(monkeypatch, tools={"app-release": "/bin/app-release"})
        calls = []

        def fake_run(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, stdout=f"{plugin}\n", stderr="")

        monkeypatch.setattr(build_exe.subprocess, "run", fake_run)
        assert build_exe._memory_wait_plugin() == str(plugin)
        assert calls == [["/bin/app-release", "--memory-wait-plugin"]]

    def test_no_plugin_anywhere_builds_without_it(self, monkeypatch, caplog):
        self._no_tool(monkeypatch)
        with caplog.at_level("WARNING", logger="build_exe"):
            assert build_exe._memory_wait_plugin() is None
        assert any("app-release" in message for message in caplog.messages)

    def test_the_plugin_found_is_passed_to_nuitka(self):
        args = build_exe._nuitka_args("Muse.exe", "1.2.3", "20261009-095251", "/x/memory_wait_plugin.py")
        assert build_exe._pop_option(args, "--user-plugin") == "/x/memory_wait_plugin.py"
        args = build_exe._nuitka_args("Muse.exe", "1.2.3", "20261009-095251")
        assert build_exe._pop_option(args, "--user-plugin") is None

    def test_min_free_memory_reaches_nuitka(self, monkeypatch):
        monkeypatch.delenv(build_exe.MIN_FREE_MEMORY_ENV, raising=False)
        assert build_exe._nuitka_env("C:/coqui", "12")[build_exe.MIN_FREE_MEMORY_ENV] == "12"
        assert build_exe.MIN_FREE_MEMORY_ENV not in build_exe._nuitka_env("C:/coqui", None)

    def test_coqui_checkout_is_on_the_path(self, monkeypatch):
        monkeypatch.setenv("PYTHONPATH", "elsewhere")
        assert build_exe._nuitka_env("C:/coqui")["PYTHONPATH"] == os.pathsep.join(["C:/coqui", "elsewhere"])

    @pytest.mark.parametrize("value", ["0", "12", "2.5"])
    def test_min_free_memory_accepts_gib(self, value):
        assert build_exe._min_free_memory(value) == value

    @pytest.mark.parametrize("value", ["-1", "lots", ""])
    def test_min_free_memory_refuses_other_values(self, value):
        with pytest.raises(SystemExit):
            build_exe._min_free_memory(value)

    def test_the_variable_is_the_one_the_plugin_reads(self):
        # app-release's tests pin the plugin's side of this name.
        assert build_exe.MIN_FREE_MEMORY_ENV == "BUILD_MIN_FREE_MEMORY_GB"


@pytest.mark.unit
class TestTiming:
    @pytest.mark.parametrize("seconds, text", [
        (0, "0s"), (59.6, "1m 00s"), (125, "2m 05s"), (2 * 3600 + 5, "2h 00m 05s"),
    ])
    def test_duration(self, seconds, text):
        assert build_exe._duration(seconds) == text

    def test_timed_logs_the_duration_of_a_step(self, caplog):
        with caplog.at_level("INFO", logger="build_exe"):
            with build_exe._timed("Compiling"):
                pass
        assert caplog.messages[0] == "Compiling..."
        assert caplog.messages[-1].startswith("Compiling done in ")

    def test_timed_logs_a_failed_step(self, caplog):
        with caplog.at_level("INFO", logger="build_exe"):
            with pytest.raises(SystemExit):
                with build_exe._timed("Compiling"):
                    raise SystemExit("broken")
        assert caplog.messages[-1].startswith("Compiling failed after ")


@pytest.mark.unit
class TestCopyToDist:
    def test_replaces_a_folder_build(self, monkeypatch, tmp_path):
        build_dir, dist_dir = tmp_path / "build", tmp_path / "dist"
        build_dir.mkdir()
        (build_dir / "Muse").write_bytes(b"exe")
        (dist_dir / "Muse").mkdir(parents=True)
        monkeypatch.setattr(build_exe, "BUILD_DIR", str(build_dir))
        monkeypatch.setattr(build_exe, "DIST_DIR", str(dist_dir))
        assert build_exe._copy_to_dist("Muse") == str(dist_dir / "Muse")
        assert (dist_dir / "Muse").read_bytes() == b"exe"
