"""Tests for BlacklistItemType-scoped matching and serialization."""

import pytest

from library_data.blacklist import Blacklist, BlacklistItem
from utils.globals import BlacklistItemType


@pytest.fixture(autouse=True)
def _isolated_blacklist():
    Blacklist.clear()
    yield
    Blacklist.clear()


@pytest.mark.unit
class TestBlacklistItemTypeDefaults:
    def test_default_item_type_is_general(self):
        item = BlacklistItem("badword")
        assert item.item_type == BlacklistItemType.GENERAL

    def test_to_dict_includes_type(self):
        item = BlacklistItem("badword", item_type=BlacklistItemType.CHANNEL)
        assert item.to_dict()["type"] == "channel"

    def test_from_dict_round_trips_type(self):
        item = BlacklistItem("badword", item_type=BlacklistItemType.ARTIST)
        restored = BlacklistItem.from_dict(item.to_dict())
        assert restored.item_type == BlacklistItemType.ARTIST

    def test_from_dict_missing_type_defaults_to_general(self):
        """Legacy items serialized before this feature existed have no "type" key at all."""
        data = {"string": "badword", "enabled": True}
        restored = BlacklistItem.from_dict(data)
        assert restored.item_type == BlacklistItemType.GENERAL

    def test_from_dict_invalid_type_defaults_to_general(self):
        data = {"string": "badword", "type": "not-a-real-type"}
        restored = BlacklistItem.from_dict(data)
        assert restored.item_type == BlacklistItemType.GENERAL

    def test_from_dict_any_is_coerced_to_general(self):
        """ANY is a query-only wildcard, never a valid item type -- even if present in serialized data."""
        data = {"string": "badword", "type": "any"}
        restored = BlacklistItem.from_dict(data)
        assert restored.item_type == BlacklistItemType.GENERAL

    def test_assignable_types_excludes_any(self):
        assert BlacklistItemType.ANY not in BlacklistItemType.assignable_types()
        assert BlacklistItemType.GENERAL in BlacklistItemType.assignable_types()

    def test_any_has_no_display_round_trip_via_assignable_types(self):
        """The per-item type picker (display_values/from_display) never offers ANY."""
        assert BlacklistItemType.ANY.display() not in BlacklistItemType.display_values()


@pytest.mark.unit
class TestTypedMatching:
    def test_no_item_type_argument_checks_everything_like_before(self):
        Blacklist.set_blacklist([BlacklistItem("badword", item_type=BlacklistItemType.CHANNEL)])
        assert Blacklist.get_violation_item("this has badword in it") is not None

    def test_any_item_type_argument_checks_everything_too(self):
        """ANY as an explicit query value behaves exactly like omitting item_type."""
        Blacklist.set_blacklist([BlacklistItem("badword", item_type=BlacklistItemType.CHANNEL)])
        result = Blacklist.get_violation_item("this has badword in it", item_type=BlacklistItemType.ANY)
        assert result is not None

    def test_matching_type_is_checked(self):
        Blacklist.set_blacklist([BlacklistItem("badword", item_type=BlacklistItemType.CHANNEL)])
        result = Blacklist.get_violation_item("a badword channel", item_type=BlacklistItemType.CHANNEL)
        assert result is not None

    def test_non_matching_type_is_not_checked(self):
        Blacklist.set_blacklist([BlacklistItem("badword", item_type=BlacklistItemType.CHANNEL)])
        result = Blacklist.get_violation_item("a badword artist", item_type=BlacklistItemType.ARTIST)
        assert result is None

    def test_general_typed_item_matches_regardless_of_requested_type(self):
        Blacklist.set_blacklist([BlacklistItem("badword")])
        assert Blacklist.get_violation_item("badword", item_type=BlacklistItemType.CHANNEL) is not None
        assert Blacklist.get_violation_item("badword", item_type=BlacklistItemType.ARTIST) is not None

    def test_find_blacklisted_items_respects_type(self):
        Blacklist.set_blacklist([BlacklistItem("badword", item_type=BlacklistItemType.CHANNEL)])
        assert Blacklist.find_blacklisted_items("badword", item_type=BlacklistItemType.CHANNEL)
        assert not Blacklist.find_blacklisted_items("badword", item_type=BlacklistItemType.ARTIST)

    def test_find_violated_patterns_respects_type(self):
        Blacklist.set_blacklist([BlacklistItem("badword", item_type=BlacklistItemType.ARTIST)])
        assert Blacklist.find_violated_patterns("badword", item_type=BlacklistItemType.ARTIST) == {"badword"}
        assert Blacklist.find_violated_patterns("badword", item_type=BlacklistItemType.CHANNEL) == set()


@pytest.mark.unit
class TestVersionInvalidation:
    def test_version_differs_for_items_that_differ_only_by_type(self):
        Blacklist.set_blacklist([BlacklistItem("badword", item_type=BlacklistItemType.ARTIST)])
        version_artist = Blacklist.get_version()

        Blacklist.set_blacklist([BlacklistItem("badword", item_type=BlacklistItemType.CHANNEL)])
        version_channel = Blacklist.get_version()

        assert version_artist != version_channel
