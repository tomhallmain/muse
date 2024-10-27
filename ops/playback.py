import glob
import os
import subprocess
from time import sleep
import vlc

from ops.playback_config import PlaybackConfig
from utils.globals import Globals
from utils.utils import Utils

INSTANCE = vlc.Instance("verbose=-2")

class Playback:
    VLC_MEDIA_PLAYER = INSTANCE.media_player_new()

    @staticmethod
    def new_playback(override_dir=None):
        config = PlaybackConfig.new_playback_config(override_dir=override_dir)
        return Playback(config, None, True)

    def __init__(self, playback_config, song_text_callback, run):
        self._playback_config = playback_config
        self._song_text_callback = song_text_callback
        self._run = run
        self.is_paused = False
        self.skip_song = False
        self.skip_delay = False
        self.song = ""
        self.previous_song = ""

    def get_song(self):
        self.previous_song = self.song
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

    def get_song_quality_info(self):
        # TODO: Get info like bit rate, mono vs stereo, possibly try to infer if it's AI or not
        pass

    @staticmethod
    def get_song_name(song):
        return os.path.splitext(os.path.basename(song))[0]

    def play_one_song(self):
        if self.get_song():
            Playback.VLC_MEDIA_PLAYER.play()
            sleep(0.5)
            while (Playback.VLC_MEDIA_PLAYER.is_playing() or self.is_paused) and not self.skip_song:
                sleep(0.5)
            Playback.VLC_MEDIA_PLAYER.stop()
        else:
            raise Exception("No songs in playlist")

    def run(self):
        while self.get_song() and not self._run.is_cancelled:
            song_name = Playback.get_song_name(self.song)
            self._run.muse.maybe_dj(song_name, Playback.get_song_name(self.previous_song))
            directory = Utils.get_relative_dirpath(os.path.dirname(self.song))
            if self._song_text_callback is not None:
                self._song_text_callback(song_name, directory)
            delay_timer = 0
            while not self.skip_delay and delay_timer < Globals.DELAY_TIME_SECONDS:
                sleep(0.5)
                delay_timer += 0.5
            if self.skip_delay:
                self.skip_delay = False
            mean_volume, max_volume = self.get_song_volume()
            print("Mean volume: " + str(mean_volume))
            print("Max volume: " + str(max_volume))
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

    def get_song_text_file(self):
        if self.song is None or self.song == "" or not os.path.exists(self.song):
            return None
        song_basename = os.path.basename(self.song).lower()
        dirname = os.path.dirname(self.song)
        txt_files = glob.glob(os.path.join(dirname, "*.txt"))
        txt_basenames = []
        for f in txt_files:
            basename = os.path.basename(f).lower()
            if song_basename.startswith(basename):
                return f
            txt_basenames.append(basename)
        for basename in txt_basenames:
            if basename[:-4] in song_basename:
                return os.path.join(dirname,  basename)
        string_distance_dict = {}
        song_basename_no_ext = os.path.splitext(song_basename)[0]
        print("Song basename no ext: " + song_basename_no_ext)
        min_string_distance = (999999999, None)
        for basename in txt_basenames:
            basename_no_ext = os.path.splitext(basename)[0]
            string_distance = Utils.string_distance(song_basename_no_ext,  basename_no_ext)
            string_distance_dict[basename] = string_distance
            print("Txt basename no ext: " + basename_no_ext + ", string distance: " + str(string_distance))
            if min_string_distance[0] > string_distance:
                min_string_distance = (string_distance, basename)
        if min_string_distance[1] is not None and min_string_distance[0] < 30:
            return os.path.join(dirname,  min_string_distance[1])
        raise Exception("No matching text file found for song: " + self.song)

