"""Unit tests for InstrumentsData save/delete against the DB, and for the
transliterations/notes column migration in utils/db.py.
"""

import sqlite3

import pytest

from library_data.instrument import Instrument, InstrumentsData, InstrumentsDataSearch


@pytest.mark.unit
class TestInstrumentsDataPersistence:
    def test_search_finds_seeded_instrument(self):
        data = InstrumentsData()
        search = InstrumentsDataSearch(instrument="accordion")
        data.do_search(search)
        names = [i.name for i in search.get_results()]
        assert "accordion" in names

    def test_save_and_delete_instrument_roundtrip(self):
        data = InstrumentsData()
        name = "__muse_test_instrument_xyzz__"
        existing = data._instruments.get(name)
        if existing:
            data.delete_instrument(existing)

        instrument = Instrument(name=name, transliterations=[name, "xyzzinstrument"], notes={"k": "v"})
        ok, err = data.save_instrument(instrument)
        assert ok, err
        assert name in data._instruments
        assert data._instruments[name].notes.get("k") == "v"

        renamed = Instrument(name=name + "_2", transliterations=[name + "_2"], notes={})
        ok, err = data.save_instrument(renamed, original_name=name)
        assert ok, err
        assert name not in data._instruments
        assert name + "_2" in data._instruments

        ok, err = data.delete_instrument(renamed)
        assert ok, err
        assert name + "_2" not in data._instruments

        reloaded = InstrumentsData()
        assert name not in reloaded._instruments
        assert name + "_2" not in reloaded._instruments


@pytest.mark.unit
class TestInstrumentsColumnMigration:
    def test_migrate_adds_missing_columns_to_old_table(self):
        from utils.db import _migrate_instruments_columns

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        # Simulate a pre-migration installation: instruments table with only `name`.
        conn.execute("CREATE TABLE instruments (name TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO instruments (name) VALUES ('Oud')")
        conn.commit()

        _migrate_instruments_columns(conn)

        columns = {row[1]: row for row in conn.execute("PRAGMA table_info(instruments)").fetchall()}
        assert "transliterations" in columns
        assert "notes" in columns

        row = conn.execute("SELECT name, transliterations, notes FROM instruments WHERE name = 'Oud'").fetchone()
        assert row["transliterations"] == ""
        assert row["notes"] == "{}"
        conn.close()

    def test_migrate_is_a_no_op_on_already_migrated_table(self):
        from utils.db import _migrate_instruments_columns

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE instruments ("
            "name TEXT PRIMARY KEY, "
            "transliterations TEXT NOT NULL DEFAULT '', "
            "notes TEXT NOT NULL DEFAULT '{}')"
        )
        conn.commit()

        # Must not raise (e.g. "duplicate column name") when columns already exist.
        _migrate_instruments_columns(conn)
        _migrate_instruments_columns(conn)

        columns = [row[1] for row in conn.execute("PRAGMA table_info(instruments)").fetchall()]
        assert columns.count("transliterations") == 1
        assert columns.count("notes") == 1
        conn.close()
