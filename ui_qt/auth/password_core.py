"""
Core password functionality for the Muse application.
This module contains the foundational password management and configuration classes.
It has no dependencies on other password modules to avoid circular imports.
"""

from utils.globals import AppInfo, ProtectedActions
from utils.app_info_cache import app_info_cache
from utils.encryptor import store_encrypted_password, retrieve_encrypted_password, delete_stored_password


class SecurityConfig:
    """Central configuration manager for password protection settings."""
    
    # Default password-protected actions (START_APPLICATION excluded - not used in Qt app)
    DEFAULT_PROTECTED_ACTIONS = {
        ProtectedActions.RUN_SEARCH.value: False,
        ProtectedActions.VIEW_LIBRARY.value: False,
        ProtectedActions.VIEW_HISTORY.value: False,
        ProtectedActions.EDIT_LIBRARY_VOCABULARY.value: False,
        ProtectedActions.EDIT_SCHEDULES.value: True,
        ProtectedActions.EDIT_EXTENSIONS.value: False,
        ProtectedActions.EDIT_PLAYLISTS.value: False,
        ProtectedActions.EDIT_FAVORITES.value: False,
        ProtectedActions.DELETE_MEDIA.value: True,
        ProtectedActions.EDIT_CONFIGURATION.value: False,
        ProtectedActions.ACCESS_ADMIN.value: True  # Always protected
    }
    
    # Default session timeout settings (in minutes)
    DEFAULT_SESSION_TIMEOUT_ENABLED = True
    DEFAULT_SESSION_TIMEOUT_MINUTES = 30  # 30 minutes default

    # Default security advertisement settings
    DEFAULT_SHOW_SECURITY_ADVICE = True  # Show security advice when no password is configured

    # Renamed/merged ProtectedActions values, old cache key -> current enum.
    # Composers/Forms/Genres/Artists windows used to each have (or, briefly,
    # did have) their own protected action; all merged into
    # EDIT_LIBRARY_VOCABULARY. A user's existing preference (protected or
    # not) is carried over to the new key on load rather than silently
    # resetting to the new key's default; the old key is then dropped.
    LEGACY_ACTION_KEYS = {
        "edit_composers": ProtectedActions.EDIT_LIBRARY_VOCABULARY,
        "edit_forms": ProtectedActions.EDIT_LIBRARY_VOCABULARY,
        "edit_genres": ProtectedActions.EDIT_LIBRARY_VOCABULARY,
        "edit_artists": ProtectedActions.EDIT_LIBRARY_VOCABULARY,
    }

    def __init__(self):
        self._load_settings()

    def _migrate_legacy_action_keys(self) -> bool:
        """One-time migration for renamed/merged ProtectedActions members.

        Checked on every load, but only does real work the first time a
        given cache is loaded after the rename/merge — once the old keys are
        gone there's nothing left to find. Also covers settings saved by a
        version of the app between the merge and the rename (multiple old
        keys collapsing onto the same new key). If old keys disagree, the
        most protective (True) value wins, since a looser value should never
        silently emerge from a rename. Returns whether anything changed, so
        the caller only re-persists when there was actually a migration.
        """
        migrated = False
        for old_key, new_action in self.LEGACY_ACTION_KEYS.items():
            if old_key not in self.protected_actions:
                continue
            old_value = self.protected_actions.pop(old_key)
            new_key = new_action.value
            if new_key in self.protected_actions:
                self.protected_actions[new_key] = self.protected_actions[new_key] or old_value
            else:
                self.protected_actions[new_key] = old_value
            migrated = True
        return migrated

    def _load_settings(self):
        """Load settings from cache or use defaults."""
        self.session_timeout_enabled = app_info_cache.get("session_timeout_enabled", default_val=self.DEFAULT_SESSION_TIMEOUT_ENABLED)
        self.session_timeout_minutes = app_info_cache.get("session_timeout_minutes", default_val=self.DEFAULT_SESSION_TIMEOUT_MINUTES)
        self.protected_actions = app_info_cache.get("protected_actions", default_val=self.DEFAULT_PROTECTED_ACTIONS.copy())
        self.show_security_advice = app_info_cache.get("show_security_advice", default_val=self.DEFAULT_SHOW_SECURITY_ADVICE)

        if self._migrate_legacy_action_keys():
            # Persist the migration now so the legacy key doesn't linger in
            # the cache and get re-migrated (harmlessly, but pointlessly)
            # on every future load.
            self.save_settings()

        # Exclude START_APPLICATION from Qt (not used on startup)
        if ProtectedActions.START_APPLICATION.value in self.protected_actions:
            del self.protected_actions[ProtectedActions.START_APPLICATION.value]

        # Add any new protected actions that aren't in cache yet
        for action_enum in ProtectedActions:
            if action_enum == ProtectedActions.START_APPLICATION:
                continue
            action = action_enum.value
            if action not in self.protected_actions:
                # Default to True for new actions (protected by default)
                self.protected_actions[action] = True

        # Ensure ACCESS_ADMIN always remains protected
        self.protected_actions[ProtectedActions.ACCESS_ADMIN.value] = True

    def save_settings(self):
        """Save current settings to cache."""
        app_info_cache.set("protected_actions", self.protected_actions)
        app_info_cache.set("session_timeout_enabled", self.session_timeout_enabled)
        app_info_cache.set("session_timeout_minutes", self.session_timeout_minutes)
        app_info_cache.set("show_security_advice", self.show_security_advice)

    def reset_to_defaults(self):
        """Reset all settings to their default values."""
        self.protected_actions = self.DEFAULT_PROTECTED_ACTIONS.copy()
        self.session_timeout_enabled = self.DEFAULT_SESSION_TIMEOUT_ENABLED
        self.session_timeout_minutes = self.DEFAULT_SESSION_TIMEOUT_MINUTES
        self.show_security_advice = self.DEFAULT_SHOW_SECURITY_ADVICE

        # Ensure ACCESS_ADMIN always remains protected
        self.protected_actions[ProtectedActions.ACCESS_ADMIN.value] = True
    
    def is_action_protected(self, action_name):
        """Check if a specific action requires password authentication."""
        if not action_name or not isinstance(action_name, str) or not action_name in self.protected_actions:
            print("Invalid action name was not found in protected actions: " + str(action_name))
            return False
        return self.protected_actions.get(action_name, False)
    
    def is_session_timeout_enabled(self):
        """Check if session timeout is enabled."""
        return self.session_timeout_enabled
    
    def get_session_timeout_minutes(self):
        """Get the session timeout duration in minutes."""
        return self.session_timeout_minutes
    
    def set_action_protected(self, action_name, protected):
        """Set whether an action requires password protection."""
        self.protected_actions[action_name] = protected
        # Ensure ACCESS_ADMIN always remains protected
        self.protected_actions[ProtectedActions.ACCESS_ADMIN.value] = True
    
    def set_session_timeout_enabled(self, enabled):
        """Set whether session timeout is enabled."""
        self.session_timeout_enabled = enabled
    
    def set_session_timeout_minutes(self, minutes):
        """Set the session timeout duration in minutes."""
        if minutes > 0:
            self.session_timeout_minutes = minutes

    def is_security_advice_enabled(self):
        """Check if security advice should be shown when no password is configured."""
        return self.show_security_advice

    def set_security_advice_enabled(self, enabled):
        """Set whether security advice should be shown when no password is configured."""
        self.show_security_advice = enabled

# Global instance
_security_config = None

def get_security_config():
    """Get the global password configuration instance."""
    global _security_config
    if _security_config is None:
        _security_config = SecurityConfig()
    return _security_config


class PasswordManager:
    """Manages password storage and verification using encrypted storage."""
    
    PASSWORD_ID = "base"
    _security_configured_cache = None

    @staticmethod
    def is_security_configured():
        """Check if a password is configured."""
        if PasswordManager._security_configured_cache is not None:
            return PasswordManager._security_configured_cache
        try:
            # Check if password exists in encrypted storage
            stored_password = retrieve_encrypted_password(
                AppInfo.SERVICE_NAME,
                AppInfo.APP_IDENTIFIER,
                PasswordManager.PASSWORD_ID
            )
            PasswordManager._security_configured_cache = stored_password is not None and len(stored_password) > 0
            return PasswordManager._security_configured_cache
        except:
            PasswordManager._security_configured_cache = False
            return False
    
    @staticmethod
    def set_password(password):
        """Set a new password using encrypted storage."""
        try:
            # Store the password using encrypted storage
            success = store_encrypted_password(
                AppInfo.SERVICE_NAME,
                AppInfo.APP_IDENTIFIER,
                PasswordManager.PASSWORD_ID,
                password
            )
            if success:
                PasswordManager._security_configured_cache = True
            return success
        except Exception as e:
            print(f"Error setting password: {e}")
            return False
    
    @staticmethod
    def verify_password(password):
        """Verify a password against the stored encrypted password."""
        try:
            # Retrieve the stored password from encrypted storage
            stored_password = retrieve_encrypted_password(
                AppInfo.SERVICE_NAME,
                AppInfo.APP_IDENTIFIER,
                PasswordManager.PASSWORD_ID
            )
            
            if not stored_password:
                return False
            
            # Compare the provided password with the stored password
            return password == stored_password
        except Exception as e:
            print(f"Error verifying password: {e}")
            return False
    
    @staticmethod
    def clear_password():
        """Clear the stored password from encrypted storage."""
        try:
            # Remove the password from encrypted storage
            delete_stored_password(
                AppInfo.SERVICE_NAME,
                AppInfo.APP_IDENTIFIER,
                PasswordManager.PASSWORD_ID
            )
            PasswordManager._security_configured_cache = False
            return True
        except Exception as e:
            print(f"Error clearing password: {e}")
            return False 