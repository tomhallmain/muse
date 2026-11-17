#!/usr/bin/env python3
"""Encrypt an edited library extender q dict into extensions/library_ext_q_dict.enc.

The source defaults to the app's decrypted cache. The previous encrypted file is
backed up, and restored if what was written does not decrypt back to the source.

    python scripts/encrypt_library_ext_q_dict.py --dry-run
    python scripts/encrypt_library_ext_q_dict.py --source edited_q_dict.json
"""

import os
import sys

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_ROOT_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

import argparse
import json
import shutil
from typing import Optional

from extensions import library_extender_q_dict as q_dict_store


def describe_changes(before: Optional[dict], after: dict) -> str:
    if before is None:
        return f"{len(after)} key(s) for a new file"
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    if not (added or removed or changed):
        return "no change from the encrypted file"
    parts = [f"{label}: {', '.join(keys)}" for label, keys in
             (("added", added), ("removed", removed), ("changed", changed)) if keys]
    return "; ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", metavar="FILE",
                        help="JSON file holding the q dict (default: the app's decrypted cache)")
    parser.add_argument("--target", metavar="FILE",
                        help="Encrypted file to write (default: the shipped one)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would change and write nothing")
    parser.add_argument("--force", action="store_true",
                        help="Encrypt even when the source is older than the encrypted file")
    args = parser.parse_args()

    source = args.source or q_dict_store.cache_path()
    target = args.target or q_dict_store.encrypted_path()

    if not os.path.isfile(source):
        print(f"Source not found: {source}")
        return 1
    try:
        with open(source, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        print(f"Could not read {source}: {type(e).__name__}: {e}")
        return 1
    if not isinstance(data, dict) or not data:
        print(f"Refusing to encrypt: {source} does not hold a non-empty dictionary")
        return 1
    print(f"Read {len(data)} key(s) from {source}")

    existing = None
    if os.path.isfile(target):
        try:
            existing = q_dict_store.decrypt(target)
        except Exception as e:
            print(f"The existing {target} could not be decrypted: {type(e).__name__}: {e}")
        if not args.force and os.path.getmtime(source) < os.path.getmtime(target):
            print(f"{source} is older than {target}, so it may predate the last change to "
                  f"the encrypted file. Nothing written; pass --force to encrypt it anyway.")
            return 1
    print(describe_changes(existing, data))

    if args.dry_run:
        print(f"Dry run: nothing written. {target} is unchanged.")
        return 0

    backup = None
    if os.path.isfile(target):
        backup = target + ".bak"
        shutil.copy2(target, backup)
        print(f"Backed up the previous file to {backup}")

    q_dict_store.encrypt(data, target)
    try:
        round_tripped = q_dict_store.decrypt(target)
    except Exception as e:
        round_tripped = None
        print(f"Could not decrypt what was just written: {type(e).__name__}: {e}")

    if round_tripped != data:
        if backup is not None:
            shutil.copy2(backup, target)
            print("Verification FAILED. The previous encrypted file has been restored.")
        else:
            print("Verification FAILED and there was no previous encrypted file to restore.")
        return 1

    print(f"Encrypted {len(data)} key(s) to {target} and decrypted it back to confirm.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
