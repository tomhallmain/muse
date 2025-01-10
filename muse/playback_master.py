

class PlaybackMaster:
    def __init__(self, playback_configs=[]):
        self.playback_configs = playback_configs
        self.current_playback_config = None
        self.current_playback_config_index = -1
        self.played_tracks = []

    def next_song(self):
        self.current_playback_config_index += 1
        if (self.current_playback_config_index >= len(self.playback_configs)):
            self.current_playback_config_index = 0
        self.current_playback_config = self.playback_configs[self.current_playback_config_index]
        return self.current_playback_config.next_song()

    def get_played_tracks(self):
        return self.played_tracks

