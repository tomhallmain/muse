"""
Run main-artist resolution over the real media_tracks table and report what it
catches, what it leaves alone, and how much it actually reduces artist-group
fragmentation.

Calls MediaTrack._derive_main_artist directly, so what is reported is what the
grouping would do -- not a reimplementation of it.

The headline number is "distinct artist values before vs after": ARTIST_SHUFFLE
groups by that value, so a large reduction means fewer near-duplicate groups,
which is the point of the card. A reduction that looks too large is worth
inspecting in the over-merge section, since collapsing genuinely different
artists together is the failure mode in the other direction.

Run from the workspace root:
    python scripts/check_main_artist_resolution.py
    python scripts/check_main_artist_resolution.py --preference last
    python scripts/check_main_artist_resolution.py --preference both
    python scripts/check_main_artist_resolution.py --contains "feat."
    python scripts/check_main_artist_resolution.py --show 25
"""

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from library_data.media_track import (
    MediaTrack,
    _ALBUMARTIST_PLACEHOLDERS,
    _MAIN_ARTIST_FEATURING_RE,
    _MAIN_ARTIST_SEPARATOR_RE,
)
from utils.db import get_connection

ALBUMARTIST = "albumartist"
FEATURING = "featuring"
SEPARATOR = "separator"
UNCHANGED = "unchanged"
REASONS = (ALBUMARTIST, FEATURING, SEPARATOR, UNCHANGED)


def _reason(albumartist, artist):
    """Which resolution step decided the value. Mirrors the order in _derive_main_artist."""
    if albumartist:
        candidate = str(albumartist).strip()
        if candidate and candidate.lower() not in _ALBUMARTIST_PLACEHOLDERS:
            return ALBUMARTIST
    if not artist or not str(artist).strip():
        return UNCHANGED
    value = str(artist).strip()
    if _MAIN_ARTIST_FEATURING_RE.search(value):
        return FEATURING
    if len([s for s in _MAIN_ARTIST_SEPARATOR_RE.split(value) if s.strip()]) > 1:
        return SEPARATOR
    return UNCHANGED


def _load_rows(limit, contains):
    sql = ("SELECT filepath, artist, albumartist FROM media_tracks "
           "WHERE artist IS NOT NULL AND artist != ''")
    params = []
    if contains:
        sql += " AND (artist LIKE ? OR albumartist LIKE ?)"
        params += [f"%{contains}%", f"%{contains}%"]
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    conn = get_connection()
    conn.row_factory = __import__("sqlite3").Row
    return list(conn.execute(sql, params))


def _resolve_all(rows, prefer_last):
    resolved = []
    for row in rows:
        main = MediaTrack._derive_main_artist(
            row["albumartist"], row["artist"], prefer_last_segment=prefer_last)
        resolved.append((row, main or "", _reason(row["albumartist"], row["artist"])))
    return resolved


def _report(resolved, prefer_last, show):
    label = "last" if prefer_last else "first"
    print(f"\n{'=' * 78}\nPreference: {label} segment\n{'=' * 78}")

    counts = collections.Counter(reason for _row, _main, reason in resolved)
    total = len(resolved)
    print(f"\nResolution step used ({total} tracks with an artist tag):")
    for reason in REASONS:
        n = counts[reason]
        pct = (n / total * 100) if total else 0
        print(f"  {reason:12s} {n:7d}  {pct:5.1f}%")

    raw_values = {(r["artist"] or "").strip() for r, _m, _x in resolved}
    main_values = {m for _r, m, _x in resolved if m}
    print(f"\nGrouping impact:")
    print(f"  distinct artist values (today) : {len(raw_values)}")
    print(f"  distinct main artists (after)  : {len(main_values)}")
    if raw_values:
        drop = len(raw_values) - len(main_values)
        print(f"  reduction                      : {drop} ({drop / len(raw_values) * 100:.1f}%)")

    changed = [(r, m) for r, m, _x in resolved if m and m != (r["artist"] or "").strip()]
    print(f"  tracks whose group key changes : {len(changed)}")

    for reason in (ALBUMARTIST, FEATURING, SEPARATOR):
        samples = [(r, m) for r, m, x in resolved
                   if x == reason and m != (r["artist"] or "").strip()]
        if not samples:
            continue
        print(f"\n--- {reason}: {len(samples)} changed, showing {min(show, len(samples))} ---")
        seen = set()
        shown = 0
        for row, main in samples:
            key = ((row["artist"] or "").strip(), main)
            if key in seen:
                continue
            seen.add(key)
            aa = f"  [albumartist: {row['albumartist']}]" if reason == ALBUMARTIST else ""
            print(f"  {row['artist']!r}\n      -> {main!r}{aa}")
            shown += 1
            if shown >= show:
                break

    # Riskiest marker: "with" can be part of a real name, unlike feat./ft.
    with_hits = [(r, m) for r, m, x in resolved
                 if x == FEATURING and _MAIN_ARTIST_FEATURING_RE.search((r["artist"] or "").strip())
                 and _MAIN_ARTIST_FEATURING_RE.search((r["artist"] or "").strip()).group(0).lower().startswith("with")]
    if with_hits:
        print(f"\n--- REVIEW: split on 'with' ({len(with_hits)} tracks) ---")
        print("  'with' is the least certain marker -- it can be part of a real name.")
        seen = set()
        for row, main in with_hits:
            key = (row["artist"], main)
            if key in seen:
                continue
            seen.add(key)
            print(f"  {row['artist']!r} -> {main!r}")
            if len(seen) >= show:
                break

    # Over-merge: one main artist absorbing many distinct raw values
    absorbed = collections.defaultdict(set)
    for row, main, _x in resolved:
        if main:
            absorbed[main].add((row["artist"] or "").strip())
    multi = sorted(((m, v) for m, v in absorbed.items() if len(v) > 1),
                   key=lambda kv: -len(kv[1]))
    if multi:
        print(f"\n--- merged groups: {len(multi)} main artists absorb >1 raw value ---")
        print("  Large counts are the intended win; check the top few are really one artist.")
        for main, values in multi[:show]:
            print(f"  {main!r}  <- {len(values)} raw values")
            for value in sorted(values)[:3]:
                print(f"        {value!r}")
            if len(values) > 3:
                print(f"        ... and {len(values) - 3} more")

    suspicious = sorted({(r["artist"], m) for r, m, _x in resolved
                         if m and len(m) <= 2 and m != (r["artist"] or "").strip()})
    if suspicious:
        print(f"\n--- REVIEW: suspiciously short results ({len(suspicious)}) ---")
        for raw, main in suspicious[:show]:
            print(f"  {raw!r} -> {main!r}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--preference", choices=("first", "last", "both"), default="both",
                        help="Which segment of a combined credit is the main one (default: both).")
    parser.add_argument("--limit", type=int, default=None, help="Only examine this many tracks.")
    parser.add_argument("--contains", default=None,
                        help="Only examine tracks whose artist/albumartist contains this text.")
    parser.add_argument("--show", type=int, default=15, help="Examples per section (default: 15).")
    args = parser.parse_args()

    rows = _load_rows(args.limit, args.contains)
    if not rows:
        print("No matching tracks found.")
        return 1
    print(f"Loaded {len(rows)} tracks with an artist tag"
          + (f" matching {args.contains!r}" if args.contains else ""))

    preferences = [False, True] if args.preference == "both" else [args.preference == "last"]
    for prefer_last in preferences:
        _report(_resolve_all(rows, prefer_last), prefer_last, args.show)

    if args.preference == "both":
        first = _resolve_all(rows, False)
        last = _resolve_all(rows, True)
        differing = [(f[0], f[1], l[1]) for f, l in zip(first, last) if f[1] != l[1]]
        print(f"\n{'=' * 78}\nfirst vs last: {len(differing)} tracks resolve differently\n{'=' * 78}")
        seen = set()
        for row, first_value, last_value in differing:
            key = (first_value, last_value)
            if key in seen:
                continue
            seen.add(key)
            print(f"  {row['artist']!r}\n      first -> {first_value!r}\n      last  -> {last_value!r}")
            if len(seen) >= args.show:
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
