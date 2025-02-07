
import random


from utils.config import config
from utils.translations import I18N

_ = I18N._


class MuseSpotProfile:
    chance_speak_after_track = config.muse_config["chance_speak_after_track"]
    chance_speak_before_track = config.muse_config["chance_speak_before_track"]
    chance_speak_about_other_topics = config.muse_config["chance_speak_about_other_topics"]

    def __init__(self, previous_track, track, last_track_failed, skip_track, old_grouping, new_grouping, grouping_type, get_previous_spot_profile_callback=None):
        self.previous_track = previous_track
        self.track = track
        self.get_previous_spot_profile_callback = get_previous_spot_profile_callback
        # say good day on the second spot (i.e. first spot after the first track)
        self.say_good_day = previous_track is not None and self.get_previous_spot_profile().previous_track is None and random.random() < 0.5
        # Speak about the previous track as long as there is one.
        self.speak_about_prior_track = previous_track is not None and (previous_track._is_extended or random.random() < self.chance_speak_after_track)
        # Speak about the upcoming track, even if it's the first one.
        self.speak_about_upcoming_track = track is not None and track._is_extended or random.random() < self.chance_speak_before_track
        # Skip talking about random stuff if we just started playing, to avoid a long delay.
        self.talk_about_something = previous_track is not None and random.random() < self.chance_speak_about_other_topics
        self.has_already_spoken = False
        self.last_track_failed = last_track_failed
        self.skip_previous_track_remark = last_track_failed or skip_track
        self.immediate = False
        self.is_prepared = False
        self.topic = None
        self.topic_translated = None
        # If the playlist has been sorted by a grouping (e.g. artist, album, composer etc.)
        # the DJ needs to keep track of it and be eager let us know when there a change.
        self.old_grouping = old_grouping
        self.new_grouping = new_grouping
        self.grouping_type = grouping_type
        if old_grouping is not None and new_grouping is not None and old_grouping != new_grouping:
            self.speak_about_prior_group = previous_track is not None and random.random() < 0.5
            self.speak_about_upcoming_group = track is not None and random.random() < 0.9
        else:
            self.speak_about_prior_group = False
            self.speak_about_upcoming_group = False

    def get_previous_spot_profile(self, idx=0):
        if self.get_previous_spot_profile_callback is None:
            raise Exception("Previous spot profile callback was not set properly")
        return self.get_previous_spot_profile_callback(idx=idx)

    def is_going_to_say_something(self):
        return self.say_good_day or self.speak_about_prior_track or self.speak_about_upcoming_track or self.talk_about_something or self.speak_about_prior_group or self.speak_about_upcoming_group

    def update_skip_previous_track_remark(self, skip_track):
        self.skip_previous_track_remark = self.skip_previous_track_remark or skip_track

    def get_upcoming_track_title(self) -> None | str:
        return None if self.track is None else self.track.title

    def get_previous_track_title(self) -> None | str:
        return None if self.previous_track is None else self.previous_track.title

    def get_topic_text(self) -> str:
        if self.talk_about_something and self.topic_translated is not None:
            return _("Talking about: ") + self.topic_translated
        return ""

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
