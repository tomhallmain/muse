"""
Generate a JSON file containing the diff between two encoded blacklist files.

One blacklist is the repo default at library_data/data/blacklist_default.enc
(always decrypted with muse_blacklist). The other is a path set below or
passed as the first command-line argument; its passphrase is configurable
(variable below or second CLI argument).

Output JSON structure:
  only_in_repo: items present only in the repo default
  only_in_other: items present only in the other file
  in_both_identical: items in both with identical fields
  in_both_modified: same "string" in both but different enabled/regex/etc.
  summary: counts for each category

Run from repo root:
  python scripts/diff_blacklist_enc.py
  python scripts/diff_blacklist_enc.py /path/to/other/blacklist_default.enc
  python scripts/diff_blacklist_enc.py /path/to/other.enc sd_runner_blacklist
"""
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Path to the other encoded blacklist (override via CLI)
OTHER_BLACKLIST_ENC_PATH = os.path.join(PROJECT_ROOT, "library_data", "data", "blacklist_other.enc")

# Output path for the diff JSON
OUTPUT_DIFF_JSON_PATH = os.path.join(PROJECT_ROOT, "blacklist_diff.json")

REPO_BLACKLIST_ENC_PATH = os.path.join(
    PROJECT_ROOT, "library_data", "data", "blacklist_default.enc"
)

MUSE_BLACKLIST_PASSPHRASE = b"muse_blacklist"

# Passphrase for the other blacklist (override via second CLI argument)
OTHER_BLACKLIST_PASSPHRASE = b"muse_blacklist"


def load_blacklist_items_from_enc(enc_path: str, passphrase: bytes) -> list[dict]:
    """Decrypt and postprocess an encoded blacklist file; return list of item dicts."""
    from utils.encryptor import symmetric_decrypt_data_from_file
    from utils.utils import Utils

    encoded_data = symmetric_decrypt_data_from_file(enc_path, passphrase)
    blacklist_json = Utils.postprocess_data_from_decryption(encoded_data)
    return json.loads(blacklist_json)


def diff_blacklists(repo_items: list[dict], other_items: list[dict]) -> dict:
    """Compare two lists of blacklist item dicts by 'string'; return diff structure."""
    by_string_repo = {item["string"]: item for item in repo_items}
    by_string_other = {item["string"]: item for item in other_items}

    only_in_repo = []
    only_in_other = []
    in_both_identical = []
    in_both_modified = []

    all_strings = set(by_string_repo) | set(by_string_other)
    for s in sorted(all_strings):
        r = by_string_repo.get(s)
        o = by_string_other.get(s)
        if r is None:
            only_in_other.append(o)
        elif o is None:
            only_in_repo.append(r)
        elif r == o:
            in_both_identical.append(r)
        else:
            in_both_modified.append({"string": s, "repo": r, "other": o})

    return {
        "only_in_repo": only_in_repo,
        "only_in_other": only_in_other,
        "in_both_identical": in_both_identical,
        "in_both_modified": in_both_modified,
        "summary": {
            "only_in_repo": len(only_in_repo),
            "only_in_other": len(only_in_other),
            "in_both_identical": len(in_both_identical),
            "in_both_modified": len(in_both_modified),
        },
    }


def main():
    other_path = OTHER_BLACKLIST_ENC_PATH
    other_passphrase = OTHER_BLACKLIST_PASSPHRASE
    if len(sys.argv) > 1:
        other_path = sys.argv[1].strip()
    if len(sys.argv) > 2:
        other_passphrase = sys.argv[2].strip().encode("utf-8")
    output_path = OUTPUT_DIFF_JSON_PATH

    if not os.path.isfile(REPO_BLACKLIST_ENC_PATH):
        print(f"Error: Repo blacklist not found: {REPO_BLACKLIST_ENC_PATH}")
        sys.exit(1)
    if not os.path.isfile(other_path):
        print(f"Error: Other blacklist not found: {other_path}")
        sys.exit(1)

    print(f"Repo blacklist: {REPO_BLACKLIST_ENC_PATH}")
    print(f"Other blacklist: {other_path} (passphrase: {other_passphrase.decode('utf-8')})")
    print("Decrypting and loading repo blacklist...")
    try:
        repo_items = load_blacklist_items_from_enc(REPO_BLACKLIST_ENC_PATH, MUSE_BLACKLIST_PASSPHRASE)
    except Exception as e:
        import traceback
        print(f"Error loading repo blacklist: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)

    print("Decrypting and loading other blacklist...")
    try:
        other_items = load_blacklist_items_from_enc(other_path, other_passphrase)
    except Exception as e:
        import traceback
        print(f"Error loading other blacklist: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)

    diff = diff_blacklists(repo_items, other_items)
    print(f"Writing diff to: {output_path}")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(diff, f, indent=2, ensure_ascii=False)

    s = diff["summary"]
    print("Summary:")
    print(f"  only_in_repo:       {s['only_in_repo']}")
    print(f"  only_in_other:     {s['only_in_other']}")
    print(f"  in_both_identical: {s['in_both_identical']}")
    print(f"  in_both_modified:  {s['in_both_modified']}")


if __name__ == "__main__":
    main()
