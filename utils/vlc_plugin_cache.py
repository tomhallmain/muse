"""
Detect and fix VLC's stale plugin cache (avoids libvlc 'stale plugins cache' errors).

Detection uses a filesystem heuristic: if any plugin module under the VLC plugins directory
is newer than ``plugins.dat``, the cache is stale.

**Windows:** ``vlc-cache-gen.exe`` must run with administrator rights when VLC is under
``Program Files``. This module never runs the tool in-process; it records that the cache is
stale and the Qt UI may prompt the user, then start ``scripts/vlc_cache_fixer.py`` in a
separate process (that script triggers UAC and runs the generator).

**macOS / Linux:** Regeneration runs automatically via ``vlc-cache-gen`` when stale (may
still fail under system paths without sufficient privileges; see logs).

Opt out: set environment variable ``MUSE_SKIP_VLC_PLUGIN_CACHE_FIX=1``, or set
``auto_fix_vlc_plugin_cache`` to false in config.json.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_PLUGIN_SUFFIXES: Tuple[str, ...] = (
    ".dll",
    ".so",
    ".dylib",
)


def _find_vlc_windows() -> Optional[Path]:
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "VideoLAN" / "VLC",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "VideoLAN" / "VLC",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "VideoLAN" / "VLC",
    ]
    for path in candidates:
        if path.exists() and (path / "vlc-cache-gen.exe").exists():
            return path
    return None


def _find_vlc_macos() -> Optional[Path]:
    for path in (
        Path("/Applications/VLC.app/Contents/MacOS"),
        Path.home() / "Applications/VLC.app/Contents/MacOS",
    ):
        if path.exists() and (path / "vlc-cache-gen").exists():
            return path
    return None


def _linux_plugin_dirs() -> Tuple[Path, ...]:
    return (
        Path("/usr/lib/x86_64-linux-gnu/vlc/plugins"),
        Path("/usr/lib64/vlc/plugins"),
        Path("/usr/lib/vlc/plugins"),
        Path("/usr/local/lib/vlc/plugins"),
        Path("/snap/vlc/current/usr/lib/x86_64-linux-gnu/vlc/plugins"),
        Path("/snap/vlc/current/usr/lib/vlc/plugins"),
    )


def find_vlc_paths() -> Tuple[Optional[Path], Optional[Path]]:
    """
    Return (directory containing vlc-cache-gen binary, plugins directory) or (None, None).
    """
    system = platform.system()
    if system == "Windows":
        vlc_bin = _find_vlc_windows()
        if vlc_bin is None:
            return None, None
        plugins = vlc_bin / "plugins"
        return (vlc_bin, plugins) if plugins.exists() else (None, None)

    if system == "Darwin":
        vlc_bin = _find_vlc_macos()
        if vlc_bin is None:
            return None, None
        bundle = vlc_bin.parent
        plugins = bundle / "PlugIns"
        if not plugins.exists():
            plugins = bundle.parent / "PlugIns"
        return (vlc_bin, plugins) if plugins.exists() else (None, None)

    if system == "Linux":
        which = shutil.which("vlc-cache-gen")
        if which:
            gen_dir = Path(which).resolve().parent
            for plugins in _linux_plugin_dirs():
                if plugins.is_dir():
                    return gen_dir, plugins
        for plugins in _linux_plugin_dirs():
            if plugins.is_dir():
                gen = plugins.parent / "vlc-cache-gen"
                if gen.is_file():
                    return gen.parent, plugins
        return None, None

    return None, None


def max_plugin_mtime(plugins_dir: Path) -> Optional[float]:
    """Latest mtime among native plugin modules (not plugins.dat)."""
    latest: Optional[float] = None
    try:
        for root, _, files in os.walk(plugins_dir):
            for name in files:
                if not name.endswith(_PLUGIN_SUFFIXES):
                    continue
                if name == "plugins.dat":
                    continue
                try:
                    m = (Path(root) / name).stat().st_mtime
                except OSError:
                    continue
                if latest is None or m > latest:
                    latest = m
    except OSError as e:
        logger.debug("Could not scan VLC plugins dir %s: %s", plugins_dir, e)
        return None
    return latest


def is_plugin_cache_stale(plugins_dir: Path) -> bool:
    """
    True if plugins.dat is missing or older than the newest plugin module.
    """
    if not plugins_dir.is_dir():
        return False
    latest_plugin = max_plugin_mtime(plugins_dir)
    if latest_plugin is None:
        return False
    cache_file = plugins_dir / "plugins.dat"
    if not cache_file.exists():
        return True
    try:
        return latest_plugin > cache_file.stat().st_mtime
    except OSError:
        return True


def _regenerate_unix(cache_gen: Path, plugins_dir: Path) -> bool:
    if not cache_gen.is_file():
        logger.warning("VLC cache generator not found: %s", cache_gen)
        return False
    try:
        logger.info("Regenerating VLC plugin cache: %s %s", cache_gen, plugins_dir)
        r = subprocess.run(
            [str(cache_gen), str(plugins_dir)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r.returncode == 0:
            logger.info("VLC plugin cache regenerated successfully.")
            return True
        logger.warning(
            "vlc-cache-gen exited with %s. stderr: %s",
            r.returncode,
            (r.stderr or "")[:500],
        )
        if str(plugins_dir).startswith(("/usr/", "/snap/")):
            logger.warning(
                "If permission was denied, run once: sudo %s %s",
                cache_gen,
                plugins_dir,
            )
    except subprocess.TimeoutExpired:
        logger.warning("vlc-cache-gen timed out.")
    except OSError as e:
        logger.warning("Could not run vlc-cache-gen: %s", e)
    return False


def _config_allows_fix() -> bool:
    skip = os.environ.get("MUSE_SKIP_VLC_PLUGIN_CACHE_FIX", "").strip().lower()
    if skip in ("1", "true", "yes", "on"):
        return False
    try:
        from utils.config import config

        return bool(getattr(config, "auto_fix_vlc_plugin_cache", True))
    except Exception:
        return True


_ensure_ran = False
_ensure_lock = threading.Lock()

# Windows: stale cache detected; Qt may prompt once per session to run scripts/vlc_cache_fixer.py
_windows_stale_cache_needs_prompt: bool = False
_windows_stale_cache_dialog_shown: bool = False


def get_vlc_cache_fixer_script_path() -> Path:
    """Path to ``scripts/vlc_cache_fixer.py`` (repo root relative to this package)."""
    return Path(__file__).resolve().parent.parent / "scripts" / "vlc_cache_fixer.py"


def should_show_windows_stale_cache_dialog() -> bool:
    """True if the UI should ask the user to launch the elevated cache fixer (Windows only)."""
    if platform.system() != "Windows":
        return False
    if not _windows_stale_cache_needs_prompt or _windows_stale_cache_dialog_shown:
        return False
    return _config_allows_fix()


def mark_windows_stale_cache_dialog_shown() -> None:
    global _windows_stale_cache_dialog_shown
    _windows_stale_cache_dialog_shown = True


def launch_windows_vlc_cache_fixer() -> bool:
    """Start ``scripts/vlc_cache_fixer.py`` in a new process (UAC elevation happens inside that script on Windows)."""
    script = get_vlc_cache_fixer_script_path()
    if not script.is_file():
        logger.error("VLC cache fixer script not found: %s", script)
        return False
    try:
        subprocess.Popen(
            [sys.executable, str(script)],
            cwd=str(script.resolve().parent.parent),
            close_fds=sys.platform != "win32",
        )
        logger.info("Started VLC cache fixer: %s", script)
        return True
    except OSError as e:
        logger.error("Failed to start VLC cache fixer: %s", e)
        return False


def ensure_vlc_plugin_cache_if_stale() -> None:
    """
    If the VLC plugin cache appears stale, run vlc-cache-gen once per process.
    Safe to call multiple times; subsequent calls no-op after the first run.
    """
    global _ensure_ran
    global _windows_stale_cache_needs_prompt
    if _ensure_ran:
        return
    with _ensure_lock:
        if _ensure_ran:
            return
        try:
            if not _config_allows_fix():
                logger.debug("VLC plugin cache auto-fix skipped (config or env).")
                return

            vlc_bin, plugins_dir = find_vlc_paths()
            if not vlc_bin or not plugins_dir:
                logger.debug("VLC installation not found; skipping plugin cache check.")
                return

            if not is_plugin_cache_stale(plugins_dir):
                logger.debug("VLC plugin cache is up to date (%s).", plugins_dir)
                return

            system = platform.system()
            if system == "Windows":
                logger.info(
                    "VLC plugin cache appears stale (%s). The app may prompt to run the "
                    "elevated cache fixer (scripts/vlc_cache_fixer.py).",
                    plugins_dir,
                )
                if _config_allows_fix():
                    _windows_stale_cache_needs_prompt = True
                return

            logger.info(
                "VLC plugin cache appears stale (plugins newer than plugins.dat). Regenerating…"
            )
            if system == "Darwin":
                ok = _regenerate_unix(vlc_bin / "vlc-cache-gen", plugins_dir)
            else:
                cache_gen = vlc_bin / "vlc-cache-gen"
                ok = _regenerate_unix(cache_gen, plugins_dir) if cache_gen.is_file() else False

            if not ok:
                logger.warning(
                    "Automatic VLC plugin cache rebuild failed. You can run vlc-cache-gen manually "
                    "on the plugins folder, or reinstall VLC."
                )
        except Exception as e:
            logger.warning("VLC plugin cache check failed: %s", e)
        finally:
            _ensure_ran = True
