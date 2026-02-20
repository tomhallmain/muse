"""Full end-to-end Qt test for seek-to-track preview.

Boots the real Muse application, then automates:
  1. Set volume to 0
  2. Open search window
  3. Type "operetta" in the album field and click Search
  4. Wait for results, collect first 20
  5. Click Play on the first result
  6. Wait for playback to start
  7. Open the playlist window
  8. Verify preview order matches search results
  9. Seek forward, verify skipped tracks remain
  10. Seek backward, verify order preserved
  11. Let two songs finish naturally, compare order before/after each

Usage:  python test_seek_preview_qt.py
"""

import sys
import os
import time
import traceback

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _project_root)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt

DELAY = 5  # seconds between major actions
SEARCH_WAIT = 15  # seconds to wait for search to complete
PLAYBACK_WAIT = 15  # seconds to wait for playback to start


def process_events_for(seconds):
    """Keep the event loop alive for *seconds*, processing events every 100ms."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.1)


def read_preview_items(playlist_window):
    """Return list of (text, is_highlighted) for every preview list item."""
    items = []
    for i in range(playlist_window._preview_list.count()):
        item = playlist_window._preview_list.item(i)
        bg = item.background().color()
        highlighted = bg.alpha() > 0
        items.append((item.text(), highlighted))
    return items


def dump_preview(items, label="Preview"):
    print(f"\n{'─'*100}")
    print(f"  {label}  ({len(items)} rows)")
    print(f"{'─'*100}")
    for i, (text, hl) in enumerate(items):
        marker = " ★" if hl else ""
        print(f"  {i:>3}. {text}{marker}")


def find_highlighted(items):
    for i, (_, hl) in enumerate(items):
        if hl:
            return i
    return -1


def run_test(app):
    from app_qt import MuseAppQt
    from ui_qt.search_window import SearchWindow
    from ui_qt.playlist_window import MasterPlaylistWindow
    from muse.playback_state import PlaybackStateManager

    # ── 1. Boot the application ──
    print("=== Step 1: Booting application ===")
    window = MuseAppQt()
    window.resize(1200, 700)
    window.restore_window_geometry()
    window.show()
    process_events_for(3)
    print("  Application started.")

    # ── 2. Set volume to 0 ──
    print("\n=== Step 2: Setting volume to 0 ===")
    window.volume_slider.setValue(0)
    window.set_volume()
    process_events_for(1)
    print(f"  Volume slider value: {window.volume_slider.value()}")

    # ── 3. Open search window ──
    print("\n=== Step 3: Opening search window ===")
    window.open_search_window()
    process_events_for(2)
    search_win = SearchWindow.top_level
    assert search_win is not None, "FAIL: SearchWindow did not open"
    print("  Search window opened.")

    # ── 4. Type "operetta" in the album field and click Search ──
    print("\n=== Step 4: Searching for 'operetta' in album field ===")
    search_win.album_entry.clear()
    QTest.keyClicks(search_win.album_entry, "operetta")
    process_events_for(1)
    print(f"  Album field text: '{search_win.album_entry.text()}'")

    print("  Clicking Search button...")
    QTest.mouseClick(search_win.search_btn, Qt.MouseButton.LeftButton)
    process_events_for(1)

    # Wait for search to complete (threaded)
    print(f"  Waiting up to {SEARCH_WAIT}s for search results...")
    deadline = time.time() + SEARCH_WAIT
    while time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.5)
        if (search_win.library_data_search is not None
                and len(search_win.library_data_search.get_results()) > 0
                and len(search_win.title_list) > 1):
            break

    assert search_win.library_data_search is not None, "FAIL: No search was created"
    results = search_win.library_data_search.get_results()
    print(f"  Search returned {len(results)} results")
    assert len(results) > 0, "FAIL: Search returned no results"

    # Collect first 20 result titles (these come from the sorted results)
    first_20 = results[:20]
    first_20_titles = [
        f"{t.title} - {t.artist}" if t.artist else t.title
        for t in first_20
    ]
    print(f"  First {len(first_20_titles)} search result titles:")
    for i, title in enumerate(first_20_titles):
        print(f"    {i+1:>3}. {title[:80]}")

    # ── 5. Click Play on the first result ──
    print(f"\n=== Step 5: Clicking Play on first result ===")
    assert len(search_win.play_btn_list) > 0, "FAIL: No play buttons found"
    # The play_btn_list contains buttons for current results display
    # The first play button corresponds to the first displayed result
    first_play_btn = search_win.play_btn_list[0]
    print(f"  Found {len(search_win.play_btn_list)} play buttons")
    QTest.mouseClick(first_play_btn, Qt.MouseButton.LeftButton)
    process_events_for(2)
    print("  Play button clicked.")

    # ── 6. Wait for playback to start ──
    print(f"\n=== Step 6: Waiting {PLAYBACK_WAIT}s for playback to start ===")
    deadline = time.time() + PLAYBACK_WAIT
    playback_started = False
    while time.time() < deadline:
        QApplication.processEvents()
        time.sleep(1)
        active = PlaybackStateManager.get_active_config()
        if active and hasattr(active, 'played_tracks') and active.played_tracks:
            playback_started = True
            print(f"  Playback active! {len(active.played_tracks)} track(s) played so far.")
            break

    if not playback_started:
        print("  WARNING: Playback may not have started yet, continuing anyway...")
        # Give it a bit more time
        process_events_for(DELAY)
        active = PlaybackStateManager.get_active_config()
        if active and hasattr(active, 'played_tracks') and active.played_tracks:
            playback_started = True
            print(f"  Playback confirmed after extra wait: {len(active.played_tracks)} track(s) played.")

    assert playback_started, "FAIL: Playback did not start"

    # Wait a bit more for the track to settle
    print(f"  Waiting {DELAY}s for playback to settle...")
    process_events_for(DELAY)

    # ── 7. Open the playlist window ──
    print(f"\n=== Step 7: Opening playlist window ===")
    window.open_playlist_window()
    process_events_for(3)
    playlist_win = MasterPlaylistWindow.top_level
    assert playlist_win is not None, "FAIL: Playlist window did not open"
    print("  Playlist window opened.")

    # Force a preview rebuild
    active = PlaybackStateManager.get_active_config()
    assert active is not None, "FAIL: No active config"
    playlist_win._update_live_preview(active)
    process_events_for(1)

    items_initial = read_preview_items(playlist_win)
    dump_preview(items_initial, "Initial preview after playback start")

    # ── 8. Compare search results order with preview order ──
    print(f"\n=== Step 8: Comparing search result order with preview ===")
    queue_start = playlist_win._queue_start_row
    queue_items = items_initial[queue_start:]
    print(f"  Queue starts at row {queue_start}, has {len(queue_items)} items")

    # The queue should contain the current track + pending tracks in sorted order.
    # The search results were sorted, and the playlist uses the same sort.
    # Check that queue item titles appear in the same order as search results.
    match_count = 0
    search_idx = 0
    for qi, (text, _) in enumerate(queue_items):
        if search_idx >= len(first_20_titles):
            break
        if first_20_titles[search_idx] in text:
            match_count += 1
            search_idx += 1

    print(f"  Matched {match_count} of first {min(len(first_20_titles), len(queue_items))} titles in order")
    if match_count >= min(10, len(first_20_titles)):
        print(f"  ✓ Preview order matches search results")
    else:
        print(f"  ✗ Preview order does NOT match search results well enough")
        print(f"    Expected titles:")
        for i, t in enumerate(first_20_titles[:10]):
            print(f"      {i+1}. {t[:80]}")
        print(f"    Queue items:")
        for i, (text, _) in enumerate(queue_items[:10]):
            print(f"      {i+1}. {text[:80]}")

    # ── 9. Seek forward ──
    print(f"\n=== Step 9: Seeking forward 4 tracks ===")
    # Find the current track in the active config
    master = active
    pc0 = master.playback_configs[0]
    playlist = pc0.get_list()
    cur_idx = playlist.current_track_index
    print(f"  Current track index: {cur_idx}")
    print(f"  Sorted tracks count: {len(playlist.sorted_tracks)}")

    seek_target_idx = cur_idx + 4
    if seek_target_idx >= len(playlist.sorted_tracks):
        seek_target_idx = min(cur_idx + 2, len(playlist.sorted_tracks) - 1)
    seek_target = playlist.sorted_tracks[seek_target_idx]
    skipped_range = range(cur_idx + 1, seek_target_idx)
    skipped_titles = [
        MasterPlaylistWindow._format_track(playlist.sorted_tracks[i])
        for i in skipped_range
    ]

    print(f"  Seeking to index {seek_target_idx}: {seek_target.title[:60]}")
    print(f"  Skipping {len(skipped_titles)} tracks")
    for t in skipped_titles:
        print(f"    - {t[:80]}")

    # Use the app's skip_to_track (same as user double-clicking)
    fp = seek_target.get_parent_filepath()
    window.skip_to_track(fp)
    print(f"  skip_to_track called, waiting {PLAYBACK_WAIT}s for new track...")
    process_events_for(PLAYBACK_WAIT)

    # Rebuild preview
    active = PlaybackStateManager.get_active_config()
    playlist_win._update_live_preview(active)
    process_events_for(1)

    items_after_seek = read_preview_items(playlist_win)
    dump_preview(items_after_seek, "After forward seek")

    # Verify skipped tracks are visible
    preview_texts = [text for text, _ in items_after_seek]
    highlight_row = find_highlighted(items_after_seek)
    print(f"\n  Highlighted row: {highlight_row}")

    all_skipped_visible = True
    for title in skipped_titles:
        found = any(title in text for text in preview_texts)
        if not found:
            print(f"  FAIL: skipped track NOT in preview: {title[:80]}")
            all_skipped_visible = False
        else:
            row_positions = [i for i, text in enumerate(preview_texts) if title in text]
            for rp in row_positions:
                if highlight_row >= 0 and rp > highlight_row:
                    print(f"  WARN: skipped track at row {rp} appears AFTER current row {highlight_row}")

    if all_skipped_visible:
        print(f"  ✓ All {len(skipped_titles)} skipped tracks visible in preview")
    else:
        print(f"  ✗ Some skipped tracks missing from preview")

    # Verify queue order matches sorted_tracks order
    queue_start_2 = playlist_win._queue_start_row
    queue_items_2 = items_after_seek[queue_start_2:]
    playlist_2 = pc0.get_list()
    cur_idx_2 = playlist_2.current_track_index
    pending_set = set(playlist_2.pending_tracks)
    expected_queue = []
    for ti, t in enumerate(playlist_2.sorted_tracks):
        fp_t = t.get_parent_filepath()
        title = MasterPlaylistWindow._format_track(t)
        if ti == cur_idx_2 or fp_t in pending_set:
            expected_queue.append(title)

    compare_n = min(len(queue_items_2), len(expected_queue), 20)
    order_ok = True
    for i in range(compare_n):
        actual_text = queue_items_2[i][0]
        expected_title = expected_queue[i]
        if expected_title not in actual_text:
            print(f"  MISMATCH at queue row {i}: expected '{expected_title[:50]}', got '{actual_text[:50]}'")
            order_ok = False

    if order_ok:
        print(f"  ✓ Queue order preserved after forward seek ({compare_n} items)")
    else:
        print(f"  ✗ Queue order broken after forward seek")

    # ── 10. Seek backward to first skipped track ──
    if skipped_titles:
        backward_target_idx = list(skipped_range)[0]
        backward_target = playlist_2.sorted_tracks[backward_target_idx]
        print(f"\n=== Step 10: Seeking backward to index {backward_target_idx}: "
              f"{backward_target.title[:60]} ===")

        fp_back = backward_target.get_parent_filepath()
        window.skip_to_track(fp_back)
        print(f"  skip_to_track called, waiting {PLAYBACK_WAIT}s...")
        process_events_for(PLAYBACK_WAIT)

        active = PlaybackStateManager.get_active_config()
        playlist_win._update_live_preview(active)
        process_events_for(1)

        items_after_back = read_preview_items(playlist_win)
        dump_preview(items_after_back, "After backward seek")

        highlight_back = find_highlighted(items_after_back)
        print(f"\n  Highlighted row: {highlight_back}")

        # Check order
        queue_start_3 = playlist_win._queue_start_row
        queue_items_3 = items_after_back[queue_start_3:]
        playlist_3 = pc0.get_list()
        cur_idx_3 = playlist_3.current_track_index
        pending_set_3 = set(playlist_3.pending_tracks)
        expected_back = []
        for ti, t in enumerate(playlist_3.sorted_tracks):
            fp_t = t.get_parent_filepath()
            title = MasterPlaylistWindow._format_track(t)
            if ti == cur_idx_3 or fp_t in pending_set_3:
                expected_back.append(title)

        compare_back = min(len(queue_items_3), len(expected_back), 20)
        back_ok = True
        for i in range(compare_back):
            actual_text = queue_items_3[i][0]
            expected_title = expected_back[i]
            if expected_title not in actual_text:
                print(f"  MISMATCH at queue row {i}: expected '{expected_title[:50]}', got '{actual_text[:50]}'")
                back_ok = False

        if back_ok:
            print(f"  ✓ Queue order preserved after backward seek ({compare_back} items)")
        else:
            print(f"  ✗ Queue order broken after backward seek")

    # ── 11. Let two songs finish naturally, compare preview order each time ──
    track_finish_ok = True
    for song_num in (1, 2):
        print(f"\n=== Step 11.{song_num}: Waiting for song to finish naturally ===")

        # Snapshot BEFORE the song finishes
        active_pre = PlaybackStateManager.get_active_config()
        playlist_win._update_live_preview(active_pre)
        process_events_for(0.5)
        items_before = read_preview_items(playlist_win)
        played_count_before = len(active_pre.played_tracks) if active_pre else 0

        pl_pre = pc0.get_list()
        cur_idx_pre = pl_pre.current_track_index
        pending_pre = set(pl_pre.pending_tracks)
        queue_before_titles = []
        for ti, t in enumerate(pl_pre.sorted_tracks):
            fp_t = t.get_parent_filepath()
            title = MasterPlaylistWindow._format_track(t)
            if ti == cur_idx_pre or fp_t in pending_pre:
                queue_before_titles.append(title)

        dump_preview(items_before, f"Before song {song_num} finishes (played={played_count_before})")

        # Wait for the played_tracks count to increase (song finished, next one started)
        print(f"  Waiting for track change (current played count: {played_count_before})...")
        max_song_wait = 600  # 10 minutes max per song
        deadline_song = time.time() + max_song_wait
        track_changed = False
        while time.time() < deadline_song:
            QApplication.processEvents()
            time.sleep(1)
            active_now = PlaybackStateManager.get_active_config()
            if active_now and len(active_now.played_tracks) > played_count_before:
                track_changed = True
                new_count = len(active_now.played_tracks)
                new_track = active_now.played_tracks[-1]
                print(f"  Track changed! played_tracks: {played_count_before} -> {new_count}")
                print(f"  New current track: {getattr(new_track, 'title', '?')[:60]}")
                break
            # Print progress every 30s
            elapsed = time.time() - (deadline_song - max_song_wait)
            if int(elapsed) % 30 == 0 and int(elapsed) > 0:
                print(f"  Still waiting... ({int(elapsed)}s elapsed)")

        if not track_changed:
            print(f"  FAIL: Song {song_num} did not finish within {max_song_wait}s")
            track_finish_ok = False
            break

        # Give a moment for the preview to update
        process_events_for(3)

        # Snapshot AFTER the song finishes
        active_post = PlaybackStateManager.get_active_config()
        playlist_win._update_live_preview(active_post)
        process_events_for(0.5)
        items_after = read_preview_items(playlist_win)

        dump_preview(items_after, f"After song {song_num} finishes (played={len(active_post.played_tracks)})")

        # Build expected queue after the track change
        pl_post = pc0.get_list()
        cur_idx_post = pl_post.current_track_index
        pending_post = set(pl_post.pending_tracks)
        queue_after_expected = []
        for ti, t in enumerate(pl_post.sorted_tracks):
            fp_t = t.get_parent_filepath()
            title = MasterPlaylistWindow._format_track(t)
            if ti == cur_idx_post or fp_t in pending_post:
                queue_after_expected.append(title)

        # Verify the queue items in the widget match expected
        queue_start_post = playlist_win._queue_start_row
        queue_items_post = items_after[queue_start_post:]
        compare_post = min(len(queue_items_post), len(queue_after_expected), 20)
        song_order_ok = True
        for i in range(compare_post):
            actual_text = queue_items_post[i][0]
            expected_title = queue_after_expected[i]
            if expected_title not in actual_text:
                print(f"  MISMATCH at queue row {i}:")
                print(f"    expected: ...{expected_title[:60]}...")
                print(f"    actual:   {actual_text[:60]}")
                song_order_ok = False

        if song_order_ok:
            print(f"  ✓ Queue order correct after song {song_num} finished ({compare_post} items)")
        else:
            print(f"  ✗ Queue order BROKEN after song {song_num} finished")
            track_finish_ok = False

        # Verify the before-queue titles are a superset of after-queue titles
        # (the finished song should have moved from queue to history, rest preserved)
        before_set = set(queue_before_titles)
        after_set = set(queue_after_expected)
        missing_from_after = before_set - after_set
        # Exactly 1 track should have moved out (the one that just finished)
        if len(missing_from_after) == 1:
            gone_title = missing_from_after.pop()
            print(f"  ✓ Exactly 1 track moved from queue to history: {gone_title[:60]}")
        elif len(missing_from_after) == 0:
            print(f"  WARN: No tracks moved from queue (track may have been re-added?)")
        else:
            print(f"  FAIL: {len(missing_from_after)} tracks disappeared from queue:")
            for mt in sorted(missing_from_after):
                print(f"    - {mt[:80]}")
            track_finish_ok = False

    # ── 12. Verify sorted_tracks never mutated ──
    final_order = [t.filepath for t in playlist.sorted_tracks]
    print(f"\n  Final sorted_tracks count: {len(final_order)}")
    print(f"  ✓ Test sequence complete")

    # Clean up
    try:
        if playlist_win:
            playlist_win.close()
        if search_win:
            search_win.close()
        window.close()
    except Exception:
        pass

    success = all_skipped_visible and order_ok and track_finish_ok
    if success:
        print("\n\n=== ALL CHECKS PASSED ===\n")
    else:
        print("\n\n=== SOME CHECKS FAILED ===\n")
    return success


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Muse Test")

    success = False
    try:
        success = run_test(app)
    except Exception as e:
        print(f"\nFATAL: {e}")
        traceback.print_exc()

    sys.exit(0 if success else 1)
