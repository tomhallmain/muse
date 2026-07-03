"""
UI tests for ConfigurationWindow — Playlist Options and General tabs.

Covers the exclusion-filter list widget: loading from app_info_cache,
adding entries (button and Return key), duplicate/empty-string guards,
removing selected entries, and saving back to app_info_cache.

Also covers the General tab's Language Learning list widget (loading
from config.muse_language_learning_languages, add/remove, save), and
contains a signal-bridge regression test: verifies that a signal-based
toast implementation delivers the slot call on the main thread even
when toast() is called from a background thread.
"""
import importlib
import threading
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from muse.playlist import TRACK_EXCLUSIONS_KEY, _DEFAULT_TRACK_EXCLUSIONS
from tests.utils.qt_test_helpers import process_events_for
from utils.translations import I18N

_ = I18N._


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _open_window(qt_master, mock_app_actions):
    from ui_qt.configuration_window import ConfigurationWindow
    win = ConfigurationWindow(qt_master, mock_app_actions)
    process_events_for(0.1)
    return win


def _switch_to_playlist_options(win):
    notebook = win.notebook
    for i in range(notebook.count()):
        if _("Playlist Options") in notebook.tabText(i):
            notebook.setCurrentIndex(i)
            QApplication.processEvents()
            return
    raise AssertionError("Playlist Options tab not found")


def _switch_to_general(win):
    notebook = win.notebook
    for i in range(notebook.count()):
        if _("General") in notebook.tabText(i):
            notebook.setCurrentIndex(i)
            QApplication.processEvents()
            return
    raise AssertionError("General tab not found")


def _close_clean(win):
    """Close the window without triggering the unsaved-changes dialog."""
    import importlib
    cfg_mod = importlib.import_module("utils.config")
    cfg_mod.config.clear_changes()
    win.close()
    QApplication.processEvents()


# ---------------------------------------------------------------------------
# Playlist Options tab — loading
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestPlaylistOptionsTabLoading:
    def test_tab_exists(self, qapp, qt_master, mock_app_actions):
        win = _open_window(qt_master, mock_app_actions)
        labels = [win.notebook.tabText(i) for i in range(win.notebook.count())]
        assert any(_("Playlist Options") in t for t in labels)
        _close_clean(win)

    def test_default_exclusions_loaded_on_open(self, qapp, qt_master, mock_app_actions):
        from utils.app_info_cache import app_info_cache
        app_info_cache.set(TRACK_EXCLUSIONS_KEY, list(_DEFAULT_TRACK_EXCLUSIONS))
        win = _open_window(qt_master, mock_app_actions)
        _switch_to_playlist_options(win)
        items = [win._exclusions_list.item(i).text()
                 for i in range(win._exclusions_list.count())]
        assert items == list(_DEFAULT_TRACK_EXCLUSIONS)
        _close_clean(win)

    def test_custom_exclusions_loaded_on_open(self, qapp, qt_master, mock_app_actions):
        from utils.app_info_cache import app_info_cache
        app_info_cache.set(TRACK_EXCLUSIONS_KEY, ["JINGLE", "ADVERT"])
        win = _open_window(qt_master, mock_app_actions)
        _switch_to_playlist_options(win)
        items = [win._exclusions_list.item(i).text()
                 for i in range(win._exclusions_list.count())]
        assert items == ["JINGLE", "ADVERT"]
        _close_clean(win)

    def test_empty_cache_shows_empty_list(self, qapp, qt_master, mock_app_actions):
        from utils.app_info_cache import app_info_cache
        app_info_cache.set(TRACK_EXCLUSIONS_KEY, [])
        win = _open_window(qt_master, mock_app_actions)
        _switch_to_playlist_options(win)
        assert win._exclusions_list.count() == 0
        _close_clean(win)


# ---------------------------------------------------------------------------
# Playlist Options tab — add
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestPlaylistOptionsTabAdd:
    def test_add_via_button(self, qapp, qt_master, mock_app_actions):
        from utils.app_info_cache import app_info_cache
        app_info_cache.set(TRACK_EXCLUSIONS_KEY, [])
        win = _open_window(qt_master, mock_app_actions)
        _switch_to_playlist_options(win)

        win._exclusion_entry.setText("PROMO")
        win._add_exclusion()
        QApplication.processEvents()

        items = [win._exclusions_list.item(i).text()
                 for i in range(win._exclusions_list.count())]
        assert "PROMO" in items
        _close_clean(win)

    def test_add_via_return_key(self, qapp, qt_master, mock_app_actions):
        from utils.app_info_cache import app_info_cache
        app_info_cache.set(TRACK_EXCLUSIONS_KEY, [])
        win = _open_window(qt_master, mock_app_actions)
        _switch_to_playlist_options(win)

        win._exclusion_entry.setText("JINGLE")
        QTest.keyClick(win._exclusion_entry, Qt.Key.Key_Return)
        QApplication.processEvents()

        items = [win._exclusions_list.item(i).text()
                 for i in range(win._exclusions_list.count())]
        assert "JINGLE" in items
        _close_clean(win)

    def test_entry_cleared_after_add(self, qapp, qt_master, mock_app_actions):
        from utils.app_info_cache import app_info_cache
        app_info_cache.set(TRACK_EXCLUSIONS_KEY, [])
        win = _open_window(qt_master, mock_app_actions)
        _switch_to_playlist_options(win)

        win._exclusion_entry.setText("PROMO")
        win._add_exclusion()

        assert win._exclusion_entry.text() == ""
        _close_clean(win)

    def test_duplicate_not_added(self, qapp, qt_master, mock_app_actions):
        from utils.app_info_cache import app_info_cache
        app_info_cache.set(TRACK_EXCLUSIONS_KEY, ["TTS"])
        win = _open_window(qt_master, mock_app_actions)
        _switch_to_playlist_options(win)

        win._exclusion_entry.setText("TTS")
        win._add_exclusion()

        assert win._exclusions_list.count() == 1
        _close_clean(win)

    def test_empty_string_not_added(self, qapp, qt_master, mock_app_actions):
        from utils.app_info_cache import app_info_cache
        app_info_cache.set(TRACK_EXCLUSIONS_KEY, [])
        win = _open_window(qt_master, mock_app_actions)
        _switch_to_playlist_options(win)

        win._exclusion_entry.setText("   ")
        win._add_exclusion()

        assert win._exclusions_list.count() == 0
        _close_clean(win)


# ---------------------------------------------------------------------------
# Playlist Options tab — remove
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestPlaylistOptionsTabRemove:
    def test_remove_selected_entry(self, qapp, qt_master, mock_app_actions):
        from utils.app_info_cache import app_info_cache
        app_info_cache.set(TRACK_EXCLUSIONS_KEY, ["TTS", "JINGLE"])
        win = _open_window(qt_master, mock_app_actions)
        _switch_to_playlist_options(win)

        win._exclusions_list.setCurrentRow(0)
        win._remove_exclusion()
        QApplication.processEvents()

        items = [win._exclusions_list.item(i).text()
                 for i in range(win._exclusions_list.count())]
        assert "TTS" not in items
        assert "JINGLE" in items
        _close_clean(win)

    def test_remove_with_nothing_selected_is_safe(self, qapp, qt_master, mock_app_actions):
        from utils.app_info_cache import app_info_cache
        app_info_cache.set(TRACK_EXCLUSIONS_KEY, ["TTS"])
        win = _open_window(qt_master, mock_app_actions)
        _switch_to_playlist_options(win)

        win._exclusions_list.clearSelection()
        win._remove_exclusion()  # must not raise

        assert win._exclusions_list.count() == 1
        _close_clean(win)


# ---------------------------------------------------------------------------
# Playlist Options tab — save
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestPlaylistOptionsTabSave:
    def test_save_persists_exclusions_to_cache(self, qapp, qt_master, mock_app_actions, monkeypatch):
        from utils.app_info_cache import app_info_cache
        cfg_mod = importlib.import_module("utils.config")
        monkeypatch.setattr(cfg_mod.config, "save_config", lambda: True)

        app_info_cache.set(TRACK_EXCLUSIONS_KEY, [])
        win = _open_window(qt_master, mock_app_actions)
        _switch_to_playlist_options(win)

        win._exclusion_entry.setText("PROMO")
        win._add_exclusion()
        win._exclusion_entry.setText("JINGLE")
        win._add_exclusion()

        win.save_config()
        QApplication.processEvents()

        saved = app_info_cache.get(TRACK_EXCLUSIONS_KEY, [])
        assert "PROMO" in saved
        assert "JINGLE" in saved
        _close_clean(win)

    def test_save_with_empty_list_clears_cache(self, qapp, qt_master, mock_app_actions, monkeypatch):
        from utils.app_info_cache import app_info_cache
        cfg_mod = importlib.import_module("utils.config")
        monkeypatch.setattr(cfg_mod.config, "save_config", lambda: True)

        app_info_cache.set(TRACK_EXCLUSIONS_KEY, ["TTS"])
        win = _open_window(qt_master, mock_app_actions)
        _switch_to_playlist_options(win)

        win._exclusions_list.setCurrentRow(0)
        win._remove_exclusion()

        win.save_config()
        QApplication.processEvents()

        saved = app_info_cache.get(TRACK_EXCLUSIONS_KEY, ["sentinel"])
        assert saved == []
        _close_clean(win)

    def test_save_preserves_existing_entries_unchanged(self, qapp, qt_master, mock_app_actions, monkeypatch):
        """Saving without modifying the list must round-trip the existing entries."""
        from utils.app_info_cache import app_info_cache
        cfg_mod = importlib.import_module("utils.config")
        monkeypatch.setattr(cfg_mod.config, "save_config", lambda: True)

        app_info_cache.set(TRACK_EXCLUSIONS_KEY, ["TTS"])
        win = _open_window(qt_master, mock_app_actions)
        win.save_config()
        QApplication.processEvents()

        assert app_info_cache.get(TRACK_EXCLUSIONS_KEY) == ["TTS"]
        _close_clean(win)


# ---------------------------------------------------------------------------
# General tab — Language Learning list — loading
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestGeneralTabLanguageLearningLoading:
    def test_tab_exists(self, qapp, qt_master, mock_app_actions):
        win = _open_window(qt_master, mock_app_actions)
        labels = [win.notebook.tabText(i) for i in range(win.notebook.count())]
        assert any(_("General") in t for t in labels)
        _close_clean(win)

    def test_existing_languages_loaded_on_open(self, qapp, qt_master, mock_app_actions, monkeypatch):
        cfg_mod = importlib.import_module("utils.config")
        monkeypatch.setattr(cfg_mod.config, "muse_language_learning_languages", [
            {"language_code": "de", "level": "intermediate"},
            {"language_code": "fr", "level": "beginner"},
        ])
        win = _open_window(qt_master, mock_app_actions)
        _switch_to_general(win)
        items = [win._language_learning_list.item(i).text()
                 for i in range(win._language_learning_list.count())]
        assert items == ["de: intermediate", "fr: beginner"]
        _close_clean(win)

    def test_empty_list_shows_empty(self, qapp, qt_master, mock_app_actions, monkeypatch):
        cfg_mod = importlib.import_module("utils.config")
        monkeypatch.setattr(cfg_mod.config, "muse_language_learning_languages", [])
        win = _open_window(qt_master, mock_app_actions)
        _switch_to_general(win)
        assert win._language_learning_list.count() == 0
        _close_clean(win)


# ---------------------------------------------------------------------------
# General tab — Language Learning list — add
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestGeneralTabLanguageLearningAdd:
    def test_add_via_button(self, qapp, qt_master, mock_app_actions, monkeypatch):
        cfg_mod = importlib.import_module("utils.config")
        monkeypatch.setattr(cfg_mod.config, "muse_language_learning_languages", [])
        win = _open_window(qt_master, mock_app_actions)
        _switch_to_general(win)

        idx = win._language_learning_code_combo.findText("es")
        win._language_learning_code_combo.setCurrentIndex(idx)
        win._language_learning_level_entry.setText("beginner")
        win._add_language_learning_entry()
        QApplication.processEvents()

        items = [win._language_learning_list.item(i).text()
                 for i in range(win._language_learning_list.count())]
        assert "es: beginner" in items
        _close_clean(win)

    def test_default_level_when_blank(self, qapp, qt_master, mock_app_actions, monkeypatch):
        cfg_mod = importlib.import_module("utils.config")
        monkeypatch.setattr(cfg_mod.config, "muse_language_learning_languages", [])
        win = _open_window(qt_master, mock_app_actions)
        _switch_to_general(win)

        idx = win._language_learning_code_combo.findText("it")
        win._language_learning_code_combo.setCurrentIndex(idx)
        win._language_learning_level_entry.setText("")
        win._add_language_learning_entry()

        items = [win._language_learning_list.item(i).text()
                 for i in range(win._language_learning_list.count())]
        assert "it: intermediate" in items
        _close_clean(win)

    def test_duplicate_code_not_added(self, qapp, qt_master, mock_app_actions, monkeypatch):
        cfg_mod = importlib.import_module("utils.config")
        monkeypatch.setattr(cfg_mod.config, "muse_language_learning_languages", [
            {"language_code": "de", "level": "intermediate"},
        ])
        win = _open_window(qt_master, mock_app_actions)
        _switch_to_general(win)

        idx = win._language_learning_code_combo.findText("de")
        win._language_learning_code_combo.setCurrentIndex(idx)
        win._language_learning_level_entry.setText("advanced")
        win._add_language_learning_entry()

        assert win._language_learning_list.count() == 1
        _close_clean(win)


# ---------------------------------------------------------------------------
# General tab — Language Learning list — remove
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestGeneralTabLanguageLearningRemove:
    def test_remove_selected_entry(self, qapp, qt_master, mock_app_actions, monkeypatch):
        cfg_mod = importlib.import_module("utils.config")
        monkeypatch.setattr(cfg_mod.config, "muse_language_learning_languages", [
            {"language_code": "de", "level": "intermediate"},
            {"language_code": "fr", "level": "beginner"},
        ])
        win = _open_window(qt_master, mock_app_actions)
        _switch_to_general(win)

        win._language_learning_list.setCurrentRow(0)
        win._remove_language_learning_entry()
        QApplication.processEvents()

        items = [win._language_learning_list.item(i).text()
                 for i in range(win._language_learning_list.count())]
        assert "de: intermediate" not in items
        assert "fr: beginner" in items
        _close_clean(win)

    def test_remove_with_nothing_selected_is_safe(self, qapp, qt_master, mock_app_actions, monkeypatch):
        cfg_mod = importlib.import_module("utils.config")
        monkeypatch.setattr(cfg_mod.config, "muse_language_learning_languages", [
            {"language_code": "de", "level": "intermediate"},
        ])
        win = _open_window(qt_master, mock_app_actions)
        _switch_to_general(win)

        win._language_learning_list.clearSelection()
        win._remove_language_learning_entry()  # must not raise

        assert win._language_learning_list.count() == 1
        _close_clean(win)


# ---------------------------------------------------------------------------
# General tab — Language Learning list — save
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestGeneralTabLanguageLearningSave:
    def test_save_persists_languages_to_config(self, qapp, qt_master, mock_app_actions, monkeypatch):
        cfg_mod = importlib.import_module("utils.config")
        monkeypatch.setattr(cfg_mod.config, "muse_language_learning_languages", [])
        monkeypatch.setattr(cfg_mod.config, "save_config", lambda: True)
        win = _open_window(qt_master, mock_app_actions)
        _switch_to_general(win)

        idx = win._language_learning_code_combo.findText("de")
        win._language_learning_code_combo.setCurrentIndex(idx)
        win._language_learning_level_entry.setText("intermediate")
        win._add_language_learning_entry()

        win.save_config()
        QApplication.processEvents()

        assert cfg_mod.config.muse_language_learning_languages == [
            {"language_code": "de", "level": "intermediate"},
        ]
        _close_clean(win)

    def test_save_with_empty_list_disables_feature(self, qapp, qt_master, mock_app_actions, monkeypatch):
        cfg_mod = importlib.import_module("utils.config")
        monkeypatch.setattr(cfg_mod.config, "muse_language_learning_languages", [
            {"language_code": "de", "level": "intermediate"},
        ])
        monkeypatch.setattr(cfg_mod.config, "save_config", lambda: True)
        win = _open_window(qt_master, mock_app_actions)
        _switch_to_general(win)

        win._language_learning_list.setCurrentRow(0)
        win._remove_language_learning_entry()

        win.save_config()
        QApplication.processEvents()

        assert cfg_mod.config.muse_language_learning_languages == []
        _close_clean(win)


# ---------------------------------------------------------------------------
# Signal-bridge regression: toast slot runs on the main thread
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestToastSignalBridgeMainThread:
    """
    Verify that a signal-based toast implementation (the fix applied to
    MuseAppQt.toast) delivers the _do_toast slot on the main thread even
    when toast() is called from a background thread.

    Without the bridge, creating a QMessageBox directly from a background
    thread raises:
        QObject::setParent: Cannot set parent, new parent is in a different thread
    """

    def test_slot_runs_on_main_thread_when_called_from_worker(self, qapp):
        from PySide6.QtCore import QObject, Signal

        class ToastBridge(QObject):
            _sig = Signal(str)

            def __init__(self):
                super().__init__()
                self.received: list = []
                self.slot_threads: list = []
                self._sig.connect(self._on_toast)

            def toast(self, message: str) -> None:
                self._sig.emit(message)

            def _on_toast(self, message: str) -> None:
                self.received.append(message)
                self.slot_threads.append(threading.current_thread())

        bridge = ToastBridge()
        errors: list = []

        def worker():
            try:
                bridge.toast("3 track(s) excluded from playlist by filters")
            except Exception as exc:
                errors.append(exc)

        t = threading.Thread(target=worker, name="playback-worker")
        t.start()
        t.join(timeout=5.0)
        QApplication.processEvents()

        assert not errors, f"toast() raised from background thread: {errors}"
        assert len(bridge.received) == 1
        assert "3" in bridge.received[0]
        assert bridge.slot_threads[0] is threading.main_thread(), (
            "_on_toast (the slot) must execute on the main thread"
        )
