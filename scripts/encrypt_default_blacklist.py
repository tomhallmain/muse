"""Write the current blacklist back out as the encrypted default.

The list that gets encrypted is whatever BlacklistWindow.set_blacklist() loads,
which is the working list from app_info_cache only once a non-default list has
been confirmed in the UI. Until then it falls back to decrypting the existing
file, and re-encrypting that would achieve nothing -- so which source was used
is reported before anything is written.

    python -m scripts.encrypt_default_blacklist --dry-run
"""

import argparse
import os
import shutil
import sys

# A Windows console defaults to cp1252 and cannot encode the check and arrow
# marks printed below; without this, the summary raises UnicodeEncodeError.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Before the project imports, so running the file directly works as well as -m.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from library_data.blacklist import Blacklist
from ui_qt.blacklist_window import BlacklistWindow
from utils.app_info_cache import app_info_cache


def item_key(item):
    """What makes two blacklist entries the same entry, for diffing."""
    item_type = getattr(item, "item_type", None)
    return (item.string, getattr(item_type, "name", str(item_type)))


def snapshot(items) -> dict:
    """Map each entry's key to its full serialised form, so changes show up too."""
    taken = {}
    for item in items:
        try:
            taken[item_key(item)] = item.to_dict()
        except Exception as e:
            print(f"  ! could not read an entry for comparison: {type(e).__name__}: {e}")
    return taken


def report_diff(before: dict, after: dict) -> None:
    added = [k for k in after if k not in before]
    removed = [k for k in before if k not in after]
    changed = [k for k in before if k in after and before[k] != after[k]]

    for heading, keys in (("added", added), ("removed", removed), ("changed", changed)):
        if not keys:
            continue
        mark = {"added": "+", "removed": "-", "changed": "~"}[heading]
        print(f"\n{len(keys)} item(s) {heading}:")
        for key in sorted(keys):
            string, item_type = key
            print(f"  {mark} {string!r}  [{item_type}]")
            if heading == "changed":
                for field in sorted(set(before[key]) | set(after[key])):
                    was, now = before[key].get(field), after[key].get(field)
                    if was != now:
                        print(f"        {field}: {was!r} -> {now!r}")
    if not added and not removed and not changed:
        print("\nNo differences between the two lists.")


def describe_change(items_before: int, items_in_encrypted: int) -> str:
    if items_in_encrypted == 0:
        return f"{items_before} item(s) would be written to a new file"
    change = items_before - items_in_encrypted
    if change > 0:
        return f"{change} item(s) added since the encrypted version"
    if change < 0:
        return f"{abs(change)} item(s) removed since the encrypted version"
    return "no change in item count from the encrypted version"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would change and write nothing")
    parser.add_argument("--show-diff", action="store_true",
                        help="List every entry that differs, not just the counts. "
                             "Runs to thousands of lines; redirect it to a file")
    args = parser.parse_args()

    target = Blacklist.DEFAULT_BLACKLIST_FILE_LOC

    try:
        Blacklist.decrypt_blacklist()
        # Taken before set_blacklist() replaces the loaded entries.
        encrypted_snapshot = snapshot(Blacklist.get_items())
        items_in_encrypted = len(Blacklist.get_items())
        print(f"Existing encrypted blacklist holds {items_in_encrypted} item(s)")
        if len(encrypted_snapshot) != items_in_encrypted:
            print(f"  note: {items_in_encrypted - len(encrypted_snapshot)} of them share "
                  f"a string and type with another entry")
    except Exception as e:
        print(f"No existing encrypted blacklist, or it could not be read: {e}")
        encrypted_snapshot = {}
        items_in_encrypted = 0

    from_working_list = app_info_cache.get(
        BlacklistWindow.DEFAULT_BLACKLIST_KEY, default_val=False)
    BlacklistWindow.set_blacklist()
    items_before = len(Blacklist.get_items())

    if from_working_list:
        print(f"Loaded {items_before} item(s) from the working blacklist")
    else:
        print(f"Loaded {items_before} item(s) by decrypting the existing file: no "
              f"non-default blacklist has been confirmed in the UI, so there is "
              f"nothing new to write")

    print(f"\n{describe_change(items_before, items_in_encrypted)}")

    if args.show_diff:
        report_diff(encrypted_snapshot, snapshot(Blacklist.get_items()))

    if args.dry_run:
        print(f"Dry run: nothing written. {target} is unchanged.")
        return 0

    if items_before == 0:
        print("Refusing to encrypt an empty blacklist.")
        return 1

    backup = None
    if os.path.isfile(target):
        backup = target + ".bak"
        shutil.copy2(target, backup)
        print(f"Backed up the previous file to {backup}")

    Blacklist.encrypt_blacklist()
    print(f"Encrypted the blacklist to {target}")

    try:
        Blacklist.decrypt_blacklist()
        items_after = len(Blacklist.get_items())
    except Exception as e:
        items_after = -1
        print(f"Could not decrypt what was just written: {type(e).__name__}: {e}")

    if items_after != items_before:
        print(f"FAILED verification: wrote {items_before} item(s), read back {items_after}")
        if backup is not None:
            shutil.copy2(backup, target)
            print("The previous file has been restored.")
        return 1

    print(f"Verified by decrypting it back: {items_after} item(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
