import pickle
from typing import Optional

from muse.muse_spot_profile import MuseSpotProfile
from muse.dj_persona import DJPersonaManager

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
                # Initialize persona manager during loading
                MuseMemory.persona_manager = DJPersonaManager()
        except FileNotFoundError:
            # Initialize persona manager even if no memory file exists
            MuseMemory.persona_manager = DJPersonaManager()

    @staticmethod
    def save():
        with open('muse_memory', 'wb') as f:
            swap = MuseMemory()
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
    def get_previous_session_spot_profile(idx=0):
        return None if len(MuseMemory.current_session_spot_profiles) <= idx else MuseMemory.current_session_spot_profiles[idx]

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

