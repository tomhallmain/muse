from dataclasses import dataclass, fields
from typing import Optional


@dataclass
class SortConfig:
    """Configuration controlling playlist sort behaviour.

    Attached to ``PlaylistDescriptor`` (persisted), ``PlaybackConfig`` (runtime),
    and ``PlaybackConfigMaster`` (as an optional override that merges onto
    per-playlist configs).
    """

    skip_memory_shuffle: bool = False
    skip_random_start: bool = False
    check_count_override: Optional[int] = None
    check_entire_playlist: bool = False

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        data: dict = {}
        if self.skip_memory_shuffle:
            data["skip_memory_shuffle"] = True
        if self.skip_random_start:
            data["skip_random_start"] = True
        if self.check_count_override is not None:
            data["check_count_override"] = self.check_count_override
        if self.check_entire_playlist:
            data["check_entire_playlist"] = True
        return data

    @staticmethod
    def from_dict(data: dict) -> 'SortConfig':
        return SortConfig(
            skip_memory_shuffle=bool(data.get("skip_memory_shuffle", False)),
            skip_random_start=bool(data.get("skip_random_start", False)),
            check_count_override=data.get("check_count_override"),
            check_entire_playlist=bool(data.get("check_entire_playlist", False)),
        )

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    def merge(self, override: 'SortConfig') -> 'SortConfig':
        """Return a new SortConfig where non-default fields in *override* win.

        Fields left at their default in *override* fall through to *self*.
        """
        defaults = SortConfig()
        merged_kwargs = {}
        for f in fields(SortConfig):
            base_val = getattr(self, f.name)
            over_val = getattr(override, f.name)
            default_val = getattr(defaults, f.name)
            merged_kwargs[f.name] = over_val if over_val != default_val else base_val
        return SortConfig(**merged_kwargs)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def is_default(self) -> bool:
        return self == DEFAULT_SORT_CONFIG

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SortConfig):
            return False
        return (self.skip_memory_shuffle == other.skip_memory_shuffle
                and self.skip_random_start == other.skip_random_start
                and self.check_count_override == other.check_count_override
                and self.check_entire_playlist == other.check_entire_playlist)

    def __hash__(self) -> int:
        return hash((self.skip_memory_shuffle, self.skip_random_start,
                      self.check_count_override, self.check_entire_playlist))

    def __repr__(self) -> str:
        parts = []
        if self.skip_memory_shuffle:
            parts.append("skip_mem")
        if self.skip_random_start:
            parts.append("skip_rand")
        if self.check_count_override is not None:
            parts.append(f"cc={self.check_count_override}")
        if self.check_entire_playlist:
            parts.append("scour")
        return f"SortConfig({', '.join(parts)})" if parts else "SortConfig()"


DEFAULT_SORT_CONFIG = SortConfig()
