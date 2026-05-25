"""
conftest for tests/unit/.

Mirrors module-level env setup from the root conftest so singletons never touch
production cache or config when this directory is collected first.
"""

import atexit
import os
import shutil
import tempfile

if "MUSE_CACHE_DIR" not in os.environ:
    _tmp = tempfile.mkdtemp(prefix="muse_unit_")
    os.environ["MUSE_CACHE_DIR"] = os.path.join(_tmp, "cache")
    os.environ["MUSE_CONFIGS_DIR"] = os.path.join(_tmp, "configs")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.makedirs(os.environ["MUSE_CACHE_DIR"], exist_ok=True)
    os.makedirs(os.environ["MUSE_CONFIGS_DIR"], exist_ok=True)
    _src = os.path.join(os.path.dirname(__file__), "..", "..", "configs", "config_example.json")
    if os.path.isfile(_src):
        shutil.copy(_src, os.path.join(os.environ["MUSE_CONFIGS_DIR"], "config.json"))
    atexit.register(shutil.rmtree, _tmp, True)
