# `tests/ui/auth/`

Modules:

- `test_password_session.py` — session recording and validity
- `test_require_password.py` — the decorator keeps the method's name (PySide6
  signal connections in a compiled build depend on it) and runs it when granted
- `test_password_without_oqs.py` — protection fails closed when the stored
  password needs OQS the build lacks

These three create no widgets; the dialog and alerts are stubbed.

Planned modules:

- `test_password_dialog.py` — accept/reject without touching real key material
- `test_password_session_manager.py` — session timeout / lock state

Keep crypto and filesystem side effects inside `tmp_path` from root `isolated_singletons`.
