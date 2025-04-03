import random
import time

from utils.config import config
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._


class MuseSpotProfile:
    chance_speak_after_track = config.muse_config["chance_speak_after_track"]
    chance_speak_before_track = config.muse_config["chance_speak_before_track"]
    topic_discussion_chance_factor = config.muse_config["topic_discussion_chance_factor"]
    min_seconds_between_spots = config.muse_config["min_seconds_between_spots"]

    def __init__(self, previous_track, track, last_track_failed, skip_track, old_grouping, new_grouping, grouping_type, get_previous_spot_profile_callback=None):
        self.previous_track = previous_track
        self.track = track
        self.track_overwritten_time = None
        self.preparation_time = None
        self.creation_time = time.time()
        self.get_previous_spot_profile_callback = get_previous_spot_profile_callback
        # say good day on the second spot (i.e. first spot after the first track)
        self.say_good_day = previous_track is not None and self.get_previous_spot_profile().previous_track is None and random.random() < 0.5
        # Speak about the previous track as long as there is one.
        self.speak_about_prior_track = previous_track is not None and (previous_track._is_extended or random.random() < self.chance_speak_after_track)
        # Speak about the upcoming track, even if it's the first one.
        self.speak_about_upcoming_track = track is not None and track._is_extended or random.random() < self.chance_speak_before_track
        # Track whether this spot profile resulted in actual speech
        self.was_spoken = False
        # Modify the talk_about_something probability calculation
        if previous_track is not None:
            base_chance = self.topic_discussion_chance_factor
            previous_profile = self.get_last_spoken_profile()
            time_since_last = self.get_time() - previous_profile.get_time() if previous_profile else self.min_seconds_between_spots
            # Increase probability up to 4x base chance after 15 minutes of silence
            # Use minutes instead of seconds for more meaningful adjustment
            minutes_since_last = time_since_last / 60
            adjusted_chance = min(base_chance * 4, base_chance * (1 + minutes_since_last / 15))
            self.talk_about_something = random.random() < adjusted_chance
            print(f"Talk about something: {self.talk_about_something}, base chance: {base_chance}, adjusted chance: {adjusted_chance}, minutes since last: {minutes_since_last}, previous profile time: {previous_profile.get_time() if previous_profile else 'None'}, current time: {self.creation_time}")
        else:
            # Skip talking about random stuff if we just started playing, to avoid a long delay.
            self.talk_about_something = False
        self.has_already_spoken = False
        self.last_track_failed = last_track_failed
        self.skip_previous_track_remark = last_track_failed or skip_track
        self.immediate = False
        self.is_prepared = False
        self.topic = None
        self.topic_translated = None
        # If the playlist has been sorted by a grouping (e.g. artist, album, composer etc.)
        # the DJ needs to keep track of it and be eager to let us know when there a change.
        self.old_grouping = old_grouping
        self.new_grouping = new_grouping
        self.grouping_type = grouping_type
        if old_grouping is not None and new_grouping is not None and old_grouping != new_grouping:
            self.speak_about_prior_group = previous_track is not None and random.random() < 0.5
            self.speak_about_upcoming_group = track is not None and random.random() < 0.9
        else:
            self.speak_about_prior_group = False
            self.speak_about_upcoming_group = False
        self.override_time_restriction = self.speak_about_prior_track and previous_track._is_extended or self.speak_about_upcoming_track and track._is_extended

    def get_previous_spot_profile(self, idx=0):
        """Get the last spot profile that was actually spoken.

        NOTE: Currently this is set during preparation but at some point it could be a callback via the Muse Voice instance."""
        if self.get_previous_spot_profile_callback is None:
            raise Exception("Previous spot profile callback was not set properly")
        Utils.log_debug(f"Getting previous spot profile: idx={idx}, creation_time={self.creation_time}")
        return self.get_previous_spot_profile_callback(idx=idx, creation_time=self.creation_time)

    def get_time(self):
        # The spot profile may not have been prepared yet, so use creation time in this case.
        return self.creation_time if self.preparation_time is None else self.preparation_time

    def is_going_to_say_something(self):
        if self.say_good_day or self.speak_about_prior_group or self.speak_about_upcoming_group:
            return True
        no_time_restriction = self.last_spot_profile_more_than_seconds(MuseSpotProfile.min_seconds_between_spots)
        if not no_time_restriction:
            no_time_restriction = self.override_time_restriction
            if no_time_restriction:
                Utils.log("Overriding time restriction on spot profile due to library extension")
            else:
                Utils.log("Time restriction applied to current spot profile preparation")
        return no_time_restriction and (self.speak_about_prior_track or self.speak_about_upcoming_track or self.talk_about_something)

    def update_skip_previous_track_remark(self, skip_track):
        self.skip_previous_track_remark = self.skip_previous_track_remark or skip_track

    def get_upcoming_track_title(self) -> None | str:
        return None if self.track is None else self.track.title

    def get_previous_track_title(self) -> None | str:
        return None if self.previous_track is None else self.previous_track.title

    def set_track_overwritten_time(self):
        self.track_overwritten_time = time.time()

    def set_preparation_time(self):
        self.preparation_time = time.time()

    def needs_repreparation(self):
        return self.is_going_to_say_something() and self.track_overwritten_time is not None and \
                (not self.is_prepared or self.track_overwritten_time > self.preparation_time)

    def get_topic_text(self) -> str:
        if self.talk_about_something and self.topic_translated is not None:
            return _("Talking about: ") + self.topic_translated
        return ""

    def reset(self):
        self.is_prepared = False
        self.preparation_time = None
        self.track_overwritten_time = None

    def __str__(self):
        out = _("Track: ") + self.track.title if self.track is not None else _("No track")
        out += "\n" + _("Previous Track: ") + self.previous_track.title if self.previous_track is not None else "\n" + _("No previous track")
        if self.speak_about_prior_track or self.speak_about_prior_group:
            out += "\n - " + _("Speaking about prior track")
        if self.speak_about_upcoming_track or self.speak_about_upcoming_group:
            out += "\n - " + _("Speaking about upcoming track")
        if self.talk_about_something:
            out += "\n - " + _("Talking about something")
        return out

    def get_last_spoken_profile(self):
        """Get the most recent spot profile where the DJ actually spoke.
        
        Returns:
            MuseSpotProfile or None: The most recent spot profile where was_spoken is True, or None if none found
        """
        Utils.log_debug("Starting get_last_spoken_profile")
        profile = self.get_previous_spot_profile()
        idx = 1
        max_iterations = 100  # Failsafe to prevent infinite loops
        iterations = 0
        
        while profile is not None and not profile.was_spoken:
            Utils.log_debug(f"Looking for spoken profile: idx={idx}, was_spoken={profile.was_spoken}")
            idx += 1
            profile = self.get_previous_spot_profile(idx=idx)
            iterations += 1
            if iterations >= max_iterations:
                Utils.log_error(f"Failsafe triggered: get_last_spoken_profile exceeded {max_iterations} iterations")
                return None
                
        Utils.log_debug(f"Found last spoken profile: {profile is not None} {profile.get_time() if profile else ''}")
        return profile

    def last_spot_profile_more_than_seconds(self, seconds=min_seconds_between_spots):
        """Check if enough time has passed since the last spot profile where the DJ spoke."""
        current_time = time.time()
        last_profile = self.get_last_spoken_profile()
        if last_profile is None:
            return True
        return (current_time - last_profile.get_time()) > seconds
