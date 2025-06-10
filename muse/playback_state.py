from typing import Optional
from muse.playback_config import PlaybackConfig
from muse.playback_config_master import PlaybackConfigMaster

class PlaybackStateManager:
    """
    Singleton class to manage the current playback state.
    Provides a central place to access and update the current playback configuration.
    """
    _instance = None
    _current_config: Optional[PlaybackConfig] = None
    _current_master_config: Optional[PlaybackConfigMaster] = None

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

    @classmethod
    def get_current_master_config(cls) -> Optional[PlaybackConfigMaster]:
        """Get the current master playback configuration."""
        return cls._current_master_config

    @classmethod
    def set_current_master_config(cls, config: PlaybackConfigMaster) -> None:
        """Set the current master playback configuration."""
        cls._current_master_config = config
        # Update the PlaybackConfigMaster singleton
        PlaybackConfigMaster.set_instance(config)

    @classmethod
    def clear_current_master_config(cls) -> None:
        """Clear the current master playback configuration."""
        cls._current_master_config = None
        PlaybackConfigMaster.reset_instance()

    @classmethod
    def reset(cls) -> None:
        """Reset all playback state."""
        cls.clear_current_config()
        cls.clear_current_master_config() 
