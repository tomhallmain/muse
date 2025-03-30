import datetime
import os
import random

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
        self.prompts_dir = config.prompts_directory

    def get_prompt(self, topic):
        if not isinstance(topic, Topic):
            raise Exception(f"Invalid topic: {topic}")
        prompt_topic = topic.get_prompt_topic_value()
        Prompter.update_history(topic)
        return Prompter.get_prompt_static(prompt_topic)

    def get_translation_prompt(self, language_code, language_name_english, prompt):
        translation_prompt = Prompter.get_prompt_static("translate_" + language_code)
        translation_prompt = translation_prompt.replace("#LANGUAGE", language_name_english)
        translation_prompt = translation_prompt.replace("#PROMPT", prompt)
        return translation_prompt

    def get_prompt_static(self, prompt_name: str, language_code: str = "en", skip_fallback: bool = False) -> str:
        """Get a static prompt from the prompts directory with language support."""
        # First try language-specific path
        language_path = os.path.join(self.prompts_dir, language_code, f"{prompt_name}.txt")
        if os.path.exists(language_path):
            with open(language_path, "r", encoding="utf-8") as f:
                return f.read()
                
        if skip_fallback:
            raise FileNotFoundError(f"Prompt file not found: {prompt_name}.txt")
                
        # Fall back to English if language-specific prompt doesn't exist
        if language_code != "en":
            english_path = os.path.join(self.prompts_dir, "en", f"{prompt_name}.txt")
            if os.path.exists(english_path):
                with open(english_path, "r", encoding="utf-8") as f:
                    return f.read()
                    
        # If no language-specific or English version exists, try root directory
        prompt_path = os.path.join(self.prompts_dir, f"{prompt_name}.txt")
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
                
        raise FileNotFoundError(f"Prompt file not found: {prompt_name}.txt")

    def get_prompt_with_language(self, topic, language_code: str = "en") -> str:
        """Get a prompt for a topic with language support and fallback."""
        if not isinstance(topic, Topic):
            raise Exception(f"Invalid topic: {topic}")
            
        prompt_topic = topic.get_prompt_topic_value()
        Prompter.update_history(topic)
        
        try:
            # Try to get language-specific prompt without fallback
            return self.get_prompt_static(prompt_topic, language_code, skip_fallback=True)
        except FileNotFoundError:
            # If no language-specific prompt exists, use translation approach
            if language_code != "en":
                english_prompt = self.get_prompt_static(prompt_topic, "en")
                return self.get_translation_prompt(language_code, I18N.get_english_language_name(language_code), english_prompt)
            raise


