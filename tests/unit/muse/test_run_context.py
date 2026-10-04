"""
Unit tests for muse/run_context.py.

Run.execute() calls RunContext.reset() at the start of each run, so after a
reset nothing from the previous run (including a cancel) may remain.
"""

import pytest

from muse.run_context import RunContext, UserAction


@pytest.mark.unit
class TestRunContextCancel:

    def test_cancel_is_reported(self):
        ctx = RunContext()
        ctx.update_action(UserAction.CANCEL)
        assert ctx.was_cancelled()
        assert ctx.should_skip()

    def test_fresh_context_is_not_cancelled(self):
        assert not RunContext().was_cancelled()


@pytest.mark.unit
class TestRunContextReset:

    @pytest.mark.parametrize("action", list(UserAction))
    def test_reset_returns_to_default_state(self, action):
        ctx = RunContext()
        ctx.update_action(action)
        ctx.seek_target_filepath = "/music/track.mp3"
        ctx.reset()
        assert ctx == RunContext()

    def test_reset_clears_cancel(self):
        ctx = RunContext()
        ctx.update_action(UserAction.CANCEL)
        ctx.reset()
        assert not ctx.was_cancelled()
        assert not ctx.should_skip()
