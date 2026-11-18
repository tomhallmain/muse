"""Tests for exporting and importing the blacklist (CSV, JSON, TXT), on files under tmp_path."""

import json

import pytest

from library_data.blacklist import Blacklist, BlacklistItem
from utils.globals import BlacklistItemType


@pytest.fixture(autouse=True)
def _own_blacklist(monkeypatch):
    monkeypatch.setattr(Blacklist, "TAG_BLACKLIST", [])


def _detailed_items():
    return [
        BlacklistItem("zz plain"),
        BlacklistItem("zz disabled", enabled=False),
        BlacklistItem("zz(a|b)", use_regex=True, use_word_boundary=False,
                      use_space_as_optional_nonword=False, exception_pattern="zz allowed",
                      item_type=BlacklistItemType.CHANNEL),
    ]


def _state():
    return sorted((item.to_dict() for item in Blacklist.get_items()), key=lambda d: d["string"])


@pytest.mark.unit
class TestBlacklistRoundTrip:
    @pytest.mark.parametrize("extension, export, import_", [
        (".csv", Blacklist.export_blacklist_csv, Blacklist.import_blacklist_csv),
        (".json", Blacklist.export_blacklist_json, Blacklist.import_blacklist_json),
    ])
    def test_every_field_survives_export_and_import(self, tmp_path, extension, export, import_):
        Blacklist.set_blacklist(_detailed_items())
        exported = _state()
        path = tmp_path / f"blacklist{extension}"
        export(str(path))
        Blacklist.clear()
        import_(str(path))
        assert _state() == exported

    @pytest.mark.parametrize("extension, export, import_", [
        (".csv", Blacklist.export_blacklist_csv, Blacklist.import_blacklist_csv),
        (".json", Blacklist.export_blacklist_json, Blacklist.import_blacklist_json),
        (".txt", Blacklist.export_blacklist_txt, Blacklist.import_blacklist_txt),
    ])
    def test_reimporting_an_export_does_not_double_the_list(self, tmp_path, extension, export, import_):
        Blacklist.set_blacklist([BlacklistItem("zz one"), BlacklistItem("zz two")])
        path = tmp_path / f"blacklist{extension}"
        export(str(path))
        import_(str(path))
        assert [item.string for item in Blacklist.get_items()] == ["zz one", "zz two"]


@pytest.mark.unit
class TestBlacklistImport:
    def test_an_imported_item_replaces_the_one_with_the_same_string(self, tmp_path):
        Blacklist.set_blacklist([BlacklistItem("zz word")])
        path = tmp_path / "blacklist.json"
        path.write_text(json.dumps([{"string": "zz word", "enabled": False}]), encoding="utf-8")
        Blacklist.import_blacklist_json(str(path))
        assert [(item.string, item.enabled) for item in Blacklist.get_items()] == [("zz word", False)]

    def test_a_two_column_csv_still_imports(self, tmp_path):
        path = tmp_path / "blacklist.csv"
        path.write_text("string,enabled\nzz on,true\nzz off,false\n", encoding="utf-8")
        Blacklist.import_blacklist_csv(str(path))
        assert [(item.string, item.enabled, item.use_regex) for item in Blacklist.get_items()] == [
            ("zz off", False, False), ("zz on", True, False)]

    def test_a_single_column_csv_still_imports(self, tmp_path):
        path = tmp_path / "blacklist.csv"
        path.write_text("zz one\nzz two\n", encoding="utf-8")
        Blacklist.import_blacklist_csv(str(path))
        assert [item.string for item in Blacklist.get_items()] == ["zz one", "zz two"]

    def test_the_csv_export_has_a_column_per_field(self, tmp_path):
        Blacklist.set_blacklist([BlacklistItem("zz plain")])
        path = tmp_path / "blacklist.csv"
        Blacklist.export_blacklist_csv(str(path))
        header = path.read_text(encoding="utf-8").splitlines()[0]
        assert header.split(",") == list(BlacklistItem.CSV_FIELDNAMES)
        assert set(BlacklistItem.CSV_FIELDNAMES) == set(BlacklistItem("zz").to_dict())
