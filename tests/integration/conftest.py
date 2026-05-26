"""
Integration test layer.

Isolation env vars are set in ``tests/conftest.py`` (always loaded for paths
under ``tests/``). This file only applies the integration marker.
"""

import pytest

pytestmark = pytest.mark.integration
