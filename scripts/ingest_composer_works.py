"""
Parse scraped IMSLP/Wikipedia work-list JSON files into Work rows and
attach them to already-known composers.

This is the ingestion pipeline the older temp_gather_composer_works.py /
temp_gather_composer_works_imslp.py scripts never actually built -- those
only validated scrape quality and never wrote anything to the database.

Deliberately conservative in two ways:

- A row whose title can't be confidently extracted is skipped rather than
  stored -- the scraped formats are too inconsistent (opus-dash-title vs
  comma-plus-parenthetical-year vs no opus at all) for one parser to get
  right every time, and a missing work is a safer failure mode than a
  mis-parsed one, since it ends up quoted back to the listener.
- A file whose composer can't be matched to an existing composer is skipped
  and logged, never used to create a new composer -- that already has its
  own reviewed path (ComposersData.bulk_import_composers).

Idempotent: safe to re-run, upserts on (composer, work name).

Run from the workspace root:
    python scripts/ingest_composer_works.py
    python scripts/ingest_composer_works.py --dry-run
    python scripts/ingest_composer_works.py --limit 50
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extensions.imslp_souper import ImslpCompilationData
from extensions.wiki_souper import WikiCompilationData
from library_data.composer import composers_data
from library_data.work import Work
from library_data.works_data import works_data
from utils.logging_setup import get_logger

logger = get_logger(__name__)

WIKI_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "library_data", "wiki"
)

# Anchored, conservative: no match leaves catalogue_number as None rather than guessing.
_CATALOGUE_RE = re.compile(
    r"^(Op\.?\s*\d+[a-z]?|BWV\s*\d+|Hob\.?\s*[IVXLC]+[:.]?\d*|K\.?\s*\d+|WoO\.?\s*\d+)\b[.,:\-\s]*",
    re.IGNORECASE,
)
_TRAILING_YEAR_RE = re.compile(r"(\d{4})(?!.*\d{4})")
_TRAILING_YEAR_ANNOTATION_RE = re.compile(r"[\(\[]?\s*(Pub\.|Comp\.|Compl?\.)?\s*\d{4}\s*[\)\]]?\.?\s*$")
_MIN_TITLE_LENGTH = 3

_FILENAME_PREFIX_RE = re.compile(r"^List of .+? by (?P<name>.+)$", re.IGNORECASE)
_FILENAME_SUFFIXES = (" (IMSLP)", " by opus number")


def _parse_cell(cell_text):
    """(title, catalogue_number, date) from one scraped cell, or None to skip it."""
    if not cell_text or not isinstance(cell_text, str):
        return None
    text = cell_text.strip()
    if not text:
        return None

    catalogue_number = None
    match = _CATALOGUE_RE.match(text)
    if match:
        catalogue_number = match.group(1).strip()
        text = text[match.end():].strip()

    date_match = _TRAILING_YEAR_RE.search(text)
    date = date_match.group(1) if date_match else None

    # Drop a publisher/edition tail (never the title) and a trailing year annotation.
    title = text.split(";")[0]
    title = _TRAILING_YEAR_ANNOTATION_RE.sub("", title)
    title = title.strip(" -,:([.")

    if len(title) < _MIN_TITLE_LENGTH or not any(c.isalpha() for c in title):
        return None
    return title, catalogue_number, date


def _rows_from_compilation(compilation):
    """Yield raw cell text for every row in every table that isn't boilerplate."""
    for section in compilation._sections:
        for table in section._tables:
            if table.is_invalid_table():
                continue
            for row in table.get_rows():
                cell = next((c for c in row if isinstance(c, str) and c.strip()), None)
                if cell:
                    yield cell


def _composer_name_from_filename(filepath):
    stem = os.path.splitext(os.path.basename(filepath))[0]
    match = _FILENAME_PREFIX_RE.match(stem)
    name = match.group("name") if match else stem
    for suffix in _FILENAME_SUFFIXES:
        if name.lower().endswith(suffix.lower()):
            name = name[: -len(suffix)]
    return name.strip()


def _load_compilation(filepath):
    source = "imslp" if "IMSLP" in filepath else "wikipedia"
    loader = ImslpCompilationData if source == "imslp" else WikiCompilationData
    return loader.load_from_file(filepath), source


def ingest_file(filepath, dry_run=False):
    """Returns (composer_name_or_None, works_ingested, rows_skipped)."""
    try:
        compilation, source = _load_compilation(filepath)
    except Exception as e:
        logger.warning(f"Could not load {filepath}: {e}")
        return None, 0, 0

    guessed_name = _composer_name_from_filename(filepath)
    composer = composers_data._find_existing_composer(guessed_name)
    if composer is None:
        best_match, ratio = composers_data._find_similar_composer(guessed_name)
        if best_match is not None and ratio >= composers_data._IMPORT_AUTO_MERGE_THRESHOLD:
            composer = best_match
    if composer is None:
        logger.info(f"Skipping {filepath}: no confident composer match for '{guessed_name}'")
        return None, 0, 0

    works = []
    seen = set()
    skipped = 0
    for cell in _rows_from_compilation(compilation):
        parsed = _parse_cell(cell)
        if parsed is None:
            skipped += 1
            continue
        title, catalogue_number, date = parsed
        work = Work(title, composer.name, date=date, catalogue_number=catalogue_number, source=source)
        if work in seen:
            continue
        seen.add(work)
        works.append(work)

    if works and not dry_run:
        works_data.save_works(composer.id, works)
    return composer.name, len(works), skipped


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and log, but do not write to the DB.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only process the first N files (for testing).")
    args = parser.parse_args()

    if not os.path.isdir(WIKI_DIR):
        logger.error(f"No such directory: {WIKI_DIR}")
        return 1

    files = sorted(f for f in os.listdir(WIKI_DIR) if f.endswith(".json"))
    if args.limit:
        files = files[:args.limit]

    files_processed = 0
    files_skipped = 0
    total_works = 0
    total_rows_skipped = 0

    for filename in files:
        filepath = os.path.join(WIKI_DIR, filename)
        composer_name, works_ingested, rows_skipped = ingest_file(filepath, dry_run=args.dry_run)
        if composer_name is None:
            files_skipped += 1
            continue
        files_processed += 1
        total_works += works_ingested
        total_rows_skipped += rows_skipped
        logger.info(f"{composer_name}: {works_ingested} works ingested, "
                    f"{rows_skipped} rows skipped ({filename})")

    logger.info(
        f"Done{' (dry run)' if args.dry_run else ''}. "
        f"{files_processed} files matched to a composer, {files_skipped} skipped "
        f"(no confident composer match), {total_works} works ingested total, "
        f"{total_rows_skipped} rows skipped as unparseable."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
