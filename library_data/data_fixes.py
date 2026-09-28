"""Run-once corrections to reference data on existing installs.

Seeding only inserts rows a database lacks, so a correction made to a
*_example.json file never reaches an install seeded before it. Each entry in
data/data_fixes.json is applied once per database, when the table it targets is
first loaded, and its outcome is recorded in data_fixes_applied: the file's
history says what was corrected and why, the table what each install did.
Fixes only add, so one that was applied and later undone by hand stays undone.
"""

import datetime
import json
import os
import sqlite3
from typing import Callable, List, Tuple

from utils.db import get_connection
from utils.logging_setup import get_logger

logger = get_logger(__name__)

FIXES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "data_fixes.json")

APPLIED = "applied"
ALREADY_PRESENT = "already_present"
TARGET_MISSING = "target_missing"

_fixes = None


def load_fixes() -> List[dict]:
    """The parsed fix list, read once per process."""
    global _fixes
    if _fixes is None:
        try:
            with open(FIXES_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
        except FileNotFoundError:
            loaded = []
        except (OSError, ValueError) as e:
            logger.error(f"Could not read data fixes from {FIXES_PATH}: {e}")
            loaded = []
        if not isinstance(loaded, list):
            logger.error(f"Data fixes file is not a list: {FIXES_PATH}")
            loaded = []
        _fixes = [fix for fix in loaded if isinstance(fix, dict) and fix.get("id")]
    return _fixes


def apply_pending(table: str, apply_fix: Callable[[dict], Tuple[str, str]]) -> None:
    """Run each unrecorded fix for `table` through `apply_fix` and record its outcome.

    `apply_fix` returns (outcome, detail), or raises when the fix could not be
    applied; such a fix is left unrecorded and retried on the next load.
    """
    fixes = [fix for fix in load_fixes() if fix.get("table") == table]
    if not fixes:
        return
    try:
        conn = get_connection()
        recorded = {row[0] for row in conn.execute("SELECT id FROM data_fixes_applied").fetchall()}
    except sqlite3.Error as e:
        logger.error(f"Could not read applied data fixes: {e}")
        return
    for fix in fixes:
        fix_id = fix["id"]
        if fix_id in recorded:
            continue
        try:
            outcome, detail = apply_fix(fix)
            conn.execute(
                "INSERT OR IGNORE INTO data_fixes_applied (id, applied_at, outcome, detail) VALUES (?, ?, ?, ?)",
                (fix_id, datetime.datetime.now().isoformat(), outcome, detail),
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Data fix {fix_id} failed, will retry on next load: {e}")
            continue
        logger.info(f"Data fix {fix_id}: {outcome} ({detail})")
