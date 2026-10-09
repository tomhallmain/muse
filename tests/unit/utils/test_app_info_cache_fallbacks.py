"""Tests for AppInfoCache's plaintext fallbacks: the JSON written when an
encrypted save fails, and starting without an encrypted cache that needs OQS
this process lacks. Encryption is replaced by plain file writes."""

import importlib
import json
import os

import pytest

from utils.encryptor import OQSUnavailableError

# importlib: utils/__init__.py binds the singleton instance under this name.
cache_module = importlib.import_module("utils.app_info_cache")


@pytest.fixture
def cache_files(monkeypatch, tmp_path):
    """A cache dir in tmp_path with working fake encryption; returns its paths."""
    monkeypatch.setattr(cache_module, "cache_dir", lambda: str(tmp_path))

    def encrypt(data, service_name, app_identifier, path):
        with open(path, "wb") as f:
            f.write(data)

    def decrypt(path, service_name, app_identifier):
        with open(path, "rb") as f:
            return f.read()

    monkeypatch.setattr(cache_module, "encrypt_data_to_file", encrypt)
    monkeypatch.setattr(cache_module, "decrypt_data_from_file", decrypt)
    monkeypatch.setattr(cache_module, "stored_keys_need_unavailable_oqs", lambda *args: False)

    class Paths:
        enc = tmp_path / "app_info_cache.enc"
        json = tmp_path / "app_info_cache.json"
        no_oqs_json = tmp_path / "app_info_cache.no_oqs.json"

    return Paths


@pytest.fixture
def without_oqs(monkeypatch, cache_files):
    """The stored keys are quantum keys and OQS is unavailable."""
    def refuse(*args, **kwargs):
        raise OQSUnavailableError("Quantum keys found but OQS unavailable")

    monkeypatch.setattr(cache_module, "encrypt_data_to_file", refuse)
    monkeypatch.setattr(cache_module, "decrypt_data_from_file", refuse)
    monkeypatch.setattr(cache_module, "stored_keys_need_unavailable_oqs", lambda *args: True)
    return cache_files


def _write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.unit
class TestJsonFallback:
    def test_failed_encryption_saves_plaintext(self, cache_files, monkeypatch):
        cache = cache_module.AppInfoCache()

        def fail(*args, **kwargs):
            raise RuntimeError("keyring locked")

        monkeypatch.setattr(cache_module, "encrypt_data_to_file", fail)
        cache.set("volume", 42)
        assert cache.store() is False
        assert _read_json(cache_files.json)["info"]["volume"] == 42

    def test_successful_save_removes_a_superseded_json(self, cache_files):
        cache = cache_module.AppInfoCache()
        _write_json(cache_files.json, {"info": {"volume": 1}})
        cache.set("volume", 2)
        assert cache.store() is True
        assert not cache_files.json.exists()
        assert json.loads(cache_files.enc.read_bytes())["info"]["volume"] == 2

    def test_json_at_start_is_migrated_and_removed(self, cache_files):
        _write_json(cache_files.json, {"info": {"volume": 7}, "history": [], "directories": {}})
        cache = cache_module.AppInfoCache()
        assert cache.get("volume") == 7
        assert not cache_files.json.exists()
        assert json.loads(cache_files.enc.read_bytes())["info"]["volume"] == 7


@pytest.mark.unit
class TestWithoutOqs:
    def test_starts_empty_and_leaves_the_encrypted_cache_alone(self, without_oqs):
        without_oqs.enc.write_bytes(b"quantum ciphertext")
        cache = cache_module.AppInfoCache()
        assert cache.get("volume") is None
        assert without_oqs.enc.read_bytes() == b"quantum ciphertext"
        assert not os.path.exists(str(without_oqs.enc) + ".bak")

    def test_saves_go_to_the_no_oqs_file_only(self, without_oqs):
        without_oqs.enc.write_bytes(b"quantum ciphertext")
        cache = cache_module.AppInfoCache()
        cache.set("volume", 5)
        assert cache.store() is False
        assert _read_json(without_oqs.no_oqs_json)["info"]["volume"] == 5
        assert not without_oqs.json.exists()
        assert without_oqs.enc.read_bytes() == b"quantum ciphertext"

    def test_continues_from_the_last_no_oqs_session(self, without_oqs):
        without_oqs.enc.write_bytes(b"quantum ciphertext")
        _write_json(without_oqs.no_oqs_json, {"info": {"volume": 9}, "history": [], "directories": {}})
        cache = cache_module.AppInfoCache()
        assert cache.get("volume") == 9

    def test_unreadable_no_oqs_file_starts_empty(self, without_oqs):
        without_oqs.enc.write_bytes(b"quantum ciphertext")
        without_oqs.no_oqs_json.write_text("{not json", encoding="utf-8")
        cache = cache_module.AppInfoCache()
        assert cache.get("volume") is None

    def test_other_decryption_failures_still_raise(self, cache_files, monkeypatch):
        cache_files.enc.write_bytes(b"corrupt")

        def fail(*args, **kwargs):
            raise ValueError("bad tag")

        monkeypatch.setattr(cache_module, "decrypt_data_from_file", fail)
        with pytest.raises(Exception, match="Failed to load cache from all locations"):
            cache_module.AppInfoCache()
