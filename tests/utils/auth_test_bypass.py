"""
Disable password prompts and OS credential storage during pytest.

Windows/macOS password material is stored via ``keyring`` (Credential Manager /
Keychain). Patching only ``require_password`` is not enough: UI modules import
``from ui_qt.auth.password_utils import require_password`` at load time, so
already-decorated methods still run the real wrapper. We bypass
``check_password_required`` (called at runtime) and stub ``PasswordManager`` /
encryptor helpers so tests never touch the host credential store.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional


def _noop_require_password(*_actions: Any, **_kwargs: Any) -> Callable:
    """Weidr-style decorator replacement: return the wrapped function unchanged."""

    def decorator(func: Callable) -> Callable:
        return func

    return decorator


def _bypass_check_password_required(
    action_names: List,
    master,
    callback=None,
    app_actions=None,
    custom_text=None,
    allow_unauthenticated=True,
) -> bool:
    """Skip dialogs and keyring; invoke the success callback immediately."""
    del action_names, master, app_actions, custom_text, allow_unauthenticated
    if callback:
        return callback(True)
    return True


def install_password_bypass(monkeypatch) -> None:
    """Apply password bypass patches (call from a pytest ``autouse`` fixture)."""
    monkeypatch.setattr(
        "ui_qt.auth.password_utils.require_password",
        _noop_require_password,
    )
    monkeypatch.setattr(
        "ui_qt.auth.password_utils.check_password_required",
        _bypass_check_password_required,
    )

    # Modules that bound require_password before the patch above.
    _rebind_modules = (
        "app_qt",
        "ui_qt.search_window",
        "ui_qt.history_window",
        "ui_qt.favorites_window",
        "ui_qt.composers_window",
        "ui_qt.playlist_window",
        "ui_qt.configuration_window",
        "ui_qt.extensions_window",
        "ui_qt.blacklist_window",
        "ui_qt.schedules_window",
        "ui_qt.personas_window",
        "ui_qt.auth.password_admin_window",
    )
    for module_name in _rebind_modules:
        try:
            monkeypatch.setattr(module_name + ".require_password", _noop_require_password)
        except Exception:
            pass

    # Never read or write the host password vault during tests.
    monkeypatch.setattr(
        "ui_qt.auth.password_core.retrieve_encrypted_password",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "ui_qt.auth.password_core.store_encrypted_password",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "ui_qt.auth.password_core.delete_stored_password",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "ui_qt.auth.password_core.PasswordManager.is_security_configured",
        lambda: False,
    )
    monkeypatch.setattr(
        "ui_qt.auth.password_core.PasswordManager.verify_password",
        lambda password: False,
    )
    monkeypatch.setattr(
        "ui_qt.auth.password_core.PasswordManager.set_password",
        lambda password: True,
    )
    monkeypatch.setattr(
        "ui_qt.auth.password_core.PasswordManager.clear_password",
        lambda: True,
    )
    monkeypatch.setattr(
        "ui_qt.auth.password_core.PasswordManager._security_configured_cache",
        False,
    )

    # Fresh SecurityConfig per access; treat no actions as protected in tests.
    monkeypatch.setattr("ui_qt.auth.password_core._security_config", None)

    def _never_protected(self, action_name) -> bool:
        return False

    monkeypatch.setattr(
        "ui_qt.auth.password_core.SecurityConfig.is_action_protected",
        _never_protected,
    )

    def _no_security_advice(self) -> bool:
        return False

    monkeypatch.setattr(
        "ui_qt.auth.password_core.SecurityConfig.is_security_advice_enabled",
        _no_security_advice,
    )

    monkeypatch.setattr(
        "ui_qt.auth.password_dialog.PasswordDialog.prompt_password",
        lambda *args, **kwargs: True,
    )
