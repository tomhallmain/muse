import os
from time import sleep
import vlc

from utils.globals import Globals

class Playback:
    VLC_MEDIA_PLAYER = vlc.MediaPlayer()

    def __init__(self, playback_config):
        self._playback_config = playback_config
        self.is_paused = False
        self.skip_song = False

    def get_song(self):
        song = self._playback_config.next_song()
        if song is None:
            return False
        elif not os.path.isfile(song):
            raise Exception("Could not find song file path: " + song)
        print(f"Playing song file: {song}")
        Playback.VLC_MEDIA_PLAYER = vlc.MediaPlayer(song)
        return True

    def run(self):
        while self.get_song():
            delay_timer = 0
            while delay_timer < Globals.DELAY_TIME_SECONDS:
                sleep(0.5)
                delay_timer += 0.5
            self.is_paused = False
            self.skip_song = False
            Playback.VLC_MEDIA_PLAYER.play()
            sleep(0.5)
            while (Playback.VLC_MEDIA_PLAYER.is_playing() or self.is_paused) and not self.skip_song:
                sleep(0.5)
            Playback.VLC_MEDIA_PLAYER.stop()

    def pause(self):
        Playback.VLC_MEDIA_PLAYER.pause()
        self.is_paused = True

    def unpause(self):
        Playback.VLC_MEDIA_PLAYER.play()
        self.is_paused = False

    def next(self):
        Playback.VLC_MEDIA_PLAYER.stop()
        self.skip_song = True
