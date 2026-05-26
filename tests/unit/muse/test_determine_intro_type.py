"""Isolated unit tests for DJ introduction type selection (no muse_memory / Muse)."""

import datetime
import time
from types import SimpleNamespace

import pytest

from muse.intro_type import determine_intro_type
from utils.globals import IntroType


def mktime(dt: datetime.datetime) -> float:
    return time.mktime(dt.timetuple())


def persona(last_hello_time=None, last_signoff_time=None):
    return SimpleNamespace(
        last_hello_time=last_hello_time,
        last_signoff_time=last_signoff_time,
    )


@pytest.mark.unit
class TestDetermineIntroType:
    @pytest.fixture(autouse=True)
    def reference(self):
        self.reference_time = datetime.datetime(2024, 3, 20, 12, 0, 0)
        self.reference_timestamp = mktime(self.reference_time)

    def test_first_time_introduction(self):
        assert determine_intro_type(self.reference_timestamp, persona()) == IntroType.INTRO

    def test_long_absence(self):
        last_interaction = mktime(self.reference_time.replace(hour=5, minute=0))
        assert (
            determine_intro_type(
                self.reference_timestamp,
                persona(last_interaction, last_interaction),
            )
            == IntroType.INTRO
        )

    def test_recent_return(self):
        assert (
            determine_intro_type(
                self.reference_timestamp,
                persona(
                    mktime(self.reference_time.replace(hour=5, minute=0)),
                    mktime(self.reference_time.replace(hour=9, minute=0)),
                ),
            )
            == IntroType.REINTRO
        )

    def test_very_recent_return(self):
        assert (
            determine_intro_type(
                self.reference_timestamp,
                persona(
                    mktime(self.reference_time.replace(hour=5, minute=0)),
                    mktime(self.reference_time.replace(hour=11, minute=30)),
                ),
            )
            == IntroType.NONE
        )

    def test_sleeping_hours_case(self):
        last_signoff = mktime(self.reference_time.replace(hour=23, minute=0))
        current_time = mktime(self.reference_time.replace(hour=6, minute=0)) + 86400
        assert (
            determine_intro_type(
                current_time,
                persona(
                    mktime(self.reference_time.replace(hour=17, minute=0)),
                    last_signoff,
                ),
            )
            == IntroType.INTRO
        )

    def test_recent_hello_and_signoff(self):
        assert (
            determine_intro_type(
                self.reference_timestamp,
                persona(
                    mktime(self.reference_time.replace(hour=9, minute=0)),
                    mktime(self.reference_time.replace(hour=9, minute=0)),
                ),
            )
            == IntroType.REINTRO
        )

    def test_exactly_six_hours_since_signoff(self):
        assert (
            determine_intro_type(
                self.reference_timestamp,
                persona(
                    mktime(self.reference_time.replace(hour=5, minute=0)),
                    mktime(self.reference_time.replace(hour=6, minute=0)),
                ),
            )
            == IntroType.REINTRO
        )

    def test_exactly_one_hour_since_signoff(self):
        assert (
            determine_intro_type(
                self.reference_timestamp,
                persona(
                    mktime(self.reference_time.replace(hour=5, minute=0)),
                    mktime(self.reference_time.replace(hour=11, minute=0)),
                ),
            )
            == IntroType.NONE
        )
