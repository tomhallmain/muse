
import random

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
        self.prompter = Prompter()

    def maybe_dj(self, song_name, previous_song_name):
        # TODO quality info for songs
        if previous_song_name != "" and random.random() < 0.2:
            self.voice.say("That was " + previous_song_name + ", how about that.")
        if random.random() < 0.3:
            self.voice.say("Next up, we'll be playing: " + song_name)
        if random.random() < 0.2:
            self.talk_about_something()

    def talk_about_something(self):
        if Prompter.over_n_hours_since_last("weather", n_hours=24):
            topic = "weather"
            print("Talking about the weather")
        elif Prompter.over_n_hours_since_last("news", n_hours=96):
            topic = "news"
            print("Talking about the news")
        else:
            topic = Prompter.get_oldest_topic()
            print("Talking about topic: " + topic)
        if topic == "weather":
            self.talk_about_weather()
        elif topic == "news":
            self.talk_about_news()
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
        news = self.news_api.get_news(topic=topic)
        news_summary = self.llm.generate_response(
            self.prompter.get_prompt("news") + "\n\n" + str(news))
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
        playback = Playback.new_playback(config.tongue_twisters_dir)
        playback.play_one_song()
