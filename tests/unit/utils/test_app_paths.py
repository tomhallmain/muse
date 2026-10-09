"""Tests for utils/app_paths.py: the per-user dirs, their overrides, and the
one-time move of legacy files out of the repo."""

import logging
import os

import pytest

from utils import app_paths

_OVERRIDES = ("MUSE_APP_DATA_DIR", "MUSE_CONFIGS_DIR", "MUSE_CACHE_DIR")


@pytest.fixture
def quiet_logger(monkeypatch):
    """Keep the migration's log calls away from the real logs dir: the first
    get_logger() call for a module resolves logs_dir() through app_data_dir()."""
    monkeypatch.setattr(app_paths, "_logger", lambda: logging.getLogger("test_app_paths"))


@pytest.fixture
def fake_repo(tmp_path, monkeypatch, quiet_logger):
    """A throwaway REPO_ROOT holding legacy files; returns a writer for them."""
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(app_paths, "REPO_ROOT", str(repo))

    def write(relpath, content="legacy"):
        path = repo / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    write.root = repo
    return write


@pytest.fixture
def no_app_data_override(monkeypatch):
    """Unset only MUSE_APP_DATA_DIR, for tests that compute the default path
    and create nothing; the cache override, which also places the key store,
    stays set."""
    monkeypatch.delenv("MUSE_APP_DATA_DIR", raising=False)


@pytest.mark.unit
class TestAppDataDir:
    def test_override_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MUSE_APP_DATA_DIR", str(tmp_path))
        assert app_paths.app_data_dir() == str(tmp_path)

    def test_windows_uses_appdata(self, monkeypatch, no_app_data_override):
        monkeypatch.setattr(app_paths.sys, "platform", "win32")
        monkeypatch.setenv("APPDATA", os.path.join("X:", "Roaming"))
        assert app_paths.app_data_dir() == os.path.join("X:", "Roaming", "muse")

    def test_windows_without_appdata_uses_home(self, monkeypatch, no_app_data_override):
        monkeypatch.setattr(app_paths.sys, "platform", "win32")
        monkeypatch.delenv("APPDATA", raising=False)
        monkeypatch.setattr(app_paths.os.path, "expanduser", lambda p: p.replace("~", "HOME"))
        assert app_paths.app_data_dir() == os.path.join("HOME", "AppData", "Roaming", "muse")

    @pytest.mark.parametrize("platform", ["linux", "darwin"])
    def test_other_platforms_use_local_share(self, monkeypatch, no_app_data_override, platform):
        monkeypatch.setattr(app_paths.sys, "platform", platform)
        monkeypatch.setattr(app_paths.os.path, "expanduser", lambda p: p.replace("~", "HOME"))
        assert app_paths.app_data_dir() == os.path.join("HOME", ".local", "share", "muse")


@pytest.mark.unit
class TestDirs:
    @pytest.fixture(autouse=True)
    def migrated(self, monkeypatch):
        """Mark every migration as done so resolving a dir moves nothing."""
        monkeypatch.setattr(app_paths, "_migrated", {"configs", "cache", "tts_output"})

    def test_configs_dir_override(self, monkeypatch, tmp_path):
        target = tmp_path / "my_configs"
        monkeypatch.setenv("MUSE_CONFIGS_DIR", str(target))
        assert app_paths.configs_dir() == str(target)
        assert target.is_dir()

    def test_configs_dir_under_app_data_dir(self, monkeypatch, tmp_path):
        monkeypatch.delenv("MUSE_CONFIGS_DIR", raising=False)
        monkeypatch.setenv("MUSE_APP_DATA_DIR", str(tmp_path))
        assert app_paths.configs_dir() == os.path.join(str(tmp_path), "configs")

    def test_cache_dir_override(self, monkeypatch, tmp_path):
        target = tmp_path / "my_cache"
        monkeypatch.setenv("MUSE_CACHE_DIR", str(target))
        assert app_paths.cache_dir() == str(target)
        assert target.is_dir()

    def test_cache_dir_under_app_data_dir(self, monkeypatch, tmp_path):
        monkeypatch.delenv("MUSE_CACHE_DIR", raising=False)
        monkeypatch.setenv("MUSE_APP_DATA_DIR", str(tmp_path))
        assert app_paths.cache_dir() == os.path.join(str(tmp_path), "cache")

    def test_logs_and_tts_output_under_app_data_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MUSE_APP_DATA_DIR", str(tmp_path))
        assert app_paths.logs_dir() == os.path.join(str(tmp_path), "logs")
        assert app_paths.tts_output_dir() == os.path.join(str(tmp_path), "tts_output")
        assert (tmp_path / "logs").is_dir()
        assert (tmp_path / "tts_output").is_dir()

    def test_user_library_data_dir_is_inside_configs(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MUSE_CONFIGS_DIR", str(tmp_path))
        assert app_paths.user_library_data_dir() == os.path.join(str(tmp_path), "library_data")

    def test_resource_path_is_under_resource_root(self):
        assert app_paths.resource_path("locale", "en") == os.path.join(app_paths.RESOURCE_ROOT, "locale", "en")


@pytest.mark.unit
class TestMigrateConfigs:
    def test_moves_configs(self, fake_repo, tmp_path):
        fake_repo("configs/config.json", "{}")
        fake_repo("configs/muse_library.db", "db")
        target = tmp_path / "target"
        app_paths._migrate_configs(str(target))
        assert (target / "config.json").read_text(encoding="utf-8") == "{}"
        assert (target / "muse_library.db").is_file()
        assert not (fake_repo.root / "configs" / "config.json").exists()

    def test_never_overwrites(self, fake_repo, tmp_path):
        source = fake_repo("configs/config.json", "legacy")
        target = tmp_path / "target"
        target.mkdir()
        (target / "config.json").write_text("current", encoding="utf-8")
        app_paths._migrate_configs(str(target))
        assert (target / "config.json").read_text(encoding="utf-8") == "current"
        assert source.read_text(encoding="utf-8") == "legacy"

    def test_library_data_user_files_move_and_shipped_files_stay(self, fake_repo, tmp_path):
        shipped = [
            fake_repo("library_data/data/composers_example.json"),
            fake_repo("library_data/data/blacklist_default.enc"),
            fake_repo("library_data/data/data_fixes.json"),
        ]
        fake_repo("library_data/data/artists.json", "user")
        target = tmp_path / "target"
        app_paths._migrate_configs(str(target))
        assert (target / "library_data" / "artists.json").read_text(encoding="utf-8") == "user"
        for path in shipped:
            assert path.is_file()
            assert not (target / "library_data" / path.name).exists()

    def test_no_legacy_dirs_is_a_no_op(self, fake_repo, tmp_path):
        target = tmp_path / "target"
        app_paths._migrate_configs(str(target))
        assert not target.exists()


@pytest.mark.unit
class TestMigrateCacheAndOutput:
    def test_cache_files_go_to_their_subdirs(self, fake_repo, tmp_path):
        fake_repo("app_info_cache.enc")
        fake_repo("app_info_cache.enc.bak1")
        fake_repo("temp_llm_prompt_response_history_x.json")
        fake_repo("extensions/library_ext_q_dict.json")
        fake_repo("extensions/library_ext_q_dict.enc")
        fake_repo("library_data/wiki/Bach.txt")
        fake_repo("assets/spinning_record_videos/clip.mp4")
        fake_repo("assets/icon.png")
        target = tmp_path / "migrated_cache"  # the root conftest already creates tmp_path/cache
        app_paths._migrate_cache(str(target))
        assert (target / "app_info_cache.enc").is_file()
        assert (target / "app_info_cache.enc.bak1").is_file()
        assert (target / "temp_llm_prompt_response_history_x.json").is_file()
        assert (target / "library_ext_q_dict.json").is_file()
        assert (target / "wiki" / "Bach.txt").is_file()
        assert (target / "spinning_record_videos" / "clip.mp4").is_file()
        # Bundled, read-only files stay.
        assert (fake_repo.root / "extensions" / "library_ext_q_dict.enc").is_file()
        assert (fake_repo.root / "assets" / "icon.png").is_file()

    def test_tts_output_moves(self, fake_repo, tmp_path):
        fake_repo("tts_output/spot.wav")
        target = tmp_path / "migrated_tts_output"
        app_paths._migrate_tts_output(str(target))
        assert (target / "spot.wav").is_file()


@pytest.mark.unit
class TestMigrateOnce:
    """The real overrides stay set (the test environment needs them); the
    override check runs against a stand-in variable name instead."""

    _FAKE_OVERRIDE = "MUSE_TEST_FAKE_OVERRIDE"

    @pytest.fixture(autouse=True)
    def fresh_state(self, monkeypatch, quiet_logger):
        monkeypatch.setattr(app_paths, "_migrated", set())
        monkeypatch.setattr(app_paths, "_OVERRIDE_VARS", (self._FAKE_OVERRIDE,))
        monkeypatch.delenv(self._FAKE_OVERRIDE, raising=False)

    def test_runs_once_per_key(self, tmp_path):
        calls = []
        app_paths._migrate_once("k", calls.append, str(tmp_path))
        app_paths._migrate_once("k", calls.append, str(tmp_path))
        assert calls == [str(tmp_path)]

    def test_skipped_while_an_override_is_set(self, monkeypatch, tmp_path):
        monkeypatch.setenv(self._FAKE_OVERRIDE, str(tmp_path))
        calls = []
        app_paths._migrate_once("k", calls.append, str(tmp_path))
        assert calls == []

    def test_a_failing_migration_is_logged_not_raised(self, tmp_path, caplog):
        def fail(_target):
            raise RuntimeError("disk full")

        with caplog.at_level(logging.ERROR, logger="test_app_paths"):
            app_paths._migrate_once("k", fail, str(tmp_path))
        assert "disk full" in caplog.text


@pytest.mark.unit
def test_the_override_list_names_every_override():
    assert set(app_paths._OVERRIDE_VARS) == set(_OVERRIDES)
