"""
Test environment bootstrap (cache/config paths, offscreen Qt).

Called at import time from ``tests/conftest.py`` and ``tests/unit/conftest.py``
so env vars exist before ``utils`` / ``muse`` singletons load. Safe to call
multiple times; only the first call creates temp dirs.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path

_applied = False
_cleanup_tmp: str | None = None


def apply() -> None:
    global _applied, _cleanup_tmp
    if _applied or os.environ.get("MUSE_CACHE_DIR"):
        _applied = True
        return

    project_root = Path(__file__).resolve().parent.parent
    config_example = project_root / "configs" / "config_example.json"

    _cleanup_tmp = tempfile.mkdtemp(prefix="muse_tests_")
    os.environ["MUSE_CACHE_DIR"] = os.path.join(_cleanup_tmp, "cache")
    os.environ["MUSE_CONFIGS_DIR"] = os.path.join(_cleanup_tmp, "configs")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.makedirs(os.environ["MUSE_CACHE_DIR"], exist_ok=True)
    os.makedirs(os.environ["MUSE_CONFIGS_DIR"], exist_ok=True)
    if config_example.is_file():
        shutil.copy(config_example, os.path.join(os.environ["MUSE_CONFIGS_DIR"], "config.json"))
    atexit.register(shutil.rmtree, _cleanup_tmp, True)
    _applied = True


def project_root() -> str:
    return str(Path(__file__).resolve().parent.parent)
