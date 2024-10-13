import os
import subprocess
from time import sleep
import vlc

from utils.globals import Globals
from utils.utils import Utils

class Playback:
    VLC_MEDIA_PLAYER = vlc.MediaPlayer()

    def __init__(self, playback_config, song_text_callback, run):
        self._playback_config = playback_config
        self._song_text_callback = song_text_callback
        self._run = run
        self.is_paused = False
        self.skip_song = False
        self.skip_delay = False
        self.song = ""

    def get_song(self):
        self.song = self._playback_config.next_song()
        if self.song is None:
            return False
        elif not os.path.isfile(self.song):
            raise Exception("Could not find song file path: " + self.song)
        print(f"Playing song file: {self.song}")
        Playback.VLC_MEDIA_PLAYER = vlc.MediaPlayer(self.song)
        return True

    def get_song_volume(self):
        args = ["ffmpeg", "-i", self.song, "-af", "volumedetect", "-f", "null", "/dev/null"]
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output, _ = process.communicate()
        mean_volume_tag = "] mean_volume: "
        max_volume_tag = "] max_volume: "
        mean_volume = -1.0
        max_volume = -1.0
        for line in output.decode("utf-8", errors="ignore").split("\n"):
            if mean_volume_tag in line:
                mean_volume = float(line[line.index(mean_volume_tag)+len(mean_volume_tag):-3].strip())
            if max_volume_tag in line:
                max_volume = float(line[line.index(max_volume_tag)+len(max_volume_tag):-3].strip())
        return mean_volume, max_volume

    def run(self):
        while self.get_song() and not self._run.is_cancelled:
            song_name = os.path.basename(self.song)
            if "." in self.song:
                song_name = song_name[:song_name.rfind(".")]
            directory = Utils.get_relative_dirpath(os.path.dirname(self.song))
            self._song_text_callback(song_name, directory)
            delay_timer = 0
            while not self.skip_delay and delay_timer < Globals.DELAY_TIME_SECONDS:
                sleep(0.5)
                delay_timer += 0.5
            if self.skip_delay:
                self.skip_delay = False
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
        self.skip_delay = True

