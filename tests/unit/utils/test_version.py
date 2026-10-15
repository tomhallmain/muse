"""Tests for utils/version.py and the smoke test's build info check. Build
info is read from a file in tmp_path."""

import json
import re

import pytest

from utils import app_paths, smoke_test, version


@pytest.fixture
def resource_root(monkeypatch, tmp_path):
    """Resolve bundled files under tmp_path, with a VERSION file of 1.2.3;
    returns the build_info.json path."""
    monkeypatch.setattr(app_paths, "resource_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    (tmp_path / version.VERSION_FILE).write_text("1.2.3\n", encoding="utf-8")
    return tmp_path / version.BUILD_INFO_FILE


def _write_info(path, **overrides):
    info = {"version": "1.2.3", "build_id": "20261009-095251", "python": "3.10.14",
            "packages": {"PySide6": "6.11.2", "Nuitka": "4.2.2"}, "coqui_commit": "abc123"}
    info.update(overrides)
    path.write_text(json.dumps(info), encoding="utf-8")


@pytest.mark.unit
class TestVersion:
    def test_app_version_fits_windows_version_information(self):
        assert re.fullmatch(r"\d+(\.\d+){0,3}", version.app_version())

    def test_app_version_is_read_from_the_version_file(self, resource_root):
        assert version.app_version() == "1.2.3"

    def test_source_checkout(self, resource_root):
        assert version.build_info() == {}
        assert version.describe() == "Muse 1.2.3 (source checkout)"

    def test_missing_version_file(self, resource_root):
        (resource_root.parent / version.VERSION_FILE).unlink()
        assert "version unreadable" in version.describe()

    def test_build(self, resource_root):
        _write_info(resource_root, source={"repo": "R", "commit": "0123456789abcdef", "changes": ""})
        assert version.describe() == (
            "Muse 1.2.3, build 20261009-095251 from 0123456789 (Nuitka 4.2.2, PySide6 6.11.2)"
        )

    def test_build_with_uncommitted_changes(self, resource_root):
        _write_info(resource_root, source={"repo": "R", "commit": "0123456789abcdef", "changes": "f00"})
        assert "from 0123456789 with uncommitted changes" in version.describe()

    def test_build_without_source(self, resource_root):
        _write_info(resource_root)
        assert "from unknown commit" in version.describe()

    def test_unreadable_build_info(self, resource_root):
        resource_root.write_text("{broken", encoding="utf-8")
        assert "build info unreadable" in version.describe()


@pytest.mark.unit
class TestSmokeCheckBuildInfo:
    def test_checkout_passes_without_build_info(self, resource_root, monkeypatch):
        monkeypatch.setattr(app_paths, "IS_BUILD", False)
        assert "source checkout" in smoke_test._check_build_info()

    def test_build_without_build_info_fails(self, resource_root, monkeypatch):
        monkeypatch.setattr(app_paths, "IS_BUILD", True)
        with pytest.raises(FileNotFoundError):
            smoke_test._check_build_info()

    def test_build_with_another_version_fails(self, resource_root, monkeypatch):
        monkeypatch.setattr(app_paths, "IS_BUILD", True)
        _write_info(resource_root, version="0.0.1")
        with pytest.raises(ValueError, match="0.0.1"):
            smoke_test._check_build_info()

    def test_build_without_version_file_fails(self, resource_root, monkeypatch):
        monkeypatch.setattr(app_paths, "IS_BUILD", True)
        _write_info(resource_root)
        (resource_root.parent / version.VERSION_FILE).unlink()
        with pytest.raises(FileNotFoundError):
            smoke_test._check_build_info()

    def test_build_with_matching_build_info_passes(self, resource_root, monkeypatch):
        monkeypatch.setattr(app_paths, "IS_BUILD", True)
        _write_info(resource_root)
        assert "build 20261009-095251" in smoke_test._check_build_info()


@pytest.mark.unit
class TestSourceState:
    def test_commit_and_clean_tree_from_git(self, monkeypatch):
        outputs = {("rev-parse", "HEAD"): "abc123\n", ("rev-parse", "HEAD^{tree}"): "fed987\n",
                   ("diff", "HEAD", "--binary"): ""}
        monkeypatch.setattr(version, "run_git", lambda repo, *args: outputs[args])
        assert version.source_state("R") == {"commit": "abc123", "tree": "fed987", "changes": ""}

    def test_uncommitted_changes_are_fingerprinted(self, monkeypatch):
        outputs = {("rev-parse", "HEAD"): "abc123\n", ("rev-parse", "HEAD^{tree}"): "fed987\n",
                   ("diff", "HEAD", "--binary"): "diff --git a b\n"}
        monkeypatch.setattr(version, "run_git", lambda repo, *args: outputs[args])
        changes = version.source_state("R")["changes"]
        assert changes and len(changes) == 40

    def test_without_git_reads_the_commit_from_dot_git(self, monkeypatch, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "HEAD").write_text("def456\n", encoding="utf-8")
        monkeypatch.setattr(version, "run_git", lambda repo, *args: None)
        assert version.source_state(str(tmp_path)) == {"commit": "def456", "tree": "", "changes": None}


@pytest.mark.unit
class TestSourceDrift:
    @pytest.fixture
    def built(self, monkeypatch, tmp_path):
        """A build recorded from a checkout in tmp_path; returns a setter for
        the checkout's current state and git's rev-list answers."""
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr(version, "build_info", lambda: {
            "source": {"repo": str(tmp_path), "commit": "aaaa111122223333", "changes": ""},
        })

        def now(commit, changes="", newer="0", missing="0"):
            monkeypatch.setattr(version, "source_state", lambda repo: {"commit": commit, "changes": changes})
            counts = {"newer": newer, "missing": missing}

            def run_git(repo, *args):
                if args[0] != "rev-list":
                    return None
                key = "newer" if args[-1].startswith("aaaa") else "missing"
                return counts[key]
            monkeypatch.setattr(version, "run_git", run_git)
        now.repo = tmp_path
        return now

    def test_source_checkout_has_nothing_to_compare(self, monkeypatch):
        monkeypatch.setattr(version, "build_info", lambda: {})
        assert version.source_drift() is None

    def test_missing_checkout(self, monkeypatch, tmp_path):
        monkeypatch.setattr(version, "build_info", lambda: {
            "source": {"repo": str(tmp_path / "gone"), "commit": "aaaa", "changes": ""},
        })
        drifted, message = version.source_drift()
        assert drifted is False
        assert "not found" in message

    def test_same_commit_and_changes_match(self, built):
        built("aaaa111122223333")
        drifted, message = version.source_drift()
        assert drifted is False
        assert "matches" in message

    def test_same_commit_without_git_counts_as_matching(self, built):
        built("aaaa111122223333", changes=None)
        assert version.source_drift()[0] is False

    def test_same_commit_with_other_changes_drifted(self, built):
        built("aaaa111122223333", changes="f00")
        drifted, message = version.source_drift()
        assert drifted is True
        assert "uncommitted changes differ" in message

    def test_newer_commits_are_counted(self, built):
        built("bbbb444455556666", newer="3\n")
        drifted, message = version.source_drift()
        assert drifted is True
        assert "3 commit(s) not in this build" in message
        assert "lacks" not in message

    def test_commits_missing_from_the_checkout_are_counted(self, built):
        built("bbbb444455556666", newer="1", missing="2")
        assert "lacks 2 commit(s) this build has" in version.source_drift()[1]

    def test_without_git_counts_says_a_different_commit(self, built, monkeypatch):
        built("bbbb444455556666")
        monkeypatch.setattr(version, "run_git", lambda repo, *args: None)
        drifted, message = version.source_drift()
        assert drifted is True
        assert "a different commit" in message

    def _rewritten(self, monkeypatch, tmp_path, current_tree):
        """A build from commit dddd..., whose checkout is now at eeee... with
        *current_tree*, and in which git finds no commit dddd... (history
        rewritten, then gc)."""
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr(version, "build_info", lambda: {
            "source": {"repo": str(tmp_path), "commit": "d" * 40, "tree": "t" * 40, "changes": ""},
        })
        monkeypatch.setattr(version, "source_state",
                            lambda repo: {"commit": "e" * 40, "tree": current_tree, "changes": ""})
        monkeypatch.setattr(version, "run_git", lambda repo, *args: None)

    def test_rewritten_commit_with_the_same_files_matches(self, monkeypatch, tmp_path):
        self._rewritten(monkeypatch, tmp_path, current_tree="t" * 40)
        drifted, message = version.source_drift()
        assert drifted is False
        assert "same files" in message

    def test_commit_missing_from_the_history_is_named(self, monkeypatch, tmp_path):
        self._rewritten(monkeypatch, tmp_path, current_tree="u" * 40)
        drifted, message = version.source_drift()
        assert drifted is True
        assert "not in its history" in message
