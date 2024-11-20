
import subprocess
from time import sleep
import vlc

from muse.playback_config import PlaybackConfig
from utils.globals import Globals
from utils.utils import Utils
from utils.translations import I18N

_ = I18N._

INSTANCE = vlc.Instance("verbose=-2")

class Playback:

    @staticmethod
    def new_playback(override_dir=None):
        config = PlaybackConfig.new_playback_config(override_dir=override_dir)
        return Playback(config, None, False)

    def __init__(self, playback_config, callbacks, run):
        self.vlc_media_player = INSTANCE.media_player_new()
        self._playback_config = playback_config
        self.callbacks = callbacks
        self._run = run
        self.is_paused = False
        self.skip_track = False
        self.skip_delay = False
        self.track = None
        self.previous_track = ""
        self.last_track_failed = False
        self.has_played_first_track = False
        self.count = 0
        self.muse_spot_profiles = []

    def has_muse(self):
        return self._run and self._run.muse is not None

    def get_track(self):
        self.previous_track = self.track
        self.track = self._playback_config.next_track()
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

    def get_spot_profile(self, audio_track=None):
        if audio_track is None:
            audio_track = self.track
        for profile in self.muse_spot_profiles:
            if audio_track == profile.track:
                return profile
        # It is possible for the spot profile to not have been prepared for the next track if the 
        # next track was a late addition due to a forced playback extension. In this case, need
        # to overwrite the "Next" track in the previously generated spot profile with the new one
        for profile in self.muse_spot_profiles:
            if profile.previous_track == self.previous_track:
                profile.track = audio_track
                return profile
        raise Exception(f"No spot profile found for track: {audio_track}")

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
            if self.has_muse() and self._run.muse.voice.can_speak:
                if not self.has_played_first_track or not self._run.muse.has_started_prep:
                    # First track, or if user skipped before end of last track
                    self.prepare_muse(first_prep=not self.has_played_first_track, delayed_prep=True)
                # TODO enable muse to be cancelled when user clicks Next
                # The user may have requested to skip the last track since the muse profile was created
                self.get_spot_profile().update_skip_previous_track_remark(self.skip_track)
                if self.get_spot_profile().is_going_to_say_something():
                    # TODO handle long delays edge case
                    self._run.muse.maybe_dj(self.get_spot_profile())
                    self.register_new_song()
                    # self._run.muse.maybe_dj_prior(self.muse_spot_profile)
                else:
                    self.delay()
                    self.register_new_song()
                self.reset_muse()
            else:
                if self._run:
                    Utils.log_yellow("No voice available due to import failure, skipping Muse.")
                self.delay()
                self.register_new_song()

            self.set_volume()
            self.last_track_failed = False
            self.is_paused = False
            self.skip_track = False

            self.vlc_media_player.play()
            sleep(0.5)
            cumulative_sleep_seconds = 0.5
            if not self.vlc_media_player.is_playing():
                self.last_track_failed = True
            while (self.vlc_media_player.is_playing() or self.is_paused) and not self.skip_track:
                sleep(0.5)
                cumulative_sleep_seconds += 0.5
                seconds_remaining = self.update_progress()
                if  self._run.muse is not None and \
                        self._run.muse.ready_to_prepare(cumulative_sleep_seconds, seconds_remaining):
                    self.prepare_muse()

            self.vlc_media_player.stop()
            self.has_played_first_track = True
            if self.increment_count():
                break

    def update_progress(self):
        duration = self.vlc_media_player.get_length()
        current_time = self.vlc_media_player.get_time()
        if self.callbacks.update_progress_callback is not None:
            if duration > 0:
                progress = int((current_time / duration) * 100)
            else:
                progress = 0
            self.callbacks.update_progress_callback(progress, current_time, duration)
        return duration - current_time

    def reset_muse(self):
        self._run.muse.reset()
        self.muse_spot_profiles.remove(self.get_spot_profile(self.track))

    def prepare_muse(self, first_prep=False, delayed_prep=False):
        # At the moment the local LLM and TTS models are not that fast, so need to start generation
        # for muse before the previous track stops playing, to avoid waiting extra time beyond
        # the expected delay.
        next_track = self.track if delayed_prep else self._playback_config.upcoming_track()
        previous_track = None if first_prep else (self.previous_track if delayed_prep else self.track)
        spot_profile = self._run.muse.get_spot_profile(previous_track, next_track, self.last_track_failed, self.skip_track)
        self.muse_spot_profiles.append(spot_profile)
        if delayed_prep:
            spot_profile.immediate = True
            if not first_prep:
                Utils.log("Delayed preparation.")
            self._run.muse.prepare(spot_profile, self.callbacks.update_muse_text)
        else:
            Utils.start_thread(self._run.muse.prepare, use_asyncio=False, args=(spot_profile, self.callbacks.update_muse_text))

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
            if Globals.DELAY_TIME_SECONDS > 4:
                self.callbacks.track_details_callback(_("Sleeping for seconds") + ": " + str(Globals.DELAY_TIME_SECONDS))
            delay_timer = 0
            while not self.skip_delay and delay_timer < Globals.DELAY_TIME_SECONDS:
                sleep(0.5)
                delay_timer += 0.5
            if self.skip_delay:
                self.skip_delay = False

    def set_volume(self):
        mean_volume, max_volume = self.get_song_volume()
        volume = (Globals.DEFAULT_VOLUME_THRESHOLD + 30) if mean_volume < -50 else min(int(Globals.DEFAULT_VOLUME_THRESHOLD + (-1 * mean_volume)), 100)
        Utils.log(f"Mean volume: {mean_volume} Max volume: {max_volume} Setting volume to: {volume}")
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
        Utils.log("Skipping ahead to next track.")
        self.skip_track = True
        self.skip_delay = True

    def get_track_text_file(self):
        if self.track is None or self.track.is_invalid():
            return None
        return self.track.get_track_text_file()
