"""Unit tests for GenresData save/delete against the DB."""

import pytest

from library_data.genre import Genre, GenresData, GenresDataSearch


@pytest.mark.unit
class TestGenresDataPersistence:
    def test_search_finds_seeded_genre(self):
        data = GenresData()
        search = GenresDataSearch(genre="baroque")
        data.do_search(search)
        names = [g.name for g in search.get_results()]
        assert "Baroque" in names

    def test_save_and_delete_genre_roundtrip(self):
        data = GenresData()
        name = "__muse_test_genre_xyzz__"
        existing = data._genres.get(name)
        if existing:
            data.delete_genre(existing)

        genre = Genre(name=name, transliterations=[name, "xyzzgenre"], notes={"k": "v"})
        ok, err = data.save_genre(genre)
        assert ok, err
        assert name in data._genres
        assert data._genres[name].notes.get("k") == "v"

        renamed = Genre(name=name + "_2", transliterations=[name + "_2"], notes={})
        ok, err = data.save_genre(renamed, original_name=name)
        assert ok, err
        assert name not in data._genres
        assert name + "_2" in data._genres

        ok, err = data.delete_genre(renamed)
        assert ok, err
        assert name + "_2" not in data._genres

        reloaded = GenresData()
        assert name not in reloaded._genres
        assert name + "_2" not in reloaded._genres
