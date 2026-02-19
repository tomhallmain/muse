from typing import Optional
from muse.playback_config_master import PlaybackConfigMaster
from muse.sort_config import SortConfig


class PlaybackStateManager:
    """Singleton class to manage the current playback state.

    Three separate slots:

    - **master_config** -- The user-configured master playlist, set by the
      playlist UI.  Persists across runs and is read by ``Run.do_workflow()``
      when the ``PLAYLIST_CONFIG`` strategy is selected.
    - **active_config** -- The config that is currently playing, set by
      ``Run.run()`` at playback start and cleared when playback ends.
    - **override_sort_config** -- A global sort config override applied to
      every ``PlaybackConfigMaster`` at construction time.  Managed from
      the main app window and also reflected in the ``MasterPlaylistWindow``.
    """

    _instance = None
    _master_config: Optional[PlaybackConfigMaster] = None
    _active_config: Optional[PlaybackConfigMaster] = None
    _override_sort_config: Optional[SortConfig] = None

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
    # Override sort config
    # ------------------------------------------------------------------

    @classmethod
    def get_override_sort_config(cls) -> Optional[SortConfig]:
        """Get the global sort config override."""
        return cls._override_sort_config

    @classmethod
    def set_override_sort_config(cls, config: Optional[SortConfig]) -> None:
        """Set the global sort config override."""
        cls._override_sort_config = config

    # ------------------------------------------------------------------
    # Persistent override (app cache)
    # ------------------------------------------------------------------

    _SORT_CONFIG_CACHE_KEY = "override_sort_config"

    @classmethod
    def load_override_sort_config(cls) -> None:
        """Restore the global override SortConfig from the app cache."""
        from utils.app_info_cache_qt import app_info_cache
        raw = app_info_cache.get(cls._SORT_CONFIG_CACHE_KEY)
        if raw and isinstance(raw, dict):
            sc = SortConfig.from_dict(raw)
            if not sc.is_default():
                cls.set_override_sort_config(sc)

    @classmethod
    def store_override_sort_config(cls) -> None:
        """Persist the global override SortConfig to the app cache."""
        from utils.app_info_cache_qt import app_info_cache
        osc = cls.get_override_sort_config()
        app_info_cache.set(cls._SORT_CONFIG_CACHE_KEY, osc.to_dict() if osc else None)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @classmethod
    def reset(cls) -> None:
        """Reset all playback state."""
        cls.clear_active_config()
        cls.clear_master_config()
        cls._override_sort_config = None
