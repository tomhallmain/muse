# Feature Spec: Combined / Interspersed Playlists

**Branch:** `combine-playlists`
**Status:** Design / Pre-implementation
**Date:** 2026-02-16

---

## 1. Motivation

The application currently treats the user's entire music library as a single pool of tracks. The only playback axis is *sort type* (random, sequence, album shuffle, artist shuffle, etc.) applied to all files in one or more directories. There is no way to:

- Define a **named, reusable subset** of tracks (a "playlist").
- **Combine multiple playlists** with different sort strategies and interleave their playback.
- Weight the interleaving so that, e.g., 2 music tracks play for every 1 audiobook chapter.

**Primary use case:** Listen to an audiobook in sequence while interspersing music tracks between chapters (or groups of chapters).

**Secondary use cases:**
- Mix classical music (composer shuffle) with jazz (artist shuffle).
- Alternate between study material (sequence) and ambient music (random).
- Any N-playlist combination with per-playlist weights.

---

## 2. Definitions

| Term | Meaning |
|------|---------|
| **Named Playlist** | A persistent, user-defined set of *instructions* for producing a track list. May be defined as: (a) an explicit list of track filepaths, (b) a directory filter, or (c) a **search query** (`LibraryDataSearch`) that is resolved against the current library at runtime. A playlist is not necessarily a static list of tracks -- it is a recipe. |
| **Playback Config** | Runtime wrapper around a Named Playlist that adds playback settings (dynamic volume, track splitting, etc.). Already exists as `PlaybackConfig`. |
| **Master Playlist** | An ordered list of Playback Configs with per-config **weights** that define the interleaving pattern. Already partially exists as `PlaybackConfigMaster`. |
| **Weight** | An integer specifying how many consecutive tracks to draw from a given config before advancing to the next config in the master sequence. |
| **Cycle** | One complete pass through all configs in the master sequence. After a cycle, the pattern repeats. |

---

## 3. Current State Assessment

### 3.1 What Already Exists

| Component | Status | Notes |
|-----------|--------|-------|
| `Playlist` class (`muse/playlist.py`) | **Functional but library-scoped** | Accepts a list of filepaths + sort type. Sorting, grouping, memory-based shuffling all work. Can already be instantiated with an arbitrary track list. |
| `PlaybackConfig` (`muse/playback_config.py`) | **Functional** | Wraps one `Playlist`. Lazy-loads tracks via `data_callbacks.get_all_filepaths(directories)`. This is the key coupling point -- it assumes "all files in directories." |
| `PlaybackConfigMaster` (`muse/playback_config_master.py`) | **Partially implemented** | Has `playback_configs` list and `songs_per_config` list. Has `_precompute_sequence()` but the interleaving logic is incomplete (see Section 4.1). `next_track()` cycles through the sequence. |
| `PlaybackStateManager` (`muse/playback_state.py`) | **Functional** | Singleton tracking current `PlaybackConfig` and `PlaybackConfigMaster`. |
| `Run.run()` (`muse/run.py`) | **Has hook** | Lines 98-101 check for `PLAYLIST_CONFIG` strategy and swap in the master config from `PlaybackStateManager`. |
| `Playback` (`muse/playback.py`) | **Tightly coupled** | Calls `self._playback_config.next_track()`, `.upcoming_track()`, `.get_list()`, `.split_track()`, `.enable_long_track_splitting`, `.upcoming_grouping()`. These must all work on `PlaybackConfigMaster`. |
| `PlaybackMasterStrategy` (`utils/globals.py`) | **Defined** | `ALL_MUSIC` and `PLAYLIST_CONFIG` enum values exist. `PLAYLIST_CONFIG` is never actually activated by any working code path. |
| `MasterPlaylistWindow` (Tkinter + Qt) | **Scaffolded** | Both UI layers have windows for listing available playlists, adding to a master, creating new playlists. Qt version has a TODO noting it's not wired into the app menu. |
| `named_playlist_configs` persistence | **Basic** | Dict stored in `app_info_cache`. Format: `{name: {tracks: [...], sort_type: ..., config_type: ...}}`. |

### 3.2 What's Broken or Missing

1. **`PlaybackConfigMaster._precompute_sequence()` is wrong.** It iterates configs sequentially rather than interleaving. With configs A(weight=2) and B(weight=1), it produces `[A, A, B]` once then stops. It should produce a repeating cycle `[A, A, B, A, A, B, ...]` bounded by actual track availability.

2. **`PlaybackConfigMaster.next_track()` has no exhaustion handling.** When a playlist runs out of tracks, the method will fail. Need to handle: skip exhausted playlists, optionally loop them, or end playback.

3. **`PlaybackConfig.get_list()` only knows about directories.** It calls `data_callbacks.get_all_filepaths(self.directories, self.overwrite)` which gets ALL files from the specified directories. There is no code path for "use this explicit list of tracks."

4. **`Playback` accesses config attributes directly.** It reads `self._playback_config.enable_long_track_splitting`, `.long_track_splitting_time_cutoff_minutes`, `.total`, etc. `PlaybackConfigMaster` doesn't have these attributes; they live on individual `PlaybackConfig` instances.

5. **No formal Named Playlist data model.** The persistence format in `app_info_cache` is ad-hoc dicts. No validation, no schema, no migration path.

6. **No UI path to activate `PLAYLIST_CONFIG` strategy.** The combo box in the main app window shows `PlaybackMasterStrategy` options, but selecting `PLAYLIST_CONFIG` doesn't open a playlist management window or set up a `PlaybackConfigMaster`.

7. **`PlaybackConfigMaster` duplicates static state from `PlaybackConfig`.** Both classes have `OPEN_CONFIGS`, `READY_FOR_EXTENSION`, `LAST_EXTENSION_PLAYED`, and `assign_extension()`. This will conflict.

---

## 4. Architecture Strategy

### 4.1 Layer Diagram

```
┌──────────────────────────────────────────────────────────────┐
│  UI Layer (Tkinter first, Qt port later)                     │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  SearchWindow ──"Create Playlist from Search"──┐       │  │
│  │  (existing search + "Add to Playlist" buttons) │       │  │
│  └────────────────────────────────────────────────┼───────┘  │
│  ┌────────────────────────────────────────────────▼───────┐  │
│  │  MasterPlaylistWindow  ←→  NewPlaylistWindow           │  │
│  │  (create / edit / combine / reorder named playlists)   │  │
│  └───────────────────────┬────────────────────────────────┘  │
│                          │ activates                          │
│  ┌───────────────────────▼────────────────────────────────┐  │
│  │  Main Window: PlaybackMasterStrategy selector          │  │
│  │  ALL_MUSIC ←→ PLAYLIST_CONFIG                          │  │
│  │  (auto-opens MasterPlaylistWindow if no config set)    │  │
│  └───────────────────────┬────────────────────────────────┘  │
├──────────────────────────┼────────────────────────────────────┤
│  Orchestration Layer     │ (unified code path)                │
│  ┌───────────────────────▼────────────────────────────────┐  │
│  │  Run  →  ALWAYS creates PlaybackConfigMaster           │  │
│  │       →  ALL_MUSIC = single-config master (weight=1)   │  │
│  │       →  PLAYLIST_CONFIG = multi-config master         │  │
│  │       →  passes to Playback                            │  │
│  └───────────────────────┬────────────────────────────────┘  │
│  ┌───────────────────────▼────────────────────────────────┐  │
│  │  Playback  (main playback loop)                        │  │
│  │  calls _playback_config.next_track()                   │  │
│  │  (identical interface for single or multi config)      │  │
│  └───────────────────────┬────────────────────────────────┘  │
├──────────────────────────┼────────────────────────────────────┤
│  Config / Interleaving   │                                    │
│  ┌───────────────────────▼────────────────────────────────┐  │
│  │  PlaybackConfigMaster                                  │  │
│  │  - playback_configs: List[PlaybackConfig]              │  │
│  │  - weights: List[int]                                  │  │
│  │  - cursor-based weighted round-robin                   │  │
│  │  - next_track() → delegates to current config          │  │
│  │  - property proxies for Playback compatibility         │  │
│  └───────────────────────┬────────────────────────────────┘  │
│  ┌───────────────────────▼────────────────────────────────┐  │
│  │  PlaybackConfig  (per-playlist runtime config)         │  │
│  │  - explicit_tracks OR directory list (dual-mode)       │  │
│  │  - Playback settings (volume, splitting, etc.)         │  │
│  │  - Lazy-loaded Playlist instance                       │  │
│  │  - from_named_playlist() factory (resolves search      │  │
│  │    queries at construction time)                       │  │
│  └───────────────────────┬────────────────────────────────┘  │
├──────────────────────────┼────────────────────────────────────┤
│  Playlist Engine         │                                    │
│  ┌───────────────────────▼────────────────────────────────┐  │
│  │  Playlist                                              │  │
│  │  - sorted_tracks: List[MediaTrack]                     │  │
│  │  - sort(), next_track(), upcoming_track()              │  │
│  │  - loop flag + _reset_for_loop()                       │  │
│  │  - skip_memory_shuffle for small/curated playlists     │  │
│  │  - Memory-based shuffle, grouping logic (unchanged)    │  │
│  └────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────┤
│  Data Layer                                                   │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  NamedPlaylist (new dataclass)                         │  │
│  │  - search_query mode (LibraryDataSearch definition)    │  │
│  │  - directory mode                                      │  │
│  │  - explicit tracks mode                                │  │
│  │  - resolve_tracks(library_data) → List[str]            │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  NamedPlaylistStore (new)                              │  │
│  │  - CRUD for named playlists                            │  │
│  │  - Persisted in app_info_cache                         │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  LibraryData / LibraryDataCallbacks                    │  │
│  │  - get_all_filepaths(), get_track(), do_search()       │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 Design Principles

1. **`Playlist` gains loop and lightweight flags, but core logic is unchanged.** It
   already accepts an arbitrary list of filepaths. The changes are a `loop` flag for
   repeat-when-exhausted behavior and a `skip_memory_shuffle` flag for small curated
   playlists. No subclassing -- both flags are conditional branches in the same class.

2. **`PlaybackConfig` gains a dual-mode track source.** Either directory-based (current
   behavior for `ALL_MUSIC`) or explicit-track-list-based (for `PLAYLIST_CONFIG`). This
   is the minimal change to support named playlists without refactoring the entire class.

3. **`PlaybackConfigMaster` becomes a proper interleaving engine.** It owns the cursor
   state and delegates to individual `PlaybackConfig` instances. It must present the same
   interface as `PlaybackConfig` to `Playback` (duck-typing or shared protocol).

4. **A playlist is a recipe, not a resolved list.** `NamedPlaylist` stores *instructions*
   (a search query, a directory path, or an explicit track list) rather than always
   storing resolved filepaths. Search-based playlists re-resolve against the current
   library at load time, which avoids staleness and aligns with the existing saved
   searches UX in `SearchWindow`.

5. **Unified code path.** Both `ALL_MUSIC` and `PLAYLIST_CONFIG` flow through
   `PlaybackConfigMaster`. This eliminates branching in `Run` and `Playback`.

6. **Tkinter first, Qt later.** UI development targets `ui/` and `app.py`. The
   Qt/PySide6 port happens after the Tkinter version is finalized.

---

## 5. Detailed Design

### 5.1 Named Playlist Data Model

A playlist is not simply a list of tracks. It is a **set of instructions** for producing
a track list from any given library. This has several advantages:

- **Avoids staleness**: A search-query-based playlist re-resolves against the current
  library each time it is loaded. Files that have been deleted won't appear; newly added
  files that match the query will.
- **Portability**: The instructions are library-agnostic in the search-query case.
- **Alignment with existing UX**: The `SearchWindow` already has "saved searches"
  (`LibraryDataSearch` objects persisted via `app_info_cache`). A search-based playlist
  is conceptually a saved search that has been promoted to playlist status.

A `NamedPlaylist` supports three track source modes:

| Mode | Description | When to use |
|------|-------------|-------------|
| **Search query** | Stores a `LibraryDataSearch` definition (field values, not resolved results). Resolved at runtime via `LibraryData.do_search()`. | Most playlists created through the search window. Recommended default. |
| **Directory** | Stores one or more directory paths. All media files in those directories become the track list. | "Play everything in my Audiobooks folder." |
| **Explicit tracks** | Stores an ordered list of filepaths. | Hand-curated playlists, or when a search result set has been manually reordered. |

```python
@dataclass
class NamedPlaylist:
    """Persistent definition of a user-created playlist.

    A playlist is a set of instructions for producing a track list, not
    necessarily a resolved list of tracks.  It supports three source modes:
    search query, directory, and explicit tracks.
    """
    name: str

    # Track source -- exactly one of these should be populated:
    search_query: Optional[dict] = None            # LibraryDataSearch.to_json() form
    source_directories: Optional[List[str]] = None # Directory-based
    track_filepaths: Optional[List[str]] = None    # Explicit track list (ordered)

    # Sorting
    sort_type: PlaylistSortType = PlaylistSortType.SEQUENCE

    # Playback behavior
    loop: bool = False  # Whether this playlist should loop when exhausted

    # Metadata (for display / management)
    created_at: Optional[str] = None
    description: Optional[str] = None

    def is_search_based(self) -> bool:
        return self.search_query is not None and len(self.search_query) > 0

    def is_directory_based(self) -> bool:
        return self.source_directories is not None and len(self.source_directories) > 0

    def is_track_based(self) -> bool:
        return self.track_filepaths is not None and len(self.track_filepaths) > 0

    def resolve_tracks(self, library_data) -> List[str]:
        """Resolve the playlist instructions into an ordered list of filepaths.

        For search-based playlists, runs the search against the current library.
        For directory-based, gets all files from the directories.
        For explicit-track, returns the stored list (with stale entries filtered).
        """
        ...

    def to_dict(self) -> dict:
        """Serialize for app_info_cache storage."""
        ...

    @staticmethod
    def from_dict(data: dict) -> 'NamedPlaylist':
        """Deserialize from app_info_cache storage."""
        ...
```

**Relationship to `LibraryDataSearch`:** A search-based `NamedPlaylist` stores the
*query definition* (the `to_json()` dict from `LibraryDataSearch`), not the resolved
results. At playlist load time, the query is re-executed via
`LibraryDataSearch.from_json()` + `LibraryData.do_search()`. This reuses the existing
search infrastructure and keeps playlists fresh.

**Storage:** `app_info_cache.set("named_playlists", {name: playlist.to_dict(), ...})`

This replaces the current ad-hoc `named_playlist_configs` format with a formal schema.

### 5.2 Named Playlist Store

```python
class NamedPlaylistStore:
    """CRUD operations for named playlists. Thin wrapper around app_info_cache."""

    @staticmethod
    def load_all() -> Dict[str, NamedPlaylist]: ...

    @staticmethod
    def save(playlist: NamedPlaylist) -> None: ...

    @staticmethod
    def delete(name: str) -> None: ...

    @staticmethod
    def get(name: str) -> Optional[NamedPlaylist]: ...

    @staticmethod
    def rename(old_name: str, new_name: str) -> None: ...
```

### 5.3 PlaybackConfig Changes

The key change is allowing `PlaybackConfig` to be initialized with an explicit track list instead of relying on directory-based loading.

```python
class PlaybackConfig:
    def __init__(self, args=None, override_dir=None, data_callbacks=None,
                 explicit_tracks=None):   # <-- NEW parameter
        # ... existing init ...
        self._explicit_tracks = explicit_tracks  # List[str] of filepaths, or None

    def get_list(self) -> Playlist:
        if self.list.is_valid():
            return self.list
        if self._explicit_tracks is not None:
            # Named playlist mode: use the explicit track list
            track_list = self._explicit_tracks
        else:
            # Directory mode: load all files from directories (existing behavior)
            track_list = self.data_callbacks.get_all_filepaths(
                self.directories, self.overwrite
            )
        self.list = Playlist(
            track_list, self.type,
            data_callbacks=self.data_callbacks,
            start_track=self.start_track,
            check_entire_playlist=self.check_entire_playlist,
        )
        return self.list
```

**Factory method** for creating from a `NamedPlaylist`:

```python
    @staticmethod
    def from_named_playlist(named_playlist: NamedPlaylist,
                            data_callbacks,
                            library_data=None,
                            **playback_overrides) -> 'PlaybackConfig':
        """Create a PlaybackConfig from a NamedPlaylist definition.

        For search-based playlists, library_data must be provided so the
        search query can be resolved at runtime.
        """
        # Resolve the track list from the playlist instructions
        if named_playlist.is_search_based():
            if library_data is None:
                raise ValueError("library_data required for search-based playlists")
            explicit = named_playlist.resolve_tracks(library_data)
        elif named_playlist.is_track_based():
            explicit = named_playlist.track_filepaths
        else:
            explicit = None  # Will fall through to directory-based loading

        args = SimpleNamespace(
            playlist_sort_type=named_playlist.sort_type,
            directories=named_playlist.source_directories or [],
            total=-1,
            overwrite=False,
            enable_dynamic_volume=playback_overrides.get('enable_dynamic_volume', True),
            enable_long_track_splitting=playback_overrides.get('enable_long_track_splitting', False),
            long_track_splitting_time_cutoff_minutes=playback_overrides.get('long_track_splitting_time_cutoff_minutes', 20),
            check_entire_playlist=False,
            track=None,
        )
        return PlaybackConfig(args=args, data_callbacks=data_callbacks, explicit_tracks=explicit)
```

### 5.4 PlaybackConfigMaster Rewrite

This is the most critical change. The current implementation has fundamental issues with its interleaving logic and interface compatibility with `Playback`.

#### 5.4.1 Interleaving Algorithm

The interleaving should work as a **weighted round-robin with exhaustion handling**:

```
Given:  configs = [A, B, C]
        weights = [2, 1, 3]

Cycle:  A, A, B, C, C, C, A, A, B, C, C, C, ...

When A is exhausted:
        B, C, C, C, B, C, C, C, ...

When all are exhausted:
        Playback ends (or optionally loop from start).
```

#### 5.4.2 Revised Class

```python
class PlaybackConfigMaster:
    def __init__(self, playback_configs=None, weights=None):
        self.playback_configs: List[PlaybackConfig] = playback_configs or []
        self.weights: List[int] = weights or [1] * len(self.playback_configs)
        # Validate
        assert len(self.weights) == len(self.playback_configs)

        # Interleaving state
        self._config_cursor: int = 0          # Which config we're currently drawing from
        self._weight_counter: int = 0         # How many tracks drawn from current config in this slot
        self._active_mask: List[bool] = [True] * len(self.playback_configs)  # Track which configs still have tracks

        # Playback state
        self.playing: bool = False
        self.played_tracks: List[MediaTrack] = []
        self.next_track_override = None

    def _advance_cursor(self):
        """Move to the next active config in the round-robin."""
        if not any(self._active_mask):
            return False  # All exhausted
        start = self._config_cursor
        while True:
            self._config_cursor = (self._config_cursor + 1) % len(self.playback_configs)
            self._weight_counter = 0
            if self._active_mask[self._config_cursor]:
                return True
            if self._config_cursor == start:
                return False  # Wrapped around, all exhausted

    def next_track(self, skip_grouping=False, places_from_current=0):
        """Get the next track using weighted round-robin interleaving."""
        self.playing = True

        # Handle override
        if self.next_track_override is not None:
            track = self.next_track_override
            self.next_track_override = None
            return track, None, None

        if not any(self._active_mask):
            return None, None, None  # All playlists exhausted

        # Get track from current config
        config = self.playback_configs[self._config_cursor]
        track, old_grouping, new_grouping = config.next_track(
            skip_grouping=skip_grouping,
            places_from_current=places_from_current,
        )

        if track is None:
            # Current config exhausted
            self._active_mask[self._config_cursor] = False
            if self._advance_cursor():
                return self.next_track(skip_grouping, places_from_current)  # Recurse to next config
            return None, None, None  # All exhausted

        self._weight_counter += 1
        self.played_tracks.append(track)

        # Check if we've drawn enough from this config
        if self._weight_counter >= self.weights[self._config_cursor]:
            self._advance_cursor()

        return track, old_grouping, new_grouping

    # --- Interface compatibility with Playback ---

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
        return -1  # Master playlists run until exhaustion

    def get_list(self) -> Playlist:
        cfg = self.current_playback_config
        return cfg.get_list() if cfg else None

    def upcoming_track(self, places_from_current=1):
        """Peek at the next track without advancing state."""
        # Determine which config would be next
        cfg = self._peek_next_config()
        if cfg is None:
            return None, None, None
        return cfg.upcoming_track(places_from_current=places_from_current)

    def upcoming_grouping(self):
        cfg = self.current_playback_config
        return cfg.upcoming_grouping() if cfg else None

    def split_track(self, track, do_split_override=True, offset=1):
        cfg = self.current_playback_config
        if cfg:
            return cfg.split_track(track, do_split_override, offset)
        raise Exception("No current configuration available")

    def current_track(self):
        cfg = self.current_playback_config
        return cfg.current_track() if cfg else None
```

#### 5.4.3 Key Design Decisions

**Q: Should exhausted playlists loop?**
A: Configurable per-playlist via `NamedPlaylist.loop` / `Playlist.loop`. Default: **no loop** (play through once). The audiobook use case explicitly does NOT want looping for the audiobook playlist, but might want looping for the music playlist. The `loop` flag is set per `NamedPlaylist` and propagated to `Playlist` at construction time.

**Q: What happens when the interleaving cursor advances but the upcoming config is also exhausted?**
A: Skip to the next active config. If all configs are exhausted, return `None` to signal end of playback. `Playback` already handles a `None` return from `get_track()` by exiting the playback loop.

**Q: What happens when ALL playlists are exhausted?**
A: **Playback stops.** This is the default behavior. See "Out of Scope" (Section 10) for a future option to fall back to a "smart continuation" playlist.

**Q: How does `Playback.get_track()` need to change?**
A: Minimally. `Playback` already calls `self._playback_config.next_track()` which returns `(track, old_grouping, new_grouping)`. As long as `PlaybackConfigMaster` provides this interface (which it does), `Playback` works unchanged. The attribute accesses (`enable_long_track_splitting`, etc.) are handled by properties on `PlaybackConfigMaster` that delegate to the current config.

### 5.5 TrackResult Enrichment for Multi-Playlist Context

#### 5.5.1 Motivation

`TrackResult` currently carries `(track, old_grouping, new_grouping)`. These grouping
fields are always produced by a single `Playlist` instance and describe transitions
*within* that playlist's sort order (e.g., switching from one composer to another in a
`COMPOSER_SHUFFLE` playlist). Because `PlaybackConfigMaster.next_track()` passes the
child config's `TrackResult` through unchanged, grouping values are never mixed across
configs -- the grouping fields remain coherent.

However, `Playback` and the DJ layer currently have no visibility into which config
produced a given track, or whether the interleaving cursor just switched configs. This
matters for two reasons:

1. **Suppressing misleading grouping remarks at config boundaries.** When the cursor
   moves from config A (music, `COMPOSER_SHUFFLE`) to config B (audiobook,
   `SEQUENCE`), the DJ sees `old_grouping=None, new_grouping=None` from the audiobook
   side -- harmless today. But if both configs use grouping sort types with
   overlapping attribute names (e.g., two music playlists sorted by different
   groupings), the DJ could see a grouping "change" that is really just a config
   switch. The DJ needs a signal to distinguish the two.

2. **Context-aware transitions (future).** For the DJ to make remarks like "Now let's
   continue with our audiobook" or "Back to the jazz playlist," it needs to know the
   full scope of what is being presented: which configs exist, which one is active,
   and when a switch just happened. This is the foundation for the context-aware
   transition work noted in Section 10.

#### 5.5.2 Recommended Approach

Enrich `TrackResult` with metadata that lets downstream consumers (primarily
`MuseSpotProfile` and `Playback`) identify config boundaries and, eventually,
describe transitions to the listener:

```python
class TrackResult(NamedTuple):
    track: Optional[Any] = None
    old_grouping: Optional[str] = None
    new_grouping: Optional[str] = None
    config_index: Optional[int] = None       # Index of the config that produced this track
    config_changed: bool = False              # True when this track came from a different config than the previous one
```

Because `NamedTuple` fields with defaults are append-only, adding new fields at the
end preserves full backward compatibility -- existing `(track, old_grouping,
new_grouping)` destructuring continues to work, and code that doesn't know about the
new fields simply ignores them.

#### 5.5.3 Producer Side (PlaybackConfigMaster)

`PlaybackConfigMaster.next_track()` is the natural place to populate the new fields.
It already knows `_config_cursor` and can compare to the previous cursor value:

```python
def next_track(self, ...):
    prev_cursor = self._config_cursor
    # ... interleaving logic, get result from child config ...
    return TrackResult(
        track=result.track,
        old_grouping=result.old_grouping,
        new_grouping=result.new_grouping,
        config_index=self._config_cursor,
        config_changed=(self._config_cursor != prev_cursor),
    )
```

When only a single config is present (the `ALL_MUSIC` case), `config_changed` is
always `False` and the behavior is identical to today.

#### 5.5.4 Consumer Side

**v1 (Phase 4):** Suppress grouping speech at config boundaries as a safe default.

**`Playback.prepare_muse()`** -- When constructing the `TrackResult` passed to
`get_spot_profile`, propagate the config metadata from `self._track_result`.

**`MuseSpotProfile.__init__()`** -- When `config_changed` is `True`, suppress
grouping-related speech (`speak_about_prior_group`, `speak_about_upcoming_group`):

```python
if track_result.config_changed:
    self.speak_about_prior_group = False
    self.speak_about_upcoming_group = False
```

**Caveat -- equal-weight interleaving:** In a weight=1 scenario (A, B, A, B, ...),
*every* track is a config boundary, so `config_changed` is always `True` and this
guard suppresses *all* grouping speech. This is acceptable for v1 -- grouping remarks
in that pattern would be disjointed anyway since the DJ only sees one config's
groupings at a time. For weights > 1 (e.g., A, A, B), the second consecutive A-track
has `config_changed=False` and grouping speech works normally within that run. The
exact tuning of this behavior will become clearer once multi-config playback is
testable end-to-end.

**Future (context-aware DJ):** Once `config_index` and `config_changed` are flowing
through the system, the DJ can be extended to:
- Announce playlist transitions ("Now back to our audiobook...")
- Reference the overall listening session structure
- Tailor remarks based on the *type* of content in the active config

This requires additional context beyond `config_index` (e.g., the `NamedPlaylist`
name or description), which can be attached to `PlaybackConfig` and surfaced through
`PlaybackConfigMaster.current_playback_config`. The `TrackResult` fields provide the
trigger; the richer context lives on the config objects.

#### 5.5.5 Implementation Status

The `TrackResult` fields (`config_index`, `config_changed`) and the consumer-side
guard in `MuseSpotProfile` are implemented. The context-aware DJ transitions are
explicitly out of scope for v1 (see Section 10) but the `TrackResult` enrichment
lays the groundwork.

### 5.6 Run Integration (Unified Code Path)

Both `ALL_MUSIC` and `PLAYLIST_CONFIG` strategies flow through `PlaybackConfigMaster`.
This unifies the run/play code path: `ALL_MUSIC` is simply a master with a single
config and weight=1.

```python
# In Run.do_workflow():
def do_workflow(self) -> None:
    if self.args.playback_master_strategy == PlaybackMasterStrategy.PLAYLIST_CONFIG:
        # Use the master config set by the playlist UI
        master_config = PlaybackStateManager.get_current_master_config()
        if master_config and master_config.playback_configs:
            playback_config = master_config
        else:
            raise ValueError("PLAYLIST_CONFIG strategy selected but no master config set")
    else:
        # ALL_MUSIC: wrap in a single-config master for unified code path
        playback_config = PlaybackConfigMaster(
            playback_configs=[PlaybackConfig(args=self.args, data_callbacks=self.library_data.data_callbacks)]
        )

    self._playback = Playback(playback_config, self.app_actions, self)
    self.last_config = None
    try:
        self.run(playback_config)
    except KeyboardInterrupt:
        pass
```

The existing hook in `Run.run()` (lines 98-101) can be simplified since `do_workflow()` now handles the strategy check upfront. The `PLAYLIST_CONFIG` branch in `Run.run()` becomes redundant and should be removed to avoid double-wrapping.

### 5.7 Playlist Class Changes

**What stays the same:**
- `Playlist.__init__(tracks, _type, data_callbacks, ...)` -- already accepts an arbitrary track list
- `sort()`, `next_track()`, `upcoming_track()`, `current_track()` -- all work on `self.sorted_tracks`
- `update_recently_played_lists()` -- still works per-track

**What changes:**

#### 5.7.1 Loop Flag

Add a `loop: bool = False` parameter to `Playlist.__init__`. When `loop=True` and
`next_track()` would return `None` (playlist exhausted), the playlist resets its
cursor to the beginning and optionally re-shuffles:

```python
def next_track(self, skip_grouping=False, places_from_current=0):
    # ... existing logic ...
    if track is None and self.loop:
        self._reset_for_loop()
        return self.next_track(skip_grouping, places_from_current)
    return track, old_grouping, new_grouping

def _reset_for_loop(self):
    """Reset playlist state for looping. Re-shuffles if not SEQUENCE."""
    self.current_track_index = -1
    self.pending_tracks = list(self.in_sequence)
    self.played_tracks.clear()
    if self.sort_type != PlaylistSortType.SEQUENCE:
        self.sort()
```

The `loop` flag is propagated from `NamedPlaylist.loop` through `PlaybackConfig`.

#### 5.7.2 Lightweight Mode for Small / Curated Playlists

Small curated playlists (e.g., 10 audiobook chapters) should not run through the
memory-based shuffling logic. The existing `MIN_PLAYLIST_SIZE = 200` guard in
`shuffle_with_memory_for_attr()` already skips shuffling for small playlists, so
this is largely handled.

To make this explicit and avoid unnecessary overhead, add a `skip_memory_shuffle`
parameter:

```python
def __init__(self, tracks=[], _type=PlaylistSortType.SEQUENCE,
             data_callbacks=None, start_track=None,
             check_entire_playlist=False,
             loop=False,                    # NEW
             skip_memory_shuffle=False):    # NEW
    # ... existing init ...
    self.loop = loop
    self._skip_memory_shuffle = skip_memory_shuffle
```

In `sort()`, check `self._skip_memory_shuffle` before calling
`shuffle_with_memory_for_attr()`. This keeps the `Playlist` class unified -- no
subclass needed. The full-featured memory shuffle path and the lightweight path
coexist as conditional branches within the same class.

**Why the Playlist class is the "hardest part" (and why it's actually OK):**
The `Playlist` class was built for whole-library sorting. However, `Playlist.__init__`
is already generic -- it takes a `List[str]` of filepaths. The library-specific
behavior is in:
1. `PlaybackConfig.get_list()` which calls `get_all_filepaths(directories)` -- this is the coupling point, and we fix it with `explicit_tracks`.
2. `Playlist.sort()` memory-based shuffling which checks `recently_played_*` lists -- this is harmless for small playlists (the `MIN_PLAYLIST_SIZE = 200` check already skips shuffling for small lists, and `skip_memory_shuffle` makes it explicit).
3. Grouping logic -- irrelevant for SEQUENCE-sorted playlists (audiobook chapters).

The real work is in `PlaybackConfig` (dual-mode track source) and `PlaybackConfigMaster` (interleaving engine).

---

## 6. Implementation Plan

> **UI strategy:** Tkinter first. The Qt/PySide6 UI will be ported once the Tkinter
> version is finalized and proven. Phase 3 targets `ui/` and `app.py` only.

### Phase 1: Foundation (Named Playlist Data Model + Storage) -- COMPLETE

| # | Task | Files | Complexity | Status |
|---|------|-------|------------|--------|
| 1.1 | Create `NamedPlaylist` dataclass with search-query, directory, and explicit-track modes | `muse/named_playlist.py` (new) | Low | **Done** |
| 1.2 | Create `NamedPlaylistStore` (CRUD wrapper around `app_info_cache`) | `muse/named_playlist.py` | Low | **Done** |
| 1.3 | Implement `NamedPlaylist.resolve_tracks()` for all three source modes (with retry logic for sleeping external drives via `Utils.isfile_with_retry` / `Utils.isdir_with_retry`) | `muse/named_playlist.py` | Medium | **Done** |
| 1.4 | ~~Migrate existing `named_playlist_configs` format to new schema~~ | `muse/named_playlist.py` | Low | **Cancelled** -- no legacy data exists |

### Phase 2: Backend Core (Playlist + PlaybackConfig + PlaybackConfigMaster) -- COMPLETE

| # | Task | Files | Complexity | Status |
|---|------|-------|------------|--------|
| 2.1 | Add `loop` and `skip_memory_shuffle` params to `Playlist.__init__` | `muse/playlist.py` | Low | **Done** |
| 2.2 | Implement `Playlist.reset()` / `_reset_for_loop()` and loop-aware `next_track()` | `muse/playlist.py` | Medium | **Done** |
| 2.3 | Add `skip_memory_shuffle` guard in `Playlist.sort()` | `muse/playlist.py` | Low | **Done** |
| 2.4 | Add `explicit_tracks` param to `PlaybackConfig.__init__` | `muse/playback_config.py` | Low | **Done** |
| 2.5 | Update `PlaybackConfig.get_list()` for dual-mode (directory vs explicit); propagate `loop` and `skip_memory_shuffle` to `Playlist` constructor | `muse/playback_config.py` | Low | **Done** |
| 2.6 | Add `PlaybackConfig.from_named_playlist()` factory (handles search resolution) | `muse/playback_config.py` | Medium | **Done** |
| 2.7 | Rewrite `PlaybackConfigMaster` with cursor-based weighted round-robin interleaving | `muse/playback_config_master.py` | **High** | **Done** |
| 2.8 | Add property proxies on `PlaybackConfigMaster` for `Playback` compatibility | `muse/playback_config_master.py` | Medium | **Done** |
| 2.9 | Consolidate extension handling: remove `last_extension_played`, `ready_for_extension`, `assign_extension()`, `next_track_override`, `set_next_track_override()` from `PlaybackConfig`; keep solely on `PlaybackConfigMaster`. Add `get_playing_config()` and `get_playing_track()` on `PlaybackConfigMaster`. Update `extension_manager.py` to call `PlaybackConfigMaster`. Fix `reamining_count` typo on `PlaybackConfig`. | `muse/playback_config.py`, `muse/playback_config_master.py`, `extensions/extension_manager.py` | Medium | **Done** |
| 2.10 | Update `Run.do_workflow()` for unified code path (both strategies go through `PlaybackConfigMaster`) | `muse/run.py` | Low | **Done** |
| 2.11 | Remove redundant `PLAYLIST_CONFIG` check in `Run.run()`; rename `PlaybackStateManager` slots for clarity (`active_config` / `master_config`) | `muse/run.py`, `muse/playback_state.py` | Low | **Done** |

### Phase 3: UI -- Tkinter (Playlist Management Windows)

| # | Task | Files | Complexity |
|---|------|-------|------------|
| 3.1 | Wire `MasterPlaylistWindow` into Tkinter app menu; auto-open when `PLAYLIST_CONFIG` is selected with no master config | `app.py`, `ui/playlist_window.py` | Low |
| 3.2 | Refactor `NewPlaylistWindow` to use `NamedPlaylist` model | `ui/playlist_window.py` | Medium |
| 3.3 | Add "Add to Playlist" buttons in `SearchWindow` results (reuse or embed search functionality to add tracks to a named playlist from search results) | `ui/search_window.py`, `ui/playlist_window.py` | Medium |
| 3.4 | Add "Create Playlist from Search" action in `SearchWindow` (promotes a saved search to a search-based `NamedPlaylist`) | `ui/search_window.py` | Medium |
| 3.5 | Add track reordering UI in `NewPlaylistWindow` / playlist editor (move up/down buttons for SEQUENCE playlists) | `ui/playlist_window.py` | Medium |
| 3.6 | Add weight configuration UI to `MasterPlaylistWindow` (per-config weight spinbox) | `ui/playlist_window.py` | Low |
| 3.7 | Add loop toggle per-config in `MasterPlaylistWindow` | `ui/playlist_window.py` | Low |
| 3.8 | Add playlist preview (show interspersed track order) | `ui/playlist_window.py` | Medium |
| 3.9 | Activate `PLAYLIST_CONFIG` in main window when a master playlist is configured | `app.py` | Low |

### Phase 4: Polish + Edge Cases

| # | Task | Files | Complexity | Status |
|---|------|-------|------------|--------|
| 4.1 | Handle tracks that no longer exist on disk (for explicit-track playlists: filter on load, warn user) | `muse/named_playlist.py`, `muse/playback_config.py` | Low | **Done** (filtering in `_resolve_explicit_tracks()` with `isfile_with_retry`) |
| 4.2 | Enrich `TrackResult` with `config_index` / `config_changed` fields; suppress grouping speech at config boundaries (see Section 5.5) | `utils/globals.py`, `muse/playback_config_master.py`, `muse/muse_spot_profile.py`, `muse/playback.py`, `muse/muse.py`, `muse/muse_memory.py` | Medium | **Done** |
| 4.3 | Persist master playlist state for resume-on-restart | `muse/playback_config_master.py`, `muse/playback_state.py` | Medium | Pending |
| 4.4 | Unit tests for interleaving logic, loop behavior, and search-based resolution | `tests/` | Medium | Pending |

### Phase 5: Qt Port (Future)

| # | Task | Files | Complexity |
|---|------|-------|------------|
| 5.1 | Port finalized Tkinter `MasterPlaylistWindow` to PySide6 | `ui_qt/playlist_window.py` | Medium |
| 5.2 | Port finalized Tkinter `NewPlaylistWindow` to PySide6 | `ui_qt/playlist_window.py` | Medium |
| 5.3 | Wire Qt playlist window into `app_qt.py` menu | `app_qt.py` | Low |
| 5.4 | Port search integration (add-to-playlist buttons) to Qt `SearchWindow` | `ui_qt/search_window.py` | Medium |

---

## 7. Interleaving Examples

### Example 1: Audiobook + Music (1:1)

```
Playlist A (Music):     search_query={genre: "jazz"}  sort=RANDOM,  loop=False
Playlist B (Audiobook): directory="/audiobooks/lotr/"  sort=SEQUENCE, loop=False
Weights:                [1, 1]

Playback order: M1, Ch1, M2, Ch2, M3, Ch3, M4, Ch4, M5, M6, ...
                                                      ^^^^^^^^^^^^
                                           Audiobook exhausted, music continues
                ... M150, M151 → STOP (music also exhausted)
```

### Example 2: Audiobook + Music (2:1)

```
Playlist A (Music):     search_query={artist: "miles davis"}  sort=ARTIST_SHUFFLE, loop=True
Playlist B (Audiobook): tracks=[Ch1, Ch2, Ch3]                sort=SEQUENCE,       loop=False
Weights:                [2, 1]

Playback order: M1, M2, Ch1, M3, M4, Ch2, M5, M6, Ch3, M7, M8, M9, ...
                                                         ^^^^^^^^^^^^^^
                                              Audiobook exhausted, music continues (loops)
                This runs indefinitely because music playlist loops.
```

### Example 3: Music + Music (1:1, both loop)

```
Playlist A (Classical): search_query={composer: "bach"}  sort=COMPOSER_SHUFFLE, loop=True
Playlist B (Jazz):      search_query={genre: "jazz"}     sort=ARTIST_SHUFFLE,   loop=True
Weights:                [1, 1]

Playback order: C1, J1, C2, J2, C3, J1, C1, J2, C2, J1, ...
                                     ^^          ^^
                              Jazz loops    Classical loops
                This runs indefinitely because both playlists loop.
```

### Example 4: All playlists exhausted → stop

```
Playlist A: tracks=[T1, T2]   sort=SEQUENCE, loop=False
Playlist B: tracks=[T3, T4]   sort=SEQUENCE, loop=False
Weights:    [1, 1]

Playback order: T1, T3, T2, T4 → STOP (all exhausted, playback ends)
```

---

## 8. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| `Playback` accesses attributes not proxied by `PlaybackConfigMaster` | Runtime crash | Audit all attribute accesses in `Playback` and add proxies. Add integration test. |
| Memory-based shuffling thrashes for small named playlists | Poor track ordering | Already handled: `Playlist.shuffle_with_memory_for_attr()` skips playlists < 200 tracks. Made explicit with `skip_memory_shuffle` flag. |
| ~~Extension system (`assign_extension`) conflicts between `PlaybackConfig` and `PlaybackConfigMaster`~~ | ~~Extension tracks assigned to wrong config~~ | **Resolved (2.9):** Extension state (`last_extension_played`, `ready_for_extension`, `assign_extension()`, `next_track_override`) now lives solely on `PlaybackConfigMaster`. `PlaybackConfig` no longer has override handling. `extension_manager.py` updated to call `PlaybackConfigMaster.assign_extension()`. |
| Named playlist tracks become stale (files deleted/moved) | Crash on load or silent empty playlist | Search-based playlists avoid this entirely (re-resolved at runtime). For explicit-track playlists: validate filepaths on load, warn user, remove invalid entries. |
| DJ (Muse) generates context-inappropriate remarks when switching between audiobook and music | Confusing DJ output | **Deferred** (see Out of Scope, Section 10). For v1, ensure no runtime errors at config boundaries; accept that DJ context may be imperfect. |
| Search-based playlist resolution is slow for large libraries | Slow playlist startup | Search is already threaded. Show a loading indicator in the UI. Consider caching resolved results with a TTL. |

---

## 9. Resolved Design Decisions

1. **Track reordering within a named playlist:** Yes. For SEQUENCE playlists, the UI
   will provide move-up / move-down controls (or equivalent repositioning functionality)
   to allow manual ordering. This is important for audiobooks where file naming may not
   produce the correct chapter order.

2. **Weight model:** Simple per-config integer weights. Complex patterns (e.g.,
   "play 2 from A, then 1 from B, then 3 from A") are deferred to a future "advanced
   mode" pass.

3. **Unified run/play code path:** Yes. Both `ALL_MUSIC` and `PLAYLIST_CONFIG`
   strategies flow through `PlaybackConfigMaster`. `ALL_MUSIC` is a master with a
   single config and weight=1. This eliminates branching in `Run` and `Playback`.

4. **UI behavior when `PLAYLIST_CONFIG` selected with no playlists:**
   Open the `MasterPlaylistWindow` automatically.

5. **Track addition via search:** Users add tracks to a playlist through a search
   interface, either the existing `SearchWindow` instance or a similar embedded search
   panel in the playlist editor. The `SearchWindow` already shows "Add to playlist"
   button placeholders (line 686: `# TODO add to playlist buttons`). A search-based
   `NamedPlaylist` can also be created by promoting a saved search directly.

6. **UI framework order:** Tkinter first. The Qt/PySide6 port happens after the
   Tkinter version is finalized and working.

7. **Exhaustion behavior:** When all playlists in a master are exhausted, playback
   **stops** by default. See Section 10 for future continuation options.

8. **Playlist loop flag:** Implemented on `Playlist` class. Propagated from
   `NamedPlaylist.loop` through `PlaybackConfig`. Default: `False`.

9. **Lightweight playlist mode:** Implemented as a `skip_memory_shuffle` flag on
   `Playlist`, not a separate subclass. Keeps the class hierarchy flat.

---

## 10. Out of Scope (Future Work)

The following items are explicitly deferred from v1 and noted here for future passes:

| Item | Description |
|------|-------------|
| **Smart playlist criteria** | Filter-based playlist definitions (e.g., "all tracks by Bach longer than 5 minutes"). The search-query-based `NamedPlaylist` is a step toward this but does not cover duration filters, compound boolean logic, etc. |
| **Muse/DJ context-aware transitions** | The DJ may generate contextually inappropriate remarks when switching between audiobook and music configs (e.g., discussing the "next artist" when the next track is an audiobook chapter). For v1, the `TrackResult.config_changed` field (Section 5.5) provides the trigger to suppress grouping speech at boundaries; accept that DJ context may otherwise be imperfect. Future: use `config_index` plus `NamedPlaylist` metadata (name, description) surfaced through `PlaybackConfigMaster.current_playback_config` to enable contextual transition remarks ("Now back to our audiobook..."). |
| **Post-exhaustion smart continuation** | When all dedicated playlists are exhausted, optionally fall back to a "smart continuation" playlist (e.g., play similar music, or switch to `ALL_MUSIC` mode). This requires a new `PlaybackMasterStrategy` value or an exhaustion callback. |
| **Complex interleaving patterns** | Support for non-uniform weight sequences (e.g., "A, A, B, A, A, A, B" as a custom pattern rather than simple integer weights). |
| **Drag-and-drop track reordering** | Full drag-and-drop in the UI. v1 provides move-up / move-down buttons. |
| **Qt/PySide6 UI** | Port of finalized Tkinter UI to PySide6. Tracked in Phase 5. |

---

## 11. Summary of File Changes

| File | Change Type | Description | Status |
|------|-------------|-------------|--------|
| `muse/named_playlist.py` | **New** | `NamedPlaylist` dataclass (search-query / directory / explicit-track modes) + `NamedPlaylistStore` | **Done** (Phase 1) |
| `muse/playlist.py` | **Modify** | Add `loop` flag, `skip_memory_shuffle` flag, `reset()` / `_reset_for_loop()` methods, loop-aware `next_track()`, `skip_memory_shuffle` guard in `sort()` | **Done** (Phase 2) |
| `muse/playback_config.py` | **Modify** | Add `explicit_tracks` parameter, dual-mode `get_list()` (propagates `loop`/`skip_memory_shuffle`), `from_named_playlist()` factory. Remove extension state (`last_extension_played`, `ready_for_extension`, `assign_extension()`, `next_track_override`, `set_next_track_override()`). Fix `reamining_count` typo. | **Done** (Phase 2) |
| `muse/playback_config_master.py` | **Rewrite** | Cursor-based weighted round-robin interleaving, property proxies, exhaustion/loop handling. Sole owner of extension state. Added `get_playing_config()`, `get_playing_track()`, `_stamp_result()` for `TrackResult` enrichment. | **Done** (Phase 2) |
| `muse/playback_state.py` | **Modify** | Renamed slots for clarity: `active_config` (runtime) vs `master_config` (UI-configured). Removed dead `set_instance` / `reset_instance` calls. Added `reset()` convenience method. | **Done** (Phase 2) |
| `muse/run.py` | **Modify** | Unified code path in `do_workflow()` -- both `ALL_MUSIC` and `PLAYLIST_CONFIG` produce a `PlaybackConfigMaster`. Remove redundant strategy check in `run()`. | **Done** (Phase 2) |
| `muse/playback.py` | **Modify** | `TrackResult`-based flow: replaced separate `old_grouping`/`new_grouping` ivars with `_track_result`. Passes `TrackResult` to `get_spot_profile()`. | **Done** (Phase 4.2) |
| `muse/muse_spot_profile.py` | **Modify** | Accept `TrackResult` instead of separate args. Suppress grouping speech when `config_changed` is `True`. | **Done** (Phase 4.2) |
| `muse/muse.py`, `muse/muse_memory.py` | Minor modify | `get_spot_profile` signatures updated to accept `TrackResult`. | **Done** (Phase 4.2) |
| `utils/globals.py` | **Modify** | `TrackResult` NamedTuple: add `config_index` and `config_changed` fields for multi-playlist context. | **Done** (Phase 4.2) |
| `utils/utils.py` | Minor modify | Add `Utils.isfile_with_retry()` (mirrors `isdir_with_retry()`). | **Done** (Phase 1.3) |
| `extensions/extension_manager.py` | Minor modify | Updated to call `PlaybackConfigMaster.assign_extension()` and `PlaybackConfigMaster.get_playing_track()`. | **Done** (Phase 2.9) |
| `tests/integration/test_playback_integration.py` | Minor modify | Updated for `TrackResult` named fields and lowercase `open_configs`. | **Done** |
| `tests/unit/test_muse_core.py` | Minor modify | Updated `MuseSpotProfile` constructor calls for `TrackResult`. | **Done** |
| `ui/playlist_window.py` | **Modify** | Refactor to use `NamedPlaylist`, add weight/loop UI, track reordering, search integration. Updated `PlaybackStateManager` calls. | Pending (Phase 3) |
| `ui/search_window.py` | **Modify** | Add "Add to Playlist" and "Create Playlist from Search" actions | Pending (Phase 3) |
| `app.py` | **Modify** | Wire playlist window into menu, auto-open on `PLAYLIST_CONFIG` selection | Pending (Phase 3) |
| `ui_qt/playlist_window.py` | Deferred (Phase 5) | Qt port of finalized Tkinter version |
| `app_qt.py` | Deferred (Phase 5) | Qt wiring of playlist window |
