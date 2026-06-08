"""
Auto-filing logic for downloaded library extensions.

Given a downloaded file and the metadata available at download time (TrackAttribute,
entity name/object, track title), computes the appropriate subdirectory and moves
the file there.

Directory structure assumed:
    config.directories[0]/
        <Genre>/           ← top-level genre dirs discovered by _discover_genre_dirs()
            <Artist|Composer>/
                <Album>/
                    track.mp3

When the genre cannot be determined the file still lands in a structured location
under config.directories[0] rather than at the root.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Optional

from utils.config import config
from utils.globals import TrackAttribute
from utils.logging_setup import get_logger

if TYPE_CHECKING:
    from extensions.llm import LLM

logger = get_logger(__name__)


def _discover_genre_dirs(base_dir: str) -> dict:
    """Return {lowercase_name: full_path} for candidate genre directories.

    If the user has configured auto_file_extensions_genres, only those names are
    used as candidates (the directory need not exist yet — it will be created on
    demand).  Otherwise every Title-Case, non-underscore-prefixed direct child of
    base_dir is treated as a genre target.
    """
    configured = [g.strip() for g in config.auto_file_extensions_genres if g.strip()]
    result: dict = {}
    if configured:
        for name in configured:
            result[name.lower()] = os.path.join(base_dir, name)
    else:
        try:
            for entry in os.scandir(base_dir):
                if entry.is_dir() and entry.name[0].isupper() and not entry.name.startswith("_"):
                    result[entry.name.lower()] = entry.path
        except OSError:
            pass
    return result


def _match_genre(candidate: str, genre_dirs: dict) -> Optional[str]:
    """Return the full path of the best-matching genre dir for candidate, or None."""
    if not candidate or not genre_dirs:
        return None
    c = candidate.lower().strip()
    if c in genre_dirs:
        return genre_dirs[c]
    for name, path in genre_dirs.items():
        if name in c or c in name:
            return path
    return None


def _genre_from_filesystem(entity_name: str, genre_dirs: dict) -> Optional[str]:
    """Scan genre dirs for a pre-existing subdirectory whose name matches entity_name.

    This handles the common case where the library already contains tracks filed
    under e.g. Classical/Bach/ — a new Bach download should land there too.
    """
    if not entity_name or not genre_dirs:
        return None
    entity_lower = entity_name.lower()
    for _name, path in genre_dirs.items():
        try:
            for entry in os.scandir(path):
                if entry.is_dir() and entry.name.lower() == entity_lower:
                    return path
        except OSError:
            pass
    return None


def _infer_genre_dir(
    attr: Optional[TrackAttribute],
    entity_name: Optional[str],
    entity_obj: Any,
    track_title: str,
    genre_dirs: dict,
    llm: Optional["LLM"] = None,
) -> Optional[str]:
    """Determine the target genre directory for a downloaded extension.

    Resolution order:
      1. GENRE attr: match entity name directly against genre dirs
      2. ARTIST/COMPOSER: entity object's .genres field → filesystem scan → Classical fallback (COMPOSER only)
      3. ALBUM: filesystem scan for existing album subdir
      4. LLM fallback: ask the configured LLM to pick from the genre list
    """
    genre_dir = None

    if attr == TrackAttribute.GENRE:
        genre_dir = _match_genre(entity_name, genre_dirs)

    elif attr in (TrackAttribute.ARTIST, TrackAttribute.COMPOSER):
        # 1. Genres embedded in the entity data object
        entity_genres = getattr(entity_obj, "genres", None) if not isinstance(entity_obj, str) else None
        if entity_genres:
            for g in (entity_genres if isinstance(entity_genres, list) else [entity_genres]):
                genre_dir = _match_genre(str(g), genre_dirs)
                if genre_dir:
                    break

        # 2. Pre-existing subdirectory in the filesystem
        if genre_dir is None:
            genre_dir = _genre_from_filesystem(entity_name, genre_dirs)

        # 3. Composer catch-all: Classical
        if genre_dir is None and attr == TrackAttribute.COMPOSER:
            genre_dir = _match_genre("Classical", genre_dirs)

    elif attr == TrackAttribute.ALBUM:
        genre_dir = _genre_from_filesystem(entity_name, genre_dirs)

    # LLM fallback when nothing resolved and genre dirs exist
    if genre_dir is None and genre_dirs and llm is not None:
        try:
            from extensions.llm import LLMResponseException
            if not llm.is_failing():
                genre_list = ", ".join(sorted(genre_dirs.keys()))
                prompt = (
                    f'Classify this track into one of the following genre directories. '
                    f'Track: "{track_title}". '
                    f'Attribute: {attr.get_translation() if attr else "unknown"} = "{entity_name or "unknown"}". '
                    f'Genre directories: {genre_list}. '
                    f'Respond with JSON only: {{"genre": "<chosen_genre>"}}'
                )
                result = llm.generate_json_get_value(prompt, "genre")
                if result and result.response:
                    genre_dir = _match_genre(result.response.strip(), genre_dirs)
        except Exception as e:
            logger.debug("LLM genre inference failed: %s", e)

    return genre_dir


def file_extension(
    f: str,
    attr: Optional[TrackAttribute],
    entity_name: Optional[str],
    entity_obj: Any,
    track_title: str,
    llm: Optional["LLM"] = None,
) -> Optional[str]:
    """Move downloaded file f into the appropriate genre/artist/album subdirectory.

    Returns the new filepath on success, None if auto-filing was skipped or failed.
    Directories are created as needed so the feature works even before the target
    tree exists.
    """
    from library_data.media_track import MediaTrack

    if not config.directories:
        logger.warning("Auto-filing skipped: no directories configured")
        return None

    base_dir = config.directories[0]
    genre_dirs = _discover_genre_dirs(base_dir)
    genre_dir = _infer_genre_dir(attr, entity_name, entity_obj, track_title, genre_dirs, llm)

    root = genre_dir if genre_dir is not None else base_dir

    def san(s: Optional[str]) -> str:
        return MediaTrack.sanitize_filename_stem(str(s)) if s else "Unknown"

    if attr in (TrackAttribute.ARTIST, TrackAttribute.COMPOSER):
        target_dir = os.path.join(root, san(entity_name), "Unknown Album")
    elif attr == TrackAttribute.ALBUM:
        target_dir = os.path.join(root, "Unknown Artist", san(entity_name))
    else:
        target_dir = os.path.join(root, "Unknown Artist", "Unknown Album")

    try:
        os.makedirs(target_dir, exist_ok=True)
        new_path = os.path.join(target_dir, os.path.basename(f))
        os.rename(f, new_path)
        logger.info("Auto-filed extension to: %s", new_path)
        return new_path
    except Exception as e:
        logger.error("Auto-filing move failed: %s", e)
        return None
