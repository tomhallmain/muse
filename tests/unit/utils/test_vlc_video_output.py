"""Tests for utils.vlc_video_output.set_video_output_window."""

from unittest.mock import MagicMock

import pytest

from utils import vlc_video_output
from utils.vlc_video_output import set_video_output_window


@pytest.mark.parametrize("system, call", [
    ("Windows", "set_hwnd"),
    ("Darwin", "set_nsobject"),
    ("Linux", "set_xwindow"),
])
def test_uses_the_call_for_the_os(monkeypatch, system, call):
    monkeypatch.setattr(vlc_video_output.platform, "system", lambda: system)
    player = MagicMock()
    assert set_video_output_window(player, 1234) is True
    getattr(player, call).assert_called_once_with(1234)
    for other in {"set_hwnd", "set_nsobject", "set_xwindow"} - {call}:
        getattr(player, other).assert_not_called()


@pytest.mark.parametrize("handle", [None, 0])
def test_no_handle_sets_nothing(handle):
    player = MagicMock()
    assert set_video_output_window(player, handle) is False
    player.set_hwnd.assert_not_called()
    player.set_nsobject.assert_not_called()
    player.set_xwindow.assert_not_called()


def test_no_player_sets_nothing():
    assert set_video_output_window(None, 1234) is False
