"""
Overwrite library_data/data/composers_example.json with current composers
from the DB.

This script writes a seed copy with EXCLUDED_SEED_KEYS stripped: fields that
are meaningful for the live DB (e.g. date_added, when a composer was actually
added to this install) but meaningless -- or actively misleading -- when
baked into a seed/example file distributed with the repo. Composer.from_json()
and utils/db.py's seeding already tolerate these keys being absent.

Safety: if the DB composer count is significantly lower than the existing
example file count, exit with status 1 (avoids accidentally wiping the seed
dataset).

Run from the workspace root:
    python scripts/export_composers_example.py
    python scripts/export_composers_example.py --dry-run
    python scripts/export_composers_example.py --min-ratio 0.8
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from library_data.composer import ComposersData

EXAMPLE_PATH = (
    Path(__file__).resolve().parent.parent / "library_data" / "data" / "composers_example.json"
)
DEFAULT_MIN_RATIO = 0.5
EXCLUDED_SEED_KEYS = ("date_added",)


def _load_example_names(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise SystemExit(f"Expected object in {path}, got {type(data).__name__}")
    return set(data.keys())


def _composers_to_seed_dict(composers_data: ComposersData) -> dict:
    seed = {}
    for composer in composers_data.get_all_composers():
        entry = composer.to_json()
        for key in EXCLUDED_SEED_KEYS:
            entry.pop(key, None)
        seed[composer.name] = entry
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
            "Abort if DB composer count / example composer count is below this "
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
    composers_data = ComposersData()
    seed = _composers_to_seed_dict(composers_data)
    source_count = len(seed)
    source_names = set(seed.keys())
    new_names = sorted(source_names - example_names)
    removed_names = sorted(example_names - source_names)

    print(f"DB composers: {source_count}")
    print(f"Example ({args.output}): {example_count} composers")
    print(f"New composers: {len(new_names)}")
    for name in new_names[:10]:
        print(f"  {name}")
    if len(new_names) > 10:
        print(f"  ... and {len(new_names) - 10} more")
    print(f"Removed composers: {len(removed_names)}")
    for name in removed_names[:10]:
        print(f"  {name}")
    if len(removed_names) > 10:
        print(f"  ... and {len(removed_names) - 10} more")

    if example_count > 0:
        ratio = source_count / example_count
        print(f"Ratio (DB / example): {ratio:.2%}")
        if ratio < args.min_ratio:
            print(
                f"error: DB composer count ({source_count}) is significantly lower "
                f"than example count ({example_count}); "
                f"ratio {ratio:.2%} < min {args.min_ratio:.0%}. "
                f"Refusing to overwrite. Use --min-ratio to adjust.",
                file=sys.stderr,
            )
            return 1

    if args.dry_run:
        print(f"Dry run — would write {source_count} composers to {args.output}")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8", newline="\n") as f:
        json.dump(seed, f, indent=4, ensure_ascii=True)
        f.write("\n")

    print(f"Wrote {source_count} composers to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
