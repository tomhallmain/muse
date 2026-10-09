"""
Test environment bootstrap (cache/config paths, offscreen Qt, keyring).

Called at import time from ``tests/conftest.py`` and ``tests/unit/conftest.py``
so env vars exist before ``utils`` / ``muse`` singletons load. Safe to call
multiple times; only the first call creates temp dirs.

Also substitutes the OS credential store, which has to happen at import for the
reason given on ``_install_fake_keyring``.
"""

from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

_applied = False
_cleanup_tmp: str | None = None
_fake_keyring: "_FakeKeyring | None" = None


class _FakeKeyring:
    """In-memory stand-in for the OS credential store."""

    def __init__(self) -> None:
        self._store: dict = {}

    def get_password(self, service_name, key):
        return self._store.get((service_name, key))

    def set_password(self, service_name, key, value):
        self._store[(service_name, key)] = value

    def delete_password(self, service_name, key):
        # The real backends raise when the entry is absent, and the encryptor's
        # quiet-delete helpers rely on that.
        if (service_name, key) not in self._store:
            raise Exception(f"No such password: {service_name}:{key}")
        del self._store[(service_name, key)]

    def clear(self) -> None:
        self._store.clear()


def _install_fake_keyring() -> None:
    """Substitute the OS credential store before anything can reach it.

    Everything that encrypts or decrypts goes through ``utils.encryptor``, which
    talks to the real Credential Manager / Keychain / Secret Service. The cache
    itself is already redirected to a temp directory, but the *keys* for it were
    not: ``AppInfoCache`` decrypts in its constructor, which runs at import, so
    this has to be in place before the first project import rather than in a
    fixture.

    Substituted at module level for the same reason -- a fixture leaves a window
    in which a test can reach the real store.
    """
    global _fake_keyring
    if _fake_keyring is not None:
        return
    root = project_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        import utils.encryptor as encryptor_module
    except ImportError:
        # No keyring/cryptography here, so the encryptor cannot run at all and
        # there is no real store for a test to reach.
        return
    _fake_keyring = _FakeKeyring()
    encryptor_module.keyring = _fake_keyring


def clear_fake_keyring() -> None:
    """Empty the substitute store between tests."""
    if _fake_keyring is not None:
        _fake_keyring.clear()


def _pin_key_backup_dir() -> None:
    """Keep automatic key-material backups inside the throwaway directory.

    With no destination set the encryptor picks the first writable external
    drive it finds, which on a developer machine is a real USB stick. Assigned
    rather than defaulted: a developer with this set in their own environment
    has it pointing somewhere real, which is the case that most needs
    overriding.
    """
    cache_dir = os.environ.get("MUSE_CACHE_DIR")
    if cache_dir:
        os.environ["MUSE_KEY_BACKUP_DIR"] = os.path.join(cache_dir, "key_backup")


def apply() -> None:
    global _applied
    # The temp dirs come before the keyring substitution: installing it imports
    # the ``utils`` package, whose config and app info cache singletons resolve
    # their paths -- and would move legacy repo files into the real app data
    # dir -- as they load.
    if not _applied:
        _redirect_user_data()
    _install_fake_keyring()
    _pin_key_backup_dir()
    _applied = True


def _redirect_user_data() -> None:
    """Point every per-user location at one temp dir; a value the caller set wins."""
    global _cleanup_tmp
    if all(os.environ.get(v) for v in ("MUSE_APP_DATA_DIR", "MUSE_CACHE_DIR", "MUSE_CONFIGS_DIR")):
        return
    _cleanup_tmp = tempfile.mkdtemp(prefix="muse_tests_")
    atexit.register(shutil.rmtree, _cleanup_tmp, True)
    # The app data root covers what has no override of its own (logs, tts_output).
    os.environ.setdefault("MUSE_APP_DATA_DIR", _cleanup_tmp)
    os.environ.setdefault("MUSE_CACHE_DIR", os.path.join(_cleanup_tmp, "cache"))
    os.environ.setdefault("MUSE_CONFIGS_DIR", os.path.join(_cleanup_tmp, "configs"))
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.makedirs(os.environ["MUSE_CACHE_DIR"], exist_ok=True)
    os.makedirs(os.environ["MUSE_CONFIGS_DIR"], exist_ok=True)
    config_path = os.path.join(os.environ["MUSE_CONFIGS_DIR"], "config.json")
    config_example = Path(project_root()) / "library_data" / "data" / "config_example.json"
    if config_example.is_file() and not os.path.exists(config_path):
        shutil.copy(config_example, config_path)


def project_root() -> str:
    return str(Path(__file__).resolve().parent.parent)
