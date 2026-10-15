"""Checks a built executable runs against itself with ``--smoke-test``.

``build_exe.py`` runs the built app this way with ``MUSE_APP_DATA_DIR``
pointing at a scratch directory. Getting far enough to run any check already
proves the app's imports resolved, libvlc included.
"""

import gettext
import json
import os
import traceback

from utils.app_paths import resource_path
from utils.crash_log import enable_fault_log
from utils.logging_setup import get_logger

logger = get_logger("smoke_test")

_EXAMPLE_FILES = (
    "config_example.json",
    "artists_example.json",
    "composers_example.json",
    "forms_example.json",
    "genres_example.json",
    "instruments_example.json",
)


def _check_build_info() -> str:
    """VERSION and build_info.json are bundled, and name the same version;
    returns the startup log line."""
    from utils.app_paths import IS_BUILD
    from utils.version import BUILD_INFO_FILE, app_version, build_info, describe

    version = app_version()
    info = build_info()
    if IS_BUILD:
        if not info:
            raise FileNotFoundError(f"{BUILD_INFO_FILE} is not bundled")
        if info.get("version") != version:
            raise ValueError(f"{BUILD_INFO_FILE} names version {info.get('version')}, the app is {version}")
    return describe()


class SmokeTest:
    def __init__(self):
        self.failures = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        logger.info(f"smoke test: {name}: {'ok' if ok else 'FAILED'} {detail}".rstrip())
        if not ok:
            self.failures.append(name)

    def check_call(self, name: str, func) -> None:
        """Run *func*; it passes unless it raises. A returned string is logged."""
        try:
            detail = func()
            self.check(name, True, detail if isinstance(detail, str) else "")
        # SystemExit too: Nuitka's metadata lookup exits the build when a
        # bundled package's metadata is missing.
        except (Exception, SystemExit) as e:
            self.check(name, False, f"{type(e).__name__}: {e}")
            # The message alone can be bare (e.g. "KeyError: 2"); the build log
            # is the only place a build's failure can be diagnosed from.
            logger.error(f"smoke test: {name}: traceback:\n{traceback.format_exc()}")

    def report(self, name: str, detail: str) -> None:
        """Log something the build does not require (external programs)."""
        logger.info(f"smoke test: {name}: {detail}")

    def run_all(self, expect_oqs: bool = False) -> None:
        self.check_files()
        self.check_data()
        self.check_dependencies(expect_oqs)

    def check_files(self) -> None:
        """Bundled read-only files at the paths the app resolves them under; the fault log opens."""
        from utils.config import config
        from utils.translations import I18N

        self.check("config", os.path.isfile(config.config_path), config.config_path)
        self.check("locale", gettext.find("base", I18N.localedir, ["de"]) is not None, I18N.localedir)
        self.check(
            "prompts",
            os.path.isdir(os.path.join(config.prompts_directory, "en")),
            config.prompts_directory,
        )
        self.check("app icon", os.path.isfile(resource_path("assets", "icon.png")))
        self.check("sounds", os.path.isfile(resource_path("lib", "sounds", "success.wav")))
        self.check("English dictionary", os.path.isfile(resource_path("tts", "dictionary_en.txt")))
        for name in _EXAMPLE_FILES:
            self.check(name, os.path.isfile(resource_path("library_data", "data", name)))
        self.check_call("fault log", enable_fault_log)
        self.check_call("build info", _check_build_info)

    def check_data(self) -> None:
        """Encrypted bundled data decrypts, and the library DB is created and seeded."""
        from utils.encryptor import symmetric_decrypt_data_from_file
        from utils.globals import AppInfo
        from utils.utils import Utils

        def default_blacklist():
            from library_data.blacklist import Blacklist

            encoded = symmetric_decrypt_data_from_file(
                Blacklist.DEFAULT_BLACKLIST_FILE_LOC,
                (AppInfo.APP_IDENTIFIER + "_blacklist").encode("utf-8"),
            )
            return f"{len(json.loads(Utils.postprocess_data_from_decryption(encoded)))} items"

        def library_db():
            from utils.db import DB_PATH, get_connection

            count = get_connection().execute("SELECT COUNT(*) FROM composers").fetchone()[0]
            if count == 0:
                raise ValueError(f"no composers seeded into {DB_PATH}")
            return f"{count} composers in {DB_PATH}"

        self.check_call("default blacklist", default_blacklist)
        self.check_call("library DB", library_db)

    def check_dependencies(self, expect_oqs: bool) -> None:
        """Keyring backend, Coqui, OQS, and the external programs (reported only)."""
        import keyring
        import keyring.backends.fail

        backend = keyring.get_keyring()
        self.check(
            "keyring backend",
            not isinstance(backend, keyring.backends.fail.Keyring),
            f"{type(backend).__module__}.{type(backend).__name__}",
        )

        def coqui():
            from tts.providers.coqui import CoquiTTSProvider

            CoquiTTSProvider.prepare_import()
            # The model class Muse loads (XTTS v2), without its weights.
            from TTS.api import TTS  # noqa: F401
            from TTS.tts.models.xtts import Xtts  # noqa: F401

        self.check_call("Coqui TTS", coqui)

        from utils import encryptor

        oqs_available = encryptor.KeyEncapsulation is not None
        if expect_oqs:
            self.check("OQS key encapsulation", oqs_available)
        else:
            self.report("OQS key encapsulation", "available" if oqs_available else "not in this build")

        try:
            import vlc

            self.report("libvlc", vlc.libvlc_get_version().decode("utf-8", "replace"))
        except Exception as e:
            self.report("libvlc", f"not usable ({type(e).__name__}: {e})")

        from utils.utils import Utils

        self.report("ffmpeg", "found" if Utils.executable_available("ffmpeg") else "not on PATH")

    def result(self) -> int:
        """Exit code: 0 if every check passed."""
        if self.failures:
            logger.error(f"smoke test failed: {', '.join(self.failures)}")
            return 1
        logger.info("smoke test passed")
        return 0
