"""
Scan a text file line-by-line for composer indicator matches.

Uses `library_data.composer.ComposersData` and reports which lines contain
one or more composer indicators. Also writes a sibling output file containing
all lines with no composer-indicator match, in original order.

Run from repo root:
  python scripts/check_composer_indicators.py /path/to/input.txt
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


def get_unmatched_output_path(input_file):
    input_dir = os.path.dirname(input_file)
    input_name = os.path.basename(input_file)
    stem, ext = os.path.splitext(input_name)
    return os.path.join(input_dir, f"{stem}_non_composer_lines{ext or '.txt'}")


def write_unmatched_lines(output_path, unmatched_lines):
    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(unmatched_lines)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Check a text file for matches against composer indicators."
    )
    parser.add_argument("input_file", help="Path to text file to scan")
    return parser.parse_args()


def main():
    args = parse_args()
    input_file = args.input_file

    if not os.path.isfile(input_file):
        print(f"Error: file not found: {input_file}")
        sys.exit(1)

    composers_data = ComposersData()
    indicator_rows = build_indicator_rows(composers_data)
    matched_lines, total_matches, unmatched_lines = scan_file(input_file, indicator_rows)
    unmatched_output_path = get_unmatched_output_path(input_file)
    write_unmatched_lines(unmatched_output_path, unmatched_lines)

    print("\nDone.")
    print(f"Matched lines: {matched_lines}")
    print(f"Total indicator matches: {total_matches}")
    print(f"Non-matching lines written: {len(unmatched_lines)}")
    print(f"Output file: {unmatched_output_path}")


if __name__ == "__main__":
    main()
