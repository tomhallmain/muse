# `tests/ui/auth/`

Planned modules:

- `test_password_dialog.py` — accept/reject without touching real key material
- `test_password_session_manager.py` — session timeout / lock state

Keep crypto and filesystem side effects inside `tmp_path` from root `isolated_singletons`.
