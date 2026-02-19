from copy import deepcopy
from types import SimpleNamespace
from typing import Dict, List, Optional, Any, TYPE_CHECKING

from library_data.media_track import MediaTrack
from muse.playlist import Playlist
from muse.playlist_descriptor import PlaylistDescriptor
from utils.globals import PlaylistSortType, TrackResult
from utils.logging_setup import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from library_data.library_data import LibraryData
    from library_data.library_data_callbacks import LibraryDataCallbacks


class PlaybackConfig:
    open_configs: List['PlaybackConfig'] = []

    @staticmethod
    def get_playing_config() -> Optional['PlaybackConfig']:
        for _config in PlaybackConfig.open_configs:
            if _config.playing:
                return _config
        return None

    @staticmethod
    def get_playing_track() -> Optional[MediaTrack]:
        playing_config = PlaybackConfig.get_playing_config()
        if not playing_config:
            return None
        return playing_config.current_track()

    @staticmethod
    def new_playback_config(override_dir: Optional[str] = None, 
                          data_callbacks: Optional['LibraryDataCallbacks'] = None) -> 'PlaybackConfig':
        return PlaybackConfig(override_dir=override_dir, data_callbacks=data_callbacks)

    @staticmethod
    def from_playlist_descriptor(playlist_descriptor: 'PlaylistDescriptor',
                            data_callbacks: 'LibraryDataCallbacks',
                            library_data: Optional['LibraryData'] = None,
                            **playback_overrides: Any) -> 'PlaybackConfig':
        """Create a PlaybackConfig from a PlaylistDescriptor definition.

        For search-based and track-based playlists the track list is resolved
        eagerly and passed as ``explicit_tracks``.  Directory-based playlists
        fall through to the standard directory-loading path in ``get_list()``.

        Args:
            playlist_descriptor: The playlist definition to build from.
            data_callbacks: LibraryDataCallbacks for Playlist construction.
            library_data: Required for search-based playlists so the query can
                be executed against the current library.
            **playback_overrides: Optional overrides for playback settings
                (``enable_dynamic_volume``, ``enable_long_track_splitting``,
                ``long_track_splitting_time_cutoff_minutes``).
        """
        explicit: Optional[List[str]] = None

        if playlist_descriptor.is_search_based():
            if library_data is None:
                raise ValueError(
                    f"library_data is required for search-based playlist "
                    f"'{playlist_descriptor.name}'"
                )
            explicit = playlist_descriptor.resolve_tracks(library_data)
        elif playlist_descriptor.is_track_based():
            explicit = playlist_descriptor.resolve_tracks(library_data)
        # Directory-based: explicit stays None, directories are set below.

        args = SimpleNamespace(
            playlist_sort_type=playlist_descriptor.sort_type,
            directories=playlist_descriptor.source_directories or [],
            total=-1,
            overwrite=False,
            enable_dynamic_volume=playback_overrides.get(
                'enable_dynamic_volume', True
            ),
            enable_long_track_splitting=playback_overrides.get(
                'enable_long_track_splitting', False
            ),
            long_track_splitting_time_cutoff_minutes=playback_overrides.get(
                'long_track_splitting_time_cutoff_minutes', 20
            ),
            check_entire_playlist=False,
            track=None,
        )

        pc = PlaybackConfig(
            args=args,
            data_callbacks=data_callbacks,
            explicit_tracks=explicit,
        )
        pc.playlist_descriptor = playlist_descriptor
        pc.loop = playlist_descriptor.loop
        pc.skip_memory_shuffle = playlist_descriptor.is_reshuffle_redundant()
        return pc

    def __init__(self, args: Optional[Any] = None, override_dir: Optional[str] = None,
                 data_callbacks: Optional['LibraryDataCallbacks'] = None,
                 explicit_tracks: Optional[List[str]] = None) -> None:
        self.total: int = int(args.total) if args else -1
        self.type: PlaylistSortType = args.playlist_sort_type if args else PlaylistSortType.RANDOM
        self.directories: List[str] = args.directories if args else ([override_dir] if override_dir else [])
        self.overwrite: bool = args.overwrite if args else False
        self.enable_dynamic_volume: bool = args.enable_dynamic_volume if args else True
        self.enable_long_track_splitting: bool = args.enable_long_track_splitting if args else False
        self.long_track_splitting_time_cutoff_minutes: int = args.long_track_splitting_time_cutoff_minutes if args else 20
        self.long_track_splitting_play_all: bool = False
        self.data_callbacks: Optional['LibraryDataCallbacks'] = data_callbacks
        self.check_entire_playlist: bool = args.check_entire_playlist if args else False
        self.list: Playlist = Playlist(data_callbacks=self.data_callbacks, check_entire_playlist=self.check_entire_playlist)
        self.start_track: Optional[str] = args.track if args else None
        self.playing: bool = False
        self._explicit_tracks: Optional[List[str]] = explicit_tracks
        self.loop: bool = False
        self.skip_memory_shuffle: bool = False
        self.playlist_descriptor: Optional[PlaylistDescriptor] = None
        PlaybackConfig.open_configs.append(self)

    def maximum_plays(self) -> int:
        return 1

    def length(self) -> int:
        return self.get_list().size()
    
    def remaining_count(self) -> int:
        return self.get_list().remaining_count()

    def get_playlist_descriptor(self) -> PlaylistDescriptor:
        return self.playlist_descriptor

    def get_list(self) -> Playlist:
        if self.list.is_valid():
            return self.list
        if self._explicit_tracks is not None:
            track_list = self._explicit_tracks
        else:
            track_list = self.data_callbacks.get_all_filepaths(self.directories, self.overwrite)
        self.list = Playlist(track_list, self.type, data_callbacks=self.data_callbacks,
                             start_track=self.start_track,
                             check_entire_playlist=self.check_entire_playlist,
                             loop=self.loop,
                             skip_memory_shuffle=self.skip_memory_shuffle)
        return self.list

    def set_playing(self, playing: bool = True) -> None:
        self.playing = playing

    def next_track(self, skip_grouping: bool = False, places_from_current: int = 0) -> TrackResult:
        self.set_playing()
        return self.get_list().next_track(skip_grouping=skip_grouping, places_from_current=places_from_current)

    def upcoming_track(self, places_from_current: int = 1) -> TrackResult:
        return self.get_list().upcoming_track(places_from_current=places_from_current)

    def current_track(self) -> Optional[MediaTrack]:
        return self.get_list().current_track()

    def upcoming_grouping(self):
        """Get the next grouping that will be encountered in the playlist.
        
        Returns:
            str or None: The name of the next grouping, or None if no grouping change found
        """
        l = self.get_list()
        return l.get_next_grouping()

    def split_track(self, track: MediaTrack, do_split_override: bool = True, offset: int = 1) -> MediaTrack:
        self.get_list().print_upcoming("split_track before")
        tracks = track.extract_non_silent_track_parts(select_random_track_part=not self.long_track_splitting_play_all)
        if len(tracks) == 0:
            # Track split failed for some reason, skip to the next track
            raise Exception("Track split failed")
        if do_split_override:
            self.get_list().insert_upcoming_tracks(tracks, offset=offset)
            logger.info(f"Assigned split track overrides: {tracks}")
        self.get_list().print_upcoming("split_track after")
        return tracks[0]

    def __str__(self) -> str:
        base = "PlaybackConfig(type=" + str(self.type) + ", directories=" + str(len(self.directories))
        if self.playlist_descriptor is not None:
            base += ", playlist_descriptor=" + self.playlist_descriptor.name
        return base + ")"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, PlaybackConfig):
            return False

        return self.type == other.type and self.directories == other.directories \
            and self.overwrite == other.overwrite and self.enable_dynamic_volume == other.enable_dynamic_volume \
            and self.enable_long_track_splitting == other.enable_long_track_splitting \
            and self.long_track_splitting_time_cutoff_minutes == other.long_track_splitting_time_cutoff_minutes \
            and self.long_track_splitting_play_all == other.long_track_splitting_play_all \
            and self.start_track == other.start_track \
            and self.check_entire_playlist == other.check_entire_playlist

    def __hash__(self) -> int:
        return hash((self.type, tuple(self.directories), self.overwrite, self.enable_dynamic_volume,
                     self.enable_long_track_splitting, self.long_track_splitting_time_cutoff_minutes,
                     self.long_track_splitting_play_all, self.start_track, self.check_entire_playlist))

    def __deepcopy__(self, memo: Dict[int, Any]) -> 'PlaybackConfig':
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        for k, v in self.__dict__.items():
            if not k == "data_callbacks" and not k == "list":
                setattr(result, k, deepcopy(v, memo))
        return result

