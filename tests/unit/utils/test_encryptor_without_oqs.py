"""Tests for how utils/encryptor.py reports quantum keys without OQS."""

import pytest

import utils.encryptor as enc

SERVICE = "TestService"
APP = "test_app"


@pytest.fixture
def stored_type(monkeypatch):
    """Set the encryptor type the key store reports."""
    def set_type(value):
        monkeypatch.setattr(enc, "read_key_store", lambda service, app: {enc.ENCRYPTOR_TYPE_KEY: value})
    return set_type


@pytest.mark.unit
class TestStoredKeysNeedUnavailableOqs:
    def test_quantum_keys_without_oqs(self, monkeypatch, stored_type):
        monkeypatch.setattr(enc, "KeyEncapsulation", None)
        stored_type("quantum")
        assert enc.stored_keys_need_unavailable_oqs(SERVICE, APP) is True

    def test_quantum_keys_with_oqs(self, monkeypatch, stored_type):
        monkeypatch.setattr(enc, "KeyEncapsulation", object())
        stored_type("quantum")
        assert enc.stored_keys_need_unavailable_oqs(SERVICE, APP) is False

    @pytest.mark.parametrize("value", ["standard", None])
    def test_other_keys_without_oqs(self, monkeypatch, stored_type, value):
        monkeypatch.setattr(enc, "KeyEncapsulation", None)
        stored_type(value)
        assert enc.stored_keys_need_unavailable_oqs(SERVICE, APP) is False

    def test_falls_back_to_the_keychain_item_without_a_key_store(self, monkeypatch):
        monkeypatch.setattr(enc, "KeyEncapsulation", None)
        monkeypatch.setattr(enc, "read_key_store", lambda service, app: None)

        class Keyring:
            @staticmethod
            def get_password(service, key):
                return "quantum" if key == enc.namespaced_key(APP, enc.ENCRYPTOR_TYPE_KEY) else None

        monkeypatch.setattr(enc, "keyring", Keyring)
        assert enc.stored_keys_need_unavailable_oqs(SERVICE, APP) is True


@pytest.mark.unit
class TestDetermineEncryptor:
    def test_quantum_keys_without_oqs_raise_a_specific_error(self, monkeypatch, stored_type):
        monkeypatch.setattr(enc, "KeyEncapsulation", None)
        stored_type("quantum")
        with pytest.raises(enc.OQSUnavailableError):
            enc._determine_encryptor(SERVICE, APP)

    def test_the_error_is_still_a_runtime_error(self):
        assert issubclass(enc.OQSUnavailableError, RuntimeError)
