"""Tests for run-once reference-data corrections (library_data/data_fixes.py)."""

import json

import pytest

import utils.db as db
from library_data import data_fixes
from library_data.composer import ComposersData

COMPOSER = "Johann Sebastian Bach"


def _fix(fix_id="fix-1", table="composers", op="add_indicator", name=COMPOSER, value="Zz Fix Value"):
    return {"id": fix_id, "table": table, "op": op, "name": name, "value": value}


@pytest.fixture
def fixes(monkeypatch):
    """Replace the shipped fix list with the given entries."""
    def install(*entries):
        monkeypatch.setattr(data_fixes, "_fixes", list(entries))
    return install


def _recorded():
    rows = db.get_connection().execute("SELECT id, outcome, detail FROM data_fixes_applied").fetchall()
    return {row["id"]: row["outcome"] for row in rows}


def _stored_indicators(name):
    row = db.get_connection().execute("SELECT indicators FROM composers WHERE name = ?", (name,)).fetchone()
    return db.delim_to_list(row["indicators"])


@pytest.mark.unit
class TestComposerFixes:
    def test_a_pending_fix_is_applied_on_load(self, fixes):
        fixes(_fix())
        data = ComposersData()
        assert "Zz Fix Value" in data.get_data(COMPOSER).indicators
        assert "Zz Fix Value" in _stored_indicators(COMPOSER)
        assert _recorded() == {"fix-1": data_fixes.APPLIED}

    def test_an_indicator_already_present_is_recorded_as_such(self, fixes):
        fixes()
        existing = ComposersData().get_data(COMPOSER).indicators[0]
        fixes(_fix(value=existing))
        ComposersData().get_composer_names()
        assert _recorded() == {"fix-1": data_fixes.ALREADY_PRESENT}

    def test_a_missing_composer_is_recorded_as_such(self, fixes):
        fixes(_fix(name="No Such Composer"))
        ComposersData().get_composer_names()
        assert _recorded() == {"fix-1": data_fixes.TARGET_MISSING}

    def test_a_recorded_fix_is_not_reapplied(self, fixes):
        """An indicator removed by hand after the fix ran stays removed."""
        fixes(_fix())
        data = ComposersData()
        composer = data.get_data(COMPOSER)
        composer.indicators.remove("Zz Fix Value")
        data.save_composer(composer)
        assert "Zz Fix Value" not in ComposersData().get_data(COMPOSER).indicators

    def test_an_unsupported_op_is_left_unrecorded_and_loading_continues(self, fixes):
        fixes(_fix(op="no_such_op"))
        data = ComposersData()
        assert COMPOSER in data.get_composer_names()
        assert _recorded() == {}

    def test_a_fix_for_another_table_is_left_alone(self, fixes):
        fixes(_fix(table="artists"))
        ComposersData().get_composer_names()
        assert _recorded() == {}


def _merge(source, target, fix_id="merge-1", **extra):
    fix = {"id": fix_id, "table": "composers", "op": "merge_into", "name": source, "value": target}
    fix.update(extra)
    return fix


def _add(data, name, **fields):
    from library_data.composer import Composer

    composer = Composer(None, name, **fields)
    success, error = data.save_composer(composer)
    assert success, error
    return composer


@pytest.mark.unit
class TestMergeFixes:
    def test_the_source_is_folded_into_the_target(self, fixes):
        fixes()
        data = ComposersData()
        _add(data, "Zz Source", indicators=["Zz Source", "Zz Alias"], genres=["Baroque"],
             notes={"notiz": "source note", "quelle": "source"}, start_date=1700, end_date=1750)
        _add(data, "Zz Target", notes={"notiz": "target note"})
        fixes(_merge("Zz Source", "Zz Target"))
        data = ComposersData()
        assert "Zz Source" not in data.get_composer_names()
        target = data.get_data("Zz Target")
        assert target.indicators == ["Zz Target", "Zz Source", "Zz Alias"]
        assert target.genres == ["Baroque"]
        assert target.notes == {"notiz": "target note", "quelle": "source"}
        assert (target.start_date, target.end_date) == (1700, 1750)
        assert _recorded() == {"merge-1": data_fixes.APPLIED}

    def test_works_move_to_the_target(self, fixes):
        fixes()
        data = ComposersData()
        source = _add(data, "Zz Source")
        target = _add(data, "Zz Target")
        conn = db.get_connection()
        conn.execute("INSERT INTO works (composer_id, name) VALUES (?, ?)", (source.id, "Zz Work"))
        conn.commit()
        fixes(_merge("Zz Source", "Zz Target"))
        ComposersData().get_composer_names()
        rows = conn.execute("SELECT composer_id FROM works WHERE name = ?", ("Zz Work",)).fetchall()
        assert [row["composer_id"] for row in rows] == [target.id]

    def test_without_a_target_the_source_is_renamed(self, fixes):
        fixes()
        data = ComposersData()
        source = _add(data, "Zz Source", indicators=["Zz Source", "Zz Alias"])
        fixes(_merge("Zz Source", "Zz Target"))
        data = ComposersData()
        renamed = data.get_data("Zz Target")
        assert "Zz Source" not in data.get_composer_names()
        assert renamed.id == source.id
        assert renamed.indicators == ["Zz Target", "Zz Source", "Zz Alias"]

    def test_drop_name_leaves_the_source_name_out(self, fixes):
        fixes()
        data = ComposersData()
        _add(data, "Zz Source", indicators=["Zz Source", "Zz Alias"])
        fixes(_merge("Zz Source", "Zz Target", drop_name=True))
        assert ComposersData().get_data("Zz Target").indicators == ["Zz Target", "Zz Alias"]

    def test_a_missing_source_is_recorded_as_such(self, fixes):
        fixes(_merge("No Such Composer", COMPOSER))
        ComposersData().get_composer_names()
        assert _recorded() == {"merge-1": data_fixes.TARGET_MISSING}


@pytest.mark.unit
class TestLoadFixes:
    def test_a_missing_file_means_no_fixes(self, monkeypatch, tmp_path):
        monkeypatch.setattr(data_fixes, "_fixes", None)
        monkeypatch.setattr(data_fixes, "FIXES_PATH", str(tmp_path / "absent.json"))
        assert data_fixes.load_fixes() == []

    def test_entries_without_an_id_are_dropped(self, monkeypatch, tmp_path):
        path = tmp_path / "fixes.json"
        path.write_text(json.dumps([_fix(), {"table": "composers"}, "not an entry"]), encoding="utf-8")
        monkeypatch.setattr(data_fixes, "_fixes", None)
        monkeypatch.setattr(data_fixes, "FIXES_PATH", str(path))
        assert [fix["id"] for fix in data_fixes.load_fixes()] == ["fix-1"]

    def test_the_shipped_file_is_well_formed(self):
        with open(data_fixes.FIXES_PATH, "r", encoding="utf-8") as f:
            shipped = json.load(f)
        ids = [fix["id"] for fix in shipped]
        assert len(ids) == len(set(ids))
        for fix in shipped:
            assert {"id", "date", "reason", "table", "op"} <= fix.keys()
