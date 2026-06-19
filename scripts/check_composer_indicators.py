"""
Scan a text file line-by-line for composer indicator matches.

Uses `library_data.composer.ComposersData` and reports which lines contain
one or more composer indicators. By default writes a sibling output file
containing all lines with no composer-indicator match, in original order.

With --invert, writes composer names that have no indicator match anywhere
in the input file.

Run from repo root:
  python scripts/check_composer_indicators.py /path/to/input.txt
  python scripts/check_composer_indicators.py /path/to/input.txt --invert
"""

import argparse
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from library_data.composer import ComposersData


def build_indicator_rows(composers_data):
    rows = []
    for composer in composers_data._composers.values():
        for indicator in composer.indicators:
            cleaned = indicator.strip()
            if cleaned:
                rows.append((composer.name, cleaned, cleaned.lower()))

    # Prefer longer indicators first to reduce noisy short matches.
    rows.sort(key=lambda row: len(row[1]), reverse=True)
    return rows


def scan_file(file_path, indicator_rows):
    total_matches = 0
    matched_lines = 0
    unmatched_lines = []

    with open(file_path, "r", encoding="utf-8") as f:
        for line_number, raw_line in enumerate(f, start=1):
            line = raw_line.rstrip("\n")
            line_lower = line.lower()
            composer_to_indicators = {}

            for composer_name, indicator, indicator_lower in indicator_rows:
                if indicator_lower in line_lower:
                    if composer_name not in composer_to_indicators:
                        composer_to_indicators[composer_name] = set()
                    composer_to_indicators[composer_name].add(indicator)

            if composer_to_indicators:
                matched_lines += 1
                total_matches += len(composer_to_indicators)
                for composer_name in sorted(composer_to_indicators.keys()):
                    indicators = sorted(composer_to_indicators[composer_name], key=len, reverse=True)
                    indicators_str = ", ".join(indicators)
                    print(
                        f"Line {line_number} | composer: {composer_name} | "
                        f"indicator(s): {indicators_str} | text: {line}"
                    )
            else:
                unmatched_lines.append(raw_line)

    return matched_lines, total_matches, unmatched_lines


def find_matched_composers(file_path, indicator_rows):
    matched_composers = set()

    with open(file_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line_lower = raw_line.lower()
            for composer_name, indicator, indicator_lower in indicator_rows:
                if indicator_lower in line_lower:
                    matched_composers.add(composer_name)

    return matched_composers


def get_composers_not_in_file(composers_data, matched_composers):
    return sorted(
        name for name in composers_data.get_composer_names()
        if name not in matched_composers
    )


def get_unmatched_lines_output_path(input_file):
    input_dir = os.path.dirname(input_file)
    input_name = os.path.basename(input_file)
    stem, ext = os.path.splitext(input_name)
    return os.path.join(input_dir, f"{stem}_non_composer_lines{ext or '.txt'}")


def get_composers_not_in_file_output_path(input_file):
    input_dir = os.path.dirname(input_file)
    input_name = os.path.basename(input_file)
    stem, ext = os.path.splitext(input_name)
    return os.path.join(input_dir, f"{stem}_composers_not_in_file{ext or '.txt'}")


def write_lines(output_path, lines):
    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def write_composer_names(output_path, composer_names):
    with open(output_path, "w", encoding="utf-8") as f:
        for name in composer_names:
            f.write(name + "\n")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Check a text file for matches against composer indicators."
    )
    parser.add_argument("input_file", help="Path to text file to scan")
    parser.add_argument(
        "--invert",
        action="store_true",
        help=(
            "Write composer names with no indicator found in the input file "
            "instead of input lines with no composer match."
        ),
    )
    return parser.parse_args()


def main():
    args = parse_args()
    input_file = args.input_file

    if not os.path.isfile(input_file):
        print(f"Error: file not found: {input_file}")
        sys.exit(1)

    composers_data = ComposersData()
    indicator_rows = build_indicator_rows(composers_data)

    if args.invert:
        matched_composers = find_matched_composers(input_file, indicator_rows)
        composers_not_in_file = get_composers_not_in_file(composers_data, matched_composers)
        output_path = get_composers_not_in_file_output_path(input_file)
        write_composer_names(output_path, composers_not_in_file)

        print("\nDone.")
        print(f"Composers matched in file: {len(matched_composers)}")
        print(f"Composers not in file written: {len(composers_not_in_file)}")
        print(f"Output file: {output_path}")
    else:
        matched_lines, total_matches, unmatched_lines = scan_file(
            input_file, indicator_rows
        )
        output_path = get_unmatched_lines_output_path(input_file)
        write_lines(output_path, unmatched_lines)

        print("\nDone.")
        print(f"Matched lines: {matched_lines}")
        print(f"Total indicator matches: {total_matches}")
        print(f"Non-matching lines written: {len(unmatched_lines)}")
        print(f"Output file: {output_path}")


if __name__ == "__main__":
    main()
