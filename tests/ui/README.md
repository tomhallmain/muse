# `tests/ui/`

PySide6 UI tests. See [UI test plan](../docs/UI_TEST_PLAN.md) for phasing.

## Layout

| Path | Maps to | Status |
|------|---------|--------|
| `windows/` | `ui_qt/*_window.py`, `media_frame.py` | Baseline tests in place |
| `auth/` | `ui_qt/auth/*` | Planned |
| (root) | `app_qt.MuseAppQt`, `app_actions.py` | Planned: `test_app_shell.py` |

## Running

```bash
pytest tests/ui -m ui
pytest -m "not ui"
```

## Conventions

- `@pytest.mark.ui` on every test module (applied via `conftest.py` `pytestmark`).
- Inject `audio_library_callbacks`; do not depend on production pickles.
- Volume to 0 before any playback; use `qt_test_helpers.process_events_for`.
- Prefer constructing a single window with mocked `LibraryData` callbacks before full `MuseAppQt` boot.

**Passwords:** Handled by root `tests/conftest.py` → `bypass_password` (not duplicated here). Same approach as Weidr’s `bypass_password` fixture.

**Window placement:** `bypass_multi_display_positioning` avoids `QWidget.screen()` during `SmartWindow` construction (see `tests/utils/qt_display_test_bypass.py`).

**Note:** Test imports use the application package `ui_qt` (e.g. `from ui_qt.search_window import SearchWindow`). That is unrelated to this directory name `tests/ui`.
