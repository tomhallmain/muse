"""
Populate mb_failed_lookups from two sources:

  1. Blank rows in mb_recordings  (--from-db, on by default)
     Before mb_failed_lookups existed, enrich_recordings() wrote an all-empty
     row to mb_recordings for every MBID whose /recording/ endpoint returned
     an error.  Those rows are indistinguishable from a legitimate recording
     that simply has no credits, and they block re-processing because
     MusicBrainzCache.__contains__ returns True.
     Heuristic: mb_title = '' AND mb_artist = ''
     A successfully-fetched recording always has at least a title from
     MusicBrainz, so that pair being empty reliably marks a failed fetch.

  2. A musicbrainz_api log file  (--log-file PATH)
     Parses WARNING lines of the form:
       Could not fetch recording <uuid>: <error>
     404 errors set status_code=404; timeouts and other transient errors set
     status_code=NULL.  Note: timeout failures (status_code NULL) will be
     skipped by future enrichment runs just like permanent 404s — remove them
     from mb_failed_lookups manually if you want to retry those MBIDs.
     MBIDs that already have a successful (non-empty) row in mb_recordings are
     skipped, as a later run may have resolved them.

Both sources use INSERT OR IGNORE, so re-running is always safe.
Blank rows migrated from mb_recordings are deleted from that table afterwards.

Run from the workspace root:
    python scripts/migrate_mb_failed_lookups.py [--dry-run] [--log-file PATH]
    python scripts/migrate_mb_failed_lookups.py --log-file failed_mbids.log
    python scripts/migrate_mb_failed_lookups.py --no-db --log-file path/to/app.log
"""

import argparse
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import get_connection

# ── argument parsing ──────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(
    description=__doc__,
    formatter_class=argparse.RawDescriptionHelpFormatter,
)
parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Report what would be changed without writing anything.",
)
parser.add_argument(
    "--no-db",
    action="store_true",
    help="Skip the blank-row migration from mb_recordings.",
)
parser.add_argument(
    "--log-file",
    metavar="PATH",
    help="Path to a musicbrainz_api log file to parse for failed MBIDs.",
)
args = parser.parse_args()

conn = get_connection()

# ── helpers ───────────────────────────────────────────────────────────────────

def _print_section(title: str) -> None:
    print(f"\n── {title} {'─' * max(0, 60 - len(title))}")


def _sample(rows: list, n: int = 20) -> None:
    for row in rows[:n]:
        mbid = row["mbid"] if hasattr(row, "keys") else row[0]
        print(f"  {mbid}")
    if len(rows) > n:
        print(f"  ... and {len(rows) - n} more.")


# ── phase 1: blank-row migration from mb_recordings ──────────────────────────

if not args.no_db:
    _print_section("Phase 1: blank rows in mb_recordings")

    blank_rows = conn.execute(
        "SELECT mbid, fetched_at FROM mb_recordings WHERE mb_title = '' AND mb_artist = ''"
    ).fetchall()

    print(f"Found {len(blank_rows)} blank row(s) (likely failed lookups).")

    if blank_rows:
        if args.dry_run:
            print("Dry-run — no changes written.")
            _sample(blank_rows)
        else:
            conn.executemany(
                "INSERT OR IGNORE INTO mb_failed_lookups "
                "(mbid, endpoint, status_code, failed_at) VALUES (?, 'recording', NULL, ?)",
                [(row["mbid"], row["fetched_at"]) for row in blank_rows],
            )
            inserted = conn.execute("SELECT changes()").fetchone()[0]

            conn.executemany(
                "DELETE FROM mb_recordings WHERE mbid = ?",
                [(row["mbid"],) for row in blank_rows],
            )
            deleted = conn.execute("SELECT changes()").fetchone()[0]
            conn.commit()

            print(f"Inserted {inserted} row(s) into mb_failed_lookups.")
            print(f"Deleted  {deleted} blank row(s) from mb_recordings.")

# ── phase 2: log-file parsing ─────────────────────────────────────────────────

if args.log_file:
    _print_section("Phase 2: log-file parsing")

    LOG_LINE_RE = re.compile(
        r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+)'          # timestamp
        r'\s+-\s+\S+\s+-\s+WARNING\s+-\s+'
        r'Could not fetch recording '
        r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'  # uuid
        r': (.+)$'                                                # error message
    )

    def _parse_ts(ts_str: str) -> float:
        return datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S,%f").timestamp()

    def _status_code(error_msg: str):
        return 404 if error_msg.startswith("Not found:") else None

    # Collect unique MBIDs; keep earliest timestamp per MBID.
    seen: dict = {}  # mbid → (failed_at_float, status_code)
    line_count = 0
    match_count = 0

    try:
        with open(args.log_file, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line_count += 1
                m = LOG_LINE_RE.match(line.rstrip())
                if not m:
                    continue
                match_count += 1
                ts_str, mbid, error_msg = m.group(1), m.group(2), m.group(3)
                failed_at = _parse_ts(ts_str)
                status = _status_code(error_msg)
                if mbid not in seen or failed_at < seen[mbid][0]:
                    seen[mbid] = (failed_at, status)
    except OSError as exc:
        print(f"Error reading log file: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanned {line_count} line(s), matched {match_count} WARNING(s), "
          f"{len(seen)} unique MBID(s).")

    if not seen:
        print("No failed MBIDs found in log.")
    else:
        # Skip MBIDs that have a successful (non-empty) record in mb_recordings —
        # a later enrichment run may have resolved them after the log was written.
        successful_mbids = {
            row[0] for row in conn.execute(
                "SELECT mbid FROM mb_recordings WHERE mb_title != '' OR mb_artist != ''"
            ).fetchall()
        }
        already_failed = {
            row[0] for row in conn.execute(
                "SELECT mbid FROM mb_failed_lookups"
            ).fetchall()
        }

        to_insert = [
            (mbid, failed_at, status)
            for mbid, (failed_at, status) in seen.items()
            if mbid not in successful_mbids and mbid not in already_failed
        ]
        skipped_success = sum(1 for mbid in seen if mbid in successful_mbids)
        skipped_known = sum(
            1 for mbid in seen
            if mbid not in successful_mbids and mbid in already_failed
        )

        print(f"  {skipped_success} already have a successful mb_recordings row — skipped.")
        print(f"  {skipped_known} already in mb_failed_lookups — skipped.")
        print(f"  {len(to_insert)} new failed MBID(s) to insert.")

        if to_insert:
            if args.dry_run:
                print("Dry-run — no changes written.")
                print("\nSample MBIDs that would be inserted:")
                for mbid, failed_at, status in to_insert[:20]:
                    sc = str(status) if status is not None else "NULL"
                    ts = datetime.fromtimestamp(failed_at).strftime("%Y-%m-%d %H:%M:%S")
                    print(f"  {mbid}  status={sc}  failed_at={ts}")
                if len(to_insert) > 20:
                    print(f"  ... and {len(to_insert) - 20} more.")
            else:
                conn.executemany(
                    "INSERT OR IGNORE INTO mb_failed_lookups "
                    "(mbid, endpoint, status_code, failed_at) VALUES (?, 'recording', ?, ?)",
                    [(mbid, status, failed_at) for mbid, failed_at, status in to_insert],
                )
                inserted = conn.execute("SELECT changes()").fetchone()[0]
                conn.commit()
                print(f"Inserted {inserted} row(s) into mb_failed_lookups.")

# ── summary ───────────────────────────────────────────────────────────────────

if not args.dry_run:
    total = conn.execute("SELECT COUNT(*) FROM mb_failed_lookups").fetchone()[0]
    not_found = conn.execute(
        "SELECT COUNT(*) FROM mb_failed_lookups WHERE status_code = 404"
    ).fetchone()[0]
    transient = conn.execute(
        "SELECT COUNT(*) FROM mb_failed_lookups WHERE status_code IS NULL"
    ).fetchone()[0]
    _print_section("mb_failed_lookups totals")
    print(f"  Total rows : {total}")
    print(f"  404 (permanent) : {not_found}")
    print(f"  NULL (transient/unknown) : {transient}")
