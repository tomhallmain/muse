"""
Quality-management and batch-import passes over the composer data.

Composer data lives in the database, which is what both modes read by default;
pass --source to work against a standalone file in the same format instead.

`check` reports data-quality problems: blank or mis-spaced names, missing or
inconsistent indicators, missing/backwards/future dates, duplicate indicators,
and (with --possible-duplicates) fuzzy near-duplicate detection across names,
indicators and matching lifespans.

`import` takes a set of candidate composer names, works out which are already
in the library and which are genuinely new, and reports the split. Unlike the
Composers window's mass import, it can parse life dates out of the incoming
names and apply genres/notes to what it adds. It reports only unless --write is
passed, which writes the merged result to composers_swap.json for review.

`report` writes the ambiguous-indicator work list to markdown: indicators held by
several composers, and indicators that occur as a whole word inside a different
composer's name. Both cause extra composers to be attached to a track, and
neither is fixable in code — they need a judgement call per entry.

`merge` upserts a reviewed file back into the database, completing the import
round-trip. The file wins for the fields it carries; composers in the DB but not
in the file are left alone. Nothing is ever deleted.

Run from the workspace root:
    python scripts/manage_composers.py check
    python scripts/manage_composers.py check --possible-duplicates
    python scripts/manage_composers.py check --source library_data/data/composers_swap.json
    python scripts/manage_composers.py report
    python scripts/manage_composers.py report --stdout
    python scripts/manage_composers.py import --names "Fazil Say,Beat Furrer"
    python scripts/manage_composers.py import --file library_data/data/support/temp_codex_manesse.json \\
        --date-format wikilist --genres codex --notes codex="Codex Manesse" --write
    python scripts/manage_composers.py merge --dry-run
    python scripts/manage_composers.py merge
"""

import argparse
from copy import deepcopy
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logging_setup import get_logger

logger = get_logger(__name__)

from library_data.life_dates import LifeDates
from utils.name_ops import NameOps
from utils.utils import Utils

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SWAP_FILE = os.path.join(PROJECT_ROOT, "library_data", "data", "composers_swap.json")
AMBIGUITY_REPORT = os.path.join(PROJECT_ROOT, "docs", "ambiguous-composer-indicators.md")


def do_print(f, s):
    f.write(s + "\n")
    print(s)


def plain_composer_date_func(composer_date_string):
    """Name only -- strip any trailing dash- or parenthesis-delimited annotation."""
    if composer_date_string.strip() == "":
        return None, None
    composer = composer_date_string.strip()
    for separator in (" - ", " – ", " — "):
        if separator in composer:
            composer = composer.split(separator)[0].strip()
            break
    if " (" in composer:
        composer = composer[:composer.find(" (")].strip()
    return composer, None


def wikilist_composer_date_func(composer_date_string):
    """Wikipedia-list style: "Name (c. 1300-1360; other detail)" -> name + LifeDates."""
    if composer_date_string.strip() == "":
        return None, None
    composer = composer_date_string.strip()
    if ("-" not in composer and "–" not in composer) or "(" not in composer or not ")" in composer:
        return None, None
    dates_part = composer[composer.find("(")+1:composer.rfind(")")].strip()
    if ";" in dates_part:
        dates_part = dates_part[:dates_part.find(";")].strip()
    dates = LifeDates(dates_part)
    composer = composer[:composer.find("(")].strip()
    return composer, dates


class ComposersManager:
    @staticmethod
    def get_composers_dict(composers_dict_location=None):
        """Return composer data as {name: composer dict}.

        Reads from the database, which is the source of truth. Pass
        composers_dict_location to analyse a standalone file in the same format
        instead (a swap file, an export, a legacy composers.json).
        """
        if composers_dict_location is not None:
            with open(composers_dict_location, "r", encoding="UTF-8") as f:
                return json.load(f)
        from library_data.composer import ComposersData
        return {composer.name: composer.to_json()
                for composer in ComposersData().get_all_composers()}

    @staticmethod
    def get_composer_data(composers, id):
        for composer, data in composers.items():
            if id == data["id"]:
                return data
        raise Exception("No composer found with ID {0}".format(id))

    @staticmethod
    def quality_check(composers_dict_location=None, print_possible_duplicates=False):
        composers_dict = ComposersManager.get_composers_dict(composers_dict_location)

        # Date values check and Duplicate composer indicators

        all_composer_indicators = {}
        all_composer_dates = {}
        duplicate_composer_indicators = {}
        invalid_name_indicators = []
        no_indicators_names = []
        inconsistent_names_and_indicators = []
        no_date_values = []
        invalid_dates = []
        future_dates = []
        unknown_start_count = 0
        unknown_end_count = 0
        current_year = datetime.datetime.now().year

        for composer, data in composers_dict.items():
            composer_id = data["id"]
            composer_name = data["name"]
            indicators = data["indicators"]
            if composer_name.strip() == "" or "\t" in composer_name or composer_name.startswith(" ") or composer_name.endswith(" "):
                invalid_name_indicators.append((composer_id, composer))
            if len(indicators) == 0:
                no_indicators_names.append((composer_id, composer))
            if composer_name != composer or (len(indicators) > 0 and composer_name != indicators[0]):
                inconsistent_names_and_indicators.append((composer_id, composer))
            start_date = data["start_date"]
            end_date = data["end_date"]
            # -1 and None both mean "unknown"; records loaded from the database
            # normalise to -1, so testing None alone never fires. An unknown end
            # date is ordinary (living, or simply unrecorded), so only a composer
            # with neither date counts as having no date values.
            start_unknown = start_date in (None, -1)
            end_unknown = end_date in (None, -1)
            if start_unknown:
                unknown_start_count += 1
            if end_unknown:
                unknown_end_count += 1
            if start_unknown and end_unknown:
                no_date_values.append((composer_id, composer))
            elif not start_unknown and not end_unknown and start_date > end_date:
                invalid_dates.append((composer_id, composer))
            elif (not start_unknown and start_date > current_year) or \
                    (not end_unknown and end_date > current_year):
                future_dates.append((composer_id, composer))
            elif not start_unknown:
                dates = (start_date, end_date)
                if dates in all_composer_dates:
                    all_composer_dates[dates].append(composer_id)
                else:
                    all_composer_dates[(start_date, end_date)] = [composer_id]
            for indicator in indicators:
                if indicator in all_composer_indicators:
                    if indicator in duplicate_composer_indicators:
                        duplicate_composer_indicators[indicator].append(composer_id)
                    else:
                        duplicate_composer_indicators[indicator] = [all_composer_indicators[indicator], composer_id]
                else:
                    all_composer_indicators[indicator] = composer_id

        if len(invalid_name_indicators) > 0:
            print("\nComposers contain invalid space in name:")
            for composer_id, composer in invalid_name_indicators:
                print(f"Composer ID {composer_id}: {composer}")

        if len(no_indicators_names) > 0:
            print("\nComposers with no indicators:")
            for composer_id, composer in no_indicators_names:
                print(f"Composer ID {composer_id}: {composer}")

        if len(inconsistent_names_and_indicators) > 0:
            print("\nComposers with inconsistent names and indicators:")
            for composer_id, composer in inconsistent_names_and_indicators:
                print(f"Composer ID {composer_id}: {composer}")

        if len(no_date_values) > 0:
            print(f"\nComposers with neither a start nor an end date ({len(no_date_values)}):")
            for composer_id, composer in no_date_values:
                print(f"Composer ID {composer_id} {composer}")

        if len(invalid_dates) > 0:
            print("\nComposers with invalid start or end dates (start date is after end date):")
            for composer_id, composer in invalid_dates:
                print(f"Composer ID {composer_id}: {composer}")

        if len(future_dates) > 0:
            print("\nComposers with invalid future dates:")
            for composer_id, composer in future_dates:
                print(f"Composer ID {composer_id}: {composer}")

        print("")
        print(f"{len(composers_dict)} composers")
        print(f"{len(all_composer_indicators)} all composer indicators")
        print(f"{unknown_start_count} with an unknown start date, "
              f"{unknown_end_count} with an unknown end date")

        shared_ids = ComposersManager.get_shared_indexes(composers_dict)
        if len(shared_ids) > 0:
            # A duplicate id makes seeding drop a record: utils/db.py seeds with
            # INSERT OR IGNORE and the composers table has id as its primary key.
            print(f"\nDuplicate ids found ({len(shared_ids)}) -- these records are "
                  f"silently dropped when seeding a fresh database:")
            for idx, names in sorted(shared_ids.items()):
                print(f"  id {idx}: {', '.join(names)}")

        if len(duplicate_composer_indicators) > 0:
            print(f"\nDuplicate indicators found ({len(duplicate_composer_indicators)}):")
            for indicator, composers in duplicate_composer_indicators.items():
                composer_names = ", ".join([ComposersManager.get_composer_data(composers_dict, composer)["name"] for composer in composers])
                print(f"{indicator}: {composer_names}")

        collisions = ComposersManager.get_indicator_collisions(composers_dict)
        if len(collisions) > 0:
            affected = len(set().union(*collisions.values()))
            print(f"\n{len(collisions)} indicators also match another composer's name "
                  f"as a whole word, affecting {affected} composers.")
            print("Run `report` for the full breakdown.")


        # Matching date composers

        matching_date_composers = dict(filter((lambda date_composers: len(date_composers[1]) > 1), all_composer_dates.items()))
        matching_date_composers = Utils.sort_dictionary(matching_date_composers, key=lambda dates: dates[0])
        possible_duplicates = set()

        print("\nMatching date composers:")
        for dates, composer_ids in matching_date_composers.items():
            possible_duplicates = set()
            for i in range(0, len(composer_ids)):
                for j in range(i+1, len(composer_ids)):
                    if i >= j: continue
                    id_i = composer_ids[i]
                    id_j = composer_ids[j]
                    data_i = ComposersManager.get_composer_data(composers_dict, id_i)
                    data_j = ComposersManager.get_composer_data(composers_dict, id_j)
                    name_i = data_i["name"]
                    name_j = data_j["name"]
                    if name_i[0] == name_j[0]:
                        possible_duplicates.add((name_i, name_j))

            if len(possible_duplicates) > 0:
                print(f"{dates}")
                all_names = set()
                for name_i, name_j in possible_duplicates:
                    all_names.add(name_i)
                    all_names.add(name_j)

                print(", ".join(sorted(list(all_names))))

        print("")

        if print_possible_duplicates:
            ComposersManager.print_possible_duplicates(composers_dict, possible_duplicates, all_composer_indicators)

    @staticmethod
    def print_possible_duplicates(composers_dict, possible_duplicates, all_composer_indicators):
        all_composers_data_list = list(composers_dict.values())
        all_composers_data_list.sort(key=lambda composer: composer["start_date"] if composer["start_date"] else -1)

        for i in range(len(all_composers_data_list)):
            data_i = all_composers_data_list[i]
            upper_bound = min(len(all_composers_data_list), i + 20)
            if i == upper_bound or i-1 == upper_bound: break
            name_i = data_i["name"]
            id_i = data_i["id"]

            for j in range(i+1, upper_bound):
                if i >= j: continue
                data_j = all_composers_data_list[j]
                id_j = data_j["id"]

                if id_i == id_j: continue
                name_j = data_j["name"]

                if Utils.is_similar_strings(name_i, name_j):
                    possible_duplicates.add((id_i, id_j))

        all_composer_indicators_list = list(all_composer_indicators.keys())
        all_composer_indicators_list.sort()

        for i in range(len(all_composer_indicators_list)):
            indicator_i = all_composer_indicators_list[i]
            upper_bound = min(len(all_composer_indicators), i + 20)
            if i == upper_bound or i-1 == upper_bound: break
            for j in range(i+1, upper_bound):
                if i >= j: continue
                indicator_j = all_composer_indicators_list[j]
                composer_id_i = all_composer_indicators[indicator_i]
                composer_id_j = all_composer_indicators[indicator_j]
                if composer_id_i == composer_id_j: continue

                if Utils.is_similar_strings(indicator_i, indicator_j):
                    possible_duplicates.add((composer_id_i, composer_id_j))

        all_composer_indicators_list.sort(key=lambda n: NameOps.get_name_sort_key(n))
        for i in range(len(all_composer_indicators_list)):
            indicator_i = all_composer_indicators_list[i]
            upper_bound = min(len(all_composer_indicators), i + 20)
            if i == upper_bound or i-1 == upper_bound: break
            for j in range(i+1, upper_bound):
                if i <= j: continue
                indicator_j = all_composer_indicators_list[j]
                composer_id_i = all_composer_indicators[indicator_i]
                composer_id_j = all_composer_indicators[indicator_j]
                if composer_id_i == composer_id_j: continue

                if Utils.is_similar_strings(indicator_i, indicator_j):
                    possible_duplicates.add((composer_id_i, composer_id_j))

        possible_duplicates_list = []
        for (composer_id_i, composer_id_j) in possible_duplicates:
            composer_data_i = ComposersManager.get_composer_data(composers_dict, composer_id_i)
            composer_data_j = ComposersManager.get_composer_data(composers_dict, composer_id_j)
            possible_duplicates_list.append((composer_data_i, composer_data_j))

        possible_duplicates_list.sort(key=lambda x: x[0]["name"])
        possible_duplicates_dates_not_close = []

        friederich_wilhelms = set()
        giovanni_battistas = set()
        jean_baptistes = set()
        johanns = set()

        print("Possible duplicates found:")
        for (composer_data_i, composer_data_j) in possible_duplicates_list:
            composer_id_i = composer_data_i["id"]
            composer_id_j = composer_data_j["id"]
            name_i = composer_data_i["name"]
            name_j = composer_data_j["name"]
            composer_start_i = composer_data_i["start_date"]
            composer_start_j = composer_data_j["start_date"]
            is_close_dates = True # no way to know if we don't know the dates, so it may be
            if composer_start_i is not None and composer_start_j is not None:
                is_close_dates = False
                if composer_start_i != -1 and composer_start_j != -1:
                    if abs(composer_start_i - composer_start_j) < 20:
                        is_close_dates = True
            if name_i.startswith("Giovanni Battista") or name_j.startswith("Giovanni Battista"):
                giovanni_battistas.add(name_i)
                giovanni_battistas.add(name_j)
            elif name_i.startswith("Friedrich Wilhelm") or name_j.startswith("Friedrich Wilhelm"):
                friederich_wilhelms.add(name_i)
                friederich_wilhelms.add(name_j)
            elif name_i.startswith("Jean-Baptiste") or name_j.startswith("Jean-Baptiste"):
                jean_baptistes.add(name_i)
                jean_baptistes.add(name_j)
            elif name_i.startswith("Johann") or name_j.startswith("Johann"):
                johanns.add(name_i)
                johanns.add(name_j)
            else:
                text = f"{composer_id_i}: {name_i} <> {composer_id_j}: {name_j}"
                if is_close_dates:
                    print(text)
                else:
                    possible_duplicates_dates_not_close.append(text)


        print("\nPossible duplicates (dates NOT close)")
        for text in possible_duplicates_dates_not_close:
            print(text)

        print("\n\n--------------------------------------\n\n")
        print("Friedrich Wilhelm close matches found:")
        for name in friederich_wilhelms:
            print(name)

        print("\n\n--------------------------------------\n\n")
        print("Giovanni Battista / Jean-Baptiste / Johann close matches found:")
        for name in sorted(list(giovanni_battistas)):
            print(name)
        for name1 in sorted(list(jean_baptistes)):
            print(name1)
        for name2 in sorted(list(johanns)):
            print(name2)

    @staticmethod
    def get_shared_indexes(composers_dict):
        """Return {id: [names]} for ids held by more than one composer."""
        indexes = {}
        for data in composers_dict.values():
            indexes.setdefault(data["id"], []).append(data["name"])
        return {idx: names for idx, names in indexes.items() if len(names) > 1}

    @staticmethod
    def get_duplicate_indicators(composers_dict):
        """Return {indicator: [names]} for indicators held verbatim by several composers."""
        seen = {}
        dupes = {}
        for data in composers_dict.values():
            for indicator in data["indicators"]:
                key = indicator.lower()
                other = seen.get(key)
                if other is not None and other != data["name"]:
                    dupes.setdefault(indicator, {other}).add(data["name"])
                else:
                    seen[key] = data["name"]
        return {i: sorted(names) for i, names in dupes.items()}

    @staticmethod
    def get_indicator_collisions(composers_dict, min_length=4):
        """Return {indicator: {composer names it wrongly matches}}.

        An indicator collides when it occurs as a whole word inside a *different*
        composer's name or indicators. Because get_composers returns every match,
        such an indicator attaches its owner to those composers' tracks on top of
        the correct one.

        Uses the same word-boundary test as the live matcher, so this reports what
        actually happens rather than an approximation of it. Substring containment
        is checked first because it is a cheap superset of a boundary match.
        """
        holders = {}
        for data in composers_dict.values():
            for indicator in data["indicators"]:
                holders.setdefault(indicator, set()).add(data["name"])

        collisions = {}
        for indicator, owners in holders.items():
            if len(indicator) < min_length:
                continue
            lowered = indicator.lower()
            wrongly_matched = set()
            for data in composers_dict.values():
                if data["name"] in owners:
                    continue
                for other in data["indicators"]:
                    other_lower = other.lower()
                    if lowered in other_lower and NameOps.contains_on_word_boundary(other_lower, lowered):
                        wrongly_matched.add(data["name"])
                        break
            if wrongly_matched:
                collisions[indicator] = wrongly_matched
        return collisions

    @staticmethod
    def build_ambiguity_report(composers_dict):
        """Return the ambiguous-indicator report as markdown text."""
        def life(data):
            fmt = lambda v: "?" if v in (None, -1) else str(v)
            return f"{fmt(data['start_date'])}–{fmt(data['end_date'])}"

        by_name = {data["name"]: data for data in composers_dict.values()}
        dupes = ComposersManager.get_duplicate_indicators(composers_dict)
        collisions = ComposersManager.get_indicator_collisions(composers_dict)
        holders = {}
        for data in composers_dict.values():
            for indicator in data["indicators"]:
                holders.setdefault(indicator, set()).add(data["name"])
        misordered = [d for d in composers_dict.values()
                      if d["indicators"] and d["indicators"][0] != d["name"]]

        lines = []
        add = lines.append
        add("# Ambiguous composer indicators")
        add("")
        add("An indicator is a string that identifies a composer in track text. "
            "`ComposersData.get_composers()` tests each indicator against the track "
            "title, album, artist and composer tag, and returns *every* match — so an "
            "ambiguous indicator does not pick the wrong composer, it attaches extra "
            "ones on top of the right one.")
        add("")
        add("Matching requires **word boundaries**, so collisions of mere position are "
            "already handled in code: `Bach` does not match *Erbach* or *Bachschmid*, "
            "`Barth` does not match *Bartholomäus*. What is listed here cannot be fixed "
            "by matching rules, because the indicator genuinely occurs as a whole word "
            "in another composer's name. Each entry needs a judgement call: narrow the "
            "indicator, drop it, or accept the collision.")
        add("")
        add(f"Generated from {len(composers_dict)} composers by "
            "`python scripts/manage_composers.py report`.")
        add("")
        add("## Class A — one indicator, several composers")
        add("")
        add(f"{len(dupes)} indicators are held verbatim by more than one composer. Every "
            "holder matches, so a track naming any of them is attributed to all of them.")
        add("")
        add("| Indicator | Held by |")
        add("|-----------|---------|")
        for indicator in sorted(dupes, key=str.lower):
            held = "<br>".join(
                f"`{by_name[n]['id']}` {n} ({life(by_name[n])})" for n in dupes[indicator])
            add(f"| `{indicator}` | {held} |")
        add("")
        add("## Class B — indicator is a whole word in another composer's name")
        add("")
        add("Read this direction: **the indicator in column 1 is falsely attached to "
            "tracks naming the composers in column 4.** Those composers do not hold the "
            "indicator; it appears as a separate word inside their own name.")
        add("")
        add("`Hermann` is the clearest case — held by Johann David Hermann, and also a "
            "middle name of many other composers. Word boundaries help none of these. "
            "Likewise `Bach` still matches the other Bachs, so a C. P. E. Bach track "
            "also gets J. S. Bach attached.")
        add("")
        affected = len(set().union(*collisions.values())) if collisions else 0
        add(f"{len(collisions)} indicators, affecting {affected} distinct composers.")
        add("")
        add("| Indicator | Held by | Falsely matches | Example composers wrongly attached |")
        add("|-----------|---------|-----------------|-------------------------------------|")
        for indicator, wrong in sorted(collisions.items(), key=lambda kv: (-len(kv[1]), kv[0].lower())):
            examples = "; ".join(sorted(wrong)[:3])
            if len(wrong) > 3:
                examples += f" … +{len(wrong) - 3}"
            add(f"| `{indicator}` | {', '.join(sorted(holders[indicator]))} | {len(wrong)} | {examples} |")
        add("")
        add("## Single-record inconsistencies")
        add("")
        add(f"{len(misordered)} composers have an indicator list whose first entry is not "
            "their own name. The convention enforced by `Composer.validate()` is that "
            "`indicators[0] == name`.")
        add("")
        for data in sorted(misordered, key=lambda d: d["name"]):
            fixed = [i for i in data["indicators"] if i != data["name"]]
            fixed.insert(0, data["name"])
            add(f"**{data['name']}** (`{data['id']}`)")
            add("")
            add(f"- current: `{data['indicators']}`")
            add(f"- expected: `{fixed}`")
            add("")
            add("  Harmless for matching, since every indicator is tested. But it is "
                "latent: editing this composer in the Composers window runs "
                "`validate()`, which silently reorders the list, producing a diff "
                "unrelated to whatever was actually edited.")
            add("")
        add("## Notes")
        add("")
        short = len([i for i in holders if " " not in i and len(i) <= 6])
        add(f"- {short} indicators are single words of 6 characters or fewer. With "
            "word-boundary matching these are no longer dangerous by position, but a "
            "bare surname still collides with every composer sharing it.")
        add("- Indicators differing only by diacritic (`Rosler`/`Rösler`) are listed "
            "separately because matching is not accent-folded at lookup time.")
        return "\n".join(lines) + "\n"

    @staticmethod
    def get_max_index(composers_dict):
        m = -1
        for data in composers_dict.values():
            idx = data["id"]
            if idx > m:
                m = idx
        return m

    @staticmethod
    def is_in_dict(composers_dict, value, strict=False):
        matches = []
        if strict:
            for composer_name, data in composers_dict.items():
                if composer_name == value or composer_name.endswith(" " + value) or (value + " ") in composer_name:
                    matches.append(data)
                    continue
                for indicator in data["indicators"]:
                    if indicator == value or indicator.endswith(" " + value) or (value + " ") in indicator or indicator in value:
                        matches.append(data)
                        break
        else:
            for composer_name, data in composers_dict.items():
                if value in composer_name:
                    matches.append(data)
                    continue
                for indicator in data["indicators"]:
                    if value in indicator or indicator in value:
                        matches.append(data)
                        break
        return matches

    @staticmethod
    def print_shared_indexes(composers_dict):
        # The database enforces id uniqueness, so this only turns up anything when
        # run against a file source (a swap file, an export, a legacy composers.json).
        indexes = {}
        for data in composers_dict.values():
            idx = data["id"]
            if idx in indexes:
                indexes[idx].append(data)
            else:
                indexes[idx] = [data]
        for idx, datas in indexes.items():
            if len(datas) > 1:
                names = [data["name"] for data in datas]
                print(names)

    @staticmethod
    def default_composer_date_func(composer_date_string):
        if composer_date_string.strip() == "":
            return None, None
        composer = composer_date_string.strip()
        if not " (" in composer or not ")" in composer:
            print("Dates not found: " + composer)
            return None, None
        line_parts = composer.split(" (")
        name = line_parts[0].strip()
        dates_string = line_parts[-1].replace(")", "").strip()
        try:
            dates = LifeDates(dates_string)
            return name, dates
        except Exception as e:
            print(f"{name} - {e}")
            return None, None

    @staticmethod
    def get_composers_with_dates_from_file(more_composers_file_loc, composer_date_func=default_composer_date_func):
        with open(more_composers_file_loc, "r", encoding="utf-8") as f:
            more_possible_composers = json.load(f)
        return ComposersManager.get_composers_with_dates(more_possible_composers, composer_date_func)

    @staticmethod
    def get_composers_with_dates(more_possible_composers_obj, composer_date_func=default_composer_date_func):
        composers_with_dates = {}

        if isinstance(more_possible_composers_obj, dict):
            for composer_name, other_data in more_possible_composers_obj.items():
                _, dates = composer_date_func(other_data)
                if composer_name is None:
                    continue
                composers_with_dates[composer_name] = dates
        elif isinstance(more_possible_composers_obj, list):
            for composer in more_possible_composers_obj:
                name, dates = composer_date_func(composer)
                if name is None:
                    continue
                composers_with_dates[name] = dates

        return composers_with_dates

    @staticmethod
    def get_full_name_and_no_space_composers(composers_with_dates):
        full_name_composers = {}
        no_space_composers = []

        for composer in composers_with_dates:
            if " " in composer:
                name_parts = composer.split(" ")
                last_name = name_parts[-1].strip()
                full_name_composers[composer] = last_name
            else:
                no_space_composers.append(composer)
                print("No space in composer: " + composer)

        return full_name_composers, no_space_composers

    @staticmethod
    def get_found_and_not_composers(composers_dict, composers_with_dates, full_name_composers, no_space_composers):
        found = {}
        maybe_false_positives = {}
        composers_not_found = []
        for full_name, last_name in full_name_composers.items():
            data = ComposersManager.is_in_dict(composers_dict, full_name, strict=True)
            if len(data) == 1:
                found[full_name] = data[0]
            elif len(data) > 1:
                maybe_false_positives[full_name] = data
            else:
                data = ComposersManager.is_in_dict(composers_dict, full_name)
                if len(data) > 0:
                    maybe_false_positives[full_name] = data
                else:
                    actual_last_name = NameOps.get_name_sort_key(full_name)
                    data = ComposersManager.is_in_dict(composers_dict, actual_last_name)
                    if len(data) > 0:
                        maybe_false_positives[full_name] = data
                    else:
                        composers_not_found.append(full_name)

        for name in no_space_composers:
            data = ComposersManager.is_in_dict(composers_dict, name, strict=True)
            if len(data) == 1:
                found[name] = data[0]
            elif len(data) > 1:
                maybe_false_positives[name] = data
            else:
                data = ComposersManager.is_in_dict(composers_dict, name)
                if len(data) > 0:
                    maybe_false_positives[name] = data
                else:
                    composers_not_found.append(name)

        composers_not_found_ii = {}

        with open("temp_output.txt", "w", encoding="utf-8") as f:
            # def get_composer_names(last_name_val=None, ordered_name_val=None):
            #     found_names = []
            #     for full_name, names in full_name_composers.items():
            #         last_name = names[0]
            #         if last_name_val is not None:
            #             if last_name == last_name_val:
            #                 found_names.append(ordered_name)
            #         elif ordered_name_val is not None:
            #             if ordered_name_val == ordered_name:
            #                 found_names.append(full_name)
            #     if len(found_names) > 0:
            #         return found_names
            #     return [last_name_val]

            do_print(f, "\n\nComposers Not Found:\n")
            for composer in composers_not_found:
                try:
                    dates = composers_with_dates[composer]
                    composers_not_found_ii[composer] = (composer, dates)
                    do_print(f, f"{composer} - {dates}")
                except Exception as e:
                    do_print(f, f"{composer} - ERROR {e}")

            do_print(f, "\n\nMaybe False Positives:\n")
            for name, data in maybe_false_positives.items():
                found_composer_names = [d["name"] for d in data]
                if len(found_composer_names) > 8:
                    found_composer_names = found_composer_names[:8] + ["..."]
                composer_names = ", ".join(found_composer_names)
                dates = composers_with_dates[name]
                do_print(f, f"{name} - {dates} - {composer_names}")
                composers_not_found_ii[name] = (name, dates)

            do_print(f, "\n\nFound:\n")
            for name, data in found.items():
                found_composer_name = data["name"]
                do_print(f, f"{name} - {found_composer_name}")

        return found, maybe_false_positives, composers_not_found_ii

    @staticmethod
    def add_composers(composers_with_dates={}, print_shared_indexes=False,
                      add_to_new_dict=False, new_genres=[], new_notes={}):
        composers_dict = ComposersManager.get_composers_dict()
        full_name_composers, no_space_composers = ComposersManager.get_full_name_and_no_space_composers(composers_with_dates)
        found, maybe_false_positives, composers_not_found = ComposersManager.get_found_and_not_composers(
            composers_dict, composers_with_dates, full_name_composers, no_space_composers)

        composers_list = []
        composers_list.extend(list(composers_not_found.keys()))
        composers_list.extend(list(composers_dict.keys()))
        composers_list.sort(key=lambda c: NameOps.get_full_name_sort_key(c))

        if print_shared_indexes:
            print("\n\nShared indexes:")
            ComposersManager.print_shared_indexes(composers_dict)
            print("\n")

        max_index = ComposersManager.get_max_index(composers_dict)
        print(f"\nMax index: {max_index}")
        print(f"Found: {len(found)}")
        print(f"Not Found: {len(composers_not_found)}")

        if add_to_new_dict:
            ComposersManager.add_to_new_dict(composers_dict, composers_list, composers_with_dates,
                                             found, composers_not_found, new_genres, new_notes)



    @staticmethod
    def add_to_new_dict(composers_dict, composers_list, composers_with_dates,
                        found, composers_not_found, new_genres=[], new_notes={}):

        # NOTE remember to add the fix - if composer dates already exist, set
        # dates_are_lifespan to true and dates_uncertain to false.

        # NOTE grab the parenthetical extra names from the wikilist as separate indicators

        # Also, go back over previously entered composers from before 1600 to
        # MAYBE set dates_uncertain to True.

        def get_composer_dates_from_found(composers_dict_name):
            for name, data in found.items():
                found_composer_name = data["name"]
                if found_composer_name == composers_dict_name:
                    dates = composers_with_dates[name]
                    print(f"found original name: {name} - {dates}")
                    return dates, True
            return None, False

        new_composers_dict = {}
        count_composers_added = 0
        count_composers_modified = 0

        id_count = ComposersManager.get_max_index(composers_dict) + 1
        for composer in composers_list:
            if composer in composers_dict:
                composer_data_orig = composers_dict[composer]
                if composer_data_orig["id"] is None or composer_data_orig["name"] is None or composer_data_orig["name"].strip() == "":
                    raise Exception("Invalid composer data: " + composer)
                dates, was_actually_found = get_composer_dates_from_found(composer)
                start_date = composer_data_orig["start_date"]
                end_date = composer_data_orig["end_date"]
                dates_are_lifespan = composer_data_orig["dates_are_lifespan"]
                dates_uncertain = composer_data_orig["dates_uncertain"]
                genres = composer_data_orig["genres"]
                notes = composer_data_orig["notes"]
                composer_modified = False
                if dates is not None:
                    if start_date is not None or end_date is not None:
                        print(f"Maybe conflicting dates found for composer: {composer}")
                    else:
                        start_date = dates.get_start_date()
                        end_date = dates.get_end_date()
                        dates_are_lifespan = dates.is_lifetime()
                        dates_uncertain = dates.is_uncertain
                        composer_modified = True
                if was_actually_found:
                    if len(new_genres) > 0:
                        genres.extend(new_genres)
                        genres = sorted(list(set(genres)))
                        composer_modified = True
                    if len(new_notes) > 0:
                        notes = {**notes, **new_notes}
                        composer_modified = True

                composer_data = {
                    "id": composer_data_orig["id"],
                    "name": composer_data_orig["name"],
                    "indicators": composer_data_orig["indicators"],
                    "start_date": start_date,
                    "end_date": end_date,
                    "dates_are_lifespan": dates_are_lifespan,
                    "dates_uncertain": dates_uncertain,
                    "genres": genres,
                    "works": composer_data_orig['works'],
                    "notes": notes
                }
                if composer_modified:
                    count_composers_modified += 1
            else:
                composer_data_pre = composers_not_found[composer]
                original_name_from_poster_data = composer_data_pre[0]
                dates = composer_data_pre[1]
                indicators = [composer]
                if composer != original_name_from_poster_data:
                    indicators.append(original_name_from_poster_data)
                if dates is not None:
                    start_date = dates.get_start_date()
                    end_date = dates.get_end_date()
                    dates_are_lifespan = dates.is_lifetime()
                    dates_uncertain = dates.is_uncertain
                else:
                    start_date = None
                    end_date = None
                    dates_are_lifespan = True
                    dates_uncertain = False
                composer_data = {
                    "id": id_count,
                    "name": composer,
                    "indicators": indicators,
                    "start_date": start_date,
                    "end_date": end_date,
                    "dates_are_lifespan": dates_are_lifespan,
                    "dates_uncertain": dates_uncertain,
                    "genres": new_genres[:],
                    "works": [],
                    "notes": deepcopy(new_notes),
                }
                id_count += 1
                count_composers_added += 1
            new_composers_dict[composer] = composer_data

        print("\n\n")
        print(f"Count composers added: {count_composers_added}")
        print(f"Count composers modified: {count_composers_modified}")
        print("\n")

        composers_swap_file = SWAP_FILE

        with open(composers_swap_file, "w", encoding="utf-8") as f:
            json.dump(new_composers_dict, f, indent=4)

        ComposersManager.quality_check(composers_swap_file, print_possible_duplicates=True)

        print(f"\nWrote {composers_swap_file}")
        print("Review it, then merge into the database with:")
        print(f"  python scripts/manage_composers.py merge --source {composers_swap_file}")


class _IdAllocator:
    """Hands out composer ids that are unique across the DB and this run.

    A file source never enforced id uniqueness, so it can carry the same id on
    two different composers; the DB's `id INTEGER PRIMARY KEY` rejects that. Any
    record whose id is already spoken for by a different name gets a fresh one.
    Safe because no table references composers(id) -- composers are referenced by
    name -- so the id is a pure surrogate.

    Resolution is two-pass so that only genuinely conflicting records move: every
    record that can keep its id claims it first, and fresh ids are handed out
    afterwards from what remains.
    """

    def __init__(self, existing_rows):
        self._owner = {row["id"]: name for name, row in existing_rows.items()
                       if row["id"] is not None}
        self._next = (max(self._owner) + 1) if self._owner else 1
        self.reassigned = []

    def resolve(self, composers):
        contested = []
        for composer in composers:
            owner = self._owner.get(composer.id)
            if composer.id is not None and (owner is None or owner == composer.name):
                self._owner[composer.id] = composer.name
            else:
                contested.append(composer)

        for composer in contested:
            original = composer.id
            while self._next in self._owner:
                self._next += 1
            composer.id = self._next
            self._owner[self._next] = composer.name
            self.reassigned.append((composer.name, original, composer.id))


def _existing_rows(conn):
    return {
        row["name"]: row
        for row in conn.execute(
            "SELECT id, name, indicators, start_date, end_date, dates_are_lifespan, "
            "dates_uncertain, genres, works, notes, date_added FROM composers"
        )
    }


def _differs(row, composer, delim):
    """True if the DB row's meaningful fields disagree with the file record."""
    if [x for x in (row["indicators"] or "").split(delim) if x] != list(composer.indicators):
        return True
    if [x for x in (row["genres"] or "").split(delim) if x] != list(composer.genres):
        return True
    if row["start_date"] != composer.start_date or row["end_date"] != composer.end_date:
        return True
    if bool(row["dates_are_lifespan"]) != bool(composer.dates_are_lifespan):
        return True
    if bool(row["dates_uncertain"]) != bool(composer.dates_uncertain):
        return True
    return json.loads(row["notes"] or "{}") != (composer.notes or {})


def merge_file_into_db(source, dry_run=False):
    """Upsert every composer in a composers.json-format file into the database.

    The file wins for the fields it carries; composers present in the DB but
    absent from the file are left alone -- nothing is deleted. Idempotent, but
    one-directional, so DB rows edited after the file was written would be
    reverted to the file's values.
    """
    from library_data.composer import Composer, ComposersData
    from utils.db import DELIM, get_connection

    if not os.path.isfile(source):
        print(f"error: source not found: {source}", file=sys.stderr)
        return 1

    with open(source, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        print(f"error: expected object in {source}, got {type(data).__name__}", file=sys.stderr)
        return 1

    # Same convention the DB seeding uses when a record carries no date_added.
    mtime_iso = datetime.datetime.fromtimestamp(os.path.getmtime(source)).isoformat()

    conn = get_connection()
    existing = _existing_rows(conn)

    composers = []
    for record in data.values():
        composer = Composer.from_json(record)
        if composer.date_added is None:
            composer.date_added = mtime_iso
        composers.append(composer)

    # Resolve ids across every record, not just the changed ones, so an
    # unchanged composer's id can never be handed to someone else.
    allocator = _IdAllocator(existing)
    allocator.resolve(composers)

    to_insert, to_update, rows = [], [], []
    for composer in composers:
        row = existing.get(composer.name)
        if row is None:
            to_insert.append(composer.name)
        elif _differs(row, composer, DELIM):
            to_update.append(composer.name)
        else:
            continue
        rows.append(ComposersData._composer_to_row_params(composer))

    print(f"Source ({source}): {len(data)} composers")
    print(f"DB composers table: {len(existing)}")
    print(f"To insert (missing from DB): {len(to_insert)}")
    for name in to_insert[:20]:
        print(f"  + {name}")
    if len(to_insert) > 20:
        print(f"  ... and {len(to_insert) - 20} more")
    print(f"To update (values differ): {len(to_update)}")
    for name in to_update[:20]:
        print(f"  ~ {name}")
    if len(to_update) > 20:
        print(f"  ... and {len(to_update) - 20} more")

    if allocator.reassigned:
        print(
            f"Reassigned ids ({len(allocator.reassigned)}) -- id was already held by "
            f"another composer (a file source allows duplicate ids, the DB does not):"
        )
        for name, old_id, new_id in allocator.reassigned:
            print(f"  # {name}: {old_id} -> {new_id}")

    only_in_db = sorted(set(existing) - set(data))
    if only_in_db:
        print(f"In DB but not in source ({len(only_in_db)}) -- left untouched:")
        for name in only_in_db[:20]:
            print(f"  . {name}")
        if len(only_in_db) > 20:
            print(f"  ... and {len(only_in_db) - 20} more")

    if not rows:
        print("\nNothing to do — DB already matches the source.")
        return 0

    if dry_run:
        print(f"\nDry run — would upsert {len(rows)} composer(s).")
        return 0

    try:
        conn.executemany(ComposersData._UPSERT_SQL, rows)
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"error: merge failed, rolled back: {e}", file=sys.stderr)
        return 1

    print(f"\nUpserted {len(rows)} composer(s) into the DB.")
    return 0


DATE_FORMATS = {
    "plain": plain_composer_date_func,
    "dates": ComposersManager.default_composer_date_func,
    "wikilist": wikilist_composer_date_func,
}


def _parse_notes(pairs):
    notes = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"error: --notes expects key=value, got {pair!r}")
        key, value = pair.split("=", 1)
        notes[key.strip()] = value.strip()
    return notes


def _split_csv(value):
    return [part.strip() for part in value.split(",") if part.strip()] if value else []


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="Report composer data-quality problems.")
    check.add_argument(
        "--source",
        default=None,
        help="File in composers.json format to check instead of the database.",
    )
    check.add_argument(
        "--possible-duplicates",
        action="store_true",
        help="Also run the (slower) fuzzy near-duplicate detection.",
    )

    importer = subparsers.add_parser("import", help="Reconcile candidate composers against the library.")
    source_group = importer.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--file",
        help="JSON file of candidate composers (array of strings, or name -> detail object).",
    )
    source_group.add_argument(
        "--names",
        help="Comma-separated candidate composer names.",
    )
    importer.add_argument(
        "--date-format",
        choices=sorted(DATE_FORMATS),
        default="dates",
        help=(
            "How to read life dates out of each candidate: 'dates' for "
            "\"Name (1685-1750)\", 'wikilist' for wiki-list entries with extra "
            "detail after a semicolon, 'plain' for names with no dates at all "
            "(default: dates)."
        ),
    )
    importer.add_argument(
        "--genres",
        default="",
        help="Comma-separated genres to apply to added/matched composers.",
    )
    importer.add_argument(
        "--notes",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Note to apply to added/matched composers; repeatable.",
    )
    importer.add_argument(
        "--print-shared-indexes",
        action="store_true",
        help="Report composers sharing an id (only possible against a file source).",
    )
    importer.add_argument(
        "--write",
        action="store_true",
        help=f"Write the merged result to {SWAP_FILE} for review (default: report only).",
    )

    reporter = subparsers.add_parser(
        "report", help="Write the ambiguous-indicator report to a markdown file."
    )
    reporter.add_argument(
        "--source",
        default=None,
        help="File in composers.json format to report on instead of the database.",
    )
    reporter.add_argument(
        "--output",
        default=AMBIGUITY_REPORT,
        help=f"Path to write (default: {AMBIGUITY_REPORT}).",
    )
    reporter.add_argument(
        "--stdout",
        action="store_true",
        help="Print the report instead of writing it to a file.",
    )

    merger = subparsers.add_parser(
        "merge", help="Upsert a reviewed composers file into the database."
    )
    merger.add_argument(
        "--source",
        default=SWAP_FILE,
        help=f"File in composers.json format to merge (default: {SWAP_FILE}).",
    )
    merger.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing to the DB.",
    )

    args = parser.parse_args()

    if args.command == "check":
        ComposersManager.quality_check(
            args.source, print_possible_duplicates=args.possible_duplicates
        )
        return 0

    if args.command == "report":
        composers_dict = ComposersManager.get_composers_dict(args.source)
        markdown = ComposersManager.build_ambiguity_report(composers_dict)
        if args.stdout:
            print(markdown)
            return 0
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8", newline="\n") as f:
            f.write(markdown)
        print(f"Wrote {args.output} ({len(composers_dict)} composers analysed)")
        return 0

    if args.command == "merge":
        return merge_file_into_db(args.source, dry_run=args.dry_run)

    date_func = DATE_FORMATS[args.date_format]
    if args.file:
        if not os.path.isfile(args.file):
            print(f"error: file not found: {args.file}", file=sys.stderr)
            return 1
        composers_with_dates = ComposersManager.get_composers_with_dates_from_file(
            args.file, composer_date_func=date_func
        )
    else:
        composers_with_dates = ComposersManager.get_composers_with_dates(
            _split_csv(args.names), composer_date_func=date_func
        )

    if not composers_with_dates:
        print("No candidate composers parsed from the input.")
        return 1

    print(f"Parsed {len(composers_with_dates)} candidate composer(s).")
    ComposersManager.add_composers(
        composers_with_dates,
        print_shared_indexes=args.print_shared_indexes,
        add_to_new_dict=args.write,
        new_genres=_split_csv(args.genres),
        new_notes=_parse_notes(args.notes),
    )
    if not args.write:
        print("\nReport only — pass --write to produce the swap file for review.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
