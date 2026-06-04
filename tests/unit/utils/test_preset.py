"""Unit tests for ui_qt/preset.py."""

import pytest

from ui_qt.preset import Preset
from utils.globals import PlaylistSortType


def make_preset(**kwargs):
    defaults = dict(
        name="Rock",
        playlist_sort_types=[PlaylistSortType.RANDOM],
        searches=["genre=Rock"],
    )
    defaults.update(kwargs)
    return Preset(**defaults)


@pytest.mark.unit
class TestPreset:
    def test_construction_with_enum_values(self):
        p = make_preset()
        assert p.name == "Rock"
        assert p.playlist_sort_types == [PlaylistSortType.RANDOM]
        assert p.searches == ["genre=Rock"]

    def test_construction_with_string_sort_type(self):
        p = Preset("Jazz", ["RANDOM"], ["genre=Jazz"])
        assert p.playlist_sort_types == [PlaylistSortType.RANDOM]

    def test_mismatched_lengths_raise(self):
        with pytest.raises(ValueError):
            Preset("Bad", [PlaylistSortType.RANDOM], ["a", "b"])

    def test_is_valid_true(self):
        assert make_preset().is_valid()

    def test_is_valid_false_when_empty(self):
        p = Preset.__new__(Preset)
        p.name = "Empty"
        p.playlist_sort_types = []
        p.searches = []
        assert not p.is_valid()

    def test_equality_same_types_and_searches(self):
        a = make_preset()
        b = make_preset()
        assert a == b

    def test_inequality_different_searches(self):
        assert make_preset(searches=["genre=Rock"]) != make_preset(searches=["genre=Jazz"])

    def test_inequality_non_preset(self):
        assert make_preset() != "not a preset"

    def test_hash_equal_objects_same_hash(self):
        assert hash(make_preset()) == hash(make_preset())

    def test_to_dict_round_trips_via_from_dict(self):
        original = make_preset()
        restored = Preset.from_dict(original.to_dict())
        assert restored == original

    def test_to_dict_structure(self):
        d = make_preset().to_dict()
        assert "name" in d
        assert "playlist_sort_types" in d
        assert "searches" in d
        assert isinstance(d["playlist_sort_types"][0], str)

    def test_str_delegates_to_readable_str(self):
        p = make_preset()
        assert str(p) == p.readable_str()

    def test_readable_str_contains_name_and_search(self):
        p = make_preset(name="Rock", searches=["genre=Rock"])
        s = p.readable_str()
        assert "Rock" in s
        assert "genre=Rock" in s

    def test_readable_str_multiple_entries_comma_separated(self):
        p = Preset("Multi", [PlaylistSortType.RANDOM, PlaylistSortType.RANDOM], ["a", "b"])
        assert ", " in p.readable_str()
