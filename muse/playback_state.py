from typing import Optional
from muse.playback_config import PlaybackConfig

class PlaybackStateManager:
    """
    Singleton class to manage the current playback state.
    Provides a central place to access and update the current playback configuration.
    """
    _instance = None
    _current_config: Optional[PlaybackConfig] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PlaybackStateManager, cls).__new__(cls)
        return cls._instance

    @classmethod
    def get_current_config(cls) -> Optional[PlaybackConfig]:
        """Get the current playback configuration."""
        return cls._current_config

    @classmethod
    def set_current_config(cls, config: PlaybackConfig) -> None:
        """Set the current playback configuration."""
        cls._current_config = config

    @classmethod
    def clear_current_config(cls) -> None:
        """Clear the current playback configuration."""
        cls._current_config = None 