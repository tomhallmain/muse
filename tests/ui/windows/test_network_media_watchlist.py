"""Watch-list tab of the Network Media window: discovery entries."""

import pytest

from tests.utils.qt_test_helpers import process_events_for


@pytest.fixture(autouse=True)
def empty_watchlist():
    from muse.radio_watchlist import save_entries
    save_entries([])
    yield
    save_entries([])


def _window(qt_master, mock_app_actions):
    from ui_qt.network_media_window import NetworkMediaWindow
    window = NetworkMediaWindow(qt_master, mock_app_actions)
    process_events_for(0.2)
    window._tabs.setCurrentIndex(2)
    process_events_for(0.1)
    return window


@pytest.mark.ui
class TestWatchlistDiscovery:
    def test_discovery_mode_swaps_the_match_fields_for_the_classical_setting(
        self, qapp, qt_master, mock_app_actions
    ):
        from muse.radio_watchlist import MODE_NOVEL

        window = _window(qt_master, mock_app_actions)
        assert window._watch_match_rows.isVisible()
        assert not window._watch_classical_row.isVisible()

        window._watch_mode_combo.setCurrentIndex(window._watch_mode_combo.findData(MODE_NOVEL))
        assert not window._watch_match_rows.isVisible()
        assert window._watch_classical_row.isVisible()
        window.close()

    def test_adding_a_discovery_entry_stores_its_mode_and_classical_setting(
        self, qapp, qt_master, mock_app_actions
    ):
        from muse.radio_watchlist import MODE_NOVEL, load_entries

        window = _window(qt_master, mock_app_actions)
        window._watch_uuid_entry.setText("uuid-1")
        window._watch_label_entry.setText("Discover on Radio One")
        window._watch_artist_entry.setText("left over from match mode")
        window._watch_mode_combo.setCurrentIndex(window._watch_mode_combo.findData(MODE_NOVEL))
        window._watch_classical_combo.setCurrentIndex(window._watch_classical_combo.findData("yes"))
        window._add_watch_entry()

        entries = load_entries()
        assert len(entries) == 1
        entry = entries[0]
        assert (entry.mode, entry.classical, entry.match_artist) == (MODE_NOVEL, "yes", "")
        assert entry.is_active()
        window.close()
