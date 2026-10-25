"""Pointing a VLC media player's video output at a Qt widget's native window."""

import platform

from utils.logging_setup import get_logger

logger = get_logger(__name__)


def set_video_output_window(media_player, window_handle) -> bool:
    """Render *media_player*'s video into the native window *window_handle*
    (QWidget.winId()). Returns whether a window was set.

    Each OS takes the handle through a different call, and the wrong one is not
    an error: on macOS, set_xwindow leaves VLC with no NSView to draw into, so
    video tracks show nothing.
    """
    if media_player is None or not window_handle:
        return False
    handle = int(window_handle)
    system = platform.system()
    if system == "Windows":
        media_player.set_hwnd(handle)
    elif system == "Darwin":
        media_player.set_nsobject(handle)
    else:
        media_player.set_xwindow(handle)
    return True
