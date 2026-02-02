from dataclasses import dataclass
import pickle
import time
import gc
from typing import Optional, Dict

from muse.dj_persona import DJPersonaManager
from muse.muse_spot_profile import MuseSpotProfile
from utils.globals import Topic
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
            topic=str(Topic.from_value(profile.topic)),
            topic_translated=profile.topic_translated,
            grouping_type=profile.grouping_type,
            old_grouping=profile.old_grouping,
            new_grouping=profile.new_grouping
        )


class MuseMemory:

    def __init__(self):
        self.all_spot_profiles = []
        self.last_session_spot_profiles = []
        self.current_session_spot_profiles = []
        self.max_memory_size = 1000
        self.max_historical_snapshots = 5000  # Maximum number of historical spot profile snapshots to keep
        self.persona_manager: Optional[DJPersonaManager] = None
        self._historical_snapshots: Dict[float, SpotProfileSnapshot] = {}  # Keyed by creation_time
        self.tracks_since_last_topic = 0
        self.tracks_since_last_spoke = 0
        self.last_topic = None
        self._is_loaded = False  # Track if memory has been loaded

        
        # Instance-based versions of your static methods
        self.load()

    def __getstate__(self):
        """Control what gets pickled - exclude non-pickleable objects."""
        state = self.__dict__.copy()
        
        # Clean up callbacks in all spot profiles to make them pickleable
        self._clean_spot_profiles_for_pickling(state)
            
        return state

    def __setstate__(self, state):
        """Restore state after unpickling."""
        # Debug: Show when __setstate__ is called and what keys are being restored
        # logger.debug(f"MuseMemory.__setstate__() called with {len(state)} keys:")
        # for key in sorted(state.keys()):
        #     value_type = type(state[key]).__name__
        #     if isinstance(state[key], list):
        #         logger.debug(f"  - {key}: {value_type} with {len(state[key])} items")
        #     elif isinstance(state[key], dict):
        #         logger.debug(f"  - {key}: {value_type} with {len(state[key])} keys")
        #     else:
        #         logger.debug(f"  - {key}: {value_type}")
        
        self.__dict__.update(state)
        
        # Reinitialize any non-pickleable objects
        if not hasattr(self, 'persona_manager') or self.persona_manager is None:
            self.persona_manager = DJPersonaManager()
        else:
            logger.debug("Preserving existing persona manager")
            # Don't reload personas - they're already correctly restored from pickle

    def load(self):
        # Prevent double loading
        if self._is_loaded:
            return
            
        try:
            with open('muse_memory', 'rb') as f:
                loaded = pickle.load(f)
                # Copy all attributes from loaded instance, being selective
                for key, value in loaded.__dict__.items():
                    if not key.startswith('_') or key in ['_historical_snapshots']:
                        setattr(self, key, value)
                
                # Persona manager is already reloaded by __setstate__() during pickle.load()
                # Only create a new one if it doesn't exist
                if not self.persona_manager:
                    self.persona_manager = DJPersonaManager()
                    logger.info("Created new persona manager")
                else:
                    logger.info("Loaded existing persona manager: {0}".format(self.persona_manager))
                    
                self._is_loaded = True
        except FileNotFoundError:
            self.persona_manager = DJPersonaManager()
        except Exception as e:
            logger.info(f"Error loading memory: {e}")
        self._is_loaded = True

    def save(self):
        try:
            with open('muse_memory', 'wb') as f:
                pickle.dump(self, f)
        except Exception as e:
            logger.info(f"Error saving muse memory: {e}")
            self._debug_pickle_attributes()
            from scripts.object_inspector import debug_pickle_issues
            debug_pickle_issues(self)

    def get_persona_manager(self) -> Optional[DJPersonaManager]:
        return self.persona_manager

    def _debug_pickle_attributes(self):
        """Test each attribute individually to identify which one causes pickling failures."""
        logger.info("Testing individual attributes for pickling issues...")
        
        # Get all instance attributes
        attributes = {}
        
        # Regular __dict__ attributes
        if hasattr(self, '__dict__'):
            attributes.update(self.__dict__)
        
        # __slots__ attributes
        if hasattr(self, '__slots__'):
            for slot_name in self.__slots__:
                if hasattr(self, slot_name):
                    attributes[slot_name] = getattr(self, slot_name)
        
        # Test each attribute individually
        problematic_attributes = []
        
        for attr_name, attr_value in attributes.items():
            try:
                # Try to pickle this specific attribute
                pickle.dumps(attr_value)
                logger.debug(f"✓ Attribute '{attr_name}' pickles successfully")
            except Exception as e:
                logger.warning(f"✗ Attribute '{attr_name}' failed to pickle: {e}")
                problematic_attributes.append((attr_name, attr_value, str(e)))

        has_run_run_spot_profile_debug = False

        # If we found problematic attributes, test nested objects
        for attr_name, attr_value, error in problematic_attributes:
            logger.info(f"Analyzing problematic attribute '{attr_name}': {type(attr_value)}")
            
            # If it's a list, test each item
            if isinstance(attr_value, list):
                logger.info(f"  Testing {len(attr_value)} items in list '{attr_name}'...")
                for i, item in enumerate(attr_value):
                    try:
                        pickle.dumps(item)
                        logger.debug(f"    ✓ Item [{i}] pickles successfully")
                    except Exception as item_error:
                        logger.warning(f"    ✗ Item [{i}] failed to pickle: {item_error}")
                        logger.info(f"    Item [{i}] type: {type(item)}")
                        if hasattr(item, '__dict__'):
                            logger.info(f"    Item [{i}] attributes: {list(item.__dict__.keys())}")
                        
                        # If it's a MuseSpotProfile, run its debug method
                        if not has_run_run_spot_profile_debug and hasattr(item, '_debug_pickle_attributes'):
                            logger.info(f"    Running detailed debug on MuseSpotProfile item [{i}]...")
                            item._debug_pickle_attributes()
                            has_run_run_spot_profile_debug = True
            
            # If it's a dict, test each value
            elif isinstance(attr_value, dict):
                logger.info(f"  Testing {len(attr_value)} values in dict '{attr_name}'...")
                for key, value in attr_value.items():
                    try:
                        pickle.dumps(value)
                        logger.debug(f"    ✓ Key '{key}' pickles successfully")
                    except Exception as value_error:
                        logger.warning(f"    ✗ Key '{key}' failed to pickle: {value_error}")
                        logger.info(f"    Key '{key}' type: {type(value)}")
        
        if problematic_attributes:
            logger.error(f"Found {len(problematic_attributes)} problematic attributes:")
            for attr_name, attr_value, error in problematic_attributes:
                logger.error(f"  - {attr_name}: {error}")
        else:
            logger.info("No individual attributes failed to pickle - issue may be with object structure")

    def _clean_spot_profiles_for_pickling(self, state):
        """Clean up callbacks in spot profiles to make them pickleable."""
        spot_profile_lists = ['all_spot_profiles', 'last_session_spot_profiles', 'current_session_spot_profiles']
        
        for list_name in spot_profile_lists:
            if list_name in state and isinstance(state[list_name], list):
                logger.debug(f"Cleaning callbacks in {list_name} for pickling...")
                for profile in state[list_name]:
                    if hasattr(profile, 'unset_non_historical_fields'):
                        profile.unset_non_historical_fields()

    def update_all_spot_profiles(self, spot_profile: MuseSpotProfile):
        """Update the spot profiles list and maintain historical snapshots."""
        logger.debug(f"Updating all spot profiles: current count={len(self.all_spot_profiles)}, new profile creation_time={spot_profile.creation_time}")
        
        if len(self.all_spot_profiles) > 0:
            # Clean up the previous spot profile if it exists
            previous_profile = self.all_spot_profiles[0]
            logger.debug(f"Cleaning up previous profile: creation_time={previous_profile.creation_time}, was_spoken={previous_profile.was_spoken}")
            # Clear fields that are no longer needed
            previous_profile.unset_non_historical_fields()
            # Force garbage collection of the cleared objects
            gc.collect()

        # Add to current profiles
        self.all_spot_profiles.insert(0, spot_profile)
        logger.debug(f"Added new profile at index 0: creation_time={spot_profile.creation_time}, was_spoken={spot_profile.was_spoken}")
        
        if len(self.all_spot_profiles) > self.max_memory_size:
            logger.debug(f"Exceeding max memory size ({self.max_memory_size}), converting excess profiles to snapshots")
            # Convert excess profiles to snapshots before removing
            for profile in self.all_spot_profiles[self.max_memory_size:]:
                logger.debug(f"Converting to snapshot: creation_time={profile.creation_time}, was_spoken={profile.was_spoken}")
                self._add_historical_snapshot(profile)
            self.all_spot_profiles = self.all_spot_profiles[:self.max_memory_size]
            logger.debug(f"Trimmed profiles list to {len(self.all_spot_profiles)} entries")

    def _add_historical_snapshot(self, profile: MuseSpotProfile):
        """Add a spot profile snapshot to historical storage."""
        snapshot = SpotProfileSnapshot.from_spot_profile(profile)
        self._historical_snapshots[profile.creation_time] = snapshot
        
        # Purge old snapshots if we exceed the limit
        if len(self._historical_snapshots) > self.max_historical_snapshots:
            # Remove oldest snapshots
            oldest_times = sorted(self._historical_snapshots.keys())[:-self.max_historical_snapshots]
            for time_key in oldest_times:
                del self._historical_snapshots[time_key]

    def purge_old_snapshots(self, days_old: int = 30):
        """Purge historical snapshots older than the specified number of days."""
        cutoff_time = time.time() - (days_old * 24 * 3600)
        self._historical_snapshots = {
            k: v for k, v in self._historical_snapshots.items()
            if k > cutoff_time
        }

    def update_current_session_spot_profiles(self, spot_profile: MuseSpotProfile):
        self.current_session_spot_profiles.insert(0, spot_profile)
        if len(self.current_session_spot_profiles) > self.max_memory_size:
            self.current_session_spot_profiles = self.current_session_spot_profiles[:self.max_memory_size]

    def get_previous_session_spot_profile(self, idx=0, creation_time=None):
        """Get the previous spot profile at the given index that was created before the specified time.
        
        Args:
            idx (int): The index of the profile to retrieve, starting from the most recent less than creation time (0 = most recent)
            creation_time (float, optional): If provided, only return profiles created before this time
            
        Returns:
            MuseSpotProfile or None: The previous spot profile if found and valid, None otherwise
        """
        # logger.debug(f"get_previous_session_spot_profile called: idx={idx}, creation_time={creation_time}, list_length={len(self.current_session_spot_profiles)}")
        
        # Check if requested index is beyond list length
        if len(self.current_session_spot_profiles) <= idx:
            logger.debug(f"Index beyond list length of {len(self.current_session_spot_profiles)}, returning None")
            return None
            
        # If no creation time specified, return profile at requested index
        if creation_time is None:
            # logger.debug(f"Returning profile at index {idx}")
            return self.current_session_spot_profiles[idx]
            
        # Find first profile created before the given creation time
        base_idx = idx
        while base_idx < len(self.current_session_spot_profiles):
            profile = self.current_session_spot_profiles[base_idx]
            # logger.debug(f"Checking profile at {base_idx}: creation_time={profile.creation_time}, target_time={creation_time}, was_spoken={profile.was_spoken}")
            if profile.creation_time < creation_time:
                break
            base_idx += 1
            
        # If no profile found before creation time, return None
        if base_idx >= len(self.current_session_spot_profiles):
            logger.debug("No profile found before creation time, returning None")
            return None
            
        # Return profile at (base_idx + requested_idx) if it exists
        target_idx = base_idx + idx
        if target_idx >= len(self.current_session_spot_profiles):
            # logger.debug(f"Target index {target_idx} beyond list length, returning None")
            return None

        spot_profile = self.current_session_spot_profiles[target_idx]
        # logger.debug(f"Returning profile at target index {target_idx}: creation_time={spot_profile.creation_time}, was_spoken={spot_profile.was_spoken}")
        return spot_profile

    def update_last_topic(self, topic):
        """Update the last topic that was discussed.
        
        Args:
            topic: The topic that was discussed (Topic enum or string)
        """
        self.last_topic = Topic.from_value(topic)
        if topic is not None and self.last_topic is None:
            logger.warning(f"Failed to convert topic to Topic enum: {topic} (type: {type(topic)})")

    def is_recent_topics(self, topics_to_check=[], n=1):
        """Check if any of the specified topics were discussed recently.
        
        Args:
            topics_to_check: List of topics to check. Can contain strings or Topic enum values.
            n: Number of tracks to look back (default 1)
            
        Returns:
            bool: True if any topic in topics_to_check was discussed within the last n tracks
        """
        if n >= self.tracks_since_last_topic:
            return False
        
        if not self.last_topic:
            return False
            
        # Convert topics_to_check to a set of Topic enum values for comparison
        topic_enums = set()
        for topic in topics_to_check:
            converted_topic = Topic.from_value(topic)
            if converted_topic is not None:
                topic_enums.add(converted_topic)
            elif topic is not None:
                logger.error(f"Failed to convert topic to Topic enum: {topic} (type: {type(topic)})")

        # Check if last_topic matches any of the topics_to_check
        return self.last_topic in topic_enums

    def get_spot_profile(self, previous_track=None, track=None, last_track_failed=False, skip_track=False,
                         old_grouping=None, new_grouping=None, grouping_type=None, get_upcoming_tracks_callback=None):
        spot_profile = MuseSpotProfile(previous_track, track, last_track_failed, skip_track, old_grouping, new_grouping, grouping_type,
                                       get_previous_spot_profile_callback=self.get_previous_session_spot_profile,
                                       get_upcoming_tracks_callback=get_upcoming_tracks_callback)
        self.update_all_spot_profiles(spot_profile)
        self.update_current_session_spot_profiles(spot_profile)
        return spot_profile


muse_memory = MuseMemory()

