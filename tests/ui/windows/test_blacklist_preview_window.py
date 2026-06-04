"""Tests for ui_qt/blacklist_preview_window.py.

Isolation:
- `Blacklist.find_blacklisted_items` is monkeypatched per-test so no real
  blacklist file is read and results are deterministic.
- `BlacklistPreviewWindow.top_level` is reset by the autouse
  `reset_ui_window_state` fixture in tests/ui/conftest.py.
- All other singleton isolation is provided by the root conftest autouse
  fixtures (app_info_cache, config, metadata JSON, etc.).
"""

import pytest

from tests.utils.qt_test_helpers import process_events_for


@pytest.mark.ui
class TestBlacklistPreviewWindow:
    @pytest.fixture
    def win(self, qapp, qt_master, mock_app_actions):
        from ui_qt.blacklist_preview_window import BlacklistPreviewWindow
        w = BlacklistPreviewWindow(qt_master, mock_app_actions)
        process_events_for(0.2)
        yield w
        w.close()
        qapp.processEvents()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def test_opens_and_is_visible(self, win):
        assert win.isVisible()

    def test_registered_as_top_level(self, win):
        from ui_qt.blacklist_preview_window import BlacklistPreviewWindow
        assert BlacklistPreviewWindow.top_level is win

    def test_second_open_closes_first(self, qapp, qt_master, mock_app_actions):
        from ui_qt.blacklist_preview_window import BlacklistPreviewWindow
        first = BlacklistPreviewWindow(qt_master, mock_app_actions)
        process_events_for(0.1)
        second = BlacklistPreviewWindow(qt_master, mock_app_actions)
        process_events_for(0.1)
        assert BlacklistPreviewWindow.top_level is second
        second.close()
        qapp.processEvents()

    # ------------------------------------------------------------------
    # _run_test: empty input
    # ------------------------------------------------------------------

    def test_empty_input_shows_prompt(self, win):
        from utils.translations import I18N
        win.input_text.setPlainText("")
        win._run_test()
        assert win.result_text.toPlainText() == I18N._("Enter some text above, then click Test.")

    # ------------------------------------------------------------------
    # _run_test: no blacklist match
    # ------------------------------------------------------------------

    def test_no_match_shows_no_match_message(self, win, monkeypatch):
        monkeypatch.setattr(
            "ui_qt.blacklist_preview_window.Blacklist.find_blacklisted_items",
            lambda text: {},
        )
        win.input_text.setPlainText("clean text")
        win._run_test()
        # A localised single-line "no match" message is shown.
        # It must be non-empty and must NOT be a multi-line match list.
        result = win.result_text.toPlainText()
        assert result != ""
        assert "\n" not in result

    # ------------------------------------------------------------------
    # _run_test: matched items
    # ------------------------------------------------------------------

    def test_matched_items_show_count_and_rule(self, win, monkeypatch):
        monkeypatch.setattr(
            "ui_qt.blacklist_preview_window.Blacklist.find_blacklisted_items",
            lambda text: {"badword": "profanity", "slur": "hate-speech"},
        )
        win.input_text.setPlainText("badword slur")
        win._run_test()
        result = win.result_text.toPlainText()
        assert "2" in result
        assert "badword" in result
        assert "profanity" in result

    def test_matched_items_sorted_by_rule_then_tag(self, win, monkeypatch):
        monkeypatch.setattr(
            "ui_qt.blacklist_preview_window.Blacklist.find_blacklisted_items",
            lambda text: {"beta": "rule_b", "alpha": "rule_a"},
        )
        win.input_text.setPlainText("alpha beta")
        win._run_test()
        result = win.result_text.toPlainText()
        assert result.index("alpha") < result.index("beta")

    # ------------------------------------------------------------------
    # Close behaviour
    # ------------------------------------------------------------------

    def test_close_clears_top_level(self, qapp, qt_master, mock_app_actions):
        from ui_qt.blacklist_preview_window import BlacklistPreviewWindow
        w = BlacklistPreviewWindow(qt_master, mock_app_actions)
        process_events_for(0.1)
        w.close()
        qapp.processEvents()
        assert BlacklistPreviewWindow.top_level is None
