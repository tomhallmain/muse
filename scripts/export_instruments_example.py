"""
Overwrite library_data/data/instruments_example.json with current instruments
from the DB.

Safety: if the DB instrument count is significantly lower than the existing
example file count, exit with status 1 (avoids accidentally wiping the seed
dataset).

Note: instruments_example.json has historically been a flat JSON array of
names (no transliterations/notes) -- utils/db.py's seeding still reads that
format. Running this script switches it to the name-keyed object format
Form/Genre/Artist already use, so future edits (transliterations/notes) made
via the Instruments window are preserved on the next export. Both formats are
still accepted when loading, so this is not a breaking change for anyone else
reading the file.

Run from the workspace root:
    python scripts/export_instruments_example.py
    python scripts/export_instruments_example.py --dry-run
    python scripts/export_instruments_example.py --min-ratio 0.8
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from library_data.instrument import InstrumentsData

EXAMPLE_PATH = (
    Path(__file__).resolve().parent.parent / "library_data" / "data" / "instruments_example.json"
)
DEFAULT_MIN_RATIO = 0.5


def _load_example_names(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return set(data)
    if isinstance(data, dict):
        return set(data.keys())
    raise SystemExit(f"Expected array or object in {path}, got {type(data).__name__}")


def _instruments_to_seed_dict(instruments_data: InstrumentsData) -> dict:
    seed = {}
    for instrument in instruments_data.get_all_instruments():
        seed[instrument.name] = instrument.to_json()
    return seed


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report counts and what would be written without modifying the file.",
    )
    parser.add_argument(
        "--min-ratio",
        type=float,
        default=DEFAULT_MIN_RATIO,
        metavar="RATIO",
        help=(
            "Abort if DB instrument count / example instrument count is below this "
            f"ratio (default: {DEFAULT_MIN_RATIO})."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=EXAMPLE_PATH,
        help=f"Path to write (default: {EXAMPLE_PATH})",
    )
    args = parser.parse_args()

    if args.min_ratio <= 0 or args.min_ratio > 1:
        print(f"error: --min-ratio must be in (0, 1], got {args.min_ratio}", file=sys.stderr)
        return 1

    example_names = _load_example_names(args.output)
    example_count = len(example_names)
    instruments_data = InstrumentsData()
    seed = _instruments_to_seed_dict(instruments_data)
    db_count = len(seed)
    db_names = set(seed.keys())
    new_names = sorted(db_names - example_names)
    removed_names = sorted(example_names - db_names)

    print(f"Example instruments ({args.output}): {example_count}")
    print(f"DB instruments: {db_count}")
    print(f"New instruments: {len(new_names)}")
    for name in new_names[:10]:
        print(f"  {name}")
    if len(new_names) > 10:
        print(f"  ... and {len(new_names) - 10} more")
    print(f"Removed instruments: {len(removed_names)}")
    for name in removed_names[:10]:
        print(f"  {name}")
    if len(removed_names) > 10:
        print(f"  ... and {len(removed_names) - 10} more")

    if example_count > 0:
        ratio = db_count / example_count
        print(f"Ratio (DB / example): {ratio:.2%}")
        if ratio < args.min_ratio:
            print(
                f"error: DB instrument count ({db_count}) is significantly lower than "
                f"example count ({example_count}); "
                f"ratio {ratio:.2%} < min {args.min_ratio:.0%}. "
                f"Refusing to overwrite. Use --min-ratio to adjust.",
                file=sys.stderr,
            )
            return 1

    if args.dry_run:
        print(f"Dry run — would write {db_count} instruments to {args.output}")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8", newline="\n") as f:
        json.dump(seed, f, indent=4, ensure_ascii=True)
        f.write("\n")

    print(f"Wrote {db_count} instruments to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
