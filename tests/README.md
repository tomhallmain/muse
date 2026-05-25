# Muse test suite

## Isolation (pytest)

The root `tests/conftest.py` follows the same pattern as the Weidr project:

1. **Module load** — Sets `MUSE_CACHE_DIR` and `MUSE_CONFIGS_DIR` to a temp directory *before* any app singleton import, so `app_info_cache`, `config`, and `muse_memory` never read production files during collection.
2. **Per test** — `isolated_singletons` rebuilds those singletons under `tmp_path` and patches module-level imports so stale singleton references stay in sync.

**Note:** `utils/__init__.py` re-exports singletons with the same names as submodules (`app_info_cache`, `config`). That shadows the real modules on the `utils` package, so `import utils.app_info_cache as x` is the **instance**, not the module — and `x.AppInfoCache()` fails. The fixture uses `from utils.app_info_cache import AppInfoCache` and `importlib.import_module("utils.config")` instead.
3. **Reset** — `reset_app_globals` clears playlist history, library pickle caches in memory, and playback config registries.

Cache file overrides use `MUSE_CACHE_DIR` via `utils/cache_paths.py`. Config overrides use `MUSE_CONFIGS_DIR` via `Config.resolve_config_path()` in `utils/config.py` (same pattern as Weidr's `WEIDR_CONFIGS_DIR`).

### What pytest touches

| Area | Isolated? | Notes |
|------|-----------|--------|
| `app_info_cache` | Yes | Per-test temp dir |
| `config.json` | Yes | Copied from `configs/config_example.json` |
| `muse_memory` | Yes | Fresh instance per test |
| `app_media_track_cache` / `app_directories_cache` | Yes | Paths under `MUSE_CACHE_DIR`; in-memory reset |
| Playlist recently-played lists | Yes | Reset via `HistoryType` |
| `tests/unit/*` | Yes | Pure or mocked; see `tests/unit/conftest.py` |
| `tests/integration/test_playback_integration.py` | Yes | Uses `mock_data_callbacks` + fixtures only |

### Intro type tests

- **Pytest:** `tests/unit/test_determine_intro_type.py` — calls `muse.intro_type.determine_intro_type` only (no `Muse`, no `muse_memory`).
- **Manual script:** `tests/scripts/test_determine_intro_type.py` — heatmaps and printed cases; not collected (`pytest.ini` → `norecursedirs = scripts`).

The former `tests/integration/test_intro_type.py` was removed; it depended on the global `muse_memory` singleton and full `Muse` construction without isolation.

## Manual scripts (`tests/scripts/`)

Not run by `pytest`. These intentionally use **your** library caches and config unless you set `MUSE_CACHE_DIR` / `MUSE_CONFIGS_DIR` yourself:

- `test_sort_compare.py` / `test_sort_compare_all_music.py` — real `LibraryData` caches
- `test_seek_to_track.py` / `test_seek_preview_qt.py` — search + playback against your library
- `test_determine_intro_type.py` — intro timing exploration (logic only; no longer needs `muse_memory`)

Use `tests/utils/project_setup.py` for the shared “load all caches” bootstrap in scripts.

## Running tests

```bash
pytest tests/unit/test_determine_intro_type.py
pytest tests/unit
pytest tests
```
