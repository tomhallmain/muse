
from extensions.news_api import NewsAPI
from extensions.open_weather import OpenWeatherAPI
from extensions.llm import LLM
from ops.prompter import Prompter
from ops.voice import Voice


class Muse:

    def __init__(self, args):
        self.args = args
        self.llm = LLM()
        self.voice = Voice()
        self.open_weather_api = OpenWeatherAPI()
        self.news_api = NewsAPI()
        self.prompter = Prompter()

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

