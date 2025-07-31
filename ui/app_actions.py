from typing import Callable, Dict, Any

class AppActions:
    REQUIRED_ACTIONS = set([
        "track_details_callback",
        "update_next_up_callback",
        "update_prior_track_callback",
        "update_spot_profile_topics_text",
        "update_progress_callback",
        "update_extension_status",
        "update_album_artwork",
        "get_media_frame_handle",
        "shutdown_callback",
        "toast",
        "alert",
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
    ])

    def __init__(self, actions: Dict[str, Callable[..., Any]]):
        missing = self.REQUIRED_ACTIONS - set(actions.keys())
        if missing:
            raise ValueError(f"Missing required actions: {missing}")
        self._actions = actions
    
    def __getattr__(self, name):
        if name in self._actions:
            return self._actions[name]
        raise AttributeError(f"Action '{name}' not found")
