import pytest

from extensions import library_extender
from extensions.library_extender import (
    EogfiaqREkb, q4, q19, q20, q21, q23, q27, q29,
)


def _option(**extra):
    return EogfiaqREkb({
        q20: {q27: "kind_resolved", q23: "t_first", q29: "PL_first"},
        q4: {q19: "A Name", q21: "A Detail", **extra},
    })


@pytest.mark.unit
class TestH:
    def test_read_when_its_key_is_known(self, monkeypatch):
        monkeypatch.setattr(library_extender, "q44", "k_h", raising=False)
        assert _option(k_h="A Source").h == "A Source"

    def test_empty_when_its_key_is_unknown(self, monkeypatch):
        monkeypatch.delattr(library_extender, "q44", raising=False)
        assert _option(k_h="A Source").h == ""

    def test_empty_when_absent_from_the_result(self, monkeypatch):
        monkeypatch.setattr(library_extender, "q44", "k_h", raising=False)
        assert _option().h == ""


@pytest.mark.unit
class TestXfgk:
    def test_an_unset_value_reads_as_absent(self):
        """Unset stays -1 internally; callers that render it need None instead."""
        assert _option().xfgk() is None

    def test_a_set_value_is_returned(self):
        option = _option()
        option.ogxz4({}, 272.0)
        assert option.xfgk() == 272.0

    def test_the_comparison_accessors_still_answer_for_a_set_value(self):
        option = _option()
        option.ogxz4({}, 272.0)
        assert option.xfgi(300) is True
        assert option.xfgj(200) is True
        assert option.xfgi(200) is False
        assert option.xfgj(300) is False

    def test_an_unset_value_is_under_every_floor_and_over_no_ceiling(self):
        option = _option()
        assert option.xfgi(120) is True
        assert option.xfgj(10800) is False
