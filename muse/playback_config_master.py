from copy import deepcopy
import datetime
import time
from typing import Dict, List, Optional, Any

from library_data.media_track import MediaTrack
from muse.playback_config import PlaybackConfig
from muse.playlist import Playlist
from utils.globals import TrackResult
from utils.logging_setup import get_logger

logger = get_logger(__name__)


class PlaybackConfigMaster:
    """Manages multiple PlaybackConfig instances with weighted round-robin interleaving.

    Provides the same interface as PlaybackConfig so that Playback can use
    either one transparently. When constructed with a single config and
    default weights, it behaves identically to a bare PlaybackConfig (the
    ALL_MUSIC code-path).

    Interleaving algorithm (weighted round-robin with exhaustion handling)::

        Given:  configs = [A, B, C]
                weights = [2, 1, 3]

        Cycle:  A, A, B, C, C, C, A, A, B, C, C, C, ...

        When A is exhausted:
                B, C, C, C, B, C, C, C, ...

        When all are exhausted:
                Playback stops (next_track returns TrackResult()).
    """

    LAST_EXTENSION_PLAYED: datetime.datetime = datetime.datetime.now()
    READY_FOR_EXTENSION: bool = True
    OPEN_CONFIGS: List['PlaybackConfigMaster'] = []

    # ------------------------------------------------------------------
    # Extension handling
    # ------------------------------------------------------------------

    @staticmethod
    def assign_extension(new_file: str) -> None:
        while not PlaybackConfigMaster.READY_FOR_EXTENSION:
            logger.info("Waiting for config to accept extension...")
            time.sleep(5)
        logger.info("Assigning extension to playback")
        PlaybackConfigMaster.READY_FOR_EXTENSION = False
        for open_config in PlaybackConfigMaster.OPEN_CONFIGS:
            open_config.set_next_track_override(new_file)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, playback_configs: Optional[List[PlaybackConfig]] = None,
                 weights: Optional[List[int]] = None) -> None:
        self.playback_configs: List[PlaybackConfig] = playback_configs or []
        self.weights: List[int] = weights or [1] * len(self.playback_configs)

        if len(self.weights) != len(self.playback_configs):
            raise ValueError(
                f"weights length ({len(self.weights)}) != "
                f"playback_configs length ({len(self.playback_configs)})"
            )

        # Interleaving state
        self._config_cursor: int = 0
        self._weight_counter: int = 0
        self._active_mask: List[bool] = [True] * len(self.playback_configs)

        # Playback state
        self.playing: bool = False
        self.played_tracks: List[MediaTrack] = []
        self.next_track_override: Optional[str] = None

        PlaybackConfigMaster.OPEN_CONFIGS.append(self)

    # ------------------------------------------------------------------
    # Interleaving helpers
    # ------------------------------------------------------------------

    def _advance_cursor(self) -> bool:
        """Move to the next active config in the round-robin.

        Returns True if an active config was found, False if all are exhausted.
        """
        if not any(self._active_mask):
            return False
        start = self._config_cursor
        while True:
            self._config_cursor = (self._config_cursor + 1) % len(self.playback_configs)
            self._weight_counter = 0
            if self._active_mask[self._config_cursor]:
                return True
            if self._config_cursor == start:
                return False

    def _peek_next_config(self) -> Optional[PlaybackConfig]:
        """Return the config that *would* provide the next track without
        mutating any interleaving state."""
        if not any(self._active_mask):
            return None

        cursor = self._config_cursor
        counter = self._weight_counter

        # If we've already drawn enough from this slot, peek at the next.
        if counter >= self.weights[cursor] or not self._active_mask[cursor]:
            start = cursor
            while True:
                cursor = (cursor + 1) % len(self.playback_configs)
                if self._active_mask[cursor]:
                    return self.playback_configs[cursor]
                if cursor == start:
                    return None
        return self.playback_configs[cursor]

    # ------------------------------------------------------------------
    # Core playback interface
    # ------------------------------------------------------------------

    def next_track(self, skip_grouping: bool = False,
                   places_from_current: int = 0) -> TrackResult:
        """Get the next track using weighted round-robin interleaving."""
        self.playing = True

        # Handle override (e.g. from library extender)
        if self.next_track_override is not None:
            track = MediaTrack(self.next_track_override)
            track.set_is_extended()
            self.next_track_override = None
            PlaybackConfigMaster.READY_FOR_EXTENSION = True
            return TrackResult(track)

        if not any(self._active_mask):
            return TrackResult()

        config = self.playback_configs[self._config_cursor]
        result = config.next_track(
            skip_grouping=skip_grouping,
            places_from_current=places_from_current,
        )

        if result.track is None:
            # Current config exhausted -- check loop flag.
            if config.loop:
                playlist = config.get_list()
                if hasattr(playlist, 'reset'):
                    playlist.reset()
                else:
                    # Invalidate so get_list() rebuilds from the same source.
                    config.list = Playlist(
                        data_callbacks=config.data_callbacks,
                        check_entire_playlist=config.check_entire_playlist,
                    )
                result = config.next_track(
                    skip_grouping=skip_grouping,
                    places_from_current=places_from_current,
                )

            if result.track is None:
                self._active_mask[self._config_cursor] = False
                if self._advance_cursor():
                    return self.next_track(skip_grouping, places_from_current)
                return TrackResult()

        self._weight_counter += 1
        self.played_tracks.append(result.track)

        if self._weight_counter >= self.weights[self._config_cursor]:
            self._advance_cursor()

        return result

    def upcoming_track(self, places_from_current: int = 1) -> TrackResult:
        """Peek at the next track without advancing interleaving state."""
        if self.next_track_override is not None:
            track = MediaTrack(self.next_track_override)
            track.set_is_extended()
            return TrackResult(track)

        cfg = self._peek_next_config()
        if cfg is None:
            return TrackResult()
        return cfg.upcoming_track(places_from_current=places_from_current)

    def current_track(self) -> Optional[MediaTrack]:
        cfg = self.current_playback_config
        return cfg.current_track() if cfg else None

    def set_next_track_override(self, new_file: str) -> None:
        self.next_track_override = new_file

    # ------------------------------------------------------------------
    # Property proxies (Playback compatibility)
    # ------------------------------------------------------------------

    @property
    def current_playback_config(self) -> Optional[PlaybackConfig]:
        if 0 <= self._config_cursor < len(self.playback_configs):
            return self.playback_configs[self._config_cursor]
        return None

    @property
    def enable_long_track_splitting(self) -> bool:
        cfg = self.current_playback_config
        return cfg.enable_long_track_splitting if cfg else False

    @property
    def long_track_splitting_time_cutoff_minutes(self) -> int:
        cfg = self.current_playback_config
        return cfg.long_track_splitting_time_cutoff_minutes if cfg else 20

    @property
    def total(self) -> int:
        """Master playlists run until all configs are exhausted."""
        return -1

    def get_list(self) -> Optional[Playlist]:
        cfg = self.current_playback_config
        return cfg.get_list() if cfg else None

    def upcoming_grouping(self) -> Optional[str]:
        cfg = self.current_playback_config
        return cfg.upcoming_grouping() if cfg else None

    def split_track(self, track: MediaTrack, do_split_override: bool = True,
                    offset: int = 1) -> MediaTrack:
        cfg = self.current_playback_config
        if cfg:
            return cfg.split_track(track, do_split_override, offset)
        raise Exception("No current configuration available")

    def maximum_plays(self) -> int:
        return 1

    def length(self) -> int:
        return sum(c.length() for c in self.playback_configs)

    def remaining_count(self) -> int:
        return sum(c.remaining_count() for c in self.playback_configs)

    def set_playing(self, playing: bool = True) -> None:
        self.playing = playing

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        config_strs = [str(c) for c in self.playback_configs]
        weight_strs = [str(w) for w in self.weights]
        active = sum(self._active_mask)
        return (
            f"PlaybackConfigMaster(configs=[{', '.join(config_strs)}], "
            f"weights=[{', '.join(weight_strs)}], active={active}/{len(self.playback_configs)})"
        )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, PlaybackConfigMaster):
            return False
        return (self.playback_configs == other.playback_configs
                and self.weights == other.weights)

    def __hash__(self) -> int:
        return hash((tuple(self.playback_configs), tuple(self.weights)))

    def __deepcopy__(self, memo: Dict[int, Any]) -> 'PlaybackConfigMaster':
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        for k, v in self.__dict__.items():
            if k != "playback_configs":
                setattr(result, k, deepcopy(v, memo))
        return result
