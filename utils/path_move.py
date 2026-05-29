"""
Filesystem rename/move helpers for track path updates.

On Windows, ``os.rename`` cannot move across drive letters; ``shutil.move`` is
used when source and destination are on different volumes. Path comparisons use
``normcase`` so case-only renames do not trip "already exists" checks.
"""

from __future__ import annotations

import os
import shutil


def normcase_path(path: str) -> str:
    """Absolute, normalized path for stable comparison (case-insensitive on Windows)."""
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def same_volume(path_a: str, path_b: str) -> bool:
    """Return True when *path_a* and *path_b* can be linked with ``os.rename``."""
    a = os.path.abspath(path_a)
    b = os.path.abspath(path_b)
    if os.name == "nt":
        return os.path.splitdrive(a)[0].lower() == os.path.splitdrive(b)[0].lower()
    try:
        st_a = os.stat(a)
        st_b = os.stat(b)
        return st_a.st_dev == st_b.st_dev
    except OSError:
        # Parent may not exist yet (e.g. move target dir); compare drives only.
        return os.path.splitdrive(a)[0].lower() == os.path.splitdrive(b)[0].lower()


def paths_equivalent(path_a: str, path_b: str) -> bool:
    return normcase_path(path_a) == normcase_path(path_b)


def destination_occupied(src: str, dst: str) -> bool:
    """True if *dst* exists and is not the same location as *src*."""
    if not os.path.lexists(dst):
        return False
    return not paths_equivalent(src, dst)


def move_on_disk(src: str, dst: str) -> str:
    """Move or rename *src* to *dst* (same- or cross-volume). Returns the final path."""
    src = os.path.abspath(src)
    dst = os.path.abspath(dst)
    if same_volume(src, dst):
        os.rename(src, dst)
        return dst
    return shutil.move(src, dst)
