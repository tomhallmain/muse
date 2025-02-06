import pickle

from muse.muse_spot_profile import MuseSpotProfile

class MuseMemory:
    all_spot_profiles = []
    last_session_spot_profiles = []
    current_session_spot_profiles = []
    max_memory_size = 1000

    @staticmethod
    def load():
        try:
            with open('muse_memory', 'rb') as f:
                swap = pickle.load(f)
                MuseMemory.all_spot_profiles = list(swap.all_spot_profiles)
                MuseMemory.last_session_spot_profiles = list(swap.current_session_spot_profiles)
        except FileNotFoundError:
            pass

    @staticmethod
    def save():
        with open('muse_memory', 'wb') as f:
            swap = MuseMemory()
            pickle.dump(swap, f)

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
        self._recently_played = []
        self._recently_played_count = 0

    def get_spot_profile(self, previous_track=None, track=None, last_track_failed=False, skip_track=False, old_grouping=None, new_grouping=None, grouping_readable_name=None):
        previous_spot_profile = MuseMemory.get_previous_session_spot_profile()
        spot_profile = MuseSpotProfile(previous_track, track, last_track_failed, skip_track, old_grouping, new_grouping, grouping_readable_name,
                                       get_previous_spot_profile_callback=MuseMemory.get_previous_session_spot_profile)
        MuseMemory.update_all_spot_profiles(spot_profile)
        MuseMemory.update_current_session_spot_profiles(spot_profile)
        return spot_profile

