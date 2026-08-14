"""Unit tests for ArtistsData save/delete against the DB."""

import pytest

from library_data.artist import Artist, ArtistsData, ArtistsDataSearch


@pytest.mark.unit
class TestArtistsDataPersistence:
    def test_search_finds_seeded_artist(self):
        data = ArtistsData()
        search = ArtistsDataSearch(artist="allman")
        data.do_search(search)
        names = [a.name for a in search.get_results()]
        assert "Allman Brothers Band" in names

    def test_save_and_delete_artist_roundtrip(self):
        data = ArtistsData()
        name = "__muse_test_artist_xyzz__"
        existing = data._artists.get(name)
        if existing:
            data.delete_artist(existing)

        artist = Artist(
            id=None,
            name=name,
            indicators=[name, "xyzzartist"],
            start_date=1900,
            end_date=1950,
            genres=["Jazz"],
            albums=["Test Album"],
            notes={"k": "v"},
        )
        ok, err = data.save_artist(artist)
        assert ok, err
        assert name in data._artists
        assert data._artists[name].notes.get("k") == "v"
        assert data._artists[name].id is not None

        renamed = Artist(id=artist.id, name=name + "_2", indicators=[name + "_2"], notes={})
        ok, err = data.save_artist(renamed, original_name=name)
        assert ok, err
        assert name not in data._artists
        assert name + "_2" in data._artists

        ok, err = data.delete_artist(renamed)
        assert ok, err
        assert name + "_2" not in data._artists

        reloaded = ArtistsData()
        assert name not in reloaded._artists
        assert name + "_2" not in reloaded._artists

    def test_save_rejects_future_start_date(self):
        data = ArtistsData()
        artist = Artist(id=None, name="__muse_test_artist_future__", start_date=9999)
        ok, err = data.save_artist(artist)
        assert not ok
        assert err
        assert "__muse_test_artist_future__" not in data._artists
