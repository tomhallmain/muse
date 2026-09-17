"""
conftest for tests/unit/.

If this tree is collected without the parent ``tests/conftest.py`` loading first
(unusual), apply the same env bootstrap as the root conftest via ``bootstrap_env``.

Also blocks real network calls for every test in this tree -- see ``no_network``.
"""

import importlib.util
import os

import pytest

if "MUSE_CACHE_DIR" not in os.environ:
    _spec = importlib.util.spec_from_file_location(
        "muse_tests_bootstrap_env",
        os.path.join(os.path.dirname(__file__), "..", "bootstrap_env.py"),
    )
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    _mod.apply()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Turn an accidental real network call in a unit test into a failure.

    Every unit test stubs its own transport, so nothing here should reach the
    network. This catches the case where a stub stops matching the code it
    stands in for and the call falls through to the real host instead --
    silently passing while hitting a third-party API. Live calls belong in
    tests/api/, which this conftest does not apply to.

    Patched at the two chokepoints this project's HTTP goes through. A test
    patching a higher-level name (``requests.get``, a module's ``urlopen``)
    still works: its patch sits in front of this one and restores to it.
    """
    def blocked(*_args, **_kwargs):
        raise AssertionError(
            "A unit test attempted a real network call. Stub the transport, or "
            "move the test to tests/api/ where live calls are expected."
        )

    monkeypatch.setattr("urllib.request.urlopen", blocked)
    try:
        import requests.sessions  # noqa: F401
    except ImportError:
        return
    monkeypatch.setattr("requests.sessions.Session.request", blocked)
