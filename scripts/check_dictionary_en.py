"""
Scan a text file line-by-line for English dictionary word coverage.

Uses `tts/dictionary_en.txt`. A line is a match when at least 80% of its
space-separated tokens appear in the dictionary (case-insensitive lookup).
Lines between 60% and 80% are
reported as possible matches but are still written to the output file.

Run from repo root:
  python scripts/check_dictionary_en.py /path/to/input.txt

  python -m scripts.check_dictionary_en ~/Downloads/uniq_artists_non_composer_lines.tsv
"""

import argparse
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

DICTIONARY_PATH = os.path.join(PROJECT_ROOT, "tts", "dictionary_en.txt")
MATCH_RATIO = 0.80
POSSIBLE_RATIO = 0.60
MAX_UNKNOWN_IN_LINE = 12

# Common English names and music terms in dictionary_en.txt that do not count
# as dictionary hits and are omitted from "unknown", but still count in the
# line's token total for threshold percentages.
EXCLUDED_TOKENS = {
    "john", "johnny", "taylor", "jimmy", "jean", "hugh", "henry", "harry",
    "graham", "george", "arthur", "lewis", "lee", "will", "edwards", "todd",
    "young", "valentine", "tom", "tommy", "ted", "teddy", "smith", "troy",
    "russell", "toby", "jack", "tori", "kelly", "timothy", "walker", "tracy",
    "david", "wallace", "don", "david", "rosa", "elliott", "tony", "thomas",
    "peter", "paul", "rebecca", "pierre", "scott", "sean", "michael", "matt",
    "samara", "robert", "robin", "robert", "ronald", "ronnie", "ronny", "ron",
    "richard", "nick", "nicole", "nicolas", "nicholas", "raymond", "ryan",
    "oliver", "olivia", "guy", "frank", "francisco", "francine", "francis", 
    "mike", "matthew", "matilda", "martin", "reeves", "jane", "carl", "carol",
    "powell", "power", "perry", "patrick", "philip", "phillip", "phillips",
    "mark", "gordon", "gabriel", "gabrielle", "gabriella", "julian", "julie",
    "jenny", "jennifer", "jenn", "jennine", "diane", "denise", "dennis", "ruth",
    "claire", "claude", "claudette", "claudia", "miller", "millie", "molly",
    "mick", "foster", "max", "maxwell", "maxine", "marion", "barbara", "craig",
    "madden", "morris", "christian", "mason", "ben", "parry", "chad", "charlie",
    "charles", "charlotte", "charlene", "brian", "brianne", "brianna", "jess",
    "jessica", "glen", "roger", "davis", "gabby", "barrett", "bill", "dobbins",
    "anthony", "wilson", "powers", "austin", "brad", "bradley", "andy", "andrew",
    "hill", "hillary", "allen", "allan", "allen", "allison", "lisa", "moore", "ken",
    "thomson", "warner", "jasmine", "jason", "edward", "white", "eric", "erica",
    "erik", "erin", "eddie", "eddy", "edmund", "edwin", "edgar", "edgars",
    "adrian", "adrienne", "albert", "alice", "alicia", "amanda", "amber",
    "anne", "anna", "walter", "walt", "william", "vincent", "collard", "tyler",
    "rob", "nelson", "maria", "isabel", "isabelle", "georgia", "gerald",
    "geraldine", "earl", "louis", "stewart", "stuart", "stacey", "stacie",
    "dave", "dan", "daniel", "danielle", "curtis", "curt", "christie", "huff",
    "calvin", "hampton", "roland", "barry", "mills", "arnold",

    # Quality terms to keep    
    "symphony", "orchestra", "quartet", "trio", "ensemble", "band", "choir",
    "traditional", "early", "music",
}


def load_dictionary():
    with open(DICTIONARY_PATH, "r", encoding="utf-8") as f:
        return {line.strip().lower() for line in f if line.strip()}


def tokenize_line(line):
    return [token for token in line.split() if token]


def analyze_line(line, dictionary):
    words = tokenize_line(line)
    if not words:
        return 0.0, 0, 0, []

    dict_count = sum(
        1 for word in words
        if word.lower() not in EXCLUDED_TOKENS and word.lower() in dictionary
    )
    ratio = dict_count / len(words)

    seen = set()
    unknown = []
    for word in words:
        key = word.lower()
        if key in EXCLUDED_TOKENS:
            continue
        if key not in dictionary and key not in seen:
            seen.add(key)
            unknown.append(word)

    return ratio, dict_count, len(words), unknown


def format_unknown_words(unknown_words):
    if not unknown_words:
        return "-"
    if len(unknown_words) <= MAX_UNKNOWN_IN_LINE:
        return ", ".join(unknown_words)
    shown = ", ".join(unknown_words[:MAX_UNKNOWN_IN_LINE])
    return f"{shown}, ... (+{len(unknown_words) - MAX_UNKNOWN_IN_LINE})"


def format_match_line(line_number, label, ratio, dict_count, word_count, unknown_words, line):
    pct = int(round(ratio * 100))
    return (
        f"Line {line_number} | {label} | {pct}% ({dict_count}/{word_count}) | "
        f"unknown: {format_unknown_words(unknown_words)} | text: {line}"
    )


def print_collected_entries(title, entries):
    print(title)
    if not entries:
        print("  (none)")
        return
    for line_number, label, ratio, dict_count, word_count, unknown_words, line in entries:
        print(format_match_line(
            line_number, label, ratio, dict_count, word_count, unknown_words, line
        ))


def print_report(excluded_entries, included_entries):
    match_pct = int(MATCH_RATIO * 100)
    possible_pct = int(POSSIBLE_RATIO * 100)

    print_collected_entries(
        f"\n=== Excluded from output (>= {match_pct}%) ===\n",
        excluded_entries,
    )
    print("\n" + ("-" * 72) + "\n")
    print_collected_entries(
        f"=== Included in output (< {match_pct}%, >= {possible_pct}%) ===\n",
        included_entries,
    )


def scan_file(file_path, dictionary):
    excluded_entries = []
    included_entries = []
    output_lines = []

    with open(file_path, "r", encoding="utf-8") as f:
        for line_number, raw_line in enumerate(f, start=1):
            line = raw_line.rstrip("\n")
            ratio, dict_count, word_count, unknown_words = analyze_line(line, dictionary)
            entry = (
                line_number, "match", ratio, dict_count, word_count, unknown_words, line
            )

            if ratio >= MATCH_RATIO:
                excluded_entries.append(entry)
            elif ratio >= POSSIBLE_RATIO:
                included_entries.append((
                    line_number, "possible", ratio, dict_count, word_count, unknown_words, line
                ))
                output_lines.append(raw_line)
            else:
                output_lines.append(raw_line)

    sort_key = lambda entry: (-entry[2], entry[0])
    excluded_entries.sort(key=sort_key)
    included_entries.sort(key=sort_key)

    return excluded_entries, included_entries, output_lines


def get_output_path(input_file):
    input_dir = os.path.dirname(input_file)
    input_name = os.path.basename(input_file)
    stem, ext = os.path.splitext(input_name)
    return os.path.join(input_dir, f"{stem}_non_dictionary_lines{ext or '.txt'}")


def write_output_lines(output_path, lines):
    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Check a text file for English dictionary word coverage."
    )
    parser.add_argument("input_file", help="Path to text file to scan")
    return parser.parse_args()


def main():
    args = parse_args()
    input_file = args.input_file

    if not os.path.isfile(input_file):
        print(f"Error: file not found: {input_file}")
        sys.exit(1)
    if not os.path.isfile(DICTIONARY_PATH):
        print(f"Error: dictionary not found: {DICTIONARY_PATH}")
        sys.exit(1)

    dictionary = load_dictionary()
    excluded_entries, included_entries, output_lines = scan_file(input_file, dictionary)
    output_path = get_output_path(input_file)
    write_output_lines(output_path, output_lines)

    print_report(excluded_entries, included_entries)

    print("\nDone.")
    print(f"Match lines (>= {int(MATCH_RATIO * 100)}%): {len(excluded_entries)}")
    print(f"Possible lines ({int(POSSIBLE_RATIO * 100)}%-{int(MATCH_RATIO * 100) - 1}%): {len(included_entries)}")
    print(f"Lines written (< {int(MATCH_RATIO * 100)}%): {len(output_lines)}")
    print(f"Output file: {output_path}")


if __name__ == "__main__":
    main()
