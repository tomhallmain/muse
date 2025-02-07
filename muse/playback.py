import platform
from random import randint
import time
import vlc

from muse.playback_config import PlaybackConfig
from utils.config import config
from utils.globals import Globals
from utils.utils import Utils
from utils.translations import I18N

_ = I18N._

INSTANCE = vlc.Instance("verbose=-2")

class Playback:

    @staticmethod
    def new_playback(override_dir=None, data_callbacks=None):
        config = PlaybackConfig.new_playback_config(override_dir=override_dir, data_callbacks=data_callbacks)
        return Playback(config, None, False)

    def __init__(self, playback_config, ui_callbacks=None, run=None):
        self.vlc_media_player = INSTANCE.media_player_new()
        self._playback_config = playback_config
        self.ui_callbacks = ui_callbacks
        self._run = run
        if run:
            self.muse = run.muse
            self.muse.set_get_playlist_callback(self._playback_config.get_list)
        else:
            self.muse = None
        self.is_paused = False
        self.skip_track = False
        self.skip_delay = False
        self.skip_grouping = False
        self.track = None
        self.previous_track = ""
        self.last_track_failed = False
        self.has_played_first_track = False
        self.count = 0
        self.muse_spot_profiles = []
        self.remaining_delay_seconds = Globals.DELAY_TIME_SECONDS
        # Keep track of grouping i.e. if shuffling by artist, album, composer etc
        self.old_grouping = None
        self.new_grouping = None

    def has_muse(self):
        return self._run and self._run.args.muse and self.muse is not None and self.muse.voice.can_speak

    def get_muse(self):
        if self.muse is None:
            raise Exception("No Muse instance found")
        return self.muse

    def get_track(self):
        self.previous_track = self.track
        self.track, self.old_grouping, self.new_grouping = self._playback_config.next_track(skip_grouping=self.skip_grouping)
        self.skip_grouping = False
        # print(f"Playback.get_track() - self.track = {self.track} {self.track.is_invalid()}")
        return self.track is not None and not self.track.is_invalid()

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
            self.register_new_song()
            self.vlc_media_player.play()
            time.sleep(0.5)
            while (self.vlc_media_player.is_playing() or self.is_paused) and not self.skip_track:
                time.sleep(0.5)
            self.vlc_media_player.stop()
        else:
            raise Exception("No tracks in playlist")

    def get_track_length(self):
        return round(float(vlc.MediaPlayer(self.track.filepath).get_length()) / 1000)

    def set_delay_seconds(self):
        track_length = self.get_track_length()
        random_buffer_threshold = round(float(track_length) / randint(5, 10))
        random_buffer = randint(0, random_buffer_threshold) * (1 if randint(0,1) == 1 else -1)
        self.remaining_delay_seconds = Globals.DELAY_TIME_SECONDS + random_buffer

    def run(self):
        assert self.vlc_media_player is not None
        if self.has_muse():
            self.get_muse().check_schedules()
        while self.get_track() and not self._run.is_cancelled:
            self.set_delay_seconds()
            self.get_muse().check_for_shutdowns()
            if self.has_muse():
                if not self.has_played_first_track or not self.get_muse().has_started_prep:
                    # First track, or if user skipped before end of last track
                    seconds_passed = self.prepare_muse(first_prep=not self.has_played_first_track, delayed_prep=True)
                    self.remaining_delay_seconds -= seconds_passed
                # TODO edge case when extension track has been assigned after the preparation for the previously expected upcoming track
                # TODO enable muse to be cancelled when user clicks Next
                # The user may have requested to skip the last track since the muse profile was created
                self.get_spot_profile().update_skip_previous_track_remark(self.skip_track)
                if self.get_spot_profile().is_going_to_say_something():
                    seconds_passed = self.get_muse().maybe_dj(self.get_spot_profile())
                    self.remaining_delay_seconds -= seconds_passed
                    self.register_new_song()
                    # self.muse.maybe_dj_prior(self.muse_spot_profile)
                    self.delay()
                    self.update_ui()
                else:
                    self.delay()
                    self.register_new_song()
            else:
                if self._run and self._run.args.muse and self._run.muse is not None:
                    Utils.log_yellow("No voice available due to import failure, skipping Muse.")
                if self.has_played_first_track:
                    self.delay()
                self.generate_silent_spot_profile()
                self.register_new_song()
            self.reset_muse()

            self.set_volume()
            self.last_track_failed = False
            self.is_paused = False
            self.skip_track = False

            self.vlc_media_player.play()
            time.sleep(0.5)
            cumulative_sleep_seconds = 0.5
            if not self.vlc_media_player.is_playing():
                self.last_track_failed = True
            while (self.vlc_media_player.is_playing() or self.is_paused) and not self.skip_track:
                time.sleep(0.5)
                cumulative_sleep_seconds += 0.5
                seconds_remaining = self.update_progress()
                if self.has_muse() and \
                        self.get_muse().ready_to_prepare(cumulative_sleep_seconds, seconds_remaining):
                    self.prepare_muse()

            self.vlc_media_player.stop()
            self.has_played_first_track = True
            if self.increment_count():
                break

    def update_progress(self):
        assert self.vlc_media_player is not None
        duration = self.vlc_media_player.get_length()
        current_time = self.vlc_media_player.get_time()
        if self.ui_callbacks is not None and self.ui_callbacks.update_progress_callback is not None:
            progress = int((current_time / duration) * 100) if duration > 0 else 0
            self.ui_callbacks.update_progress_callback(progress, current_time, duration)
        return duration - current_time

    def reset_muse(self):
        self.get_muse().reset()
        self.muse_spot_profiles.remove(self.get_spot_profile(self.track))

    def prepare_muse(self, first_prep=False, delayed_prep=False):
        # At the moment the local LLM and TTS models are not that fast, so need to start generation
        # for muse before the previous track stops playing, to avoid waiting extra time beyond
        # the expected delay.
        if delayed_prep:
            next_track = self.track
        else:
            next_track, self.old_grouping, self.new_grouping = self._playback_config.upcoming_track()
        previous_track = None if first_prep else (self.previous_track if delayed_prep else self.track)
        spot_profile = self.get_muse().get_spot_profile(previous_track, next_track, self.last_track_failed, self.skip_track,
                                                        self.old_grouping, self.new_grouping, self.get_grouping_type())
        self.muse_spot_profiles.append(spot_profile)
        start = time.time()
        if delayed_prep:
            spot_profile.immediate = True
            if not first_prep:
                Utils.log("Delayed preparation.")
            self.get_muse().prepare(spot_profile, self.ui_callbacks)
        else:
            Utils.start_thread(self.get_muse().prepare, use_asyncio=False, args=(spot_profile, self.ui_callbacks))
        return round(time.time() - start)

    def get_grouping_type(self):
        try:
            return self._playback_config.get_list().sort_type
        except AttributeError:
            return ""

    def generate_silent_spot_profile(self):
        previous_track = self.previous_track if self.has_played_first_track else None
        spot_profile = self.get_muse().get_spot_profile(previous_track, self.track, self.last_track_failed, self.skip_track)
        self.muse_spot_profiles.append(spot_profile)

    def register_new_song(self):
        assert self.track is not None
        Utils.log(f"Playing track file: {self.track.filepath}")
        self.vlc_media_player = vlc.MediaPlayer(self.track.filepath)
        if self.track.get_is_video():
            self.ensure_video_frame()
        self.update_ui()

    def ensure_video_frame(self):
        if not config.play_videos_in_separate_window:
            assert self.vlc_media_player is not None and self.ui_callbacks is not None
            # set the window id where to render VLC's video output
            if platform.system() == 'Windows':
                self.vlc_media_player.set_hwnd(self.ui_callbacks.get_media_frame_handle())
            else:
                self.vlc_media_player.set_xwindow(self.ui_callbacks.get_media_frame_handle()) # this line messes up windows

    def update_ui(self):
        if self.ui_callbacks is None:
            return
        if self.ui_callbacks.track_details_callback is not None:
            self.ui_callbacks.track_details_callback(self.track)
            self.ui_callbacks.update_next_up_callback("")
        if self.ui_callbacks.update_spot_profile_topics_text is not None:
            spot_profile = self.get_spot_profile()
            if self.ui_callbacks.update_next_up_callback is not None:
                self.ui_callbacks.update_next_up_callback("")
            if self.ui_callbacks.update_prior_track_callback is not None:
                self.ui_callbacks.update_prior_track_callback(spot_profile.get_previous_track_title())
            if self.ui_callbacks.update_spot_profile_topics_text is not None:
                self.ui_callbacks.update_spot_profile_topics_text(spot_profile.get_topic_text())
        if self.ui_callbacks.update_album_artwork is not None:
            self.ui_callbacks.update_album_artwork(image_filepath=self.track.get_album_artwork())

    def increment_count(self):
        if not self.skip_track:
            self.count += 1
        return bool(self._playback_config.total > -1 and self.count > self._playback_config.total)

    def delay(self):
        if self.has_played_first_track and not self.last_track_failed:
            if self.remaining_delay_seconds > 4 and self.ui_callbacks is not None:
                self.ui_callbacks.update_next_up_callback(_("Sleeping for seconds") + ": " + str(self.remaining_delay_seconds), no_title=True)
                # TODO set track text to "Upcoming track"
            delay_timer = 0
            while not self.skip_delay and delay_timer < self.remaining_delay_seconds:
                time.sleep(0.5)
                delay_timer += 0.5
            if self.skip_delay:
                self.skip_delay = False

    def set_volume(self):
        mean_volume, max_volume = self.track.get_volume()
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

    def next_grouping(self):
        self.vlc_media_player.stop()
        Utils.log("Skipping ahead to next track.")
        self.skip_track = True
        self.skip_delay = True
        self.skip_grouping = True

    def get_track_text_file(self):
        if self.track is None or self.track.is_invalid():
            return None
        return self.track.get_track_text_file()
