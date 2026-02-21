"""Compare playlist-descriptor resolved order vs search-window displayed order
for a composer="bach" search with COMPOSER_SHUFFLE.

Usage:  python test_sort_compare.py
"""

import sys
import os

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from tests.utils.project_setup import load_library_data

from library_data.library_data import LibraryDataSearch
from muse.playback_config import PlaybackConfig
from muse.playlist_descriptor import PlaylistDescriptor
from muse.sort_config import SortConfig
from utils.globals import PlaylistSortType

# ── 1. Load caches ──

library_data = load_library_data()

SEARCH_QUERY = {"composer": "bach"}
SORT_TYPE = PlaylistSortType.COMPOSER_SHUFFLE

# ── 2. Playlist-descriptor path ──
#   PlaylistDescriptor.resolve_tracks → PlaybackConfig.from_playlist_descriptor → get_list()

pd = PlaylistDescriptor(
    name="Test Bach",
    sort_type=SORT_TYPE,
    search_query=SEARCH_QUERY,
    sort_config=SortConfig(skip_memory_shuffle=True, skip_random_start=True),
)

print("\n[Playlist path] Resolving tracks via PlaylistDescriptor...")
resolved_filepaths = pd.resolve_tracks(library_data)
print(f"  resolve_tracks returned {len(resolved_filepaths)} filepaths")

print("[Playlist path] Building PlaybackConfig + Playlist...")
pc = PlaybackConfig.from_playlist_descriptor(
    pd,
    data_callbacks=library_data.data_callbacks,
    library_data=library_data,
)
playlist = pc.get_list()
pl_tracks = playlist.sorted_tracks
print(f"  Playlist sorted_tracks: {len(pl_tracks)} tracks")

# ── 3. Search-window path ──
#   Single search with a large max_results (same total), then sort_results_by()

print("\n[Search-window path] Running full search...")
sw_search = LibraryDataSearch(
    composer="bach",
    max_results=100_000,
    offset=0,
)
library_data.do_search(sw_search, overwrite=False)
print(f"  Raw results: {len(sw_search.get_results())} tracks")

# sort_results_by() with no args now auto-detects "composer" → searchable_composer
sw_search.sort_results_by()
sw_tracks = list(sw_search.get_results())
print(f"  After sort_results_by(): {len(sw_tracks)} tracks")

# ── 4. Show relevance tiers for the search-window results ──

query = "bach"
tier_counts = {0: 0, 1: 0, 2: 0}
for t in sw_tracks:
    sc = t.searchable_composer or ""
    tier = LibraryDataSearch._match_relevance(sc, query)
    tier_counts[tier] += 1
print(f"\n  Relevance tiers (search window): start={tier_counts[0]}, word-boundary={tier_counts[1]}, other={tier_counts[2]}")

# ── 5. Compare ──

def compare(label, ref_tracks, pl_tracks, n=30):
    n = min(n, len(ref_tracks), len(pl_tracks))
    print(f"\n{'='*140}")
    print(f"  {label}: first {n} tracks")
    print(f"{'='*140}")
    print(f"{'#':>3}  {'M':>1}  {'R':>1}  {'Search Window (searchable_composer)':50s}  {'R':>1}  {'Playlist (composer)':50s}")
    print("-" * 140)
    mismatches = 0
    for i in range(n):
        sw = ref_tracks[i]
        pl = pl_tracks[i]
        ok = sw.filepath == pl.filepath
        mark = "✓" if ok else "✗"
        if not ok:
            mismatches += 1
        sw_rel = LibraryDataSearch._match_relevance(sw.searchable_composer or "", query)
        pl_rel = LibraryDataSearch._match_relevance(pl.composer or "", query)
        sw_lbl = f"{sw.searchable_composer} | {sw.title}"[:50]
        pl_lbl = f"{pl.composer} | {pl.title}"[:50]
        print(f"{i+1:>3}  {mark:>1}  {sw_rel:>1}  {sw_lbl:50s}  {pl_rel:>1}  {pl_lbl:50s}")
    print(f"\n  → {mismatches} mismatches in first {n}")
    return mismatches

compare("search-window (with relevance sort) vs playlist (alphabetical group sort)", sw_tracks, pl_tracks)
