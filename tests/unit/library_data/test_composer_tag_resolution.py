"""Tests for ComposersData.resolve_composer_tag, on composers added to the isolated test database."""

import pytest

from library_data.composer import Composer, ComposersData

BACH = "Zz Johann Testbach"
BEETHOVEN = "Zz Ludwig van Testhoven"
RAMEAU = "Zz Jean-Phillippe Testrameau"
BIBER = "Zz Heinrich Ignaz Testbiber"


@pytest.fixture
def data():
    data = ComposersData()
    for name, indicators in ((BACH, [BACH, "Testbach"]),
                             (BEETHOVEN, [BEETHOVEN]),
                             (RAMEAU, [RAMEAU, "Zz Jean-Philippe Testrameau"]),
                             (BIBER, [BIBER, "von Testbiber"]),
                             ("Zz Charles Ives", ["Zz Charles Ives", "Ives"]),
                             ("Zz Simon Simon", ["Zz Simon Simon", "Zz Simon"])):
        success, error = data.save_composer(Composer(None, name, indicators=indicators))
        assert success, error
    return data


@pytest.mark.unit
class TestResolveComposerTag:
    @pytest.mark.parametrize("tag, names, how", [
        (BACH, [BACH], ComposersData.TAG_DIRECT),
        ("zz johann testbach", [BACH], ComposersData.TAG_DIRECT),
        ("Testbach", [BACH], ComposersData.TAG_DIRECT),
        ("Testbach, Zz Johann", [BACH], ComposersData.TAG_INVERTED),
        ("Testhoven, Zz Ludwig van", [BEETHOVEN], ComposersData.TAG_INVERTED),
        ("van Testhoven, Zz Ludwig", [BEETHOVEN], ComposersData.TAG_INVERTED),
        # The tag spells the name like an indicator, not like the composer's name.
        ("Testrameau, Zz Jean-Philippe", [RAMEAU], ComposersData.TAG_INVERTED),
        ("Testbiber, Sir Zz Heinrich Ignaz von", [BIBER], ComposersData.TAG_INVERTED),
        (f"{BACH}, {BEETHOVEN}", [BACH, BEETHOVEN], ComposersData.TAG_LIST),
        ("Testbach, Zz Johann; Testhoven, Zz Ludwig van", [BACH, BEETHOVEN], ComposersData.TAG_LIST),
        ("Testbach, Zz Johann (1685-1750)", [BACH], ComposersData.TAG_INVERTED),
        ("Zz Johann Testbach (arr. Gray)", [BACH], ComposersData.TAG_DIRECT),
        ("Anonymous", [], ComposersData.TAG_PLACEHOLDER),
        ("Anon. (12-16c., Hungary)", [], ComposersData.TAG_PLACEHOLDER),
        ("trad. Norwegian (Ottadal)", [], ComposersData.TAG_PLACEHOLDER),
        ("Nobody, Zz Known", [], ComposersData.TAG_UNMATCHED),
        ("", [], ComposersData.TAG_UNMATCHED),
    ])
    def test_resolution(self, data, tag, names, how):
        assert data.resolve_composer_tag(tag) == (names, how)

    def test_a_comma_list_needs_every_part_to_be_a_composer(self, data):
        assert data.resolve_composer_tag(f"{BACH}, Zz Nobody") == ([], ComposersData.TAG_UNMATCHED)

    def test_a_comma_list_needs_full_names_not_surname_indicators(self, data):
        # "Ives, Simon" is one composer, not the two whose indicators are "Ives" and "Simon".
        assert data.resolve_composer_tag("Ives, Zz Simon") == ([], ComposersData.TAG_UNMATCHED)

    @pytest.mark.parametrize("value, forms", [
        ("Rameau, Jean-Philippe", ["Jean-Philippe Rameau"]),
        ("Walton, Sir William", ["William Walton"]),
        ("Beethoven, Ludwig van", ["Ludwig van Beethoven", "Ludwig Beethoven"]),
        ("Easley Blackwood, Jr., Sr.", []),
        ("Vivaldi", []),
    ])
    def test_natural_order_forms(self, value, forms):
        assert ComposersData.natural_order_forms(value) == forms

    def test_a_composer_saved_later_is_found(self, data):
        assert data.resolve_composer_tag("Testmann, Zz Anna")[1] == ComposersData.TAG_UNMATCHED
        success, error = data.save_composer(Composer(None, "Zz Anna Testmann"))
        assert success, error
        assert data.resolve_composer_tag("Testmann, Zz Anna") == (["Zz Anna Testmann"],
                                                                 ComposersData.TAG_INVERTED)
