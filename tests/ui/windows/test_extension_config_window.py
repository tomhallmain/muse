"""Extension config window: settings round-trip through `config`."""

import pytest

from tests.utils.qt_test_helpers import process_events_for
from utils.translations import I18N

_ = I18N._


@pytest.fixture
def extension_config_window(qt_master, mock_app_actions, monkeypatch):
    from ui_qt.extensions_window import ExtensionConfigWindow
    from utils.config import config

    saved = []
    monkeypatch.setattr(config, "save_config", lambda: saved.append(True) or True)

    win = ExtensionConfigWindow(qt_master, mock_app_actions)
    process_events_for(0.2)
    yield win, config, saved
    win.close()


class TestExtensionConfigWindowFields:
    def test_opens_showing_current_values(self, qapp, extension_config_window, monkeypatch):
        win, config, _saved = extension_config_window

        assert win.isVisible()
        low, high = config.get_int_range("extension_track_duration_seconds", 120, -1)
        min_entry, max_entry = win._range_entries["extension_track_duration_seconds"]
        assert (min_entry.text(), max_entry.text()) == (str(low), str(high))
        assert win._checkboxes["extension_allow_emoji_titles"].isChecked() == bool(
            config.get_config_value("extension_allow_emoji_titles")
        )

    def test_every_declared_field_has_a_widget(self, qapp, extension_config_window):
        """Guards against a config key being listed but never rendered."""
        win, _config, _saved = extension_config_window

        for key, _label in win.BOOL_FIELDS:
            assert key in win._checkboxes
        for key, _label in win.INT_FIELDS:
            assert key in win._entries
        for key, _label, _defaults in win.RANGE_FIELDS:
            assert key in win._range_entries

    def test_holds_the_checkboxes_moved_out_of_the_general_tab(self, qapp, extension_config_window):
        win, _config, _saved = extension_config_window

        for key in ("enable_library_extender", "auto_file_extensions", "embed_extension_artwork"):
            assert key in win._checkboxes


class TestExtensionConfigWindowSave:
    def test_edits_reach_config(self, qapp, extension_config_window):
        win, config, saved = extension_config_window
        _min_entry, max_entry = win._range_entries["extension_track_duration_seconds"]
        max_entry.setText("900")
        win._checkboxes["extension_enable_llm_scoring"].setChecked(False)

        win._save()

        assert config.get_int_range("extension_track_duration_seconds", 120, -1)[1] == 900
        assert config.get_config_value("extension_enable_llm_scoring") is False
        assert saved == [True]

    def test_range_is_stored_as_one_key_holding_numbers(self, qapp, extension_config_window):
        """Both halves live under a single key, and as ints -- not entry text."""
        win, config, _saved = extension_config_window
        min_entry, max_entry = win._range_entries["extension_cycle_wait_minutes"]
        min_entry.setText("30")
        max_entry.setText("40")

        win._save()

        assert config.get_config_value("extension_cycle_wait_minutes") == [30, 40]

    def test_unusable_entry_falls_back_to_the_default(self, qapp, extension_config_window):
        win, config, _saved = extension_config_window
        min_entry, _max_entry = win._range_entries["extension_cycle_wait_minutes"]
        min_entry.setText("not a number")

        win._save()

        assert config.get_config_value("extension_cycle_wait_minutes")[0] == 60

    def test_plain_int_entry_still_round_trips(self, qapp, extension_config_window):
        win, config, _saved = extension_config_window
        win._entries["extension_history_max_length"].setText("500")

        win._save()

        assert config.get_int("extension_history_max_length", 0) == 500


class TestAutoFileGenresEditor:
    def test_add_appends_a_genre(self, qapp, extension_config_window):
        win, _config, _saved = extension_config_window
        before = win._genre_list.count()

        win._genre_entry.setText("Baroque")
        win._add_genre()

        assert win._genre_list.count() == before + 1
        assert "Baroque" in win._genres()
        assert win._genre_entry.text() == ""

    def test_duplicate_is_ignored(self, qapp, extension_config_window):
        win, _config, _saved = extension_config_window
        win._genre_entry.setText("Baroque")
        win._add_genre()
        count = win._genre_list.count()

        win._genre_entry.setText("Baroque")
        win._add_genre()

        assert win._genre_list.count() == count

    def test_blank_entry_is_ignored(self, qapp, extension_config_window):
        win, _config, _saved = extension_config_window
        before = win._genre_list.count()

        win._genre_entry.setText("   ")
        win._add_genre()

        assert win._genre_list.count() == before

    def test_remove_selected_drops_it(self, qapp, extension_config_window):
        win, _config, _saved = extension_config_window
        win._genre_entry.setText("Baroque")
        win._add_genre()
        win._genre_list.setCurrentRow(win._genre_list.count() - 1)

        win._remove_genre()

        assert "Baroque" not in win._genres()

    def test_genres_reach_config_on_save(self, qapp, extension_config_window):
        """The only editor for auto_file_extensions_genres; it had none before."""
        win, config, _saved = extension_config_window
        win._genre_entry.setText("Baroque")
        win._add_genre()

        win._save()

        assert "Baroque" in config.get_config_value("auto_file_extensions_genres")
