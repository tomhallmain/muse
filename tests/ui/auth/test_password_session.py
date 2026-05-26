"""Password session manager tests (no dialog UI)."""

import pytest

from utils.globals import ProtectedActions


@pytest.mark.ui
class TestPasswordSession:
    def test_session_record_and_validity(self, isolated_singletons):
        from ui_qt.auth.password_session_manager import PasswordSessionManager

        action = ProtectedActions.RUN_SEARCH
        PasswordSessionManager.clear_session(action)
        assert not PasswordSessionManager.is_session_valid(action, timeout_minutes=30)

        PasswordSessionManager.record_successful_verification(action)
        assert PasswordSessionManager.is_session_valid(action, timeout_minutes=30)

        PasswordSessionManager.clear_session(action)
        assert not PasswordSessionManager.is_session_valid(action, timeout_minutes=30)
