"""Regression guard for ALL_MUSIC + ALBUM_SHUFFLE ordering.

This mirrors the runtime path used by ALL_MUSIC:
  Run -> PlaybackConfigMaster([PlaybackConfig(...)] + override SortConfig)

It validates that the *album group order* at the front of the playlist is not
simply alphabetical, which indicates album shuffling/random start was bypassed.

Usage:
    python tests/scripts/test_sort_compare_all_music.py
"""

import os
import random
import sys
from types import SimpleNamespace

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from tests.utils.project_setup import load_library_data

from muse.playback_config import PlaybackConfig
from muse.playback_config_master import PlaybackConfigMaster
from muse.sort_config import SortConfig
from utils.config import config
from utils.globals import PlaylistSortType


def _normalize_album(album: str) -> str:
    return (album or "").strip().casefold()


def _first_distinct_albums(tracks, limit: int = 30):
    groups = []
    last = object()
    for track in tracks:
        album = track.album or ""
        if album != last:
            groups.append(album)
            last = album
            if len(groups) >= limit:
                break
    return groups


def main():
    library_data = load_library_data()

    all_dirs = config.get_subdirectories()
    directories = list(all_dirs.keys())
    if not directories:
        raise AssertionError("No subdirectories configured for ALL_MUSIC test.")

    args = SimpleNamespace(
        total=-1,
        playlist_sort_type=PlaylistSortType.ALBUM_SHUFFLE,
        directories=directories,
        overwrite=False,
        enable_dynamic_volume=True,
        enable_long_track_splitting=False,
        long_track_splitting_time_cutoff_minutes=20,
        track=None,
    )

    pc = PlaybackConfig(args=args, data_callbacks=library_data.data_callbacks)
    override_sc = SortConfig(
        skip_memory_shuffle=False,
        skip_random_start=False,
        check_entire_playlist=True,
    )
    master = PlaybackConfigMaster(playback_configs=[pc], override_sort_config=override_sc)

    playlist = master.get_list()
    sorted_tracks = playlist.sorted_tracks
    print(f"Playlist size: {len(sorted_tracks)}")
    print(f"Sort config (effective): {pc.sort_config}")

    if len(sorted_tracks) < 100:
        raise AssertionError("Playlist too small for reliable ordering validation.")

    first_groups = _first_distinct_albums(sorted_tracks, limit=30)
    if len(first_groups) < 20:
        raise AssertionError(
            f"Insufficient distinct album groups near playlist start ({len(first_groups)})."
        )

    normalized = [_normalize_album(a) for a in first_groups]
    nondecreasing_pairs = sum(
        1 for i in range(len(normalized) - 1) if normalized[i] <= normalized[i + 1]
    )
    pair_ratio = nondecreasing_pairs / max(1, (len(normalized) - 1))

    print("\nFirst distinct albums:")
    for album in first_groups[:20]:
        print(album)

    if pair_ratio >= 0.9:
        raise AssertionError(
            "Regression detected: first distinct album groups are too close to alphabetical "
            f"(nondecreasing ratio={pair_ratio:.2%}) in ALL_MUSIC ALBUM_SHUFFLE mode."
        )

    # Rebuild once more in the same process; with skip_random_start=False
    # the early group ordering should not be identical run-to-run.
    pc2 = PlaybackConfig(args=args, data_callbacks=library_data.data_callbacks)
    master2 = PlaybackConfigMaster(playback_configs=[pc2], override_sort_config=override_sc)
    first_groups_2 = _first_distinct_albums(master2.get_list().sorted_tracks, limit=20)
    if first_groups[:20] == first_groups_2[:20]:
        raise AssertionError(
            "Regression detected: two consecutive ALL_MUSIC ALBUM_SHUFFLE builds "
            "produced identical first 20 album groups."
        )

    print(f"\nPASS: ordering is not near-alphabetical (ratio={pair_ratio:.2%}) and varies across builds.")


if __name__ == "__main__":
    main()
