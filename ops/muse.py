
import random

from extensions.hacker_news_souper import HackerNewsSouper
from extensions.news_api import NewsAPI
from extensions.open_weather import OpenWeatherAPI
from extensions.llm import LLM
from ops.playback import Playback
from ops.prompter import Prompter
from ops.voice import Voice
from utils.config import config


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
        has_already_spoken = False
        if not skip_previous_track_remark and previous_track != "" and random.random() < 0.2:
            if True:
                dj_remark = "Das war „{0}“ aus „{1}“".format(previous_track.title, previous_track.album)
                if previous_track.artist is not None and previous_track.artist!= "":
                    dj_remark += " von „{0}“.".format(previous_track.artist)
                else:
                    dj_remark += "."
            else:
                dj_remark = "That was \"" + previous_track.title + "\" in \"" + previous_track.album + "\""
                if previous_track.artist is not None and previous_track.artist!= "":
                    dj_remark += " by " + previous_track.artist + "."
                else:
                    dj_remark += "."
            self.voice.say(dj_remark)
        if random.random() < 0.3:
            if True:
                start_tag = "Als Nächstes" if previous_track is not None else "Zu Beginn"
                dj_remark = start_tag + " spielen wir „{0}“ aus „{1}“".format(track.title, track.album)
                if track.artist is not None and track.artist!= "":
                    dj_remark += " von „{0}“.".format(track.artist)
                else:
                    dj_remark += "."
            else:
                start_tag = "Next up" if previous_track is not None else "To start"
                dj_remark = start_tag + ", we'll be playing: \"" + track.title + "\" from \"" + track.album + "\""
                if track.artist is not None and track.artist!= "":
                    dj_remark += " by " + track.artist + "."
                else:
                    dj_remark += "."
            self.voice.say(dj_remark)
            has_already_spoken = True
        if random.random() < 0.2:
            self.talk_about_something(previous_track, has_already_spoken, skip_previous_track_remark)

    def talk_about_something(self, previous_track=None, has_already_spoken=False, skip_previous_track_remark=False):
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
            topic = Prompter.get_oldest_topic()
            print("Talking about topic: " + topic)

        if (has_already_spoken and random.random() < 0.75) or (not has_already_spoken and random.random() < 0.6):
            if skip_previous_track_remark or previous_track is None:
                if True:
                    remark = "Zunächst zum Thema „{0}“.".format(topic)
                else:
                    remark = "First let's hear about {0}".format(topic)
            else:
                if True:
                    remark = "Doch zunächst zum Thema „{0}“.".format(topic)
                else:
                    remark = "But first, let's hear about {0}.".format(topic)
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
