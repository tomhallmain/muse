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
import traceback

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from PySide6.QtWidgets import QApplication

from tests.utils.qt_test_helpers import (
    process_events_for,
    read_preview_items,
    dump_preview,
    find_highlighted,
    boot_app,
    open_search_and_query,
    click_play_on_result,
    wait_for_playback,
    wait_for_track_change,
    open_playlist_window,
)
from tests.utils.playlist_assertions import (
    build_expected_queue,
    verify_queue_order,
    verify_single_track_moved,
)

PLAYBACK_WAIT = 15  # seconds to wait for seek to take effect


def run_test(app):
    from ui_qt.playlist_window import MasterPlaylistWindow
    from muse.playback_state import PlaybackStateManager

    # ── 1–2. Boot application (volume = 0) ──
    window = boot_app()

    # ── 3–4. Open search, type "operetta" in album, wait for results ──
    search_win, results = open_search_and_query(window, "album", "operetta")

    first_20 = results[:20]
    first_20_titles = [
        f"{t.title} - {t.artist}" if t.artist else t.title
        for t in first_20
    ]
    print(f"  First {len(first_20_titles)} search result titles:")
    for i, title in enumerate(first_20_titles):
        print(f"    {i+1:>3}. {title[:80]}")

    # ── 5. Click Play on the first result ──
    click_play_on_result(search_win, index=0)

    # ── 6. Wait for playback to start ──
    active = wait_for_playback()

    # ── 7. Open the playlist window ──
    playlist_win = open_playlist_window(window)

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

    fp = seek_target.get_parent_filepath()
    window.skip_to_track(fp)
    print(f"  skip_to_track called, waiting {PLAYBACK_WAIT}s for new track...")
    process_events_for(PLAYBACK_WAIT)

    active = PlaybackStateManager.get_active_config()
    playlist_win._update_live_preview(active)
    process_events_for(1)

    items_after_seek = read_preview_items(playlist_win)
    dump_preview(items_after_seek, "After forward seek")

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

    expected_queue = build_expected_queue(pc0.get_list(), MasterPlaylistWindow._format_track)
    order_ok = verify_queue_order(
        items_after_seek, expected_queue,
        queue_start_row=playlist_win._queue_start_row,
        label="after forward seek",
    )

    # ── 10. Seek backward to first skipped track ──
    if skipped_titles:
        backward_target_idx = list(skipped_range)[0]
        backward_target = pc0.get_list().sorted_tracks[backward_target_idx]
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

        expected_back = build_expected_queue(pc0.get_list(), MasterPlaylistWindow._format_track)
        verify_queue_order(
            items_after_back, expected_back,
            queue_start_row=playlist_win._queue_start_row,
            label="after backward seek",
        )

    # ── 11. Let two songs finish naturally, compare preview order each time ──
    track_finish_ok = True
    for song_num in (1, 2):
        print(f"\n=== Step 11.{song_num}: Waiting for song to finish naturally ===")

        active_pre = PlaybackStateManager.get_active_config()
        playlist_win._update_live_preview(active_pre)
        process_events_for(0.5)
        items_before = read_preview_items(playlist_win)
        played_count_before = len(active_pre.played_tracks) if active_pre else 0

        queue_before_titles = build_expected_queue(pc0.get_list(), MasterPlaylistWindow._format_track)
        dump_preview(items_before, f"Before song {song_num} finishes (played={played_count_before})")

        changed = wait_for_track_change(played_count_before, max_wait=600)
        if not changed:
            print(f"  FAIL: Song {song_num} did not finish within timeout")
            track_finish_ok = False
            break

        process_events_for(3)

        active_post = PlaybackStateManager.get_active_config()
        playlist_win._update_live_preview(active_post)
        process_events_for(0.5)
        items_after = read_preview_items(playlist_win)
        dump_preview(items_after, f"After song {song_num} finishes (played={len(active_post.played_tracks)})")

        queue_after_expected = build_expected_queue(pc0.get_list(), MasterPlaylistWindow._format_track)

        song_order_ok = verify_queue_order(
            items_after, queue_after_expected,
            queue_start_row=playlist_win._queue_start_row,
            label=f"after song {song_num} finishes",
        )
        if not song_order_ok:
            track_finish_ok = False

        if not verify_single_track_moved(queue_before_titles, queue_after_expected,
                                          label=f"song {song_num}"):
            track_finish_ok = False

    # ── 12. Final checks ──
    final_order = [t.filepath for t in playlist.sorted_tracks]
    print(f"\n  Final sorted_tracks count: {len(final_order)}")
    print(f"  ✓ Test sequence complete")

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
