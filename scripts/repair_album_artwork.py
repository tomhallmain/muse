#!/usr/bin/env python3
"""Inspect, remove or restore embedded album artwork.

Three operations, none of which touches a file without --apply except the
read-only inspection:

  --inspect-dir DIR       Report what artwork DIR's files hold, as seen by each
                          reader the project uses: mutagen's raw picture frames,
                          music_tag, and MediaTrack. Writes nothing and ignores
                          every other flag.

  --strip-dir DIR         Remove embedded artwork from the media files directly
                          in DIR, for a folder whose tracks should carry none.

  --like FILEPATH         Replace a wrong image wherever it was written. FILEPATH
                          is one file already confirmed to carry the wrong image;
                          the files repaired are those in the same directory
                          carrying that identical image, FILEPATH included. Each
                          gets its own YouTube thumbnail back, from a surviving
                          sidecar image or by the video id in its filename. With
                          --strip-unrestorable, a matched file with no video id,
                          or whose thumbnail cannot be fetched, has the wrong
                          image removed.

  --restore-root DIR      The same restore for the tracks an app log names as
  --log FILE              having had their metadata rewritten, located under DIR
                          by their video ids. Only the loose files directly in
                          DIR unless --recurse.

Replaced or removed artwork cannot be recovered unless --backup-dir is given,
which saves each file's existing artwork first.

    python scripts/repair_album_artwork.py --inspect-dir "F:/Music/Some Album"
    python scripts/repair_album_artwork.py --like "F:/Music/Some Album/track [abcdefghijk].m4a" \\
        --backup-dir artwork_backup --apply
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

_ROOT_DIR =os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_ROOT_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

import argparse
import hashlib
import re
from typing import Dict, List, Optional, Tuple

import requests

import utils.media_file_tools as mf
from extensions.extension_filer import find_artwork_sidecar, read_sidecar_artwork
from library_data.media_track import MediaTrack
from utils.translations import I18N

_ = I18N._

# yt-dlp writes the 11-character YouTube id into the filename in brackets.
VIDEO_ID_IN_NAME = re.compile(r"\[([A-Za-z0-9_-]{11})\]")
TRAILING_VIDEO_ID = re.compile(r"\[([A-Za-z0-9_-]{11})\]\s*$")

# Largest first; YouTube answers 404 for the sizes a given video never had.
THUMBNAIL_QUALITIES = ("maxresdefault", "sddefault", "hqdefault")
THUMBNAIL_URL = "https://i.ytimg.com/vi/{video_id}/{quality}.jpg"

Target = Tuple[Optional[str], str]  # video id where the filename carries one, filepath
Note = Tuple[str, List[str]]


# ── Choosing the files ───────────────────────────────────────────────────────

def updated_track_pattern() -> "re.Pattern":
    """Matches the line MediaTrack.update_metadata logs per rewritten track, in this run's locale.

    A log written under another locale carries the message in that language and
    does not match.
    """
    template = re.escape(_("Successfully updated metadata for {0}"))
    return re.compile(template.replace(re.escape("{0}"), r"(.+?)") + r"\s*$")


def parse_updated_titles(log_path: str) -> List[str]:
    """Titles of the tracks the log records as having had their metadata rewritten."""
    pattern = updated_track_pattern()
    titles = []
    with open(log_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            match = pattern.search(line.rstrip("\n"))
            if match:
                titles.append(match.group(1).strip())
    return titles


def index_by_video_id(root: str, recurse: bool = False) -> Dict[str, List[str]]:
    """Map every video id found in root to the media files carrying it.

    Sidecar images carry the id in their names too, so only media files count.
    Only the loose files directly in root are indexed unless recurse is set: each
    subdirectory is an album in its own right.
    """
    from utils.globals import MediaFileType
    index: Dict[str, List[str]] = {}
    walker = os.walk(root) if recurse else [(root, [], mf.media_files_in(root))]
    for dirpath, _dirnames, filenames in walker:
        for filename in filenames:
            if not MediaFileType.is_media_filetype(filename) or filename.startswith("._"):
                continue
            match = VIDEO_ID_IN_NAME.search(filename)
            if match:
                index.setdefault(match.group(1), []).append(os.path.join(dirpath, filename))
    return index


def targets_like(example: str) -> Tuple[List[Target], List[Note]]:
    """Files beside *example* carrying the very same image it does.

    One wrong image written onto several files identifies exactly the files it was
    written to. Anchoring on a file already confirmed as wrong avoids judging which
    shared image is damage and which is a legitimate album cover.
    """
    directory = os.path.dirname(os.path.abspath(example))
    reference = mf.picture_bytes(example)
    if not reference:
        print(f"  ! {example} carries no readable artwork, so there is nothing to match on")
        return [], []

    digest = hashlib.sha256(reference).hexdigest()
    print(f"  matching the {len(reference)} bytes on {os.path.basename(example)} "
          f"(sha256 {digest[:12]})")
    print(f"  against the files directly in {directory} ...")

    targets: List[Target] = []
    for filename in mf.media_files_in(directory):
        data = mf.picture_bytes(os.path.join(directory, filename))
        if not data or hashlib.sha256(data).hexdigest() != digest:
            continue
        match = VIDEO_ID_IN_NAME.search(filename)
        targets.append((match.group(1) if match else None, os.path.join(directory, filename)))

    no_id = sum(1 for video_id, _path in targets if not video_id)
    print(f"\n  {len(targets)} file(s) carry that image:")
    for video_id, filepath in targets:
        print(f"  {'   ' if video_id else ' ? '}{os.path.basename(filepath)}")
    if no_id:
        print(f"\n  '?' marks the {no_id} file(s) with no video id in the name, which have"
              "\n  no thumbnail to restore from.")
    print()
    return sorted(targets, key=lambda pair: pair[1]), []


def targets_from_log(root: str, log_path: str, recurse: bool) -> Tuple[List[Target], List[Note]]:
    titles = parse_updated_titles(log_path)
    print(f"  {len(titles)} rewritten track(s) recorded in {log_path}")

    no_id = [t for t in titles if not TRAILING_VIDEO_ID.search(t)]
    wanted = {}
    for title in titles:
        match = TRAILING_VIDEO_ID.search(title)
        if match:
            wanted[match.group(1)] = title

    scope = "under" if recurse else "directly in"
    print(f"  {len(wanted)} carry a video id; indexing files {scope} {root} ...")
    index = index_by_video_id(root, recurse=recurse)
    print(f"  found {len(index)} video id(s) on disk")

    targets: List[Target] = []
    missing: List[str] = []
    ambiguous: List[str] = []
    for video_id, title in sorted(wanted.items(), key=lambda pair: pair[1]):
        matches = index.get(video_id, [])
        if not matches:
            missing.append(title)
        elif len(matches) > 1:
            ambiguous.append(title + "".join(f"\n        {m}" for m in matches))
        else:
            targets.append((video_id, matches[0]))
    return targets, [
        ("no video id in the title", no_id),
        ("no matching file in the restore root", missing),
        ("a video id matching more than one file", ambiguous),
    ]


# ── Replacement artwork ──────────────────────────────────────────────────────

def fetch_thumbnail(video_id: str, timeout: float) -> Tuple[Optional[bytes], str]:
    """Best available thumbnail for a video id, with the quality that supplied it."""
    for quality in THUMBNAIL_QUALITIES:
        url = THUMBNAIL_URL.format(video_id=video_id, quality=quality)
        try:
            response = requests.get(url, timeout=timeout)
        except Exception as e:
            print(f"    ! {quality} request failed: {e}")
            continue
        if response.status_code == 200 and len(response.content) > 1000:
            return response.content, quality
    return None, ""


def artwork_for(filepath: str, video_id: str, timeout: float) -> Tuple[Optional[bytes], str]:
    """A surviving sidecar is the exact image originally downloaded, so it comes before a fetch."""
    sidecar = find_artwork_sidecar(filepath)
    if sidecar:
        try:
            return read_sidecar_artwork(sidecar), f"sidecar {os.path.basename(sidecar)}"
        except OSError as e:
            print(f"    ! sidecar unreadable, falling back to download: {e}")
    data, quality = fetch_thumbnail(video_id, timeout)
    return data, (f"youtube {quality}" if data else "")


class ArtworkBackup:
    """Saves artwork bytes before they are replaced, alongside a manifest.

    Backups are numbered rather than named after the track so that two tracks
    whose names differ only by characters the filesystem rejects cannot collide.
    """

    def __init__(self, directory: Optional[str]):
        self.directory = directory
        self.entries: List[Tuple[str, str]] = []
        if directory:
            os.makedirs(directory, exist_ok=True)

    def save(self, filepath: str, data: Optional[bytes]) -> None:
        if not self.directory or not data:
            return
        name = f"{len(self.entries):04d}{MediaTrack.artwork_extension(data)}"
        with open(os.path.join(self.directory, name), "wb") as fh:
            fh.write(data)
        self.entries.append((name, filepath))

    def write_manifest(self) -> None:
        if not self.directory or not self.entries:
            return
        path = os.path.join(self.directory, "manifest.tsv")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("backup_file\toriginal_filepath\n")
            for name, filepath in self.entries:
                fh.write(f"{name}\t{filepath}\n")
        print(f"\nSaved {len(self.entries)} artwork backups to {self.directory}")


# ── Operations ───────────────────────────────────────────────────────────────

def run_inspect(directory: str) -> None:
    """Report what is embedded in each file, per reader. Writes nothing."""
    print(f"\n=== Inspecting media files in {directory} (read-only) ===")
    if not os.path.isdir(directory):
        print("  ! not a directory")
        return

    for filename in mf.media_files_in(directory):
        filepath = os.path.join(directory, filename)
        print(f"  {filename}")
        try:
            audio = mf.open_audio(filepath)
        except Exception as e:
            print(f"    ! mutagen could not open the file: {e}")
            audio = None

        tags = getattr(audio, "tags", None) if audio is not None else None
        if tags is None:
            print("    no tag block")
        else:
            keys = [str(k) for k in tags.keys()]
            print(f"    tag type {type(tags).__name__}, {len(keys)} key(s)")
            picture_keys = [k for k in keys
                            if k.upper().startswith(("APIC", "COVR", "PIC", "METADATA_BLOCK_PICTURE"))]
            if not picture_keys:
                print("    no picture frame among the tag keys")
            for key in picture_keys:
                frame = tags[key]
                data = getattr(frame, "data", None)
                if data is None and isinstance(frame, list) and frame:
                    data = frame[0]
                print(f"    picture frame {key!r}: "
                      f"mime={getattr(frame, 'mime', None)} "
                      f"desc={getattr(frame, 'desc', None)!r} "
                      f"bytes={len(data) if data else 0}")

        via_mutagen = mf.picture_from(audio) if audio is not None else None
        print(f"    mutagen reads: {len(via_mutagen) if via_mutagen else 0} bytes")
        try:
            import music_tag
            item = music_tag.load_file(filepath)["artwork"]
            data = getattr(item.first, "data", None) if item is not None else None
            print(f"    music_tag reads: {len(data) if data else 0} bytes")
        except Exception as e:
            print(f"    music_tag reads: nothing ({type(e).__name__}: {e})")
        try:
            via_project = MediaTrack(filepath).load_embedded_artwork()
        except Exception as e:
            via_project = None
            print(f"    ! MediaTrack read raised: {e}")
        print(f"    MediaTrack.load_embedded_artwork reads: "
              f"{len(via_project) if via_project else 0} bytes")


def _strip_one(filepath: str, backup: ArtworkBackup, current: Optional[bytes]) -> bool:
    backup.save(filepath, current)
    try:
        if mf.remove_pictures(filepath):
            return True
        print("    ! artwork is still present after the removal attempt")
    except Exception as e:
        print(f"    ! failed to remove artwork: {e}")
    return False


def run_strip(directory: str, apply: bool, backup: ArtworkBackup) -> None:
    print(f"\n=== Removing artwork from media files in {directory} ===")
    if not os.path.isdir(directory):
        print("  ! not a directory; nothing done")
        return

    filenames = mf.media_files_in(directory)
    if not filenames:
        print("  no media files found")
        return

    stripped = skipped = failed = 0
    for filename in filenames:
        filepath = os.path.join(directory, filename)
        print(f"  {filename}")
        current = mf.picture_bytes(filepath)
        if not current:
            print("    no artwork found; skipping")
            skipped += 1
            continue
        print(f"    has {len(current)} bytes of artwork -> remove")
        if not apply:
            continue
        if _strip_one(filepath, backup, current):
            stripped += 1
        else:
            failed += 1

    verb = "Removed artwork from" if apply else "Would remove artwork from"
    print(f"\n  {verb} {stripped if apply else len(filenames) - skipped} file(s); "
          f"{skipped} already clean, {failed} failed")


def run_restore(targets: List[Target], notes: List[Note], apply: bool,
                backup: ArtworkBackup, limit: Optional[int], timeout: float,
                strip_unrestorable: bool = False) -> None:
    failed: List[str] = []
    restored = would_restore = 0
    stripped = would_strip = 0

    for reached, (video_id, filepath) in enumerate(targets):
        if limit is not None and reached >= limit:
            print(f"\n  --limit {limit} reached; stopping")
            break
        filename = os.path.basename(filepath)
        print(f"  {filename}")

        if video_id:
            data, source = artwork_for(filepath, video_id, timeout)
            reason = "no thumbnail available"
        else:
            data, source = None, ""
            reason = "no video id in the filename"

        if not data:
            # The image on the file is known to be wrong, so with nothing correct
            # to put there, none at all is the accurate state.
            if not strip_unrestorable:
                print(f"    ! {reason}")
                failed.append(filename)
                continue
            print(f"    ! {reason} -> remove the wrong artwork instead")
            would_strip += 1
            if not apply:
                continue
            if _strip_one(filepath, backup, mf.picture_bytes(filepath)):
                stripped += 1
            else:
                failed.append(filename)
            continue

        print(f"    {len(data)} bytes from {source} -> embed")
        would_restore += 1
        if not apply:
            continue
        backup.save(filepath, mf.picture_bytes(filepath))
        error = mf.write_picture(filepath, data)
        if error is None:
            restored += 1
        else:
            print(f"    ! failed to embed: {error}")
            failed.append(filename)

    verb = "Restored" if apply else "Would restore"
    print(f"\n  {verb} artwork on {restored if apply else would_restore} "
          f"of {len(targets)} target(s)")
    if strip_unrestorable:
        verb = "Removed" if apply else "Would remove"
        print(f"  {verb} artwork from {stripped if apply else would_strip} "
              f"target(s) that could not be restored")
    for heading, items in notes + [("nothing that could be done automatically", failed)]:
        if items:
            print(f"\n  {len(items)} track(s) with {heading}:")
            for item in items:
                print(f"    {item}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--inspect-dir", metavar="DIR",
                        help="Report what artwork a directory's files hold, and stop")
    parser.add_argument("--strip-dir", metavar="DIR",
                        help="Directory whose media files should end up with no artwork")
    parser.add_argument("--like", metavar="FILEPATH",
                        help="One file known to carry the wrong artwork. Every file in its "
                             "directory carrying that same image is restored, itself included")
    parser.add_argument("--restore-root", metavar="DIR",
                        help="Alternative to --like: restore the tracks named in --log, "
                             "found under DIR by the video id in their filenames")
    parser.add_argument("--log", metavar="FILE",
                        help="App log naming the rewritten tracks; required with --restore-root")
    parser.add_argument("--strip-unrestorable", action="store_true",
                        help="For a matched file with no video id, or whose thumbnail cannot "
                             "be fetched, remove its wrong artwork rather than leaving it")
    parser.add_argument("--backup-dir", metavar="DIR",
                        help="Save each file's existing artwork here before changing it")
    parser.add_argument("--recurse", action="store_true",
                        help="Also search subdirectories of --restore-root, which are separate "
                             "albums. --like always stays in one directory")
    parser.add_argument("--limit", type=int, metavar="N",
                        help="Stop after N files, to try a small batch first")
    parser.add_argument("--timeout", type=float, default=15.0,
                        help="Per-request thumbnail download timeout (default: %(default)s)")
    parser.add_argument("--apply", action="store_true",
                        help="Write to the files; without it nothing is modified")
    args = parser.parse_args()

    if args.inspect_dir:
        run_inspect(args.inspect_dir)
        return 0

    if not args.strip_dir and not args.like and not args.restore_root:
        parser.error("nothing to do: pass --inspect-dir, --strip-dir, --like "
                     "and/or --restore-root")
    if args.like and args.restore_root:
        parser.error("--like and --restore-root choose the files two different ways; pass one")
    if args.like and not os.path.isfile(args.like):
        parser.error(f"not a file: {args.like}")
    if args.restore_root:
        if not args.log:
            parser.error("--restore-root needs --log")
        if not os.path.isfile(args.log):
            parser.error(f"log file not found: {args.log}")

    if not args.apply:
        print("DRY RUN -- no file will be modified. Re-run with --apply to write.")
    elif not args.backup_dir:
        print("APPLYING with no --backup-dir: replaced artwork will not be recoverable.")

    backup = ArtworkBackup(args.backup_dir)
    if args.strip_dir:
        run_strip(args.strip_dir, args.apply, backup)
    if args.like or args.restore_root:
        if args.like:
            print(f"\n=== Restoring files matching the artwork on {args.like} ===")
            targets, notes = targets_like(args.like)
        else:
            print(f"\n=== Restoring tracks named in {args.log} ===")
            targets, notes = targets_from_log(args.restore_root, args.log, args.recurse)
        run_restore(targets, notes, args.apply, backup, args.limit, args.timeout,
                    strip_unrestorable=args.strip_unrestorable)
    backup.write_manifest()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
