"""How Muse._wrap_function reports a social source that yielded nothing.

A filtered feed with nothing usable left is a normal outcome. The DJ must not
announce it: a spoken apology would be untrue, and telling the listener there
was nothing to say advertises that something was filtered out.
"""

from unittest.mock import MagicMock

import pytest

from extensions.social_filter import SocialSourceUnusable
from extensions.soup_utils import WebConnectionException
from muse.muse import Muse
from utils.globals import Topic


def _muse():
    muse = MagicMock()
    muse.llm.get_failure_count.return_value = 0
    return muse


def _raising(exception):
    def func(*_args, **_kwargs):
        raise exception
    return func


@pytest.mark.unit
class TestSocialSourceUnusable:
    def test_the_topic_fails_without_the_dj_saying_anything(self):
        muse = _muse()

        result = Muse._wrap_function(
            muse, MagicMock(), Topic.REDDIT, _raising(SocialSourceUnusable("nothing left"))
        )

        assert result is False
        muse.say_at_some_point.assert_not_called()

    def test_a_network_fault_is_still_announced(self):
        """The contrast that makes the silence above meaningful: a source that
        could not be reached is a real fault worth apologizing for."""
        muse = _muse()

        result = Muse._wrap_function(
            muse, MagicMock(), Topic.REDDIT, _raising(WebConnectionException("no route"))
        )

        assert result is False
        muse.say_at_some_point.assert_called_once()

    def test_an_unexpected_error_is_still_announced(self):
        muse = _muse()

        result = Muse._wrap_function(
            muse, MagicMock(), Topic.REDDIT, _raising(ValueError("something else"))
        )

        assert result is False
        muse.say_at_some_point.assert_called_once()
