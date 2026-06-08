"""
Tests for extensions/extension_filer.py.

Filesystem operations use tmp_path.  Config is patched via monkeypatch on the
module-level reference so the real config singleton is never touched.
"""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import extensions.extension_filer as filer
from extensions.extension_filer import (
    _discover_genre_dirs,
    _genre_from_filesystem,
    _infer_genre_dir,
    _match_genre,
    file_extension,
)
from utils.globals import TrackAttribute


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_config(base_dir="", genres=None):
    return SimpleNamespace(
        directories=[base_dir] if base_dir else [],
        auto_file_extensions_genres=genres or [],
    )


def _artist_entity(name, genres=None):
    return SimpleNamespace(name=name, genres=genres or [], indicators=[name])


# ---------------------------------------------------------------------------
# _discover_genre_dirs
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDiscoverGenreDirs:
    def test_configured_genres_used_regardless_of_filesystem(self, tmp_path, monkeypatch):
        monkeypatch.setattr(filer, "config", _mock_config(str(tmp_path), ["Classical", "Jazz"]))
        result = _discover_genre_dirs(str(tmp_path))
        assert set(result.keys()) == {"classical", "jazz"}
        assert result["classical"] == os.path.join(str(tmp_path), "Classical")

    def test_configured_genre_path_created_on_demand(self, tmp_path, monkeypatch):
        # Directory need not exist yet — path is just computed
        monkeypatch.setattr(filer, "config", _mock_config(str(tmp_path), ["NewGenre"]))
        result = _discover_genre_dirs(str(tmp_path))
        assert "newgenre" in result

    def test_auto_detect_includes_title_case_dirs(self, tmp_path, monkeypatch):
        (tmp_path / "Classical").mkdir()
        (tmp_path / "Jazz").mkdir()
        monkeypatch.setattr(filer, "config", _mock_config(str(tmp_path)))
        result = _discover_genre_dirs(str(tmp_path))
        assert "classical" in result
        assert "jazz" in result

    def test_auto_detect_excludes_underscore_prefixed(self, tmp_path, monkeypatch):
        (tmp_path / "_unsorted").mkdir()
        (tmp_path / "Classical").mkdir()
        monkeypatch.setattr(filer, "config", _mock_config(str(tmp_path)))
        result = _discover_genre_dirs(str(tmp_path))
        assert "_unsorted" not in result
        assert "classical" in result

    def test_auto_detect_excludes_lowercase_dirs(self, tmp_path, monkeypatch):
        (tmp_path / "slop").mkdir()
        (tmp_path / "Classical").mkdir()
        monkeypatch.setattr(filer, "config", _mock_config(str(tmp_path)))
        result = _discover_genre_dirs(str(tmp_path))
        assert "slop" not in result

    def test_empty_base_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(filer, "config", _mock_config(str(tmp_path)))
        result = _discover_genre_dirs(str(tmp_path))
        assert result == {}


# ---------------------------------------------------------------------------
# _match_genre
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMatchGenre:
    def setup_method(self):
        self.dirs = {"classical": "/music/Classical", "jazz": "/music/Jazz", "metal and punk": "/music/Metal and Punk"}

    def test_exact_match(self):
        assert _match_genre("classical", self.dirs) == "/music/Classical"

    def test_case_insensitive_match(self):
        assert _match_genre("Classical", self.dirs) == "/music/Classical"

    def test_substring_candidate_in_name(self):
        # "metal" is contained in the key "metal and punk"
        assert _match_genre("metal", self.dirs) == "/music/Metal and Punk"

    def test_substring_name_in_candidate(self):
        # key "jazz" is contained in candidate "jazz fusion"
        assert _match_genre("jazz fusion", self.dirs) == "/music/Jazz"

    def test_no_match_returns_none(self):
        assert _match_genre("country", self.dirs) is None

    def test_empty_candidate_returns_none(self):
        assert _match_genre("", self.dirs) is None

    def test_empty_genre_dirs_returns_none(self):
        assert _match_genre("classical", {}) is None


# ---------------------------------------------------------------------------
# _genre_from_filesystem
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGenreFromFilesystem:
    def test_finds_existing_artist_subdir(self, tmp_path):
        classical = tmp_path / "Classical"
        (classical / "Bach").mkdir(parents=True)
        genre_dirs = {"classical": str(classical)}
        assert _genre_from_filesystem("Bach", genre_dirs) == str(classical)

    def test_case_insensitive_subdir_match(self, tmp_path):
        classical = tmp_path / "Classical"
        (classical / "bach").mkdir(parents=True)
        genre_dirs = {"classical": str(classical)}
        assert _genre_from_filesystem("Bach", genre_dirs) == str(classical)

    def test_no_match_returns_none(self, tmp_path):
        classical = tmp_path / "Classical"
        classical.mkdir()
        genre_dirs = {"classical": str(classical)}
        assert _genre_from_filesystem("Vivaldi", genre_dirs) is None

    def test_empty_entity_name_returns_none(self, tmp_path):
        genre_dirs = {"classical": str(tmp_path)}
        assert _genre_from_filesystem("", genre_dirs) is None


# ---------------------------------------------------------------------------
# _infer_genre_dir
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestInferGenreDir:
    def setup_method(self):
        self.genre_dirs = {
            "classical": "/music/Classical",
            "jazz": "/music/Jazz",
        }

    def test_genre_attr_matches_directly(self):
        result = _infer_genre_dir(TrackAttribute.GENRE, "Classical", "Classical", "", self.genre_dirs)
        assert result == "/music/Classical"

    def test_artist_entity_genres_used(self):
        entity = _artist_entity("Miles Davis", genres=["Jazz"])
        result = _infer_genre_dir(TrackAttribute.ARTIST, "Miles Davis", entity, "", self.genre_dirs)
        assert result == "/music/Jazz"

    def test_composer_falls_back_to_classical(self):
        # Composer with no genre info and no filesystem match → Classical
        entity = _artist_entity("Vivaldi", genres=[])
        result = _infer_genre_dir(TrackAttribute.COMPOSER, "Vivaldi", entity, "", self.genre_dirs)
        assert result == "/music/Classical"

    def test_filesystem_lookup_used_when_entity_genres_empty(self, tmp_path):
        classical = tmp_path / "Classical"
        (classical / "Bach").mkdir(parents=True)
        dirs = {"classical": str(classical)}
        entity = _artist_entity("Bach", genres=[])
        result = _infer_genre_dir(TrackAttribute.ARTIST, "Bach", entity, "", dirs)
        assert result == str(classical)

    def test_llm_fallback_called_when_nothing_resolves(self):
        llm = MagicMock()
        llm.is_failing.return_value = False
        llm.generate_json_get_value.return_value = SimpleNamespace(response="jazz")
        entity = _artist_entity("Unknown Band", genres=[])
        result = _infer_genre_dir(TrackAttribute.ARTIST, "Unknown Band", entity, "Some Track", self.genre_dirs, llm=llm)
        assert result == "/music/Jazz"
        llm.generate_json_get_value.assert_called_once()

    def test_llm_not_called_when_failing(self):
        llm = MagicMock()
        llm.is_failing.return_value = True
        entity = _artist_entity("Unknown Band", genres=[])
        _infer_genre_dir(TrackAttribute.ARTIST, "Unknown Band", entity, "", self.genre_dirs, llm=llm)
        llm.generate_json_get_value.assert_not_called()

    def test_no_genre_dirs_returns_none_without_llm(self):
        result = _infer_genre_dir(TrackAttribute.ARTIST, "Bach", "Bach", "", {})
        assert result is None


# ---------------------------------------------------------------------------
# file_extension (integration)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFileExtension:
    def test_artist_filed_into_genre_artist_unknown_album(self, tmp_path, monkeypatch):
        (tmp_path / "Classical").mkdir()
        monkeypatch.setattr(filer, "config", _mock_config(str(tmp_path)))
        src = tmp_path / "track.mp3"
        src.write_bytes(b"audio")
        entity = _artist_entity("Bach", genres=["Classical"])
        result = file_extension(str(src), TrackAttribute.ARTIST, "Bach", entity, "Bach Cello Suite")
        assert result is not None
        assert os.path.exists(result)
        parts = result.replace("\\", "/").split("/")
        assert "Classical" in parts
        assert "Bach" in parts
        assert "Unknown Album" in parts

    def test_composer_classical_fallback_creates_dirs(self, tmp_path, monkeypatch):
        (tmp_path / "Classical").mkdir()
        monkeypatch.setattr(filer, "config", _mock_config(str(tmp_path)))
        src = tmp_path / "symphony.mp3"
        src.write_bytes(b"audio")
        entity = _artist_entity("Vivaldi", genres=[])
        result = file_extension(str(src), TrackAttribute.COMPOSER, "Vivaldi", entity, "Four Seasons")
        assert result is not None
        assert "Classical" in result
        assert "Vivaldi" in result

    def test_album_filed_under_unknown_artist(self, tmp_path, monkeypatch):
        (tmp_path / "Jazz").mkdir()
        monkeypatch.setattr(filer, "config", _mock_config(str(tmp_path)))
        src = tmp_path / "track.mp3"
        src.write_bytes(b"audio")
        result = file_extension(str(src), TrackAttribute.ALBUM, "Kind of Blue", "Kind of Blue", "So What")
        assert result is not None
        assert "Unknown Artist" in result
        assert "Kind of Blue" in result

    def test_no_genre_resolved_files_under_base(self, tmp_path, monkeypatch):
        # No genre dirs at all → lands in base/Unknown Artist/Unknown Album/
        monkeypatch.setattr(filer, "config", _mock_config(str(tmp_path)))
        src = tmp_path / "mystery.mp3"
        src.write_bytes(b"audio")
        result = file_extension(str(src), TrackAttribute.TITLE, "Mystery Track", "Mystery Track", "Mystery Track")
        assert result is not None
        assert "Unknown Artist" in result
        assert "Unknown Album" in result

    def test_target_dirs_created_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(filer, "config", _mock_config(str(tmp_path), ["Classical"]))
        src = tmp_path / "track.mp3"
        src.write_bytes(b"audio")
        entity = _artist_entity("Bach", genres=["Classical"])
        result = file_extension(str(src), TrackAttribute.ARTIST, "Bach", entity, "BWV 1")
        # Directory must have been created even though it didn't exist
        assert result is not None
        assert os.path.exists(result)

    def test_returns_none_when_no_directories_configured(self, tmp_path, monkeypatch):
        monkeypatch.setattr(filer, "config", _mock_config(""))
        src = tmp_path / "track.mp3"
        src.write_bytes(b"audio")
        result = file_extension(str(src), TrackAttribute.ARTIST, "Bach", "Bach", "BWV 1")
        assert result is None

    def test_source_file_no_longer_at_original_path(self, tmp_path, monkeypatch):
        (tmp_path / "Classical").mkdir()
        monkeypatch.setattr(filer, "config", _mock_config(str(tmp_path)))
        src = tmp_path / "track.mp3"
        src.write_bytes(b"audio")
        entity = _artist_entity("Bach", genres=["Classical"])
        file_extension(str(src), TrackAttribute.ARTIST, "Bach", entity, "BWV 1")
        assert not src.exists()
