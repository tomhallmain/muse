
import datetime
import os

from utils.app_info_cache import app_info_cache
from utils.config import config
from utils.globals import Topic
from utils.translations import I18N

_ = I18N._


class Prompter:
    TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M"

    @staticmethod
    def minutes_since(measure_time, from_time=None):
        if from_time is None:
            from_time = datetime.datetime.now()
        td = from_time - measure_time
        return int(td.days * (60 * 24) + td.seconds / 60)

    @staticmethod
    def update_history(topic, text=""):
        if not isinstance(topic, Topic):
            raise Exception(f"Invalid topic: {topic}")
        app_info_cache.set(topic.value, datetime.datetime.now().strftime(Prompter.TIMESTAMP_FORMAT))

    @staticmethod
    def time_from_last_topic(topic):
        if not isinstance(topic, Topic):
            raise Exception(f"Invalid topic: {topic}")
        item_timestamp = app_info_cache.get(topic.value)
        if item_timestamp is None:
            return 9999999999
        else:
            return Prompter.minutes_since(datetime.datetime.strptime(item_timestamp, Prompter.TIMESTAMP_FORMAT))

    @staticmethod
    def over_n_hours_since_last(topic, n_hours=24):
        return Prompter.time_from_last_topic(topic) > (60 * n_hours)

    @staticmethod
    def under_n_hours_since_last(topic, n_hours):
        return not Prompter.over_n_hours_since_last(topic, n_hours)

    @staticmethod
    def get_oldest_topic(excluded_topics=[]):
        oldest_time = None
        for topic in Topic.__members__.values():
            if topic in excluded_topics: continue
            topic_time_str = app_info_cache.get(topic.value)
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

    def get_prompt(self, topic):
        if not isinstance(topic, Topic):
            raise Exception(f"Invalid topic: {topic}")
        prompt_topic = topic.get_prompt_topic_value()
        Prompter.update_history(topic)
        with open(os.path.join(config.prompts_directory, prompt_topic + ".txt"), 'r') as f:
            return f.read().strip()

