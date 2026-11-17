"""
Report how the composer values stored for the library's tracks resolve against
the composer data, and how much merging them would reduce composer-group
fragmentation. The script writes nothing itself; loading the composer data runs
the same pending seed sync and data fixes the app runs on start, if any are due.

Calls ComposersData.resolve_composer_tag directly, so what is reported is what
the resolution would do -- not a reimplementation of it.

The media_tracks table does not record where a composer value came from: it can
be the file's own tag ("Bach, Johann Sebastian") or a value the app derived from
title, album and artist when the tag was empty ("Johann Sebastian Bach"). Both
are examined.

Run from the workspace root:
    python scripts/check_composer_tags.py
    python scripts/check_composer_tags.py --show 50
    python scripts/check_composer_tags.py --contains Bach
"""

import argparse
import collections
import os
import sys

# A Windows console defaults to cp1252, which cannot encode accented characters
# in composer names; printing one raises UnicodeEncodeError.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3

from library_data.composer import ComposersData, composers_data
from utils.db import get_connection

HOWS = (ComposersData.TAG_DIRECT, ComposersData.TAG_INVERTED, ComposersData.TAG_LIST,
        ComposersData.TAG_AMBIGUOUS, ComposersData.TAG_PLACEHOLDER, ComposersData.TAG_UNMATCHED)


def _load_rows(limit, contains):
    sql = ("SELECT filepath, composer, album FROM media_tracks "
           "WHERE composer IS NOT NULL AND composer != ''")
    params = []
    if contains:
        sql += " AND composer LIKE ?"
        params.append(f"%{contains}%")
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    return list(conn.execute(sql, params))


def _resolve_values(rows):
    """Resolve each distinct stored value once: value -> (names, how, track count, sample album)."""
    counts = collections.Counter(row["composer"].strip() for row in rows)
    albums = {}
    for row in rows:
        albums.setdefault(row["composer"].strip(), row["album"] or "")
    return {value: (*composers_data.resolve_composer_tag(value), count, albums[value])
            for value, count in counts.items()}


def _section(title, items, show, line):
    if not items:
        return
    print(f"\n--- {title}: {len(items)} distinct value(s), "
          f"{sum(item[1][2] for item in items)} track(s); showing {min(show, len(items))} ---")
    for value, resolved in items[:show]:
        print(line(value, resolved))


def _report(resolved, show):
    total_tracks = sum(count for _names, _how, count, _album in resolved.values())
    by_how = collections.Counter()
    for _names, how, count, _album in resolved.values():
        by_how[how] += count
    print(f"\nResolution ({total_tracks} tracks, {len(resolved)} distinct composer values):")
    for how in HOWS:
        n = by_how[how]
        pct = (n / total_tracks * 100) if total_tracks else 0
        print(f"  {how:10s} {n:7d}  {pct:5.1f}%")

    groups_after = {tuple(names) if how not in (ComposersData.TAG_AMBIGUOUS, ComposersData.TAG_PLACEHOLDER,
                                                ComposersData.TAG_UNMATCHED) else (value,)
                    for value, (names, how, _count, _album) in resolved.items()}
    changed = [(v, r) for v, r in resolved.items()
               if r[1] in (ComposersData.TAG_INVERTED, ComposersData.TAG_LIST)
               or (r[1] == ComposersData.TAG_DIRECT and r[0] != [v])]
    print("\nGrouping impact:")
    print(f"  distinct composer values (today) : {len(resolved)}")
    print(f"  distinct composer groups (after) : {len(groups_after)}")
    if resolved:
        drop = len(resolved) - len(groups_after)
        print(f"  reduction                        : {drop} ({drop / len(resolved) * 100:.1f}%)")
    print(f"  tracks whose value changes       : {sum(r[2] for _v, r in changed)}")

    def by_tracks(how):
        return sorted(((v, r) for v, r in resolved.items() if r[1] == how), key=lambda vr: -vr[1][2])

    renamed = sorted(((v, r) for v, r in resolved.items()
                      if r[1] == ComposersData.TAG_DIRECT and r[0] != [v]), key=lambda vr: -vr[1][2])
    _section("matched an indicator, stored under another spelling", renamed, show,
             lambda v, r: f"  {v!r}  ({r[2]} tracks)\n      -> {r[0][0]!r}")
    _section("'Surname, given names'", by_tracks(ComposersData.TAG_INVERTED), show,
             lambda v, r: f"  {v!r}  ({r[2]} tracks)\n      -> {r[0][0]!r}")
    _section("several composers", by_tracks(ComposersData.TAG_LIST), show,
             lambda v, r: f"  {v!r}  ({r[2]} tracks)\n      -> {', '.join(repr(n) for n in r[0])}")
    _section("REVIEW: fits more than one composer", by_tracks(ComposersData.TAG_AMBIGUOUS), show,
             lambda v, r: f"  {v!r}  ({r[2]} tracks)\n      candidates: {', '.join(r[0])}")
    _section("REVIEW: no composer found -- candidates for new indicators or composers",
             by_tracks(ComposersData.TAG_UNMATCHED), show,
             lambda v, r: f"  {v!r}  ({r[2]} tracks)" + (f"  e.g. album {r[3]!r}" if r[3] else ""))

    absorbed = collections.defaultdict(set)
    for value, (names, how, _count, _album) in resolved.items():
        if how in (ComposersData.TAG_DIRECT, ComposersData.TAG_INVERTED) and names:
            absorbed[names[0]].add(value)
    multi = sorted(((name, values) for name, values in absorbed.items() if len(values) > 1),
                   key=lambda nv: -len(nv[1]))
    if multi:
        print(f"\n--- merged groups: {len(multi)} composers absorb >1 stored value ---")
        print("  Large counts are the intended win; check the top few are really one composer.")
        for name, values in multi[:show]:
            print(f"  {name!r}  <- {len(values)} values")
            for value in sorted(values)[:3]:
                print(f"        {value!r}")
            if len(values) > 3:
                print(f"        ... and {len(values) - 3} more")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=None, help="Only examine this many tracks.")
    parser.add_argument("--contains", default=None,
                        help="Only examine tracks whose composer value contains this text.")
    parser.add_argument("--show", type=int, default=15, help="Examples per section (default: 15).")
    args = parser.parse_args()

    rows = _load_rows(args.limit, args.contains)
    if not rows:
        print("No matching tracks found.")
        return 1
    print(f"Loaded {len(rows)} tracks with a composer value"
          + (f" matching {args.contains!r}" if args.contains else ""))
    _report(_resolve_values(rows), args.show)
    return 0


if __name__ == "__main__":
    sys.exit(main())
