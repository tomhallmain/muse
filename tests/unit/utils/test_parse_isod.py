"""Unit tests for Utils.parse_isod.

Regression coverage for a YouTube Data API quirk: contentDetails.duration
for a live/premiere broadcast with no determined length yet is reported as
a date-only (or entirely unit-less) ISO8601 duration, e.g. "P0D" or "P0",
with no "T" time-of-day portion at all. parse_isod used to require a
literal "PT" substring and raised ValueError("Missing PT prefix: ...") on
these, aborting the whole library-extension attempt for the affected
artist/track (see extensions/library_extender.py, extensions/
extension_manager.py ExtensionManager._extend).
"""
import pytest

from utils.utils import Utils


@pytest.mark.unit
class TestParseIsod:
    def test_full_duration_with_hours_minutes_seconds(self):
        assert Utils.parse_isod("PT3H2M59.989333S") == pytest.approx(10979.989333)

    def test_date_and_time_duration(self):
        assert Utils.parse_isod("P1DT2H") == 93600.0

    def test_date_only_duration_returns_zero(self):
        # No "T"/time portion at all -- must not raise.
        assert Utils.parse_isod("P0D") == 0.0

    def test_bare_p_with_no_unit_returns_zero(self):
        # The exact value observed from the YouTube API for an
        # indeterminate-duration live broadcast: no unit designator at all.
        assert Utils.parse_isod("P0") == 0.0

    def test_missing_p_prefix_raises(self):
        with pytest.raises(ValueError):
            Utils.parse_isod("3H2M59S")
