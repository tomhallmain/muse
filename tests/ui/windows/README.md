# `tests/ui/windows/`

Per-window UI tests (offscreen Qt). All use fixtures from `tests/ui/conftest.py`.

| Module | Status | Focus |
|--------|--------|--------|
| `test_search_window.py` | Implemented | Open, composer/album search on fixture library |
| `test_playlist_window.py` | Implemented | Open, preview widget, queue helper smoke |
| `test_favorites_window.py` | Implemented | Open, favorites persist via isolated `app_info_cache` |
| `test_library_window.py` | Implemented | Track/album/composer counts vs fixture library |
| `test_history_window.py` | Implemented | History list search over `Playlist.recently_played_*` |
| `test_composers_window.py` | Implemented | Search Beethoven/Bach; recent searches in app cache |
| `test_forms_window.py` | Implemented | Search sonata; list all; recent searches in app cache |
| `test_genres_window.py` | Implemented | Search Baroque; list all; recent searches persist across open/close |
| `test_artists_window.py` | Implemented | Search Allman Brothers Band; list all; recent searches persist across open/close |

Planned next: `test_sort_config_window.py`, `test_track_details_window.py`, end-to-end seek/preview (port `tests/scripts/test_seek_preview_qt.py`).
