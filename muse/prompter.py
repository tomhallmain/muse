import datetime
import os

from utils.app_info_cache import app_info_cache
from utils.config import config
from utils.globals import Topic
from utils.translations import I18N
from utils.logging_setup import get_logger

_ = I18N._

logger = get_logger(__name__)

class Prompter:
    """Manages prompt loading, language support, and topic history for the Muse application.
    
    The Prompter class handles three types of prompts:
    1. System prompts: Located in the root prompts directory, used for core functionality
    2. Language-specific prompts: Located in language subdirectories (e.g., 'en/', 'de/')
    3. Dynamic prompts: Generated through translation when language-specific versions don't exist
    
    Prompt Directory Structure:
        prompts/
        ├── en/                     # English prompts (fallback language)
        │   ├── weather.txt
        │   └── news.txt
        ├── de/                     # German prompts
        │   └── weather.txt
        ├── search_artist.txt       # System prompts (root directory)
        ├── search_genre.txt
        └── translate_de.txt
        
    Usage:
        prompter = Prompter()
        
        # Get a language-specific prompt with fallback
        weather_prompt = prompter.get_prompt("weather", language_code="de")
        
        # Get a system prompt
        search_prompt = prompter.get_prompt("search_artist")
        
        # Get a prompt for a specific topic
        news_prompt = prompter.get_prompt(Topic.NEWS, language_code="fr")
    
    TODO: Create migration guide for:
    - Adding new language support
    - Translating existing prompts
    - Maintaining prompt consistency across languages
    - Best practices for prompt organization
    """

    TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M"
    PERSONA_INIT_PROMPT_NAME = "persona_init"

    @staticmethod
    def minutes_since(measure_time, from_time=None):
        """Calculate minutes elapsed since a given time."""
        if from_time is None:
            from_time = datetime.datetime.now()
        td = from_time - measure_time
        return int(td.days * (60 * 24) + td.seconds / 60)

    @staticmethod
    def update_history(topic, text=""):
        """Update the timestamp for when a topic was last discussed.
        
        Args:
            topic (Topic): The topic being discussed
            text (str, optional): Reserved for future use
        
        Raises:
            Exception: If topic is not a valid Topic enum
        """
        if not isinstance(topic, Topic):
            raise Exception(f"Invalid topic: {topic}")
        app_info_cache.set(topic.value, datetime.datetime.now().strftime(Prompter.TIMESTAMP_FORMAT))

    @staticmethod
    def time_from_last_topic(topic):
        """Get minutes elapsed since a topic was last discussed.
        
        Returns:
            int: Minutes since topic was last discussed, or very large number if never discussed
        """
        if not isinstance(topic, Topic):
            raise Exception(f"Invalid topic: {topic}")
        item_timestamp = app_info_cache.get(topic.value)
        if item_timestamp is None:
            return 9999999999
        else:
            return Prompter.minutes_since(datetime.datetime.strptime(item_timestamp, Prompter.TIMESTAMP_FORMAT))

    @staticmethod
    def over_n_hours_since_last(topic, n_hours=24):
        """Check if more than n hours have passed since topic was discussed."""
        return Prompter.time_from_last_topic(topic) > (60 * n_hours)

    @staticmethod
    def under_n_hours_since_last(topic, n_hours):
        """Check if less than n hours have passed since topic was discussed."""
        return not Prompter.over_n_hours_since_last(topic, n_hours)

    @staticmethod
    def get_oldest_topic(excluded_topics=[]):
        """Find the topic that hasn't been discussed for the longest time.
        
        Args:
            excluded_topics (list): Topics to ignore in the search
            
        Returns:
            Topic: The topic with the oldest or no discussion timestamp
        """
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
        """Initialize Prompter with prompts directory from config."""
        self.prompts_dir = config.prompts_directory

    def get_prompt_update_history(self, topic):
        """Get a prompt for a topic and update its discussion history.
        
        This method is crucial for maintaining topic novelty in DJ conversations.
        It ensures that:
        1. Topics aren't repeated too frequently
        2. The DJ maintains a natural flow of conversation
        3. All topics get fair coverage over time
        
        The method:
        1. Validates the topic
        2. Gets the prompt topic value
        3. Updates the topic's timestamp in history
        4. Returns the appropriate prompt
        
        Args:
            topic (Topic): The topic to get a prompt for and update history
            
        Returns:
            str: The prompt text for the topic
            
        Raises:
            Exception: If topic is not a valid Topic enum
        """
        if not isinstance(topic, Topic):
            raise Exception(f"Invalid topic: {topic}")
        prompt_topic = topic.get_prompt_topic_value()
        Prompter.update_history(topic)
        return self.get_prompt(prompt_topic)

    def get_translation_prompt(self, language_code, language_name_english, prompt):
        """Get a prompt for translating content to a specific language.
        
        Args:
            language_code (str): Target language code
            language_name_english (str): English name of target language
            prompt (str): The prompt to translate
            
        Returns:
            str: A prompt that instructs the LLM how to translate the content
        """
        translation_prompt = self.get_prompt("translate_" + language_code)
        translation_prompt = translation_prompt.replace("#LANGUAGE", language_name_english)
        translation_prompt = translation_prompt.replace("#PROMPT", prompt)
        return translation_prompt

    def get_prompt(self, prompt_name: str, language_code: str = "en", skip_fallback: bool = False) -> str:
        """Get a prompt from the prompts directory with language support.
        
        Search order:
        1. Language-specific directory (e.g., 'de/weather.txt')
        2. English directory if fallback enabled (e.g., 'en/weather.txt')
        3. Root directory (e.g., 'search_artist.txt')
        
        Args:
            prompt_name: Name of the prompt file without extension
            language_code: Two-letter language code (e.g., 'en', 'de')
            skip_fallback: If True, only check language-specific directory
            
        Returns:
            str: Content of the prompt file
            
        Raises:
            FileNotFoundError: If prompt file not found in any location
        """
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
        """Get a prompt for a topic with language support and fallback.
        
        This method combines topic history tracking with language-aware prompt loading.
        If a language-specific prompt doesn't exist, it will attempt translation.
        
        Args:
            topic (Topic): The topic to get a prompt for
            language_code (str): Two-letter language code
            
        Returns:
            str: The prompt text in the requested language
            
        Raises:
            Exception: If topic is invalid
            FileNotFoundError: If no prompt found and translation fails
        """
        if not isinstance(topic, Topic):
            raise Exception(f"Invalid topic: {topic}")
            
        prompt_topic = topic.get_prompt_topic_value()
        Prompter.update_history(topic)
        
        try:
            # Try to get language-specific prompt without fallback
            return self.get_prompt(prompt_topic, language_code, skip_fallback=True)
        except FileNotFoundError:
            # If no language-specific prompt exists, use translation approach
            if language_code != "en":
                english_prompt = self.get_prompt(prompt_topic, "en")
                return self.get_translation_prompt(language_code, I18N.get_english_language_name(language_code), english_prompt)
            raise

    def get_persona_initialization_prompt(self, language_code: str) -> str:
        """Get a prompt for a persona initialization."""
        return self.get_prompt(Prompter.PERSONA_INIT_PROMPT_NAME, language_code)

