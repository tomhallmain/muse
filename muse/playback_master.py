
from utils.app_info_cache import app_info_cache
from utils.globals import WorkflowType


class PlaybackMaster:
    playlist_history_max_size = 1000
    playlist_history = []
    
    @staticmethod
    def load_playlist_history():
        PlaybackMaster.playlist_history = app_info_cache.get("playlist_history", default_val=[])

    @staticmethod
    def save_playlist_history():
        app_info_cache.set("playlist_history", PlaybackMaster.playlist_history)

    def __init__(self, playback_configs=[]):
        self.playback_configs = playback_configs
        self.current_playback_config = None
        self.current_playback_config_index = -1
        self.played_tracks = []

    def next_track(self):
        self.current_playback_config_index += 1
        if (self.current_playback_config_index >= len(self.playback_configs)):
            self.current_playback_config_index = 0
        self.current_playback_config = self.playback_configs[self.current_playback_config_index]
        next_track = self.current_playback_config.next_track()
        if self.current_playback_config.type == WorkflowType.RANDOM:
            taper_history_to = min(self.current_playback_config.remaining_count(), PlaybackMaster.playlist_history_max_size)
            while next_track.get_track_details() in PlaybackMaster.playlist_history[:taper_history_to]:
                next_track = self.current_playback_config.next_track()
                taper_history_to = min(self.current_playback_config.remaining_count(), PlaybackMaster.playlist_history_max_size)
        return next_track

    def get_played_tracks(self):
        return self.played_tracks

