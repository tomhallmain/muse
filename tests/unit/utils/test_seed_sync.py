"""Tests for example-file changes reaching an already seeded database (utils.db._sync_seed)."""

import json

import pytest

import utils.db as db

BACH = "Johann Sebastian Bach"


@pytest.fixture
def example_dir(monkeypatch, tmp_path):
    """Point the example-data directory at an empty temp directory."""
    monkeypatch.setattr(db, "_EXAMPLE_DATA_DIR", tmp_path)
    return tmp_path


def _write(example_dir, filename, entries):
    data = {entry["name"]: entry for entry in entries}
    (example_dir / filename).write_text(json.dumps(data), encoding="utf-8")


def _composer(name, **fields):
    entry = {
        "name": name,
        "indicators": [name],
        "start_date": -1,
        "end_date": -1,
        "dates_are_lifespan": False,
        "dates_uncertain": True,
        "genres": [],
        "works": [],
        "notes": {},
    }
    entry.update(fields)
    return entry


def _row(name):
    return db.get_connection().execute(
        "SELECT id, indicators, start_date, end_date, dates_are_lifespan, genres, notes "
        "FROM composers WHERE name = ?",
        (name,),
    ).fetchone()


def _bach_entry(**fields):
    """Bach as the database holds him, with `fields` changed."""
    row = _row(BACH)
    entry = _composer(
        BACH,
        id=row["id"],
        indicators=db.delim_to_list(row["indicators"]),
        start_date=row["start_date"],
        end_date=row["end_date"],
        dates_are_lifespan=bool(row["dates_are_lifespan"]),
        dates_uncertain=False,
        genres=db.delim_to_list(row["genres"]),
        notes=json.loads(row["notes"]),
    )
    entry.update(fields)
    return entry


def _sync():
    db._sync_seed(db.get_connection())


@pytest.mark.unit
class TestComposerSync:
    def test_a_new_composer_is_inserted_with_its_seed_id(self, example_dir):
        _write(example_dir, "composers_example.json", [_composer("Zz New Composer", id=987654)])
        _sync()
        assert _row("Zz New Composer")["id"] == 987654

    def test_a_seed_id_already_taken_gives_the_next_free_one(self, example_dir):
        taken = _row(BACH)["id"]
        _write(example_dir, "composers_example.json", [_composer("Zz New Composer", id=taken)])
        _sync()
        new_id = _row("Zz New Composer")["id"]
        assert new_id != taken
        assert _row(BACH)["id"] == taken

    def test_an_unchanged_file_is_not_applied_again(self, example_dir):
        _write(example_dir, "composers_example.json", [_composer("Zz New Composer", id=987654)])
        _sync()
        conn = db.get_connection()
        conn.execute("DELETE FROM composers WHERE name = ?", ("Zz New Composer",))
        conn.commit()
        _sync()
        assert _row("Zz New Composer") is None

    def test_a_composer_deleted_since_the_last_sync_stays_deleted(self, example_dir):
        _write(example_dir, "composers_example.json", [_composer("Zz New Composer", id=987654)])
        _sync()
        conn = db.get_connection()
        conn.execute("DELETE FROM composers WHERE name = ?", ("Zz New Composer",))
        conn.commit()
        _write(example_dir, "composers_example.json", [
            _composer("Zz New Composer", id=987654, genres=["Baroque"]),
        ])
        _sync()
        assert _row("Zz New Composer") is None

    def test_a_new_indicator_and_genre_are_appended(self, example_dir):
        before = _bach_entry()
        _write(example_dir, "composers_example.json", [
            _bach_entry(indicators=before["indicators"] + ["Zz Bach"], genres=before["genres"] + ["Zz Genre"]),
        ])
        _sync()
        row = _row(BACH)
        assert db.delim_to_list(row["indicators"]) == before["indicators"] + ["Zz Bach"]
        assert "Zz Genre" in db.delim_to_list(row["genres"])

    def test_an_indicator_removed_here_is_not_added_again(self, example_dir):
        before = _bach_entry()
        _write(example_dir, "composers_example.json", [_bach_entry(indicators=before["indicators"] + ["Zz Bach"])])
        _sync()
        conn = db.get_connection()
        conn.execute(
            "UPDATE composers SET indicators = ? WHERE name = ?",
            (db.list_to_delim(before["indicators"]), BACH),
        )
        conn.commit()
        _write(example_dir, "composers_example.json", [
            _bach_entry(indicators=before["indicators"] + ["Zz Bach"], genres=["Zz Genre"]),
        ])
        _sync()
        assert "Zz Bach" not in db.delim_to_list(_row(BACH)["indicators"])

    def test_a_new_note_key_is_added_and_a_stored_one_kept(self, example_dir):
        conn = db.get_connection()
        conn.execute("UPDATE composers SET notes = ? WHERE name = ?", (json.dumps({"notiz": "mine"}), BACH))
        conn.commit()
        _write(example_dir, "composers_example.json", [
            _bach_entry(notes={"notiz": "seed", "quelle": "seed source"}),
        ])
        _sync()
        assert json.loads(_row(BACH)["notes"]) == {"notiz": "mine", "quelle": "seed source"}

    def test_dates_are_filled_only_where_none_are_stored(self, example_dir):
        conn = db.get_connection()
        conn.execute(
            "UPDATE composers SET start_date = -1, end_date = -1, dates_are_lifespan = 0 WHERE name = ?",
            (BACH,),
        )
        conn.commit()
        _write(example_dir, "composers_example.json", [
            _bach_entry(start_date=1685, end_date=1750, dates_are_lifespan=True),
            _composer("Zz Dated", id=987654, start_date=1900, end_date=1950),
        ])
        _sync()
        row = _row(BACH)
        assert (row["start_date"], row["end_date"], row["dates_are_lifespan"]) == (1685, 1750, 1)

        conn.execute("UPDATE composers SET start_date = 1111, end_date = 1222 WHERE name = ?", ("Zz Dated",))
        conn.commit()
        _write(example_dir, "composers_example.json", [
            _composer("Zz Dated", id=987654, start_date=1901, end_date=1951),
        ])
        _sync()
        row = _row("Zz Dated")
        assert (row["start_date"], row["end_date"]) == (1111, 1222)

    def test_a_freshly_seeded_database_is_only_recorded(self, example_dir):
        _write(example_dir, "composers_example.json", [_composer("Zz New Composer", id=987654)])
        conn = db.get_connection()
        db._sync_seed(conn, merge=False)
        assert _row("Zz New Composer") is None
        assert conn.execute(
            "SELECT COUNT(*) FROM seed_snapshot WHERE kind = 'composers' AND name = ?", ("Zz New Composer",)
        ).fetchone()[0] == 1


@pytest.mark.unit
class TestGenreSync:
    def _genre(self, name, transliterations):
        return {"name": name, "transliterations": transliterations, "notes": {}}

    def _transliterations(self, name):
        row = db.get_connection().execute(
            "SELECT transliterations FROM genres WHERE name = ?", (name,)
        ).fetchone()
        return None if row is None else db.delim_to_list(row["transliterations"])

    def test_a_new_genre_is_inserted(self, example_dir):
        _write(example_dir, "genres_example.json", [self._genre("Zz Genre", ["Zz Genre", "zz genre"])])
        _sync()
        assert self._transliterations("Zz Genre") == ["Zz Genre", "zz genre"]

    def test_a_new_transliteration_is_appended(self, example_dir):
        before = self._transliterations("Baroque")
        _write(example_dir, "genres_example.json", [self._genre("Baroque", before + ["Zz Barock"])])
        _sync()
        assert self._transliterations("Baroque") == before + ["Zz Barock"]
