from dataclasses import dataclass
import pickle
import time
import gc
from typing import Optional, Dict

from muse.dj_persona import DJPersonaManager
from muse.muse_spot_profile import MuseSpotProfile
from utils.logging_setup import get_logger
from utils import Utils

logger = get_logger(__name__)

@dataclass
class SpotProfileSnapshot:
    """A memory-efficient snapshot of a spot profile's essential data."""
    creation_time: float
    previous_track_title: Optional[str]
    current_track_title: Optional[str]
    was_spoken: bool
    topic: Optional[str]
    topic_translated: Optional[str]
    grouping_type: Optional[str]
    old_grouping: Optional[str]
    new_grouping: Optional[str]

    @classmethod
    def from_spot_profile(cls, profile: MuseSpotProfile) -> 'SpotProfileSnapshot':
        """Create a snapshot from a full spot profile."""
        return cls(
            creation_time=profile.creation_time,
            previous_track_title=profile.previous_track.title if profile.previous_track else None,
            current_track_title=profile.track.title if profile.track else None,
            was_spoken=profile.was_spoken,
            topic=profile.topic,
            topic_translated=profile.topic_translated,
            grouping_type=profile.grouping_type,
            old_grouping=profile.old_grouping,
            new_grouping=profile.new_grouping
        )


class MuseMemory:
    all_spot_profiles = []
    last_session_spot_profiles = []
    current_session_spot_profiles = []
    max_memory_size = 1000
    max_historical_snapshots = 5000  # Maximum number of historical spot profile snapshots to keep
    persona_manager: Optional[DJPersonaManager] = None
    _historical_snapshots: Dict[float, SpotProfileSnapshot] = {}  # Keyed by creation_time

    @staticmethod
    def load():
        try:
            with open('muse_memory', 'rb') as f:
                swap = pickle.load(f)
                MuseMemory.all_spot_profiles = list(swap.all_spot_profiles)
                MuseMemory.last_session_spot_profiles = list(swap.current_session_spot_profiles)
                if hasattr(swap, 'persona_manager') and swap.persona_manager is not None:
                    MuseMemory.persona_manager = swap.persona_manager
                    MuseMemory.persona_manager.reload_personas()
                else:
                    MuseMemory.persona_manager = DJPersonaManager()
                # Load historical snapshots if they exist
                if hasattr(swap, '_historical_snapshots'):
                    MuseMemory._historical_snapshots = swap._historical_snapshots
        except FileNotFoundError:
            MuseMemory.persona_manager = DJPersonaManager()
        except Exception as e:
            logger.info(f"Error loading memory: {e}")

    @staticmethod
    def save():
        with open('muse_memory', 'wb') as f:
            swap = MuseMemory()
            swap.persona_manager = MuseMemory.persona_manager
            swap._historical_snapshots = MuseMemory._historical_snapshots
            pickle.dump(swap, f)

    @staticmethod
    def get_persona_manager() -> Optional[DJPersonaManager]:
        return MuseMemory.persona_manager

    @staticmethod
    def update_all_spot_profiles(spot_profile: MuseSpotProfile):
        """Update the spot profiles list and maintain historical snapshots."""
        logger.debug(f"Updating all spot profiles: current count={len(MuseMemory.all_spot_profiles)}, new profile creation_time={spot_profile.creation_time}")
        
        if len(MuseMemory.all_spot_profiles) > 0:
            # Clean up the previous spot profile if it exists
            previous_profile = MuseMemory.all_spot_profiles[0]
            logger.debug(f"Cleaning up previous profile: creation_time={previous_profile.creation_time}, was_spoken={previous_profile.was_spoken}")
            # Clear fields that are no longer needed
            previous_profile.unset_non_historical_fields()
            # Force garbage collection of the cleared objects
            gc.collect()

        # Add to current profiles
        MuseMemory.all_spot_profiles.insert(0, spot_profile)
        logger.debug(f"Added new profile at index 0: creation_time={spot_profile.creation_time}, was_spoken={spot_profile.was_spoken}")
        
        if len(MuseMemory.all_spot_profiles) > MuseMemory.max_memory_size:
            logger.debug(f"Exceeding max memory size ({MuseMemory.max_memory_size}), converting excess profiles to snapshots")
            # Convert excess profiles to snapshots before removing
            for profile in MuseMemory.all_spot_profiles[MuseMemory.max_memory_size:]:
                logger.debug(f"Converting to snapshot: creation_time={profile.creation_time}, was_spoken={profile.was_spoken}")
                MuseMemory._add_historical_snapshot(profile)
            MuseMemory.all_spot_profiles = MuseMemory.all_spot_profiles[:MuseMemory.max_memory_size]
            logger.debug(f"Trimmed profiles list to {len(MuseMemory.all_spot_profiles)} entries")

    @staticmethod
    def _add_historical_snapshot(profile: MuseSpotProfile):
        """Add a spot profile snapshot to historical storage."""
        snapshot = SpotProfileSnapshot.from_spot_profile(profile)
        MuseMemory._historical_snapshots[profile.creation_time] = snapshot
        
        # Purge old snapshots if we exceed the limit
        if len(MuseMemory._historical_snapshots) > MuseMemory.max_historical_snapshots:
            # Remove oldest snapshots
            oldest_times = sorted(MuseMemory._historical_snapshots.keys())[:-MuseMemory.max_historical_snapshots]
            for time_key in oldest_times:
                del MuseMemory._historical_snapshots[time_key]

    @staticmethod
    def purge_old_snapshots(days_old: int = 30):
        """Purge historical snapshots older than the specified number of days."""
        cutoff_time = time.time() - (days_old * 24 * 3600)
        MuseMemory._historical_snapshots = {
            k: v for k, v in MuseMemory._historical_snapshots.items()
            if k > cutoff_time
        }

    @staticmethod
    def update_current_session_spot_profiles(spot_profile: MuseSpotProfile):
        MuseMemory.current_session_spot_profiles.insert(0, spot_profile)
        if len(MuseMemory.current_session_spot_profiles) > MuseMemory.max_memory_size:
            MuseMemory.current_session_spot_profiles = MuseMemory.current_session_spot_profiles[:MuseMemory.max_memory_size]

    @staticmethod
    def get_previous_session_spot_profile(idx=0, creation_time=None):
        """Get the previous spot profile at the given index that was created before the specified time.
        
        Args:
            idx (int): The index of the profile to retrieve, starting from the most recent less than creation time (0 = most recent)
            creation_time (float, optional): If provided, only return profiles created before this time
            
        Returns:
            MuseSpotProfile or None: The previous spot profile if found and valid, None otherwise
        """
        logger.debug(f"get_previous_session_spot_profile called: idx={idx}, creation_time={creation_time}, list_length={len(MuseMemory.current_session_spot_profiles)}")
        
        # Check if requested index is beyond list length
        if len(MuseMemory.current_session_spot_profiles) <= idx:
            logger.debug(f"Index beyond list length of {len(MuseMemory.current_session_spot_profiles)}, returning None")
            return None
            
        # If no creation time specified, return profile at requested index
        if creation_time is None:
            logger.debug(f"Returning profile at index {idx}")
            return MuseMemory.current_session_spot_profiles[idx]
            
        # Find first profile created before the given creation time
        base_idx = idx
        while base_idx < len(MuseMemory.current_session_spot_profiles):
            profile = MuseMemory.current_session_spot_profiles[base_idx]
            logger.debug(f"Checking profile at {base_idx}: creation_time={profile.creation_time}, target_time={creation_time}, was_spoken={profile.was_spoken}")
            if profile.creation_time < creation_time:
                break
            base_idx += 1
            
        # If no profile found before creation time, return None
        if base_idx >= len(MuseMemory.current_session_spot_profiles):
            logger.debug("No profile found before creation time, returning None")
            return None
            
        # Return profile at (base_idx + requested_idx) if it exists
        target_idx = base_idx + idx
        if target_idx >= len(MuseMemory.current_session_spot_profiles):
            logger.debug(f"Target index {target_idx} beyond list length, returning None")
            return None

        spot_profile = MuseMemory.current_session_spot_profiles[target_idx]
        logger.debug(f"Returning profile at target index {target_idx}: creation_time={spot_profile.creation_time}, was_spoken={spot_profile.was_spoken}")
        return spot_profile

    def __init__(self):
        self.tracks_since_last_topic = 0
        self.tracks_since_last_spoke = 0
        self.last_topic = None

    def is_recent_topics(self, topics_to_check=[], n=1):
        if n >= self.tracks_since_last_topic:
            return False
        return self.last_topic in topics_to_check

    def get_spot_profile(self, previous_track=None, track=None, last_track_failed=False, skip_track=False,
                         old_grouping=None, new_grouping=None, grouping_type=None, get_upcoming_tracks_callback=None):
        spot_profile = MuseSpotProfile(previous_track, track, last_track_failed, skip_track, old_grouping, new_grouping, grouping_type,
                                       get_previous_spot_profile_callback=MuseMemory.get_previous_session_spot_profile,
                                       get_upcoming_tracks_callback=get_upcoming_tracks_callback)
        MuseMemory.update_all_spot_profiles(spot_profile)
        MuseMemory.update_current_session_spot_profiles(spot_profile)
        return spot_profile

