import platform
from random import randint
import time
import traceback
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
        self.did_advance = False # jumped ahead in the playlist occurred due to track splitting errors
        self.places_from_current = -1 # this many tracks were jumped in the process
        self.has_attempted_track_split = False
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
        if self.did_advance:
            self.track, self.old_grouping, self.new_grouping = self._playback_config.next_track(
                skip_grouping=self.skip_grouping, places_from_current=self.places_from_current)
        else:
            self.track, self.old_grouping, self.new_grouping = self._playback_config.next_track(skip_grouping=self.skip_grouping)
        self.skip_grouping = False
        if not self.has_attempted_track_split:
            self.track, self.did_advance, self.places_from_current = self.ensure_splittable_track(self.track, True)
        if self.has_muse() and self.get_muse().has_started_prep:
            # TODO this seems a bit hacky and is probably not covering all cases.
            self.has_attempted_track_split = False
        return self.track is not None and not self.track.is_invalid()

    def get_song_quality_info(self):
        # TODO: Get info like bit rate, mono vs stereo, possibly try to infer if it's AI or not
        pass

    def get_spot_profile(self, track=None):
        if track is None:
            track = self.track
        for profile in self.muse_spot_profiles:
            if track == profile.track:
                return profile
        # It is possible for the spot profile to not have been prepared for the next track if the 
        # next track was a late addition due to a forced playback extension. In this case, need
        # to overwrite the "Next" track in the previously generated spot profile with the new one
        # This can also happen if the user selected to skip to a different group.
        for profile in self.muse_spot_profiles:
            if profile.previous_track == self.previous_track:
                profile.track = track
                profile.set_track_overwritten_time()
                return profile
        raise Exception(f"No spot profile found for track: {track}")

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

    def get_track_length(self, track=None):
        if track is None:
            track = self.track
        assert track is not None
        # TODO figure out why VLC parsing fails, see temp_test_length.py
        # length = round(float(vlc.MediaPlayer(track.filepath).get_length()) / 1000)
        # track.set_track_length(length)
        length = track.get_track_length()
        Utils.log(f"Track length: {length} seconds - {track}")
        return length

    def set_delay_seconds(self):
        track_length = self.get_track_length()
        random_buffer_threshold = max(round(float(track_length) / randint(5, 10)), 40)
        random_buffer = randint(0, random_buffer_threshold) * (1 if randint(0,1) == 1 else -1)
        self.remaining_delay_seconds = min(max(1, Globals.DELAY_TIME_SECONDS + random_buffer), Globals.DELAY_TIME_SECONDS * 1.5)

    def run(self):
        assert self.vlc_media_player is not None
        if self.has_muse():
            self.get_muse().check_schedules()
        while self.get_track() and not self._run.is_cancelled:
            self.set_delay_seconds()
            self.get_muse().check_for_shutdowns()
            if self.has_muse():
                if not self.has_played_first_track:
                    self.update_ui_art_for_muse()
                if not self.has_played_first_track or not self.get_muse().has_started_prep:
                    # First track, or if user skipped before end of last track
                    seconds_passed = self.prepare_muse(delayed_prep=True)
                    self.remaining_delay_seconds -= seconds_passed
                elif self.get_spot_profile().needs_repreparation():
                    Utils.log("Spot profile track was overwritten and will be reprepared.")
#                    self.muse.cancel_preparation()
#                    self.spot_profile.reset()
                    seconds_passed = self.prepare_muse(delayed_prep=True)
                    self.remaining_delay_seconds -= seconds_passed
                # TODO edge case when extension track has been assigned after the preparation for the previously expected upcoming track
                # TODO enable muse to be cancelled when user clicks Next
                # The user may have requested to skip the last track since the muse profile was created
                self.get_spot_profile().update_skip_previous_track_remark(self.skip_track)
                if self.get_spot_profile().is_going_to_say_something():
                    self.update_ui_art_for_muse()
                    seconds_passed = self.get_muse().maybe_dj(self.get_spot_profile())
                    self.remaining_delay_seconds -= seconds_passed
                    self.register_new_song()
                    # self.muse.maybe_dj_prior(self.muse_spot_profile)
                    self.delay()
                    self.update_ui()
                else:
                    self.update_ui_art_for_silence()
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

    def prepare_muse(self, delayed_prep=False):
        # At the moment the local LLM and TTS models are not that fast, so need to start generation
        # for muse before the previous track stops playing, to avoid waiting extra time beyond
        # the expected delay.
        if delayed_prep:
            next_track = self.track
        else:
            next_track, self.old_grouping, self.new_grouping = self._playback_config.upcoming_track()

        if not self.has_attempted_track_split: # this is alternately covered by self.get_track()
            next_track, self.did_advance, self.places_from_current = self.ensure_splittable_track(next_track, delayed_prep)

        previous_track = (self.previous_track if delayed_prep else self.track) if self.has_played_first_track else None
        spot_profile = self.get_muse().get_spot_profile(previous_track, next_track, self.last_track_failed, self.skip_track,
                                                        self.old_grouping, self.new_grouping, self.get_grouping_type())
        self.muse_spot_profiles.append(spot_profile)

        # Prepare the spot using the spot profile
        start = time.time()
        if delayed_prep:
            spot_profile.immediate = True
            if self.has_played_first_track:
                Utils.log("Delayed preparation.")
            self.get_muse().prepare(spot_profile, self.ui_callbacks)
        else:
            Utils.start_thread(self.get_muse().prepare, use_asyncio=False, args=(spot_profile, self.ui_callbacks))
        if delayed_prep:
            self.has_attempted_track_split = False
        return round(time.time() - start)

    def ensure_splittable_track(self, next_track, delayed_prep):
        # Handle track splitting
        next_track, did_split, split_failed = self.split_track_if_needed(next_track)
        did_advance = bool(did_split)
        places_from_current = 0
        if did_split and split_failed:
            places_from_current = 1 if delayed_prep else 2
            while did_split and split_failed:
                next_track, self.old_grouping, self.new_grouping = self._playback_config.upcoming_track(places_from_current=places_from_current)
                next_track, did_split, split_failed = self.split_track_if_needed(next_track, delayed_prep=delayed_prep)
                places_from_current += 1
                if split_failed and places_from_current > (1 if delayed_prep else 5):
                    Utils.log_red("Failed to split too many tracks in queue!")
                    break
            places_from_current -= 1
        self.has_attempted_track_split = True
        return next_track, did_advance, places_from_current

    def split_track_if_needed(self, track, delayed_prep=False):
        if not self._playback_config.enable_long_track_splitting:
            Utils.log_debug("Split track config option not set")
            return track, False, False
        track_length = self.get_track_length(track=track)
        cutoff_seconds = self._playback_config.long_track_splitting_time_cutoff_minutes * 60
        offset = 0
        if track_length > cutoff_seconds:
            try:
                Utils.log(f"Trying to split track: {track}")
                track = self._playback_config.split_track(track=track, do_split_override=True, offset=offset)
                return track, True, False
            except Exception as e:
                traceback.print_exc()
                Utils.log_yellow(f"Error splitting track: {e}")
                return track, True, True
        elif int(track_length) == -1.0 or int(track_length) == 0:
            Utils.log_yellow(f"Failed to set track length: {track}")
        return track, False, False

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
            album_artwork = self.track.get_album_artwork()
            if album_artwork is None and not self.track.get_is_video():
                album_artwork = self._get_random_image_asset(filename_filter="record")
            self.ui_callbacks.update_album_artwork(image_filepath=album_artwork)

    def update_ui_art_for_muse(self):
        if self.ui_callbacks.update_album_artwork is not None:
            album_artwork = self._get_random_image_asset(filename_filter="muse")
            self.ui_callbacks.update_album_artwork(image_filepath=album_artwork)

    def update_ui_art_for_silence(self):
        pass

    def _get_random_image_asset(self, filename_filter="record"):
        if not filename_filter.endswith(".png"):
            filename_filter += ".*\\.png"
        filenames = Utils.get_assets_filenames(filename_filter=filename_filter)
        return Utils.get_asset(filenames[randint(0, len(filenames)-1)])

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
        Utils.log("Skipping ahead to next track grouping.")
        self.skip_track = True
        self.skip_delay = True
        self.skip_grouping = True

    def get_current_track_artwork(self):
        if self.track is None or self.track.is_invalid():
            raise Exception("Track is invalid.")
        return self.track.get_album_artwork(filename="copy")

    def get_track_text_file(self):
        if self.track is None or self.track.is_invalid():
            return None
        return self.track.get_track_text_file()
