"""
Integration test layer.

Isolation env vars are set in ``tests/conftest.py`` (always loaded for paths
under ``tests/``), which also applies the ``integration`` marker to everything
in this tree via ``pytest_collection_modifyitems``.
"""
