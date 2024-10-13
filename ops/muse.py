import datetime
import random

from utils.app_info_cache import app_info_cache


class Muse:
    topics = ["weather", "news", "joke", "fact", "fable", "truth_or_lie", "aphorism"]

    @staticmethod
    def update_history(topic):
        if not topic in Muse.topics:
            raise Exception("Invalid topic: " + topic)
        app_info_cache.set(topic, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    @staticmethod
    def time_from_last_topic(topic):
        if not topic in Muse.topics:
            raise Exception("Invalid topic: " + topic)
        item_timestamp = app_info_cache.get(topic)
        if item_timestamp == None:
            return 9999999
        else:
            return (datetime.datetime.now() - datetime.datetime.strptime(item_timestamp, "%Y-%m-%d %H:%M:%S")).min

    def __init__(self, args):
        self.args = args


    def talk_about_weather(self, city):
        return "The weather in {} is {}".format(city, self._get_weather())


