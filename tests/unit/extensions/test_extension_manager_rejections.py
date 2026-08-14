"""Tests for extension rejection feedback (extensions/extension_manager.py)."""

import pytest

import extensions.extension_manager as extension_manager_mod
from extensions.extension_manager import ExtensionManager
from utils.globals import TrackAttribute


class SimpleNamespaceLike:
    """Stand-in for the LibraryExtender result wrapper; `_is_rejected` only reads `.w`/`.n`."""

    def __init__(self, w, n):
        self.w = w
        self.n = n


class _FakeCache:
    def __init__(self, data=None):
        self._data = dict(data or {})

    def get(self, key, default_val=None):
        return self._data.get(key, default_val)

    def set(self, key, value):
        self._data[key] = value


@pytest.fixture(autouse=True)
def _reset_extension_manager_state(monkeypatch):
    monkeypatch.setattr(extension_manager_mod, "app_info_cache", _FakeCache())
    ExtensionManager.rejected_extensions = []
    ExtensionManager.rejected_ids = set()
    ExtensionManager.pending_candidate = None
    yield
    ExtensionManager.rejected_extensions = []
    ExtensionManager.rejected_ids = set()
    ExtensionManager.pending_candidate = None


def _set_pending(id_="abc123", title="Some Title", attr=TrackAttribute.ARTIST, query="some query"):
    ExtensionManager.pending_candidate = {
        "id": id_,
        "title": title,
        "rejected": False,
        "raw": {"id": id_, "snippet": {"title": title}},
        "attr": attr,
        "search_query": query,
    }


@pytest.mark.unit
class TestRejectPendingCandidate:
    def test_no_pending_candidate_returns_false(self):
        assert ExtensionManager.reject_pending_candidate() is False
        assert ExtensionManager.rejected_extensions == []

    def test_builds_full_record_not_just_id(self):
        _set_pending()

        assert ExtensionManager.reject_pending_candidate() is True

        assert len(ExtensionManager.rejected_extensions) == 1
        record = ExtensionManager.rejected_extensions[0]
        assert record["id"] == "abc123"
        assert record["snippet"]["title"] == "Some Title"
        assert record["track_attr"] == "ARTIST"
        assert record["search_query"] == "some query"
        assert record["date"]
        assert "abc123" in ExtensionManager.rejected_ids

    def test_unknown_attr_recorded_as_placeholder(self):
        _set_pending(attr=None)

        ExtensionManager.reject_pending_candidate()

        assert ExtensionManager.rejected_extensions[0]["track_attr"] == "<unknown>"

    def test_marks_pending_candidate_rejected(self):
        _set_pending()
        pending = ExtensionManager.pending_candidate

        ExtensionManager.reject_pending_candidate()

        assert pending["rejected"] is True

    def test_is_rejected_excludes_candidate_after_rejection(self):
        _set_pending(id_="xyz789")
        ExtensionManager.reject_pending_candidate()

        candidate = SimpleNamespaceLike(w="xyz789", n="Some Title")
        assert ExtensionManager._is_rejected(None, candidate) is True

    def test_persists_via_store_extensions(self):
        _set_pending()
        ExtensionManager.reject_pending_candidate()

        stored = extension_manager_mod.app_info_cache.get("rejected_extensions")
        assert stored is not None
        assert stored[0]["id"] == "abc123"


@pytest.mark.unit
class TestRemoveRejection:
    def test_removes_from_both_list_and_ids(self):
        _set_pending(id_="to-remove")
        ExtensionManager.reject_pending_candidate()
        record = ExtensionManager.rejected_extensions[0]

        assert ExtensionManager.remove_rejection(record) is True
        assert ExtensionManager.rejected_extensions == []
        assert "to-remove" not in ExtensionManager.rejected_ids

    def test_candidate_no_longer_excluded_after_removal(self):
        _set_pending(id_="to-remove")
        ExtensionManager.reject_pending_candidate()
        record = ExtensionManager.rejected_extensions[0]
        ExtensionManager.remove_rejection(record)

        candidate = SimpleNamespaceLike(w="to-remove", n="Some Title")
        assert ExtensionManager._is_rejected(None, candidate) is False

    def test_unknown_record_returns_false(self):
        assert ExtensionManager.remove_rejection({"id": "never-existed"}) is False


@pytest.mark.unit
class TestLegacyRejectedIdsMigration:
    def test_bare_ids_wrapped_into_placeholder_records(self, monkeypatch):
        monkeypatch.setattr(
            extension_manager_mod,
            "app_info_cache",
            _FakeCache({"rejected_extension_ids": ["legacy-1", "legacy-2"]}),
        )

        ExtensionManager.load_extensions()

        ids = {r["id"] for r in ExtensionManager.rejected_extensions}
        assert ids == {"legacy-1", "legacy-2"}
        for record in ExtensionManager.rejected_extensions:
            assert record["snippet"]["title"] == ""
        assert ExtensionManager.rejected_ids == {"legacy-1", "legacy-2"}

    def test_migration_keeps_excluding_legacy_ids(self, monkeypatch):
        monkeypatch.setattr(
            extension_manager_mod,
            "app_info_cache",
            _FakeCache({"rejected_extension_ids": ["legacy-1"]}),
        )

        ExtensionManager.load_extensions()

        candidate = SimpleNamespaceLike(w="legacy-1", n="Untitled")
        assert ExtensionManager._is_rejected(None, candidate) is True

    def test_migration_skips_ids_with_existing_full_record(self, monkeypatch):
        cache = _FakeCache({
            "rejected_extension_ids": ["id-1"],
            "rejected_extensions": [{
                "id": "id-1",
                "snippet": {"title": "Real Title"},
                "date": "2024-01-01T00:00:00",
                "track_attr": "ARTIST",
                "search_query": "q",
            }],
        })
        monkeypatch.setattr(extension_manager_mod, "app_info_cache", cache)

        ExtensionManager.load_extensions()

        assert len(ExtensionManager.rejected_extensions) == 1
        assert ExtensionManager.rejected_extensions[0]["snippet"]["title"] == "Real Title"

    def test_no_legacy_ids_is_a_no_op(self, monkeypatch):
        cache = _FakeCache()
        monkeypatch.setattr(extension_manager_mod, "app_info_cache", cache)

        ExtensionManager.load_extensions()

        assert ExtensionManager.rejected_extensions == []
        assert ExtensionManager.rejected_ids == set()
