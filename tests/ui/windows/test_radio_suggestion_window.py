"""Radio suggestion popup tests."""

import pytest

from tests.utils.qt_test_helpers import process_events_for
from utils.translations import I18N

_ = I18N._


def _suggestion(uuid="st-1", artist="New Band", title="New Song", signals=("new_artist",)):
    from muse.radio_novelty import Suggestion
    return Suggestion(uuid, "Radio Example", artist, title, f"{artist} - {title}".lower(),
                      list(signals), 1.0)


@pytest.fixture(autouse=True)
def reset_window():
    from ui_qt.radio_suggestion_window import RadioSuggestionWindow
    RadioSuggestionWindow.top_level = None
    yield
    if RadioSuggestionWindow.top_level is not None:
        RadioSuggestionWindow.top_level.close()
    RadioSuggestionWindow.top_level = None


@pytest.mark.ui
class TestRadioSuggestionWindow:
    def test_suggestions_share_one_window(self, qapp, qt_master, mock_app_actions):
        from ui_qt.radio_suggestion_window import RadioSuggestionWindow

        RadioSuggestionWindow.show_suggestion(qt_master, mock_app_actions, _suggestion())
        first = RadioSuggestionWindow.top_level
        RadioSuggestionWindow.show_suggestion(qt_master, mock_app_actions, _suggestion(uuid="st-2"))
        process_events_for(0.2)

        assert RadioSuggestionWindow.top_level is first
        assert len(first._rows) == 2
        assert first.isVisible()

    def test_the_reasons_are_shown_translated(self, qapp, qt_master, mock_app_actions):
        from ui_qt.radio_suggestion_window import RadioSuggestionWindow

        RadioSuggestionWindow.show_suggestion(
            qt_master, mock_app_actions, _suggestion(signals=("new_composer", "new_to_station")))
        row = next(iter(RadioSuggestionWindow.top_level._rows.values()))
        text = row.widgets[0].text()
        assert _("new composer") in text and _("new to this station") in text

    def test_moving_on_disables_switch_for_that_station_only(self, qapp, qt_master, mock_app_actions):
        from ui_qt.radio_suggestion_window import RadioSuggestionWindow

        RadioSuggestionWindow.show_suggestion(qt_master, mock_app_actions, _suggestion(uuid="st-1"))
        RadioSuggestionWindow.show_suggestion(qt_master, mock_app_actions, _suggestion(uuid="st-2"))
        RadioSuggestionWindow.station_title_changed("st-1")

        rows = {r.suggestion.station_uuid: r for r in RadioSuggestionWindow.top_level._rows.values()}
        assert not rows["st-1"].switch_btn.isEnabled()
        assert rows["st-2"].switch_btn.isEnabled()

    def test_switch_hands_the_suggestion_to_the_service(self, qapp, qt_master, mock_app_actions, monkeypatch):
        from muse.radio_watchlist import watchlist_service
        from ui_qt.radio_suggestion_window import RadioSuggestionWindow

        switched = []
        monkeypatch.setattr(watchlist_service, "switch_to_suggestion", switched.append)
        suggestion = _suggestion()
        RadioSuggestionWindow.show_suggestion(qt_master, mock_app_actions, suggestion)
        window = RadioSuggestionWindow.top_level
        next(iter(window._rows.values())).switch_btn.click()
        process_events_for(0.2)

        assert switched == [suggestion]
        assert RadioSuggestionWindow.top_level is None, "the last suggestion gone closes the window"

    def test_dismiss_removes_only_that_suggestion(self, qapp, qt_master, mock_app_actions):
        from ui_qt.radio_suggestion_window import RadioSuggestionWindow

        RadioSuggestionWindow.show_suggestion(qt_master, mock_app_actions, _suggestion(uuid="st-1"))
        RadioSuggestionWindow.show_suggestion(qt_master, mock_app_actions, _suggestion(uuid="st-2"))
        window = RadioSuggestionWindow.top_level
        first_row = min(window._rows)
        window._rows[first_row].widgets[2].click()

        assert [r.suggestion.station_uuid for r in window._rows.values()] == ["st-2"]
        assert RadioSuggestionWindow.top_level is window
