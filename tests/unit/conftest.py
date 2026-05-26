"""
conftest for tests/unit/.

If this tree is collected without the parent ``tests/conftest.py`` loading first
(unusual), apply the same env bootstrap as the root conftest via ``bootstrap_env``.
"""

import importlib.util
import os

if "MUSE_CACHE_DIR" not in os.environ:
    _spec = importlib.util.spec_from_file_location(
        "muse_tests_bootstrap_env",
        os.path.join(os.path.dirname(__file__), "..", "bootstrap_env.py"),
    )
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    _mod.apply()
