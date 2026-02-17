"""
Qt (PySide6) application actions: callback container passed to internal modules.
Internal modules (muse, library_data, etc.) receive this instance and call
e.g. app_actions.update_track_text(...), app_actions.alert(...), so the
same interface is preserved regardless of UI framework.
"""
from typing import Callable, Dict, Any, Optional


class AppActions:
    """Container of UI callbacks. Required keys must be provided by the main Qt window."""
    REQUIRED_ACTIONS = set([
        "track_details_callback",
        "update_dj_persona_callback",
        "update_next_up_callback",
        "update_prior_track_callback",
        "update_upcoming_group_callback",
        "update_spot_profile_topics_text",
        "update_progress_callback",
        "update_extension_status",
        "update_album_artwork",
        "get_media_frame_handle",
        "shutdown_callback",
        "toast",
        "_alert",
        "update_playlist_state",
        "update_favorite_status",
        "get_current_track",
        "start_play_callback",
        "add_favorite",
        "open_track_details",
        "find_track",
        "search_and_play",
        "update_directory_count",
        "open_password_admin_window",
        "set_playback_master_strategy",
    ])

    def __init__(self, actions: Dict[str, Callable[..., Any]], master: Optional[object] = None):
        missing = self.REQUIRED_ACTIONS - set(actions.keys())
        if missing:
            raise ValueError(f"Missing required actions: {missing}")
        self._actions = actions
        self._master = master

    def __getattr__(self, name):
        if name in self._actions:
            return self._actions[name]
        raise AttributeError(f"Action '{name}' not found")

    def alert(self, title: str, message: str, kind: str = "info", severity: str = "normal", master: Optional[object] = None):
        """Show an alert; parent is the provided master or the stored Qt window."""
        parent_window = master if master is not None else self._master
        return self._alert(title, message, kind=kind, severity=severity, master=parent_window)

    def get_master(self):
        return self._master
