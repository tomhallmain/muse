"""Tests for utils/runner_app_config.py."""

import pytest

from utils.runner_app_config import RunnerAppConfig


@pytest.mark.unit
class TestFromDict:
    def test_a_renamed_key_loads_into_its_attribute(self):
        app_config = RunnerAppConfig.from_dict({"overwrite": False})
        assert app_config.rescan is False
        assert "overwrite" not in app_config.to_dict()

    def test_the_current_key_loads_as_is(self):
        assert RunnerAppConfig.from_dict({"rescan": False}).rescan is False

    def test_an_unknown_key_is_still_rejected(self):
        with pytest.raises(Exception):
            RunnerAppConfig.from_dict({"no_such_key": 1})
