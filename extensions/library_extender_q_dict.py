"""Reading and writing the library extender's encrypted q dict.

The dict ships encrypted as extensions/library_ext_q_dict.enc. Its decrypted
form is cached as JSON in the cache dir and reused while it is at least as new as
the encrypted file, so writing a new encrypted file makes the app rebuild the
cache on its next start.
"""

import json
import os
from typing import Optional

from utils.app_paths import cache_dir, resource_path
from utils.encryptor import symmetric_decrypt_data_from_file, symmetric_encrypt_data_to_file
from utils.globals import AppInfo
from utils.logging_setup import get_logger
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._

logger = get_logger(__name__)


def encrypted_path() -> str:
    return resource_path("extensions", "library_ext_q_dict.enc")


def cache_path() -> str:
    return os.path.join(cache_dir(), "library_ext_q_dict.json")


def _passphrase() -> bytes:
    return (AppInfo.APP_IDENTIFIER + "_library_ext_q_dict").encode("utf-8")


def decrypt(path: Optional[str] = None) -> dict:
    """The dict stored in the encrypted file at *path* (default: the shipped one)."""
    path = path or encrypted_path()
    loaded = json.loads(Utils.postprocess_data_from_decryption(
        symmetric_decrypt_data_from_file(path, _passphrase())))
    if not isinstance(loaded, dict):
        raise ValueError(f"{os.path.basename(path)} did not decrypt to a dictionary")
    return loaded


def encrypt(data: dict, path: Optional[str] = None) -> None:
    """Write *data* encrypted to *path* (default: the shipped file)."""
    if not isinstance(data, dict):
        raise ValueError("the q dict must be a dictionary")
    preprocessed = Utils.preprocess_data_for_encryption(json.dumps(data, ensure_ascii=False))
    symmetric_encrypt_data_to_file(preprocessed, path or encrypted_path(), _passphrase())


def load() -> dict:
    """The q dict, from the cache when it is current, otherwise decrypted and re-cached."""
    encrypted, cached = encrypted_path(), cache_path()
    if os.path.isfile(cached) and os.path.isfile(encrypted):
        try:
            if os.path.getmtime(cached) >= os.path.getmtime(encrypted):
                with open(cached, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    return loaded
        except Exception as e:
            logger.warning(_("Failed to load library extender q_dict cache, will decrypt: {0}").format(e))

    loaded = decrypt(encrypted)
    tmp = cached + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(loaded, f, ensure_ascii=False)
        os.replace(tmp, cached)
    except Exception as e:
        logger.warning(_("Could not write library extender q_dict cache: {0}").format(e))
        try:
            if os.path.isfile(tmp):
                os.unlink(tmp)
        except OSError:
            pass
    return loaded
