
import datetime
import os

from utils.app_info_cache import app_info_cache
from utils.config import config

class Prompter:
    TOPICS = ["weather", "news", "joke", "fact", "fable", "truth_and_lie", "aphorism", "poem", "quote"]

    @staticmethod
    def update_history(topic):
        if not topic in Prompter.TOPICS:
            raise Exception("Invalid topic: " + topic)
        app_info_cache.set(topic, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    @staticmethod
    def time_from_last_topic(topic):
        if not topic in Prompter.TOPICS:
            raise Exception("Invalid topic: " + topic)
        item_timestamp = app_info_cache.get(topic)
        if item_timestamp == None:
            return 9999999
        else:
            return (datetime.datetime.now() - datetime.datetime.strptime(item_timestamp, "%Y-%m-%d %H:%M:%S")).min


    def __init__(self):
        pass

    def get_prompt(self, topic):
        if not topic in Prompter.TOPICS:
            raise Exception("Invalid topic: " + topic)

        with open(os.path.join(config.prompts_directory, topic + ".txt"), 'r') as f:
            return f.read().strip()

