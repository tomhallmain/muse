"""Unit tests for muse/sort_config.py."""

import pytest

from muse.sort_config import SortConfig, DEFAULT_SORT_CONFIG


@pytest.mark.unit
class TestSortConfig:
    def test_default_to_dict_is_empty(self):
        assert SortConfig().to_dict() == {}

    def test_to_dict_only_includes_non_default_fields(self):
        sc = SortConfig(skip_memory_shuffle=True, check_count_override=5)
        d = sc.to_dict()
        assert d == {"skip_memory_shuffle": True, "check_count_override": 5}
        assert "skip_random_start" not in d
        assert "check_entire_playlist" not in d

    def test_from_dict_round_trips_all_fields(self):
        original = SortConfig(
            skip_memory_shuffle=True,
            skip_random_start=True,
            check_count_override=10,
            check_entire_playlist=True,
        )
        assert SortConfig.from_dict(original.to_dict()) == original

    def test_from_dict_empty_gives_defaults(self):
        assert SortConfig.from_dict({}) == SortConfig()

    def test_merge_non_default_override_wins(self):
        base = SortConfig(skip_memory_shuffle=True)
        override = SortConfig(skip_random_start=True)
        merged = base.merge(override)
        assert merged.skip_memory_shuffle is True
        assert merged.skip_random_start is True

    def test_merge_default_override_keeps_base(self):
        base = SortConfig(check_count_override=3)
        merged = base.merge(SortConfig())
        assert merged.check_count_override == 3

    def test_merge_override_check_count_wins(self):
        assert SortConfig(check_count_override=3).merge(SortConfig(check_count_override=7)).check_count_override == 7

    def test_is_default_true_for_fresh_instance(self):
        assert SortConfig().is_default()

    def test_is_default_false_when_field_set(self):
        assert not SortConfig(skip_memory_shuffle=True).is_default()

    def test_equality(self):
        assert SortConfig(skip_memory_shuffle=True) == SortConfig(skip_memory_shuffle=True)
        assert SortConfig(skip_memory_shuffle=True) != SortConfig(skip_random_start=True)

    def test_hash_equal_objects_same_hash(self):
        assert hash(SortConfig(check_count_override=2)) == hash(SortConfig(check_count_override=2))

    def test_repr_default(self):
        assert repr(SortConfig()) == "SortConfig()"

    def test_repr_shows_active_fields(self):
        r = repr(SortConfig(skip_memory_shuffle=True, check_count_override=3))
        assert "skip_mem" in r
        assert "cc=3" in r

    def test_repr_check_entire_playlist(self):
        assert "scour" in repr(SortConfig(check_entire_playlist=True))

    def test_repr_skip_random_start(self):
        assert "skip_rand" in repr(SortConfig(skip_random_start=True))

    def test_default_sort_config_constant_is_default(self):
        assert DEFAULT_SORT_CONFIG == SortConfig()
