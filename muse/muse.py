
import datetime
import random
import time

from extensions.hacker_news_souper import HackerNewsSouper
from extensions.news_api import NewsAPI
from extensions.open_weather import OpenWeatherAPI
from extensions.wiki_opensearch_api import WikiOpenSearchAPI
from extensions.llm import LLM
from muse.playback import Playback
from muse.prompter import Prompter
from muse.voice import Voice
from utils.config import config
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._


class MuseSpotProfile:
    chance_speak_after_track = config.muse_config["chance_speak_after_track"]
    chance_speak_before_track = config.muse_config["chance_speak_before_track"]
    chance_speak_about_other_topics = config.muse_config["chance_speak_about_other_topics"]

    def __init__(self, previous_track, track, last_track_failed, skip_track):
        self.previous_track = previous_track
        self.track = track
        self.speak_about_prior_track = previous_track is not None and (previous_track._is_extended or random.random() < self.chance_speak_after_track)
        self.speak_about_upcoming_track = track._is_extended or random.random() < self.chance_speak_before_track
        self.talk_about_something = random.random() < self.chance_speak_about_other_topics
        self.has_already_spoken = False
        self.last_track_failed = last_track_failed
        self.skip_previous_track_remark = last_track_failed or skip_track
        self.immediate = False
        self.is_prepared = False
        self.topic = None
        self.topic_translated = None

    def is_going_to_say_something(self):
        return self.speak_about_prior_track or self.speak_about_upcoming_track or self.talk_about_something

    def update_skip_previous_track_remark(self, skip_track):
        self.skip_previous_track_remark = self.skip_previous_track_remark or skip_track

    def get_ui_text(self):
        if self.track is None:
            raise Exception("Track is None")
        out = _("Track: ") + self.track.title
        if self.previous_track is not None:
            out += "\n" + _("Previous Track: ") + self.previous_track.title
        if self.topic_translated is not None:
            out += "\n" + _("Talking about: ") + self.topic_translated
        return out

    def __str__(self):
        out = _("Track: ") + self.track.title if self.track is not None else _("No track")
        out += "\n" + _("Previous Track: ") + self.previous_track.title if self.previous_track is not None else "\n" + _("No previous track")
        if self.speak_about_prior_track:
            out += "\n - " + _("Speaking about prior track")
        if self.speak_about_upcoming_track:
            out += "\n - " + _("Speaking about upcoming track")
        if self.talk_about_something:
            out += "\n - " + _("Talking about something")
        return out


class Muse:
    enable_preparation = config.muse_config["enable_preparation"]
    preparation_starts_minutes_from_end = float(config.muse_config["preparation_starts_minutes_from_end"])
    preparation_starts_after_seconds_sleep = int(config.muse_config["preparation_starts_after_seconds_sleep"])

    def __init__(self, args):
        self.args = args
        self.llm = LLM()
        self.voice = Voice()
        self.open_weather_api = OpenWeatherAPI()
        self.news_api = NewsAPI()
        self.hacker_news_souper = HackerNewsSouper()
        self.prompter = Prompter()
        self.wiki_search = WikiOpenSearchAPI()
        self.has_started_prep = False
        self.post_id = "post"
        self.prior_id = "prior"

    def get_spot_profile(self, previous_track=None, track=None, last_track_failed=False, skip_track=False):
        return MuseSpotProfile(previous_track, track, last_track_failed, skip_track)

    def say_at_some_point(self, text, spot_profile):
        if spot_profile.immediate:
            self.voice.say(text)
        else:
            self.voice.prepare_to_say(text)

    def ready_to_prepare(self, cumulative_sleep_seconds, seconds_remaining):
        return Muse.enable_preparation \
            and cumulative_sleep_seconds > Muse.preparation_starts_after_seconds_sleep \
            and not self.has_started_prep \
            and seconds_remaining < int(Muse.preparation_starts_minutes_from_end * 60 * 1000)

    def prepare(self, spot_profile, update_ui_callback=None):
        # TODO Lock both TTS runner queues here
        self.has_started_prep = True
        self.set_topic(spot_profile)
        if update_ui_callback is not None:
            update_ui_callback(spot_profile.get_ui_text())
        if spot_profile.is_going_to_say_something():
            Utils.log_debug(f"Preparing muse:\n{spot_profile}")
            if not spot_profile.skip_previous_track_remark:
                self.maybe_prep_dj_post(spot_profile)
            self.maybe_prep_dj_prior(spot_profile)
        spot_profile.is_prepared = True

    def maybe_prep_dj_prior(self, spot_profile):
        # TODO quality info for songs
        if spot_profile.speak_about_upcoming_track:
            self.speak_about_upcoming_track(spot_profile)
            spot_profile.has_already_spoken = True

        if spot_profile.talk_about_something:
            self.talk_about_something(spot_profile)

    def maybe_dj(self, spot_profile):
        # TODO quality info for songs
        # Release lock on TTS runner for "prior" queue
        self.voice.finish_speaking()
        while not spot_profile.is_prepared:
            time.sleep(1)
            self.voice.finish_speaking()

    def reset(self):
        self.has_started_prep = False

    def maybe_prep_dj_post(self, spot_profile):
        # TODO quality info for songs
        if spot_profile.speak_about_prior_track:
            self.speak_about_previous_track(spot_profile)

    # def maybe_dj_post(self, spot_profile):
    #     # Release lock on TTS runner for "post" queue
    #     if spot_profile.skip_previous_track_remark:
    #         # TODO cancel the pending "post" queue
    #         return
    #     pass

    def speak_about_previous_track(self, spot_profile):
        previous_track = spot_profile.previous_track
        dj_remark = _("That was \"{0}\" in \"{1}\"").format(previous_track.readable_title(), previous_track.readable_album())
        if previous_track.artist is not None and previous_track.artist!= "":
            dj_remark += _(" by \"{0}\".").format(previous_track.readable_artist())
        else:
            dj_remark += "."
        if previous_track._is_extended and random.random() < 0.8:
            if random.random() < 0.5:
                dj_remark +=  " " + _("That was a new track. How'd you like that?")
            else:
                dj_remark = _("That was a new one. How'd you like it?") + " " + dj_remark
        self.say_at_some_point(dj_remark, spot_profile)

    def speak_about_upcoming_track(self, spot_profile):
        track = spot_profile.track
        if spot_profile.previous_track is None:
            dj_remark = _("To start, we'll be playing: \"{0}\" from \"{1}\"").format(track.readable_title(), track.readable_album())
        else:
            dj_remark = _("Next up, we'll be playing: \"{0}\" from \"{1}\"").format(track.readable_title(), track.readable_album())
        if track.artist is not None and track.artist!= "":
            dj_remark += _(" by \"{0}\".").format(track.readable_artist())
        else:
            dj_remark += "."
        if track._is_extended and random.random() < 0.8:
            dj_remark += " " + _("This one is a new track.")
        self.say_at_some_point(dj_remark, spot_profile)

    def get_topic(self, previous_track, excluded_topics=[]):
        if Prompter.over_n_hours_since_last("weather", n_hours=24):
            topic = "weather"
            Utils.log("Talking about the weather")
        elif Prompter.over_n_hours_since_last("news", n_hours=96):
            topic = "news"
            Utils.log("Talking about the news")
        elif Prompter.over_n_hours_since_last("hackernews", n_hours=96):
            topic = "hackernews"
            Utils.log("Talking about the news")
        else:
            topic = Prompter.get_oldest_topic(excluded_topics=excluded_topics)
            Utils.log("Talking about topic: " + topic)

        if topic in ["hackernews", "news"] and Prompter.under_n_hours_since_last(topic, n_hours=14):
            if topic not in excluded_topics:
                excluded_topics.append(topic)
        
        if previous_track is None and topic == "track_context_post":
            if topic not in excluded_topics:
                excluded_topics.append(topic)

        while topic in excluded_topics:
            topic = self.get_topic(previous_track, excluded_topics=excluded_topics)

        return topic

    def set_topic(self, spot_profile):
        spot_profile.topic = self.get_topic(spot_profile.previous_track)
        spot_profile.topic_translated = self.prompter.translate_topic(spot_profile.topic)

    def talk_about_something(self, spot_profile):
        if (spot_profile.has_already_spoken and random.random() < 0.75) \
                or (not spot_profile.has_already_spoken and random.random() < 0.6):
            if spot_profile.skip_previous_track_remark or spot_profile.previous_track is None:
                remark = _("First let's hear about {0}").format(spot_profile.topic_translated)
            else:
                remark = _("But first, let's hear about {0}.").format(spot_profile.topic_translated)
            self.say_at_some_point(remark, spot_profile)

        topic = spot_profile.topic

        if topic == "weather":
            self.talk_about_weather(config.open_weather_city, spot_profile)
        elif topic in ["news", "hackernews"]:
            self.talk_about_news(topic, spot_profile)
        elif topic == "joke":
            self.tell_a_joke(spot_profile)
        elif topic == "fact":
            self.share_a_fact(spot_profile)
        elif topic == "truth_and_lie":
            self.play_two_truths_and_one_lie(spot_profile)
        elif topic == "fable":
            self.share_a_fable(spot_profile)
        elif topic == "aphorism":
            self.share_an_aphorism(spot_profile)
        elif topic == "poem":
            self.share_a_poem(spot_profile)
        elif topic == "quote":
            self.share_a_quote(spot_profile)
        elif topic == "tongue_twister":
            self.share_a_tongue_twister(spot_profile)
        elif topic == "calendar":
            self.talk_about_the_calendar(spot_profile)
        elif topic == "motivation":
            self.share_a_motivational_message(spot_profile)
        elif topic =="track_context_prior":
            self.talk_about_track_context(spot_profile.track, spot_profile)
        elif topic =="track_context_post":
            self.talk_about_track_context(spot_profile.previous_track, spot_profile)
        elif topic == "random_wiki_article":
            self.talk_about_random_wiki_article(spot_profile)
        elif topic == "funny_story":
            self.share_a_funny_story(spot_profile)
        else:
            Utils.log_yellow("Unhandled topic: " + topic)

    def talk_about_weather(self, city="Washington", spot_profile=None):
        weather = self.open_weather_api.get_weather_for_city(city)
        Utils.log(weather)
        weather_summary = self.llm.generate_response(
            self.prompter.get_prompt("weather") + city + ":\n\n" + str(weather))
        self.say_at_some_point(weather_summary, spot_profile)

    def talk_about_news(self, topic=None, spot_profile=None):
        if topic == "hackernews":
            news = self.hacker_news_souper.get_news(total=15)
        else:
            news = self.news_api.get_news(topic=topic)
        news_summary = self.llm.generate_response(
            self.prompter.get_prompt(topic) + "\n\n" + str(news))
        self.say_at_some_point(news_summary, spot_profile)

    def tell_a_joke(self, spot_profile):
        joke = self.llm.generate_response(self.prompter.get_prompt("joke"))
        self.say_at_some_point(joke, spot_profile)

    def share_a_fact(self, spot_profile):
        fact = self.llm.generate_response(self.prompter.get_prompt("fact"))
        self.say_at_some_point(fact, spot_profile)

    def play_two_truths_and_one_lie(self, spot_profile):
        resp = self.llm.generate_response(self.prompter.get_prompt("truth_and_lie"))
        self.say_at_some_point(resp, spot_profile)

    def share_a_fable(self, spot_profile):
        fable = self.llm.generate_response(self.prompter.get_prompt("fable"))
        self.say_at_some_point(fable, spot_profile)

    def share_an_aphorism(self, spot_profile):
        aphorism = self.llm.generate_response(self.prompter.get_prompt("aphorism"))
        self.say_at_some_point(aphorism, spot_profile)

    def share_a_poem(self, spot_profile):
        poem = self.llm.generate_response(self.prompter.get_prompt("poem"))
        self.say_at_some_point(poem, spot_profile)
    
    def share_a_quote(self, spot_profile):
        quote = self.llm.generate_response(self.prompter.get_prompt("quote"))
        self.say_at_some_point(quote, spot_profile)

    def share_a_tongue_twister(self, spot_profile):
        # TODO need to fix this up for the prepare case
        if config.tongue_twisters_dir is None or config.tongue_twisters_dir == "":
            raise Exception("No tongue twister directory specified")
        Utils.log(f"Playing tongue twister from {config.tongue_twisters_dir}")
        playback = Playback.new_playback(config.tongue_twisters_dir)
        Prompter.update_history("tongue_twister")
        try:
            playback.play_one_song()
        except Exception as e:
            Utils.log_red("Error playing tongue twister: " + str(e))
            Utils.log(playback._playback_config.directories)
            Utils.log(playback._playback_config.list)

    def talk_about_the_calendar(self, spot_profile):
        # TODO talk about tomorrow as well, or the upcoming week
        today = datetime.datetime.today()
        prompt = self.prompter.get_prompt("calendar")
        prompt = prompt.replace("DATE", today.strftime("%A %B %d %Y"))
        prompt = prompt.replace("TIME", today.strftime("%H:%M"))
        calendar = self.llm.generate_response(prompt)
        self.say_at_some_point(calendar, spot_profile)

    def share_a_motivational_message(self, spot_profile):
        motivation = self.llm.generate_response(self.prompter.get_prompt("motivation"))
        self.say_at_some_point(motivation, spot_profile)

    def talk_about_track_context(self, track, spot_profile):
        if spot_profile.track is None or spot_profile.topic is None:
            raise Exception("No track or topic specified")
        prompt = self.prompter.get_prompt(spot_profile.topic)
        prompt = prompt.replace("TRACK_DETAILS", track.get_track_details())
        track_context = self.llm.generate_response(prompt)
        self.say_at_some_point(track_context, spot_profile)

    def talk_about_random_wiki_article(self, spot_profile):
        article = self.wiki_search.random_wiki()
        if article is None or not article.is_valid():
            Utils.log("No article found")
            return
        prompt = self.prompter.get_prompt("random_wiki_article")
        prompt = prompt.replace("ARTICLE", str(article)[:500])
        summary = self.llm.generate_response(prompt)
        self.say_at_some_point(summary, spot_profile)

    def share_a_funny_story(self, spot_profile):
        funny_story = self.llm.generate_response(self.prompter.get_prompt("funny_story"))
        self.say_at_some_point(funny_story, spot_profile)
