#!/usr/bin/env python3
"""Find source files that have already been replaced by a converted copy.

A converted copy sits beside its source under the same name with another
extension: by default an iTunes-protected .m4p and the .m4a made from it
(--source-ext / --target-ext choose another pair, e.g. .wma and .mp3).

A pair is only ever looked for within one folder: a library keeps a track in
exactly one album folder, so the same name under a different folder is a
different track. Subfolders are still walked, each on its own.

Matching is by name first, then confirmed against the container: duration and
the title/album/artist tags. Audio content is not compared, since a protected
source such as an .m4p cannot be decoded without its FairPlay keys -- duration
plus tags is the strongest check that works for every pair.

The converted side is also checked for embedded artwork: a copy that still has
none is not finished, so its source is not safe to drop yet.

Nothing is moved, deleted or written without --move-to, --delete,
--move-mismatched-to or --copy-artwork. Start with a plain run to see the counts:

    python scripts/find_replaced_tracks.py --dir "F:/iTunes Music"
    python scripts/find_replaced_tracks.py --source-ext .wma --target-ext .mp3
"""

import os
import sys

# A Windows console defaults to cp1252, which cannot encode accented characters
# in filenames; printing one raises UnicodeEncodeError.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_ROOT_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

import argparse
import re
import unicodedata
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import utils.media_file_tools as mf

# Conversion can shift the length by a frame or so.
DURATION_TOLERANCE_SECONDS = 2.0

_UNSAFE = re.compile(r"[^a-z0-9]+")
# yt-dlp and iTunes both substitute characters the filesystem rejects.
_LOOKALIKES = str.maketrans({"：": ":", "⧸": "/", "＂": '"', "｜": "|", "＊": "*", "？": "?"})


class _Tee:
    """Write to the console and to a UTF-8 file at once.

    The console copy may lose characters it cannot encode; the file never does.
    """

    def __init__(self, stream, path):
        self.stream = stream
        self.file = open(path, "w", encoding="utf-8")

    def write(self, text):
        self.stream.write(text)
        self.file.write(text)
        return len(text)

    def flush(self):
        self.stream.flush()
        self.file.flush()


def _limited(items: list, limit: Optional[int]) -> list:
    """The first *limit* items, announcing the cut when one is made."""
    if limit is not None and limit < len(items):
        print(f"\n--limit {limit}: acting on {limit} of {len(items)}")
        return items[:limit]
    return items


class Entry:
    def __init__(self, path):
        self.path = path
        self.stem = os.path.splitext(os.path.basename(path))[0]
        self.dirname = os.path.dirname(path)
        self.duration: Optional[float] = None
        self.title = self.album = self.artist = ""
        self.has_artwork = False
        # Distinguishes "read the tags, found no cover" from "read no tags at
        # all": both leave has_artwork False, and only the first is a real finding.
        self.tag_count: Optional[int] = None
        self.unreadable: Optional[str] = None

    def read(self) -> None:
        try:
            audio = mf.open_audio(self.path)
        except Exception as e:
            self.unreadable = f"{type(e).__name__}: {e}"
            return
        if audio is None:
            self.unreadable = "mutagen does not recognise the format"
            return
        info = getattr(audio, "info", None)
        length = getattr(info, "length", None) if info is not None else None
        self.duration = float(length) if length else None
        tags = getattr(audio, "tags", None)
        if tags is None:
            return
        try:
            self.tag_count = len(tags.keys())
        except Exception:
            self.tag_count = None
        self.title = mf.first_text(tags, "title")
        self.album = mf.first_text(tags, "album")
        self.artist = mf.first_text(tags, "artist")
        try:
            self.has_artwork = mf.picture_from(audio) is not None
        except Exception as e:
            print(f"  ! could not read artwork from {self.path}: {type(e).__name__}: {e}")


Pair = Tuple[Entry, Entry, str]


def normalize(text: str) -> str:
    """A comparison key tolerant of case, punctuation and filesystem substitutions."""
    text = unicodedata.normalize("NFKC", (text or "").translate(_LOOKALIKES))
    return _UNSAFE.sub("", text.casefold())


def duration_matches(a: Entry, b: Entry) -> Optional[bool]:
    """True/False when both durations are known, None when either is missing."""
    if a.duration is None or b.duration is None:
        return None
    return abs(a.duration - b.duration) <= DURATION_TOLERANCE_SECONDS


def tags_match(a: Entry, b: Entry) -> bool:
    for left, right in ((a.title, b.title), (a.album, b.album), (a.artist, b.artist)):
        if left and right and normalize(left) != normalize(right):
            return False
    return True


def _extension(value: str) -> str:
    value = value.strip().lower()
    return value if value.startswith(".") else "." + value


def classify(sources: List[Entry], targets: List[Entry]) -> Dict[str, list]:
    """Sort every source into the report groups by what its same-folder counterpart shows."""
    by_dir_stem: Dict[Tuple[str, str], List[Entry]] = defaultdict(list)
    for entry in targets:
        by_dir_stem[(entry.dirname, normalize(entry.stem))].append(entry)

    groups = {key: [] for key in ("replaced", "transferable", "artwork_missing", "no_tag_block",
                                  "mismatched", "ambiguous", "unmatched", "unreadable")}
    for source in sources:
        if source.unreadable:
            groups["unreadable"].append(source)
            continue
        candidates = by_dir_stem.get((source.dirname, normalize(source.stem)), [])
        if not candidates:
            groups["unmatched"].append(source)
            continue
        if len(candidates) > 1:
            groups["ambiguous"].append((source, candidates))
            continue
        target = candidates[0]
        same_length = duration_matches(source, target)
        how = "tags only, no duration read" if same_length is None else ""
        if same_length is False:
            groups["mismatched"].append((source, target, "duration differs"))
        elif not tags_match(source, target):
            groups["mismatched"].append((source, target, "tags differ"))
        elif target.has_artwork:
            groups["replaced"].append((source, target, how))
        elif target.tag_count is None:
            groups["no_tag_block"].append((source, target, "no tag block on the converted copy"))
        elif source.has_artwork:
            groups["transferable"].append((source, target, how))
        else:
            groups["artwork_missing"].append((source, target, "neither side has a cover"))
    return groups


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", action="append", metavar="DIR",
                        help="Directory holding the library. May be given more than once. "
                             "Defaults to the directories configured in the app")
    parser.add_argument("--source-ext", default=".m4p",
                        help="Extension of the files being replaced (default: %(default)s)")
    parser.add_argument("--target-ext", default=".m4a",
                        help="Extension of the converted copies (default: %(default)s)")
    parser.add_argument("--no-recurse", action="store_true",
                        help="Only the files directly in --dir, not its subfolders")
    parser.add_argument("--move-to", metavar="DIR",
                        help="Move the replaced source files here")
    parser.add_argument("--delete", action="store_true",
                        help="Delete the replaced source files. --move-to is reversible; this is not")
    parser.add_argument("--copy-artwork", action="store_true",
                        help="Copy the cover from each source onto its converted copy where the "
                             "copy has none. Writes to the converted files")
    parser.add_argument("--move-mismatched-to", metavar="DIR",
                        help="Move source files here whose name matched a converted copy in the "
                             "same folder but whose duration or tags did not, for a manual look. "
                             "May be combined with any other action")
    parser.add_argument("--limit", type=int, metavar="N",
                        help="Act on at most N files, to try a small batch first")
    parser.add_argument("--out", metavar="FILE",
                        help="Also write the report here, as UTF-8. The listings can run to "
                             "thousands of lines, more than a console scrollback holds")
    args = parser.parse_args()

    source_ext, target_ext = _extension(args.source_ext), _extension(args.target_ext)
    if source_ext == target_ext:
        parser.error("--source-ext and --target-ext must differ")
    if args.move_to and args.delete:
        parser.error("pass either --move-to or --delete, not both")
    if args.copy_artwork and (args.move_to or args.delete):
        parser.error("--copy-artwork writes to the converted files and --move-to/--delete clear "
                     "the sources. Run them separately, copying first, so the listing is "
                     "rebuilt in between")

    if args.out:
        sys.stdout = _Tee(sys.stdout, args.out)

    directories = args.dir or mf.configured_directories()
    if not directories:
        parser.error("no directory to search: pass --dir, or configure the library "
                     "directories in the app")
    for directory in directories:
        if not os.path.isdir(directory):
            parser.error(f"not a directory: {directory}")

    recurse = not args.no_recurse
    source_paths, skipped_sources = mf.collect_files(directories, [source_ext], recurse)
    target_paths, skipped_targets = mf.collect_files(directories, [target_ext], recurse)
    sources = [Entry(p) for p in source_paths]
    targets = [Entry(p) for p in target_paths]
    print(f"Found {len(sources)} {source_ext} and {len(targets)} {target_ext} file(s) "
          f"{'under' if recurse else 'directly in'} {', '.join(directories)}")
    if skipped_sources or skipped_targets:
        print(f"Ignored {skipped_sources + skipped_targets} AppleDouble "
              f"'._' sidecar(s), which hold no audio")
    if not sources:
        print("Nothing to do.")
        return 0

    print("Reading tags ...")
    for entry in sources + targets:
        entry.read()
    groups = classify(sources, targets)

    def report(heading: str, pairs: List[Pair]) -> None:
        if not pairs:
            return
        print(f"\n{len(pairs)} {source_ext} file(s) -- {heading}:")
        for source, target, how in pairs:
            detail = f"  [{how}]" if how else ""
            print(f"  {source.path}  ({_describe(source)})")
            print(f"    -> {target.path}  ({_describe(target)}){detail}")

    report("replaced, converted copy has artwork", groups["replaced"])
    report(f"the {source_ext} has a cover the {target_ext} lacks -- pass --copy-artwork "
           f"to move it over", groups["transferable"])
    report("neither side has a cover -- nothing here to copy from", groups["artwork_missing"])
    report("no tags could be read from the converted copy at all, so whether it has "
           "artwork is unknown", groups["no_tag_block"])
    report("name matched but the file did not", groups["mismatched"])
    if groups["ambiguous"]:
        print(f"\n{len(groups['ambiguous'])} {source_ext} file(s) matched more than one "
              f"{target_ext} in their own folder:")
        for source, candidates in groups["ambiguous"]:
            print(f"  {source.path}")
            for candidate in candidates:
                print(f"      {candidate.path}")
    if groups["unmatched"]:
        print(f"\n{len(groups['unmatched'])} {source_ext} file(s) have no {target_ext} "
              f"counterpart in their own folder -- still to convert:")
        for source in groups["unmatched"]:
            print(f"  {source.path}")
    if groups["unreadable"]:
        print(f"\n{len(groups['unreadable'])} {source_ext} file(s) could not be read:")
        for source in groups["unreadable"]:
            print(f"  {source.path}  ({source.unreadable})")

    print(f"\n{len(groups['transferable'])} {target_ext} file(s) can take a cover from "
          f"their {source_ext}")
    print(f"{len(groups['replaced'])} {source_ext} file(s) are safe to remove")

    if not (args.copy_artwork or args.move_to or args.delete or args.move_mismatched_to):
        print("Listing only. Pass --copy-artwork to move the covers over, "
              "--move-to DIR (reversible) / --delete to clear the replaced sources, or "
              "--move-mismatched-to DIR to set the name-only matches aside for review.")
        return 0

    failed = False
    if args.copy_artwork:
        failed = _copy_artwork_all(groups["transferable"], target_ext, args.limit) or failed
    if args.move_mismatched_to:
        failed = _clear_sources(groups["mismatched"], source_ext, args.move_mismatched_to,
                                False, args.limit) or failed
    if args.move_to or args.delete:
        failed = _clear_sources(groups["replaced"], source_ext, args.move_to,
                                args.delete, args.limit) or failed
    return 1 if failed else 0


def _describe(entry: Entry) -> str:
    length = f"{entry.duration:.1f}s" if entry.duration else "no duration"
    if entry.tag_count is None:
        return f"{length}, no tags"
    return f"{length}, {entry.tag_count} tags, {'cover' if entry.has_artwork else 'no cover'}"


def copy_artwork(source: Entry, target: Entry) -> Tuple[Optional[str], int]:
    """Copy the cover from the source onto the converted copy.

    Returns (error or None, bytes of cover found on the copy afterwards). Only the
    audio of a protected file is encrypted; its cover sits in the clear, so this is
    a tag copy and nothing more.
    """
    cover = mf.picture_bytes(source.path)
    if not cover:
        return "the source reported a cover but none could be read back", 0
    error = mf.write_picture(target.path, cover)
    if error:
        return error, 0
    return None, len(mf.picture_bytes(target.path) or b"")


def _copy_artwork_all(pairs: List[Pair], target_ext: str, limit: Optional[int]) -> bool:
    copied = failed = 0
    pairs = _limited(pairs, limit)
    print(f"\nWriting a cover onto {len(pairs)} {target_ext} file(s):")
    for source, target, _how in pairs:
        error, written = copy_artwork(source, target)
        if error is None:
            copied += 1
            print(f"  {target.path}")
            print(f"    <- {written} bytes of cover from {os.path.basename(source.path)}")
        else:
            failed += 1
            print(f"  ! {target.path}")
            print(f"    <- FAILED: {error}")
    print(f"\nCopied a cover onto {copied} {target_ext} file(s), {failed} failed")
    return failed > 0


def _clear_sources(pairs: List[Pair], source_ext: str, move_to: Optional[str], delete: bool,
                   limit: Optional[int]) -> bool:
    done = failed = 0
    pairs = _limited(pairs, limit)
    print(f"\n{'Moving' if move_to else 'Deleting'} {len(pairs)} {source_ext} file(s):")
    for source, _target, _how in pairs:
        try:
            if move_to:
                destination = mf.move_aside(source.path, move_to)
                print(f"  {source.path}")
                print(f"    -> {destination}")
            else:
                os.remove(source.path)
                print(f"  {source.path}")
            done += 1
        except Exception as e:
            print(f"  ! {source.path}: {type(e).__name__}: {e}")
            failed += 1
    if move_to:
        print(f"\nMoved {done} file(s) to {move_to}, {failed} failed")
    else:
        print(f"\nDeleted {done} file(s), {failed} failed")
    return failed > 0


if __name__ == "__main__":
    raise SystemExit(main())
