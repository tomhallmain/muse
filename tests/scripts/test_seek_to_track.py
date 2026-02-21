"""Verify that seek_to_track preserves playlist order and pending/played state.

Simulates:
  1. Search for "cantata" in the album field
  2. Build a PlaybackConfigMaster from the first 20 results
  3. Play a few tracks (call next_track)
  4. Seek forward 4 tracks
  5. Compare sorted_tracks order (must be unchanged) and verify
     skipped tracks remain in pending_tracks

Usage:  python test_seek_to_track.py
"""

import sys
import os
import time

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from tests.utils.project_setup import load_library_data
from tests.utils.playlist_assertions import snapshot, build_expected_queue

from library_data.library_data import LibraryDataSearch
from muse.playback_config import PlaybackConfig
from muse.playback_config_master import PlaybackConfigMaster
from muse.playlist_descriptor import PlaylistDescriptor
from muse.sort_config import SortConfig
from utils.globals import PlaylistSortType

DELAY = 5  # seconds between playlist actions

# ── 1. Load caches ──

library_data = load_library_data()

# ── 2. Search for "cantata" in album ──

SEARCH_QUERY = {"album": "cantata"}
SORT_TYPE = PlaylistSortType.COMPOSER_SHUFFLE
TRACK_LIMIT = 20

pd = PlaylistDescriptor(
    name="Test Cantata",
    sort_type=SORT_TYPE,
    search_query=SEARCH_QUERY,
    sort_config=SortConfig(skip_memory_shuffle=True, skip_random_start=True),
)

print(f"\nResolving tracks for album='cantata'...")
resolved_filepaths = pd.resolve_tracks(library_data)
print(f"  Found {len(resolved_filepaths)} tracks")

if len(resolved_filepaths) < TRACK_LIMIT:
    print(f"  WARNING: fewer than {TRACK_LIMIT} results, using all {len(resolved_filepaths)}")
    TRACK_LIMIT = len(resolved_filepaths)

if TRACK_LIMIT < 8:
    print("  ERROR: need at least 8 tracks to run this test")
    sys.exit(1)

# ── 3. Build PlaybackConfig + PlaybackConfigMaster ──

print("\nBuilding PlaybackConfig + PlaybackConfigMaster...")
time.sleep(DELAY)

pc = PlaybackConfig.from_playlist_descriptor(
    pd,
    data_callbacks=library_data.data_callbacks,
    library_data=library_data,
)
master = PlaybackConfigMaster(
    playback_configs=[pc],
    override_sort_config=None,
)

playlist = pc.get_list()
original_order = [t.filepath for t in playlist.sorted_tracks]
print(f"  Playlist has {len(original_order)} sorted tracks")

# ── 4. Snapshot the initial state ──

snapshot("Initial state (before any playback)", playlist, master, limit=TRACK_LIMIT)

# ── 5. Play 3 tracks (with delays) ──

print("\n\n=== Playing 3 tracks ===")
for i in range(3):
    print(f"  Waiting {DELAY}s before next_track()...")
    time.sleep(DELAY)
    result = master.next_track()
    if result.track:
        print(f"  Played [{i+1}/3]: {result.track.title[:60]}")
    else:
        print(f"  ERROR: next_track returned None at step {i}")
        sys.exit(1)

snapshot("After playing 3 tracks", playlist, master, limit=TRACK_LIMIT)

# ── 6. Verify sorted order unchanged ──

current_order = [t.filepath for t in playlist.sorted_tracks]
assert current_order == original_order, "FAIL: sorted_tracks order changed after playback!"
print("\n  ✓ sorted_tracks order unchanged after playback")

# ── 7. Seek forward 4 tracks ──

seek_target_idx = playlist.current_track_index + 4
seek_target = playlist.sorted_tracks[seek_target_idx]
print(f"\n\n=== Seeking forward to index {seek_target_idx}: {seek_target.title[:60]} ===")

skipped_indices = list(range(playlist.current_track_index + 1, seek_target_idx))
skipped_fps = [playlist.sorted_tracks[i].get_parent_filepath() for i in skipped_indices]

print(f"  Waiting {DELAY}s before seek_to_track()...")
time.sleep(DELAY)

found = master.seek_to_track(seek_target.get_parent_filepath())
assert found, "FAIL: seek_to_track returned False"

print(f"  Waiting {DELAY}s before next_track() after seek...")
time.sleep(DELAY)

result = master.next_track()
assert result.track is not None, "FAIL: next_track after seek returned None"
assert result.track.filepath == seek_target.filepath, (
    f"FAIL: expected {seek_target.filepath}, got {result.track.filepath}"
)
print(f"  Now playing: {result.track.title[:60]}")

snapshot("After seek + next_track", playlist, master, limit=TRACK_LIMIT)

# ── 8. Verify order still unchanged ──

current_order = [t.filepath for t in playlist.sorted_tracks]
assert current_order == original_order, "FAIL: sorted_tracks order changed after seek!"
print("\n  ✓ sorted_tracks order unchanged after seek")

# ── 9. Verify skipped tracks are still in pending_tracks ──

print(f"\n  Checking {len(skipped_fps)} skipped tracks are still in pending_tracks...")
pending_set = set(playlist.pending_tracks)
for fp in skipped_fps:
    if fp not in pending_set:
        idx = original_order.index(fp) if fp in original_order else "?"
        print(f"  FAIL: skipped track at index {idx} NOT in pending_tracks: {fp}")
        sys.exit(1)
print(f"  ✓ All {len(skipped_fps)} skipped tracks still in pending_tracks")

# ── 10. Simulate what the preview would show ──

print(f"\n\n=== Preview simulation ===")

played = master.played_tracks or []
history_played = played[:-1] if played else []
history_start = max(0, len(history_played) - 3)
history_slice = history_played[history_start:]

print(f"\n  History ({len(history_slice)} items, NOT including current):")
for i, t in enumerate(history_slice):
    print(f"      {t.title[:60]}")

queue_titles = build_expected_queue(playlist)
cur_idx = playlist.current_track_index

print(f"\n  Queue ({len(queue_titles)} items = current + pending, in sorted order):")
queue_idx = 0
for ti, t in enumerate(playlist.sorted_tracks):
    fp = t.get_parent_filepath()
    is_cur = ti == cur_idx
    in_pending = fp in pending_set
    if is_cur or in_pending:
        marker = "▶ " if is_cur else "  "
        behind = ti < cur_idx and not is_cur
        label = " ← SKIPPED (before cursor)" if behind else ""
        print(f"    {marker}sorted[{ti:>3}] {t.title[:60]}{label}")
        queue_idx += 1
        if queue_idx >= 20:
            break

skipped_in_queue = sum(1 for ti, t in enumerate(playlist.sorted_tracks)
                       if ti < cur_idx and t.get_parent_filepath() in pending_set)
print(f"\n  Skipped tracks visible in queue: {skipped_in_queue}")
print(f"  Expected skipped count:          {len(skipped_fps)}")
assert skipped_in_queue == len(skipped_fps), (
    f"FAIL: expected {len(skipped_fps)} skipped tracks in queue, "
    f"got {skipped_in_queue}"
)
print(f"  ✓ All skipped tracks visible in queue at their original sorted positions")

# ── 11. Seek backward to a skipped track ──

if skipped_indices:
    backward_target_idx = skipped_indices[0]
    backward_target = playlist.sorted_tracks[backward_target_idx]
    print(f"\n\n=== Seeking backward to index {backward_target_idx}: {backward_target.title[:60]} ===")

    print(f"  Waiting {DELAY}s before seek_to_track()...")
    time.sleep(DELAY)

    found = master.seek_to_track(backward_target.get_parent_filepath())
    assert found, "FAIL: backward seek_to_track returned False"

    print(f"  Waiting {DELAY}s before next_track() after backward seek...")
    time.sleep(DELAY)

    result = master.next_track()
    assert result.track is not None, "FAIL: next_track after backward seek returned None"
    assert result.track.filepath == backward_target.filepath, (
        f"FAIL: expected {backward_target.filepath}, got {result.track.filepath}"
    )
    print(f"  Now playing: {result.track.title[:60]}")

    snapshot("After backward seek + next_track", playlist, master, limit=TRACK_LIMIT)

    current_order = [t.filepath for t in playlist.sorted_tracks]
    assert current_order == original_order, "FAIL: sorted_tracks order changed after backward seek!"
    print("\n  ✓ sorted_tracks order unchanged after backward seek")

print("\n\n=== ALL CHECKS PASSED ===\n")
