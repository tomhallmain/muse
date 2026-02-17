from typing import Optional
from muse.playback_config_master import PlaybackConfigMaster


class PlaybackStateManager:
    """Singleton class to manage the current playback state.

    Two separate slots:

    - **master_config** -- The user-configured master playlist, set by the
      playlist UI.  Persists across runs and is read by ``Run.do_workflow()``
      when the ``PLAYLIST_CONFIG`` strategy is selected.
    - **active_config** -- The config that is currently playing, set by
      ``Run.run()`` at playback start and cleared when playback ends.
    """

    _instance = None
    _master_config: Optional[PlaybackConfigMaster] = None
    _active_config: Optional[PlaybackConfigMaster] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PlaybackStateManager, cls).__new__(cls)
        return cls._instance

    # ------------------------------------------------------------------
    # Active (running) config
    # ------------------------------------------------------------------

    @classmethod
    def get_active_config(cls) -> Optional[PlaybackConfigMaster]:
        """Get the currently playing config (set at playback start)."""
        return cls._active_config

    @classmethod
    def set_active_config(cls, config: PlaybackConfigMaster) -> None:
        """Set the currently playing config."""
        cls._active_config = config

    @classmethod
    def clear_active_config(cls) -> None:
        """Clear the currently playing config (called at playback end)."""
        cls._active_config = None

    # ------------------------------------------------------------------
    # Master (UI-configured) config
    # ------------------------------------------------------------------

    @classmethod
    def get_master_config(cls) -> Optional[PlaybackConfigMaster]:
        """Get the user-configured master playlist."""
        return cls._master_config

    @classmethod
    def set_master_config(cls, config: PlaybackConfigMaster) -> None:
        """Set the user-configured master playlist."""
        cls._master_config = config

    @classmethod
    def clear_master_config(cls) -> None:
        """Clear the user-configured master playlist."""
        cls._master_config = None

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @classmethod
    def reset(cls) -> None:
        """Reset all playback state."""
        cls.clear_active_config()
        cls.clear_master_config()
