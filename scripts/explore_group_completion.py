#!/usr/bin/env python3
"""Explore what a play-completion threshold would mean against the real library.

The cross-sort awareness feature exempts a group from recently-played demotion
while only a small proportion of its tracks have been heard. "Small proportion"
has to become a number, and the right number depends entirely on how large groups
actually are in this library -- which is what this prints.

The figure that matters is not the ratio but what it costs: how many tracks you
must play before a group stops resisting. A bare ratio fails at both ends -- two
thirds of composers here have one track, where any ratio is moot, while the
largest album would need 237 plays at 25% and so could never be spent. Pass
--cap to model the rule that fixes it: a quarter of the group *or* N tracks,
whichever comes first.

Standalone: stdlib only, no project imports, safe to run outside the app.

    python scripts/explore_group_completion.py
    python scripts/explore_group_completion.py --db /path/to/muse_library.db
    python scripts/explore_group_completion.py --thresholds 0.2 0.25 0.34
    python scripts/explore_group_completion.py --thresholds 0.25 --cap 4
"""

import argparse
import math
import os
import sqlite3
import sys
from collections import Counter

# The attributes Playlist groups by, as columns on media_tracks. catalogue is
# absent: it is derived rather than stored.
GROUPING_COLUMNS = ("album", "composer", "artist", "genre", "form", "instrument")

DEFAULT_THRESHOLDS = (0.10, 0.20, 0.25, 0.33, 0.50)

SIZE_BUCKETS = ((1, 1), (2, 4), (5, 12), (13, 30), (31, 10**9))

DEFAULT_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "configs", "muse_library.db")


def percentile(values, fraction):
    """Nearest-rank percentile over a pre-sorted list."""
    if not values:
        return 0
    index = max(0, min(len(values) - 1, int(math.ceil(fraction * len(values))) - 1))
    return values[index]


def group_sizes(conn, column):
    """Track count per distinct value of *column*, ignoring untagged tracks."""
    rows = conn.execute(
        f"SELECT {column} AS value, COUNT(*) AS n FROM media_tracks "
        f"WHERE {column} IS NOT NULL AND TRIM({column}) != '' GROUP BY {column}"
    ).fetchall()
    return {row["value"]: row["n"] for row in rows}


def describe_sizes(sizes):
    ordered = sorted(sizes.values())
    total_tracks = sum(ordered)
    buckets = Counter()
    for size in ordered:
        for low, high in SIZE_BUCKETS:
            if low <= size <= high:
                buckets[(low, high)] += 1
                break
    return {
        "groups": len(ordered),
        "tracks": total_tracks,
        "median": percentile(ordered, 0.5),
        "p90": percentile(ordered, 0.9),
        "max": ordered[-1] if ordered else 0,
        "buckets": buckets,
        "ordered": ordered,
    }


def tracks_to_spend(size, threshold, cap=None):
    """How many tracks of a group must be heard before it stops resisting.

    A bare ratio breaks at both ends of this library: a one-track composer is
    fully heard after one track, while a 947-track compilation would need 237.
    The cap is what keeps the large end sane -- a group is spent once a quarter
    of it *or* a handful of tracks have been played, whichever comes first.
    """
    needed = max(1, math.ceil(threshold * size))
    return min(needed, cap) if cap else needed


def describe_threshold(ordered_sizes, threshold, cap=None):
    """What this threshold costs, measured in tracks that must be played."""
    if not ordered_sizes:
        return None
    needed = sorted(tracks_to_spend(size, threshold, cap) for size in ordered_sizes)
    # A group whose requirement is still one track is unprotected: the very first
    # track spends it, exactly as today.
    unprotected = sum(1 for n in needed if n <= 1)
    # Weighted by tracks rather than by group, since a listener meets large groups
    # more often than their share of the group count suggests.
    track_weighted = sum(
        tracks_to_spend(size, threshold, cap) * size for size in ordered_sizes)
    return {
        "median_needed": percentile(needed, 0.5),
        "p90_needed": percentile(needed, 0.9),
        "max_needed": needed[-1],
        "unprotected_pct": 100.0 * unprotected / len(needed),
        "mean_needed_per_track": track_weighted / sum(ordered_sizes),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=DEFAULT_DB, help="path to muse_library.db")
    parser.add_argument("--thresholds", type=float, nargs="+", default=list(DEFAULT_THRESHOLDS),
                        help="completion ratios to compare")
    parser.add_argument("--columns", nargs="+", default=list(GROUPING_COLUMNS),
                        help="grouping columns to report on")
    parser.add_argument("--cap", type=int, default=None,
                        help="upper bound on tracks needed to spend a group; "
                             "without it, huge groups can never be spent")
    args = parser.parse_args(argv)

    if not os.path.exists(args.db):
        print(f"No database at {args.db}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        for column in args.columns:
            try:
                sizes = group_sizes(conn, column)
            except sqlite3.OperationalError as e:
                print(f"\n{column}: unavailable ({e})")
                continue
            if not sizes:
                print(f"\n{column}: no tagged tracks")
                continue

            stats = describe_sizes(sizes)
            print(f"\n=== {column} ===")
            print(f"{stats['groups']} groups over {stats['tracks']} tracks  "
                  f"median {stats['median']}, p90 {stats['p90']}, max {stats['max']}")
            parts = []
            for low, high in SIZE_BUCKETS:
                count = stats["buckets"][(low, high)]
                label = f"{low}" if low == high else (f"{low}+" if high > 10**8 else f"{low}-{high}")
                parts.append(f"{label}: {count} ({100.0 * count / stats['groups']:.0f}%)")
            print("  sizes  " + "   ".join(parts))

            cap_note = f" (capped at {args.cap})" if args.cap else ""
            print(f"  {'ratio':>6}  {'tracks to spend a group' + cap_note:>26}  "
                  f"{'unprotected':>11}  {'avg/track':>9}")
            for threshold in args.thresholds:
                row = describe_threshold(stats["ordered"], threshold, args.cap)
                spread = f"median {row['median_needed']}, p90 {row['p90_needed']}, max {row['max_needed']}"
                print(f"  {threshold:>6.2f}  {spread:>26}  "
                      f"{row['unprotected_pct']:>10.0f}%  {row['mean_needed_per_track']:>9.1f}")

        print("\nunprotected = groups where one track still spends the group, so the")
        print("threshold changes nothing for them. avg/track = tracks needed to spend")
        print("the group a randomly chosen track belongs to.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
