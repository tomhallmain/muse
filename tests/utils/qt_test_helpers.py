"""Qt / PySide6 helpers for automated UI tests.

Provides event-loop utilities, preview-widget reading, application boot,
search-window automation, and playback-wait helpers.

All functions in this module require a ``QApplication`` to exist.
"""

import time
from typing import Optional

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt


# ── Event loop ──────────────────────────────────────────────────────────

def process_events_for(seconds: float):
    """Keep the Qt event loop alive for *seconds*, processing events every 100 ms."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.1)


# ── Preview widget reading ──────────────────────────────────────────────

def read_preview_items(playlist_window) -> list[tuple[str, bool]]:
    """Return ``[(text, is_highlighted), ...]`` for every item in
    *playlist_window._preview_list*."""
    items = []
    for i in range(playlist_window._preview_list.count()):
        item = playlist_window._preview_list.item(i)
        bg = item.background().color()
        highlighted = bg.alpha() > 0
        items.append((item.text(), highlighted))
    return items


def dump_preview(items: list[tuple[str, bool]], label: str = "Preview"):
    """Pretty-print a list returned by :func:`read_preview_items`."""
    print(f"\n{'─'*100}")
    print(f"  {label}  ({len(items)} rows)")
    print(f"{'─'*100}")
    for i, (text, hl) in enumerate(items):
        marker = " ★" if hl else ""
        print(f"  {i:>3}. {text}{marker}")


def find_highlighted(items: list[tuple[str, bool]]) -> int:
    """Return the row index of the highlighted item, or -1."""
    for i, (_, hl) in enumerate(items):
        if hl:
            return i
    return -1


# ── Application boot ───────────────────────────────────────────────────

def boot_app():
    """Create, show and return a ``MuseAppQt`` window with volume at 0.

    Returns the window instance.  The caller is responsible for closing it.
    """
    from app_qt import MuseAppQt

    print("=== Booting application ===")
    window = MuseAppQt()
    window.resize(1200, 700)
    window.restore_window_geometry()
    window.show()
    process_events_for(3)
    print("  Application started.")

    print("\n=== Setting volume to 0 ===")
    window.volume_slider.setValue(0)
    window.set_volume()
    process_events_for(1)
    print(f"  Volume slider value: {window.volume_slider.value()}")

    return window


# ── Search automation ──────────────────────────────────────────────────

def open_search_and_query(window, field: str, query: str,
                          search_wait: float = 15.0):
    """Open the search window, type *query* into *field*, click Search and
    wait for results.

    *field* must be one of ``"album"``, ``"artist"``, ``"composer"``,
    ``"title"``, ``"all"``, ``"genre"``, ``"instrument"``, ``"form"``.

    Returns ``(search_window, results_list)``.
    """
    from ui_qt.search_window import SearchWindow

    print(f"\n=== Opening search window ===")
    window.open_search_window()
    process_events_for(2)
    search_win = SearchWindow.top_level
    assert search_win is not None, "SearchWindow did not open"
    print("  Search window opened.")

    entry_widget = getattr(search_win, f"{field}_entry", None)
    assert entry_widget is not None, f"No entry widget for field '{field}'"

    print(f"\n=== Searching for '{query}' in {field} field ===")
    entry_widget.clear()
    QTest.keyClicks(entry_widget, query)
    process_events_for(1)
    print(f"  {field} field text: '{entry_widget.text()}'")

    print("  Clicking Search button...")
    QTest.mouseClick(search_win.search_btn, Qt.MouseButton.LeftButton)
    process_events_for(1)

    print(f"  Waiting up to {search_wait}s for search results...")
    deadline = time.time() + search_wait
    while time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.5)
        if (search_win.library_data_search is not None
                and len(search_win.library_data_search.get_results()) > 0
                and len(search_win.title_list) > 1):
            break

    assert search_win.library_data_search is not None, "No search was created"
    results = search_win.library_data_search.get_results()
    print(f"  Search returned {len(results)} results")
    assert len(results) > 0, "Search returned no results"

    return search_win, results


def click_play_on_result(search_win, index: int = 0):
    """Click the Play button for result at *index* (0-based)."""
    assert len(search_win.play_btn_list) > index, (
        f"Only {len(search_win.play_btn_list)} play buttons, need index {index}"
    )
    print(f"\n=== Clicking Play on result #{index} ===")
    btn = search_win.play_btn_list[index]
    QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
    process_events_for(2)
    print("  Play button clicked.")


# ── Playback waiting ──────────────────────────────────────────────────

def wait_for_playback(timeout: float = 15.0,
                      extra_settle: float = 5.0) -> object:
    """Block (processing events) until ``PlaybackStateManager`` reports at
    least one played track.  Returns the active config.

    Raises ``AssertionError`` if playback does not start within *timeout*
    seconds (plus an optional *extra_settle* grace period).
    """
    from muse.playback_state import PlaybackStateManager

    print(f"\n=== Waiting up to {timeout}s for playback to start ===")
    deadline = time.time() + timeout
    started = False
    while time.time() < deadline:
        QApplication.processEvents()
        time.sleep(1)
        active = PlaybackStateManager.get_active_config()
        if active and hasattr(active, 'played_tracks') and active.played_tracks:
            started = True
            print(f"  Playback active! {len(active.played_tracks)} track(s) played.")
            break

    if not started:
        print("  WARNING: Playback not detected yet, giving extra time...")
        process_events_for(extra_settle)
        active = PlaybackStateManager.get_active_config()
        if active and hasattr(active, 'played_tracks') and active.played_tracks:
            started = True
            print(f"  Playback confirmed: {len(active.played_tracks)} track(s) played.")

    assert started, "Playback did not start"

    if extra_settle > 0:
        print(f"  Waiting {extra_settle}s for playback to settle...")
        process_events_for(extra_settle)

    return PlaybackStateManager.get_active_config()


def wait_for_track_change(played_count_before: int,
                          max_wait: float = 600.0):
    """Block until ``played_tracks`` grows beyond *played_count_before*.

    Returns ``True`` if a track change was detected, ``False`` on timeout.
    Prints progress every 30 s.
    """
    from muse.playback_state import PlaybackStateManager

    print(f"  Waiting for track change (current played count: {played_count_before})...")
    start = time.time()
    deadline = start + max_wait
    while time.time() < deadline:
        QApplication.processEvents()
        time.sleep(1)
        active = PlaybackStateManager.get_active_config()
        if active and len(active.played_tracks) > played_count_before:
            new_count = len(active.played_tracks)
            new_track = active.played_tracks[-1]
            print(f"  Track changed! played_tracks: {played_count_before} -> {new_count}")
            print(f"  New current track: {getattr(new_track, 'title', '?')[:60]}")
            return True
        elapsed = int(time.time() - start)
        if elapsed > 0 and elapsed % 30 == 0:
            print(f"  Still waiting... ({elapsed}s elapsed)")

    print(f"  Timeout: no track change within {max_wait}s")
    return False


# ── Playlist window ───────────────────────────────────────────────────

def open_playlist_window(window):
    """Open (or re-focus) the MasterPlaylistWindow and return it."""
    from ui_qt.playlist_window import MasterPlaylistWindow

    print(f"\n=== Opening playlist window ===")
    window.open_playlist_window()
    process_events_for(3)
    pw = MasterPlaylistWindow.top_level
    assert pw is not None, "Playlist window did not open"
    print("  Playlist window opened.")
    return pw
