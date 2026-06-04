"""Unit tests for muse/run_config.py."""

from types import SimpleNamespace

import pytest

from muse.run_config import RunConfig


@pytest.mark.unit
class TestRunConfig:
    def test_default_construction(self):
        rc = RunConfig()
        assert rc.total == -1
        assert rc.directories is None
        assert rc.overwrite is False

    def test_get_with_dict_args(self):
        rc = RunConfig(args={"directories": ["/music"]})
        assert rc.directories == ["/music"]

    def test_get_with_namespace_args(self):
        rc = RunConfig(args=SimpleNamespace(directories=["/jazz"]))
        assert rc.directories == ["/jazz"]

    def test_get_with_no_args_returns_none(self):
        assert RunConfig().get("directories") is None

    def test_validate_returns_true(self):
        assert RunConfig().validate() is True

    def test_str_contains_fields(self):
        s = str(RunConfig())
        assert "playlist_sort_type" in s
