"""Delete Track / Delete Album flows in the track details window.

The confirmation dialog is intercepted via ``_ask_confirmation`` rather than a
real modal, so the tests never block on ``QMessageBox.exec``.
"""

import os

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton

from tests.utils.qt_test_helpers import process_events_for
from utils.translations import I18N

_ = I18N._


def _record_action(app_actions, name, return_value=True):
    """Replace one AppActions callback with a recorder. Returns the call list."""
    calls = []

    def recorder(*args, **kwargs):
        calls.append(args[0] if args else None)
        return return_value

    app_actions._actions[name] = recorder
    return calls


def _stub_confirmation(window, answer):
    """Answer the confirm dialog without showing it; capture the prompts shown."""
    prompts = []

    def fake_ask(title, text, warn=False):
        prompts.append(text)
        return answer

    window._ask_confirmation = fake_ask
    return prompts


def _button_labelled(window, label):
    for btn in window.findChildren(QPushButton):
        if btn.text() == label:
            return btn
    return None


@pytest.fixture
def details_window(qt_master, mock_app_actions, audio_library_media_tracks):
    from ui_qt.track_details_window import TrackDetailsWindow

    track = audio_library_media_tracks[0]
    win = TrackDetailsWindow(qt_master, mock_app_actions, track)
    process_events_for(0.2)
    yield win, track, mock_app_actions
    win.close()


@pytest.mark.ui
class TestDeleteButtonsPresent:
    def test_both_delete_buttons_are_shown(self, details_window):
        win, _track, _actions = details_window
        assert _button_labelled(win, _("Delete Track")) is not None
        assert _button_labelled(win, _("Delete Album")) is not None

    def test_album_group_names_the_folder_that_would_go(self, details_window):
        """The blast radius must be visible before the user clicks."""
        win, track, _actions = details_window
        assert win._delete_album_target_label.text() == os.path.dirname(track.filepath)


@pytest.mark.ui
class TestDeleteTrackFlow:
    def test_confirming_deletes_the_track_file(self, details_window):
        win, track, actions = details_window
        calls = _record_action(actions, "delete_track")
        _stub_confirmation(win, True)

        QTest.mouseClick(_button_labelled(win, _("Delete Track")), Qt.MouseButton.LeftButton)
        process_events_for(0.2)

        assert calls == [track.filepath]

    def test_cancelling_deletes_nothing(self, details_window):
        win, _track, actions = details_window
        calls = _record_action(actions, "delete_track")
        _stub_confirmation(win, False)

        QTest.mouseClick(_button_labelled(win, _("Delete Track")), Qt.MouseButton.LeftButton)
        process_events_for(0.2)

        assert calls == []

    def test_prompt_names_the_file(self, details_window):
        win, track, actions = details_window
        _record_action(actions, "delete_track")
        prompts = _stub_confirmation(win, True)

        win._confirm_delete_track()

        assert track.filepath in prompts[0]

    def test_window_stays_open_when_deletion_fails(self, details_window):
        """A failed delete must not close the window and imply success."""
        win, _track, actions = details_window
        _record_action(actions, "delete_track", return_value=False)
        _stub_confirmation(win, True)

        win._confirm_delete_track()
        process_events_for(0.2)

        assert win.isVisible()


@pytest.mark.ui
class TestDeleteAlbumFlow:
    def test_confirming_deletes_the_containing_folder(self, details_window):
        win, track, actions = details_window
        calls = _record_action(actions, "delete_album")
        _stub_confirmation(win, True)

        QTest.mouseClick(_button_labelled(win, _("Delete Album")), Qt.MouseButton.LeftButton)
        process_events_for(0.2)

        assert calls == [os.path.dirname(track.filepath)]

    def test_cancelling_deletes_nothing(self, details_window):
        win, _track, actions = details_window
        calls = _record_action(actions, "delete_album")
        _stub_confirmation(win, False)

        QTest.mouseClick(_button_labelled(win, _("Delete Album")), Qt.MouseButton.LeftButton)
        process_events_for(0.2)

        assert calls == []

    def test_prompt_names_the_folder_and_counts_its_files(self, details_window):
        win, track, actions = details_window
        _record_action(actions, "delete_album")
        prompts = _stub_confirmation(win, True)
        album_dir = os.path.dirname(track.filepath)
        expected_count = sum(len(files) for _r, _d, files in os.walk(album_dir))

        win._confirm_delete_album()

        assert album_dir in prompts[0]
        assert str(expected_count) in prompts[0]

    def test_album_delete_does_not_call_track_delete(self, details_window):
        """Guard against the two buttons being cross-wired."""
        win, _track, actions = details_window
        track_calls = _record_action(actions, "delete_track")
        album_calls = _record_action(actions, "delete_album")
        _stub_confirmation(win, True)

        win._confirm_delete_album()

        assert track_calls == []
        assert len(album_calls) == 1

    def test_window_stays_open_when_deletion_fails(self, details_window):
        win, _track, actions = details_window
        _record_action(actions, "delete_album", return_value=False)
        _stub_confirmation(win, True)

        win._confirm_delete_album()
        process_events_for(0.2)

        assert win.isVisible()
