
import os
import subprocess
from time import sleep
import vlc

from muse.playback_config import PlaybackConfig
from utils.globals import Globals
from utils.utils import Utils

INSTANCE = vlc.Instance("verbose=-2")

class Playback:

    @staticmethod
    def new_playback(override_dir=None):
        config = PlaybackConfig.new_playback_config(override_dir=override_dir)
        return Playback(config, None, True)

    def __init__(self, playback_config, callbacks, run):
        self.vlc_media_player = INSTANCE.media_player_new()
        self._playback_config = playback_config
        self.callbacks = callbacks
        self._run = run
        assert self._run.muse is not None
        self.is_paused = False
        self.skip_track = False
        self.skip_delay = False
        self.track = None
        self.previous_track = ""
        self.last_track_failed = False
        self.has_played_first_track = False
        self.count = 0

    def get_track(self):
        self.previous_track = self.track
        self.track = self._playback_config.next_song()
        if self.track is None or self.track.is_invalid():
            return False
        return True

    def get_song_volume(self):
        args = ["ffmpeg", "-i", self.track.filepath, "-af", "volumedetect", "-f", "null", "/dev/null"]
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output, _ = process.communicate()
        mean_volume_tag = "] mean_volume: "
        max_volume_tag = "] max_volume: "
        mean_volume = -99999.0
        max_volume = -99999.0
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
        if self.get_track():
            self.vlc_media_player.play()
            sleep(0.5)
            while (self.vlc_media_player.is_playing() or self.is_paused) and not self.skip_track:
                sleep(0.5)
            self.vlc_media_player.stop()
        else:
            raise Exception("No tracks in playlist")

    def run(self):
        while self.get_track() and not self._run.is_cancelled:
            if self._run.muse.voice.can_speak:
                # TODO run muse in separate thread to be able to cancel it when user clicks Next
                skip_previous_song_remark = self.last_track_failed or self.skip_track
                if not skip_previous_song_remark:
                    self._run.muse.maybe_dj_post(self.previous_track)
                self.delay()
                self.register_new_song()
                self._run.muse.maybe_dj_prior(self.track, self.previous_track, skip_previous_song_remark)
            else:
                Utils.log_yellow("No voice available due to import failure, skipping Muse.")
                self.delay()
                self.register_new_song()

            self.set_volume()
            self.last_track_failed = False
            self.is_paused = False
            self.skip_track = False

            self.vlc_media_player.play()
            sleep(0.5)
            if not self.vlc_media_player.is_playing():
                self.last_track_failed = True
            while (self.vlc_media_player.is_playing() or self.is_paused) and not self.skip_track:
                sleep(0.5)
                self.update_progress()

            self.vlc_media_player.stop()
            self.has_played_first_track = True
            if self.increment_count():
                break

    def update_progress(self):
        if self.callbacks.update_progress_callback is not None:
            duration = self.vlc_media_player.get_length()
            current_time = self.vlc_media_player.get_time()
            if duration > 0:
                progress = int((current_time / duration) * 100)
            else:
                progress = 0
            self.callbacks.update_progress_callback(progress)

    def register_new_song(self):
        Utils.log(f"Playing track file: {self.track.filepath}")
        self.vlc_media_player = vlc.MediaPlayer(self.track.filepath)
        if self.callbacks.track_details_callback is not None:
            self.callbacks.track_details_callback(self.track)

    def increment_count(self):
        if not self.skip_track:
            self.count += 1
        return bool(self._playback_config.total > -1 and self.count > self._playback_config.total)

    def delay(self):
        if self.has_played_first_track and not self.last_track_failed:
            delay_timer = 0
            while not self.skip_delay and delay_timer < Globals.DELAY_TIME_SECONDS:
                sleep(0.5)
                delay_timer += 0.5
            if self.skip_delay:
                self.skip_delay = False

    def set_volume(self):
        mean_volume, max_volume = self.get_song_volume()
        Utils.log("Mean volume: " + str(mean_volume) + " Max volume: " + str(max_volume))
        volume = (Globals.DEFAULT_VOLUME_THRESHOLD + 30) if mean_volume < -50 else min(int(Globals.DEFAULT_VOLUME_THRESHOLD + (-1 * mean_volume)), 100)
        self.vlc_media_player.audio_set_volume(volume)
        # TODO callback for UI element, add a UI element for "effective volume"

    def pause(self):
        self.vlc_media_player.pause()
        self.is_paused = True

    def unpause(self):
        self.vlc_media_player.play()
        self.is_paused = False

    def next(self):
        self.vlc_media_player.stop()
        self.skip_track = True
        self.skip_delay = True

    def get_track_text_file(self):
        if self.track is None or self.track.is_invalid():
            return None
        return self.track.get_track_text_file()
