"""Disable multi-monitor Qt positioning during tests.

``QWidget.screen()`` and related APIs can trigger Windows heap corruption
(0xc0000374) under ``QT_QPA_PLATFORM=offscreen``, especially with saved
geometry on a disconnected monitor. Tests only need windows to construct.
"""

from __future__ import annotations

from PySide6.QtCore import QRect


def safe_position_window_on_same_display(
    parent_window,
    new_window,
    offset_x=50,
    offset_y=50,
    center=False,
    center_relative_to=None,
    geometry=None,
    **_kwargs,
):
    """Place *new_window* near *parent_window* without querying screens."""
    try:
        if geometry and "x" in geometry:
            size_part = geometry.split("+")[0]
            width, height = map(int, size_part.split("x"))
        elif geometry:
            width, height = map(int, geometry.split("x"))
        else:
            width = new_window.width() if new_window.width() > 0 else 400
            height = new_window.height() if new_window.height() > 0 else 300

        anchor = center_relative_to if (center and center_relative_to is not None) else parent_window
        parent_x = max(0, anchor.x())
        parent_y = max(0, anchor.y())

        if center:
            anchor_w = anchor.width() if anchor.width() > 0 else width
            anchor_h = anchor.height() if anchor.height() > 0 else height
            new_x = parent_x + (anchor_w - width) // 2
            new_y = parent_y + (anchor_h - height) // 2
        else:
            new_x = parent_x + offset_x
            new_y = parent_y + offset_y

        rect = QRect(new_x, new_y, width, height)
        new_window.setGeometry(rect)
        return rect
    except Exception:
        rect = QRect(0, 0, 400, 300)
        try:
            new_window.setGeometry(rect)
        except Exception:
            pass
        return rect


def safe_get_window_display_info(window):
    return {
        "display_index": 0,
        "is_primary": True,
        "bounds": (0, 0, 1920, 1080),
        "window_position": (max(0, window.x()), max(0, window.y())),
    }


def install_display_position_bypass(monkeypatch) -> None:
    """Patch the global ``display_manager`` used by ``SmartWindow``."""
    monkeypatch.setattr(
        "lib.multi_display_qt.display_manager.position_window_on_same_display",
        safe_position_window_on_same_display,
    )
    monkeypatch.setattr(
        "lib.multi_display_qt.display_manager.get_window_display_info",
        safe_get_window_display_info,
    )
    monkeypatch.setattr(
        "lib.multi_display_qt.display_manager.is_window_on_primary_display",
        lambda _window: True,
    )
