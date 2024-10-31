
import datetime
import os

from utils.app_info_cache import app_info_cache
from utils.config import config

class Prompter:
    TOPICS = ["weather", "news", "hackernews", "joke", "fact", "fable", "truth_and_lie", "aphorism", "poem", "quote", "tongue_twister"]
    TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M"

    @staticmethod
    def minutes_since(measure_time, from_time=None):
        if from_time is None:
            from_time = datetime.datetime.now()
        td = from_time - measure_time
        return int(td.days * (60 * 24) + td.seconds / 60)

    @staticmethod
    def update_history(topic):
        if not topic in Prompter.TOPICS:
            raise Exception("Invalid topic: " + topic)
        app_info_cache.set(topic, datetime.datetime.now().strftime(Prompter.TIMESTAMP_FORMAT))

    @staticmethod
    def time_from_last_topic(topic):
        if not topic in Prompter.TOPICS:
            raise Exception("Invalid topic: " + topic)
        item_timestamp = app_info_cache.get(topic)
        if item_timestamp is None:
            return 9999999999
        else:
            return Prompter.minutes_since(datetime.datetime.strptime(item_timestamp, Prompter.TIMESTAMP_FORMAT))

    @staticmethod
    def over_n_hours_since_last(topic, n_hours=24):
        return Prompter.time_from_last_topic(topic) > (60 * n_hours)

    @staticmethod
    def get_oldest_topic():
        oldest_time = None
        for topic in Prompter.TOPICS:
            topic_time_str = app_info_cache.get(topic)
            if topic_time_str is not None:
                topic_time = datetime.datetime.strptime(topic_time_str, Prompter.TIMESTAMP_FORMAT)
                topic_time_since = Prompter.minutes_since(topic_time)
            else:
                topic_time_since = 9999999999
            if oldest_time is None or topic_time_since > oldest_time:
                oldest_time = topic_time_since
                oldest_topic = topic
        return oldest_topic

    def __init__(self):
        pass

    def get_prompt_topic(self, topic):
        if topic == "hackernews":
            return "news"
        return str(topic)

    def get_prompt(self, topic):
        if not topic in Prompter.TOPICS:
            raise Exception("Invalid topic: " + topic)
        prompt_topic = self.get_prompt_topic(topic)
        Prompter.update_history(topic)
        with open(os.path.join(config.prompts_directory, prompt_topic + ".txt"), 'r') as f:
            return f.read().strip()

