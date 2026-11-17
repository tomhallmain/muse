"""File-level helpers for media maintenance: finding media files, reading the common
text tags, and reading, writing and removing embedded artwork in any tag format
mutagen reads (MP4, ID3, FLAC, Ogg).

They work on a file directly through mutagen and music_tag, so they suit bulk
passes over a whole library where building a MediaTrack per file would be slow.
"""

import base64
import os
from typing import Iterable, List, Optional, Tuple

from utils.logging_setup import get_logger
from utils.path_move import move_on_disk
from utils.translations import I18N

_ = I18N._

logger = get_logger(__name__)

# Tag keys per field, in the order MP4, ID3, Vorbis/FLAC.
TEXT_TAG_KEYS = {
    "title": ("\xa9nam", "TIT2", "title"),
    "album": ("\xa9alb", "TALB", "album"),
    "artist": ("\xa9ART", "TPE1", "artist"),
}
FRONT_COVER = 3  # picture type for the front cover in ID3 and FLAC


# ── Finding files ────────────────────────────────────────────────────────────

def configured_directories() -> List[str]:
    """The library roots from the app config that exist on disk."""
    try:
        from utils.config import config
        return [d for d in (config.directories or []) if d and os.path.isdir(d)]
    except Exception as e:
        logger.warning(_("Could not read the configured directories: {0}").format(e))
        return []


def collect_files(directories: Iterable[str], extensions: Iterable[str],
                  recurse: bool = True) -> Tuple[List[str], int]:
    """Files with one of *extensions*, and how many AppleDouble sidecars were passed over.

    A library copied off a Mac carries a "._name" companion beside every file,
    holding the resource fork rather than audio. Their names differ from the real
    file only by punctuation, so they would otherwise pass for a second copy of
    every track.
    """
    extensions = tuple(e.lower() for e in extensions)
    found, skipped = [], 0
    for directory in directories:
        walker = os.walk(directory) if recurse else [(directory, [], os.listdir(directory))]
        for dirpath, _dirnames, filenames in walker:
            for filename in filenames:
                if not filename.lower().endswith(extensions):
                    continue
                if filename.startswith("._"):
                    skipped += 1
                    continue
                path = os.path.join(dirpath, filename)
                if os.path.isfile(path):
                    found.append(path)
    return sorted(set(found)), skipped


def media_files_in(directory: str) -> List[str]:
    """Names of the media files directly in *directory*, as the app recognises them."""
    from utils.globals import MediaFileType
    return sorted(f for f in os.listdir(directory)
                  if MediaFileType.is_media_filetype(f) and not f.startswith("._")
                  and os.path.isfile(os.path.join(directory, f)))


def move_aside(path: str, directory: str) -> str:
    """Move *path* into *directory*, numbering the name when it is taken. Returns the new path."""
    os.makedirs(directory, exist_ok=True)
    stem, extension = os.path.splitext(os.path.basename(path))
    destination = os.path.join(directory, stem + extension)
    suffix = 1
    while os.path.lexists(destination):
        destination = os.path.join(directory, f"{stem}__{suffix}{extension}")
        suffix += 1
    return move_on_disk(path, destination)


# ── Tags and artwork ─────────────────────────────────────────────────────────

def open_audio(path: str):
    """The mutagen handle for *path*. Raises when the file cannot be parsed; None for an unknown format."""
    from mutagen import File as MutagenFile
    return MutagenFile(path)


def first_text(tags, field: str) -> str:
    """The first value of a text field ("title", "album", "artist"), whatever the tag format."""
    for key in TEXT_TAG_KEYS[field]:
        try:
            value = tags.get(key)
        except Exception:
            continue
        if value is None:
            continue
        value = getattr(value, "text", value)  # an ID3 frame holds its values in .text
        if isinstance(value, (list, tuple)):
            if not value:
                continue
            value = value[0]
        text = str(value).strip()
        if text:
            return text
    return ""


def _front_or_first(pictures) -> Optional[bytes]:
    if not pictures:
        return None
    front = next((p for p in pictures if getattr(p, "type", None) == FRONT_COVER), pictures[0])
    data = getattr(front, "data", None)
    return bytes(data) if data else None


def picture_from(audio) -> Optional[bytes]:
    """The embedded cover of an open mutagen handle, preferring the front cover."""
    if audio is None:
        return None
    pictures = getattr(audio, "pictures", None)  # FLAC
    if pictures:
        return _front_or_first(pictures)
    tags = getattr(audio, "tags", None)
    if tags is None:
        return None
    if hasattr(tags, "getall"):  # ID3, whatever description each frame carries
        return _front_or_first([f for f in tags.getall("APIC") if getattr(f, "data", None)])
    try:
        covers = tags.get("covr")  # MP4
    except Exception:
        covers = None
    if covers:
        return bytes(covers[0])
    try:
        blocks = tags.get("metadata_block_picture")  # Ogg Vorbis / Opus
    except Exception:
        blocks = None
    if blocks:
        from mutagen.flac import Picture
        decoded = []
        for block in blocks:
            try:
                decoded.append(Picture(base64.b64decode(block)))
            except Exception:
                continue
        return _front_or_first(decoded)
    return None


def picture_bytes(path: str) -> Optional[bytes]:
    """The embedded cover of *path*, or None when it has none or cannot be read."""
    try:
        return picture_from(open_audio(path))
    except Exception as e:
        logger.warning(_("Could not read the artwork of {0}: {1}").format(path, e))
        return None


def write_picture(path: str, data: bytes) -> Optional[str]:
    """Embed *data* as the cover of *path*. Returns an error message, or None on success.

    The write is read back before it counts: a tag library that cannot store a
    field can fail silently.
    """
    try:
        import music_tag
        mfile = music_tag.load_file(path)
        if mfile is None:
            return _("music_tag could not open the file")
        mfile["artwork"] = bytes(data)
        mfile.save()
    except Exception as e:
        return _("Could not write the artwork: {0}").format(e)
    if not picture_bytes(path):
        return _("The artwork is still absent after writing")
    return None


def remove_pictures(path: str) -> bool:
    """Remove every embedded picture, returning whether the file ended up with none.

    music_tag cannot clear an MP4 cover: its MP4 tag map gives artwork no remover,
    so remove_tag does nothing. The removal is verified by re-reading, and the
    container's own picture storage is cleared directly when the image survives.
    """
    try:
        import music_tag
        mfile = music_tag.load_file(path)
        mfile.remove_tag("artwork")
        mfile.save()
    except Exception as e:
        logger.debug("music_tag could not remove the artwork of %s: %s", path, e)
    if not picture_bytes(path):
        return True
    audio = open_audio(path)
    if audio is None:
        return False
    if hasattr(audio, "clear_pictures"):  # FLAC
        audio.clear_pictures()
    tags = getattr(audio, "tags", None)
    if tags is not None:
        if hasattr(tags, "delall"):  # ID3
            tags.delall("APIC")
        for key in ("covr", "metadata_block_picture", "coverart", "coverartmime"):
            try:
                del tags[key]
            except (KeyError, TypeError, ValueError):
                pass
    audio.save()
    return not picture_bytes(path)
