"""
Collect the life dates that the library's composer tags carry in a trailing
parenthesis -- "Bach, Johann Sebastian (1685-1750)" -- and propose them for the
composer seed (library_data/data/composers_example.json).

The name before the parenthesis is resolved with ComposersData.resolve_composer_tag.
The proposal is written as JSON in groups:

  fill         the seed entry has no dates yet, and every tag agrees
  differs      the seed entry has dates, and the tags give others
  conflicting  the tags disagree with each other
  not_in_seed  the name resolves to no single composer -- candidates for new entries
  implausible  dates that cannot be a life, e.g. ending before they start -- a tag error
  unparsed     a trailing parenthesis that holds no dates (an epithet, "arr. ...", a century)

The script writes only the proposal file. Loading the composer data runs the same
pending seed sync and data fixes the app runs on start, if any are due.

Run from the workspace root:
    python scripts/collect_composer_life_dates.py
    python scripts/collect_composer_life_dates.py --out composer_dates.json
"""

import argparse
import collections
import datetime
import json
import os
import re
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT_DIR)

import sqlite3

from library_data.composer import ComposersData, composers_data
from utils.db import get_connection

SEED_PATH = os.path.join(_ROOT_DIR, "library_data", "data", "composers_example.json")

_TRAILING_PARENTHESIS = re.compile(r"\(([^()]*)\)\s*$")
_CIRCA = r"(?:c\.?|ca\.?|circa)\s*"
# "1685-1750", "1675? - 1743", "c1470-c1525", "c. 1505-68", "fl.c1455-1485",
# "c1465-after 1535", "1450-1502/3", "1929-"
_DATE_RANGE = re.compile(
    rf"^(?P<fl>fl\.?\s*)?(?P<c1>{_CIRCA})?(?P<start>\d{{3,4}})(?P<a1>/\d{{1,4}})?\s*(?P<q1>\?)?"
    rf"\s*[-–—]\s*(?:(?P<rel>after|before)\s+)?"
    rf"(?:(?P<c2>{_CIRCA})?(?P<end>\d{{2,4}})(?P<a2>/\d{{1,4}})?\s*(?P<q2>\?)?)?$",
    re.IGNORECASE)
# "d. 1740", "d. after 1501?", "b. 1950", "fl. c. 1600"
_SINGLE_YEAR = re.compile(
    rf"^(?P<kind>d\.|died|b\.|born|fl\.)\s*(?:(?P<rel>after|before)\s+)?(?P<c>{_CIRCA})?"
    rf"(?P<year>\d{{3,4}})(?P<a>/\d{{1,4}})?\s*(?P<q>\?)?$",
    re.IGNORECASE)

IMPLAUSIBLE = "implausible"
UNRECOGNISED = "unrecognised"


def parse_dates(text):
    """((start, end, dates_are_lifespan, dates_uncertain), None), or (None, IMPLAUSIBLE / UNRECOGNISED).

    An unknown year is -1: "d. 1740" gives start -1, "1929-" end -1. A floruit
    ("fl.") is not a lifespan, and a single floruit year is used as start and end.
    A two-digit end year continues the start's century ("1505-68" ends in 1568).
    A range ending before it starts, or longer than 110 years, is implausible.
    """
    text = text.strip()
    match = _DATE_RANGE.match(text)
    if match:
        start = int(match["start"])
        end = -1
        if match["end"]:
            end = int(match["end"])
            if len(match["end"]) == 2:
                end += start // 100 * 100
                if end <= start:
                    end += 100
        uncertain = any(match[k] for k in ("q1", "q2", "c1", "c2", "a1", "a2", "rel"))
        if start < 500 or (end != -1 and not (start < end <= start + 110)):
            return None, IMPLAUSIBLE
        return (start, end, not match["fl"], uncertain), None
    match = _SINGLE_YEAR.match(text)
    if match:
        year = int(match["year"])
        if year < 500:
            return None, IMPLAUSIBLE
        uncertain = any(match[k] for k in ("q", "c", "a", "rel"))
        kind = match["kind"].lower()
        if kind in ("d.", "died"):
            return (-1, year, True, uncertain), None
        if kind in ("b.", "born"):
            return (year, -1, True, uncertain), None
        return (year, year, False, True), None
    return None, UNRECOGNISED


def _load_values():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT composer FROM media_tracks "
                        "WHERE composer IS NOT NULL AND composer LIKE '%(%)%'")
    return collections.Counter(row["composer"].strip() for row in rows)


def _dates_dict(dates):
    start, end, lifespan, uncertain = dates
    return {"start_date": start, "end_date": end,
            "dates_are_lifespan": lifespan, "dates_uncertain": uncertain}


def collect(values, seed):
    by_composer = collections.defaultdict(lambda: collections.defaultdict(list))
    not_in_seed, unparsed, implausible = [], [], []
    for value, tracks in sorted(values.items()):
        match = _TRAILING_PARENTHESIS.search(value)
        if not match:
            continue
        dates, problem = parse_dates(match.group(1))
        if dates is None:
            (implausible if problem == IMPLAUSIBLE else unparsed).append(
                {"value": value, "tracks": tracks})
            continue
        name_part = value[:match.start()].strip()
        names, how = composers_data.resolve_composer_tag(name_part)
        if how in (ComposersData.TAG_DIRECT, ComposersData.TAG_INVERTED) and len(names) == 1:
            by_composer[names[0]][dates].append((value, tracks))
        else:
            not_in_seed.append({"value": value, "name_part": name_part, "how": how,
                                "candidates": names, "tracks": tracks, **_dates_dict(dates)})

    fill, differs, conflicting = [], [], []
    for name, variants in sorted(by_composer.items()):
        summarized = [{**_dates_dict(dates), "tracks": sum(t for _v, t in found),
                       "values": [v for v, _t in found]}
                      for dates, found in variants.items()]
        if len(summarized) > 1:
            conflicting.append({"name": name, "variants": summarized})
            continue
        proposal = {"name": name, **summarized[0]}
        entry = seed.get(name)
        if entry is None:
            proposal["note"] = "composer is not in the seed file (added in this database only)"
            differs.append(proposal)
        elif entry.get("start_date", -1) == -1 and entry.get("end_date", -1) == -1:
            fill.append(proposal)
        elif (entry.get("start_date"), entry.get("end_date")) != (proposal["start_date"],
                                                                  proposal["end_date"]):
            proposal["seed"] = {k: entry.get(k) for k in
                                ("start_date", "end_date", "dates_are_lifespan", "dates_uncertain")}
            differs.append(proposal)
    return {"fill": fill, "differs": differs, "conflicting": conflicting,
            "not_in_seed": sorted(not_in_seed, key=lambda e: -e["tracks"]),
            "implausible": sorted(implausible, key=lambda e: -e["tracks"]),
            "unparsed": sorted(unparsed, key=lambda e: -e["tracks"])}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="temp_composer_life_dates.json",
                        help="Proposal file to write (default: %(default)s, which .gitignore "
                             "already excludes)")
    args = parser.parse_args()

    with open(SEED_PATH, encoding="utf-8") as f:
        seed = json.load(f)
    values = _load_values()
    if not values:
        print("No composer value with a parenthesis found.")
        return 1
    print(f"{len(values)} distinct composer values with a parenthesis "
          f"({sum(values.values())} tracks)")

    proposal = collect(values, seed)
    proposal = {"generated": datetime.datetime.now().isoformat(timespec="seconds"),
                "seed_file": os.path.relpath(SEED_PATH, _ROOT_DIR), **proposal}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(proposal, f, ensure_ascii=False, indent=2)

    for group in ("fill", "differs", "conflicting", "not_in_seed", "implausible", "unparsed"):
        print(f"  {group:12s} {len(proposal[group]):5d}")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
