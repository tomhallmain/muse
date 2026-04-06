#!/usr/bin/env python3
"""
Regenerate VLC's plugin cache (vlc-cache-gen). Intended to be launched as a separate process
so Windows can show UAC elevation outside the main Muse process.

Usage: python scripts/vlc_cache_fixer.py
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _is_admin_windows() -> bool:
    try:
        import ctypes

        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _elevate_windows(script_path: str) -> None:
    """Re-run this script with administrator privileges (UAC)."""
    import ctypes

    ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        sys.executable,
        f'"{script_path}"',
        None,
        1,
    )
    sys.exit(0)


def _find_vlc_windows() -> Optional[Path]:
    for path in (
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "VideoLAN" / "VLC",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "VideoLAN" / "VLC",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "VideoLAN" / "VLC",
    ):
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


def get_vlc_paths() -> Tuple[Optional[Path], Optional[Path]]:
    """Return (directory with vlc-cache-gen, plugins directory)."""
    system = platform.system()
    if system == "Windows":
        vlc_bin = _find_vlc_windows()
        if vlc_bin:
            plugins = vlc_bin / "plugins"
            return vlc_bin, plugins if plugins.exists() else None
        return None, None

    if system == "Darwin":
        vlc_bin = _find_vlc_macos()
        if vlc_bin:
            bundle = vlc_bin.parent
            plugins = bundle / "PlugIns"
            if not plugins.exists():
                plugins = bundle.parent / "PlugIns"
            return vlc_bin, plugins if plugins.exists() else None
        return None, None

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


def _regenerate_windows(vlc_bin: Path, plugins_dir: Path) -> bool:
    cache_gen = vlc_bin / "vlc-cache-gen.exe"
    if not cache_gen.is_file():
        logger.error("Cache generator not found: %s", cache_gen)
        return False
    env = os.environ.copy()
    env["PATH"] = f"{vlc_bin}{os.pathsep}{env.get('PATH', '')}"
    logger.info("Running: %s %s", cache_gen, plugins_dir)
    r = subprocess.run(
        [str(cache_gen), str(plugins_dir)],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if r.returncode == 0:
        logger.info("VLC plugin cache regenerated successfully.")
        return True
    logger.error("vlc-cache-gen failed (%s): %s", r.returncode, (r.stderr or "")[:800])
    return False


def _regenerate_unix(cache_gen: Path, plugins_dir: Path) -> bool:
    if not cache_gen.is_file():
        logger.error("Cache generator not found: %s", cache_gen)
        return False
    logger.info("Running: %s %s", cache_gen, plugins_dir)
    r = subprocess.run(
        [str(cache_gen), str(plugins_dir)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if r.returncode == 0:
        logger.info("VLC plugin cache regenerated successfully.")
        return True
    logger.error("vlc-cache-gen failed (%s): %s", r.returncode, (r.stderr or "")[:800])
    if str(plugins_dir).startswith(("/usr/", "/snap/")):
        logger.info("You may need: sudo %s %s", cache_gen, plugins_dir)
    return False


def main() -> int:
    logger.info("VLC plugin cache regenerator (%s)", platform.system())
    if platform.system() == "Windows":
        if not _is_admin_windows():
            logger.warning("Administrator rights are required to update VLC under Program Files.")
            logger.info("Requesting elevation…")
            _elevate_windows(os.path.abspath(__file__))
            return 1

    vlc_bin, plugins_dir = get_vlc_paths()
    if not vlc_bin or not plugins_dir:
        logger.error("Could not find VLC installation.")
        return 1

    if platform.system() == "Windows":
        ok = _regenerate_windows(vlc_bin, plugins_dir)
    else:
        ok = _regenerate_unix(vlc_bin / "vlc-cache-gen", plugins_dir)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
