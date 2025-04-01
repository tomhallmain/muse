import pickle
from typing import Optional

from muse.dj_persona import DJPersonaManager
from muse.muse_spot_profile import MuseSpotProfile
from utils import Utils


class MuseMemory:
    all_spot_profiles = []
    last_session_spot_profiles = []
    current_session_spot_profiles = []
    max_memory_size = 1000
    persona_manager: Optional[DJPersonaManager] = None

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
        except FileNotFoundError:
            # Initialize persona manager only if no memory file exists
            MuseMemory.persona_manager = DJPersonaManager()
        except Exception as e:
            Utils.log(f"Error loading memory: {e}")

    @staticmethod
    def save():
        with open('muse_memory', 'wb') as f:
            swap = MuseMemory()
            # Ensure the persona manager is included in what gets pickled
            swap.persona_manager = MuseMemory.persona_manager
            pickle.dump(swap, f)

    @staticmethod
    def get_persona_manager() -> Optional[DJPersonaManager]:
        """Get the persona manager instance."""
        return MuseMemory.persona_manager

    @staticmethod
    def update_all_spot_profiles(spot_profile):
        MuseMemory.all_spot_profiles.insert(0, spot_profile)
        if len(MuseMemory.all_spot_profiles) > MuseMemory.max_memory_size:
            MuseMemory.all_spot_profiles = MuseMemory.all_spot_profiles[:MuseMemory.max_memory_size]

    @staticmethod
    def update_current_session_spot_profiles(spot_profile):
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
        Utils.log_debug(f"get_previous_session_spot_profile called: idx={idx}, creation_time={creation_time}, list_length={len(MuseMemory.current_session_spot_profiles)}")
        
        # Check if requested index is beyond list length
        if len(MuseMemory.current_session_spot_profiles) <= idx:
            Utils.log_debug("Index beyond list length, returning None")
            return None
            
        # If no creation time specified, return profile at requested index
        if creation_time is None:
            Utils.log_debug(f"Returning profile at index {idx}")
            return MuseMemory.current_session_spot_profiles[idx]
            
        # Find first profile created before the given creation time
        base_idx = idx
        while base_idx < len(MuseMemory.current_session_spot_profiles):
            profile = MuseMemory.current_session_spot_profiles[base_idx]
            Utils.log_debug(f"Checking profile at {base_idx}: creation_time={profile.creation_time}, target_time={creation_time}")
            if profile.creation_time < creation_time:
                break
            base_idx += 1
            
        # If no profile found before creation time, return None
        if base_idx >= len(MuseMemory.current_session_spot_profiles):
            Utils.log_debug("No profile found before creation time, returning None")
            return None
            
        # Return profile at (base_idx + requested_idx) if it exists
        target_idx = base_idx + idx
        if target_idx >= len(MuseMemory.current_session_spot_profiles):
            Utils.log_debug(f"Target index {target_idx} beyond list length, returning None")
            return None
            
        Utils.log_debug(f"Returning profile at target index {target_idx}")
        return MuseMemory.current_session_spot_profiles[target_idx]

    def __init__(self):
        self.tracks_since_last_topic = 0
        self.tracks_since_last_spoke = 0
        self.last_topic = None

    def is_recent_topics(self, topics_to_check=[], n=1):
        if n >= self.tracks_since_last_topic:
            return False
        return self.last_topic in topics_to_check

    def get_spot_profile(self, previous_track=None, track=None, last_track_failed=False, skip_track=False, old_grouping=None, new_grouping=None, grouping_type=None):
        spot_profile = MuseSpotProfile(previous_track, track, last_track_failed, skip_track, old_grouping, new_grouping, grouping_type,
                                       get_previous_spot_profile_callback=MuseMemory.get_previous_session_spot_profile)
        MuseMemory.update_all_spot_profiles(spot_profile)
        MuseMemory.update_current_session_spot_profiles(spot_profile)
        return spot_profile

