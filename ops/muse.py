
import datetime
import random

from extensions.hacker_news_souper import HackerNewsSouper
from extensions.news_api import NewsAPI
from extensions.open_weather import OpenWeatherAPI
from extensions.llm import LLM
from ops.playback import Playback
from ops.prompter import Prompter
from ops.voice import Voice
from utils.config import config
from utils.translations import I18N

_ = I18N._


class Muse:

    def __init__(self, args):
        self.args = args
        self.llm = LLM()
        self.voice = Voice()
        self.open_weather_api = OpenWeatherAPI()
        self.news_api = NewsAPI()
        self.hacker_news_souper = HackerNewsSouper()
        self.prompter = Prompter()

    def maybe_dj(self, track, previous_track, skip_previous_track_remark=False):
        # TODO quality info for songs
        # TODO i18n
        has_already_spoken = False
        if not skip_previous_track_remark and previous_track != None and random.random() < 0.2:
            dj_remark = _("That was \"{0}\" in \"{1}\"").format(previous_track.readable_title(), previous_track.readable_album())
            if previous_track.artist is not None and previous_track.artist!= "":
                dj_remark += _(" by \"{0}\".").format(previous_track.readable_artist())
            else:
                dj_remark += "."
            self.voice.say(dj_remark)
        if random.random() < 0.3:
            if previous_track is None:
                dj_remark = _("To start, we'll be playing: \"{0}\" from \"{1}\"").format(track.readable_title(), track.readable_album())
            else:
                dj_remark = _("Next up, we'll be playing: \"{0}\" from \"{1}\"").format(track.readable_title(), track.readable_album())
            if track.artist is not None and track.artist!= "":
                dj_remark += _(" by \"{0}\".").format(track.readable_artist())
            else:
                dj_remark += "."
            self.voice.say(dj_remark)
            has_already_spoken = True
        if random.random() < 0.2:
            self.talk_about_something(previous_track, has_already_spoken, skip_previous_track_remark)

    def get_topic(self, excluded_topics=[]):
        if Prompter.over_n_hours_since_last("weather", n_hours=24):
            topic = "weather"
            print("Talking about the weather")
        elif Prompter.over_n_hours_since_last("news", n_hours=96):
            topic = "news"
            print("Talking about the news")
        elif Prompter.over_n_hours_since_last("hackernews", n_hours=96):
            topic = "hackernews"
            print("Talking about the news")
        else:
            topic = Prompter.get_oldest_topic(excluded_topics)
            print("Talking about topic: " + topic)

        while topic in ["hackernews", "news"] and Prompter.under_n_hours_since_last(topic, n_hours=14):
            if topic not in excluded_topics:
                excluded_topics.append(topic)
            topic = self.get_topic(excluded_topics=excluded_topics)

        return topic

    def talk_about_something(self, previous_track=None, has_already_spoken=False, skip_previous_track_remark=False):
        topic = self.get_topic()

        if (has_already_spoken and random.random() < 0.75) or (not has_already_spoken and random.random() < 0.6):
            if skip_previous_track_remark or previous_track is None:
                if True:
                    remark = "Zunächst zum Thema „{0}“.".format(topic)
                else:
                    remark = _("First let's hear about {0}").format(topic)
            else:
                if True:
                    remark = "Doch zunächst zum Thema „{0}“.".format(topic)
                else:
                    remark = _("But first, let's hear about {0}.").format(topic)
                self.voice.say(remark)

        if topic == "weather":
            self.talk_about_weather()
        elif topic in ["news", "hackernews"]:
            self.talk_about_news(topic)
        elif topic == "joke":
            self.tell_a_joke()
        elif topic == "fact":
            self.share_a_fact()
        elif topic == "truth_and_lie":
            self.play_two_truths_and_one_lie()
        elif topic == "fable":
            self.share_a_fable()
        elif topic == "aphorism":
            self.share_an_aphorism()
        elif topic == "poem":
            self.share_a_poem()
        elif topic == "quote":
            self.share_a_quote()
        elif topic == "tongue_twister":
            self.share_a_tongue_twister()
        elif topic == "calendar":
            self.talk_about_the_calendar()
        elif topic == "motivation":
            self.share_a_motivational_message()
        else:
            print("Unhandled topic: " + topic)

    def talk_about_weather(self, city="Washington"):
        weather = self.open_weather_api.get_weather_for_city(city)
        weather_summary = self.llm.generate_response(
            self.prompter.get_prompt("weather") + city + ":\n\n" + str(weather))
        self.voice.say(weather_summary)

    def talk_about_news(self, topic=None):
        if topic == "hackernews":
            news = self.hacker_news_souper.get_news(total=15)
        else:
            news = self.news_api.get_news(topic=topic)
        news_summary = self.llm.generate_response(
            self.prompter.get_prompt(topic) + "\n\n" + str(news))
        self.voice.say(news_summary)

    def tell_a_joke(self):
        joke = self.llm.generate_response(self.prompter.get_prompt("joke"))
        self.voice.say(joke)

    def share_a_fact(self):
        fact = self.llm.generate_response(self.prompter.get_prompt("fact"))
        self.voice.say(fact)

    def play_two_truths_and_one_lie(self):
        resp = self.llm.generate_response(self.prompter.get_prompt("truth_and_lie"))
        self.voice.say(resp)

    def share_a_fable(self):
        fable = self.llm.generate_response(self.prompter.get_prompt("fable"))
        self.voice.say(fable)

    def share_an_aphorism(self):
        aphorism = self.llm.generate_response(self.prompter.get_prompt("aphorism"))
        self.voice.say(aphorism)

    def share_a_poem(self):
        poem = self.llm.generate_response(self.prompter.get_prompt("poem"))
        self.voice.say(poem)
    
    def share_a_quote(self):
        quote = self.llm.generate_response(self.prompter.get_prompt("quote"))
        self.voice.say(quote)

    def share_a_tongue_twister(self):
        if config.tongue_twisters_dir is None or config.tongue_twisters_dir == "":
            raise Exception("No tongue twister directory specified")
        print(f"Playing tongue twister from {config.tongue_twisters_dir}")
        playback = Playback.new_playback(config.tongue_twisters_dir)
        Prompter.update_history("tongue_twister")
        try:
            playback.play_one_song()
        except Exception as e:
            print("Error playing tongue twister: " + str(e))
            print(playback._playback_config.directories)
            print(playback._playback_config.list)

    def talk_about_the_calendar(self):
        today = datetime.datetime.today()
        prompt = self.prompter.get_prompt("calendar")
        prompt = prompt.replace("DATE", today.strftime("%A %B %d %Y"))
        prompt = prompt.replace("TIME", today.strftime("%H:%M"))
        calendar = self.llm.generate_response(prompt)
        self.voice.say(calendar)

    def share_a_motivational_message(self):
        motivation = self.llm.generate_response(self.prompter.get_prompt("motivation"))
        self.voice.say(motivation)
