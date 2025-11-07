import json
import os
import sys
import time

from utils.globals import Globals, Topic
from utils.utils import Utils
from utils.logging_setup import get_logger

# Get logger for this module
logger = get_logger(__name__)

root_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
configs_dir = os.path.join(root_dir, "configs")
library_data_dir = os.path.join(root_dir, "library_data", "data")


class Config:
    CONFIGS_DIR_LOC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "configs")

    def __init__(self, config_path=None):
        self.dict = {}
        self.changed_values = set()  # Track which values have been modified
        self.foreground_color = "white"
        self.background_color = "#2596BE"
        self.directories = []
        self.dj_personas = []
        self.dj_persona_refresh_context = False
        self.muse_config = {
            Globals.ConfigKeys.ENABLE_PREPARATION: True,
            Globals.ConfigKeys.PREPARATION_STARTS_MINUTES_FROM_END: 2,
            Globals.ConfigKeys.PREPARATION_STARTS_AFTER_SECONDS_SLEEP: 10,
            Globals.ConfigKeys.CHANCE_SPEAK_AFTER_TRACK: 0.3,
            Globals.ConfigKeys.CHANCE_SPEAK_BEFORE_TRACK: 0.3,
            Globals.ConfigKeys.TOPIC_DISCUSSION_CHANCE_FACTOR: 0.2,
            Globals.ConfigKeys.MIN_SECONDS_BETWEEN_SPOTS: 500,
        }
        self.save_tts_output_topics = [Topic.LANGUAGE_LEARNING.value, Topic.POEM.value, Topic.RANDOM_WIKI_ARTICLE.value, Topic.APHORISM.value]
        self.prompts_directory = Globals.DEFAULT_PROMPTS_DIRECTORY
        self.tongue_twisters_dir = None
        self.artists_file = "artists.json"
        self.composers_file = "composers.json"
        self.forms_file = "forms.json"
        self.genres_file = "genres.json"
        self.instruments_file = "instruments.json"

        self.open_weather_city = "Washington"
        self.open_weather_api_key = None
        self.news_api_key = None
        self.news_api_source_trustworthiness = {}
        self.muse_language_learning_language = "German"
        self.muse_language_learning_language_level = "intermediate"
        self.debug = False

        self.llm_model_name = "deepseek-r1:14b"

        self.text_cleaner_ruleset = []
        self.number_words = {}  # Locale-specific number word configurations
        self.coqui_tts_location = ""
        self.coqui_tts_model = ("tts_models/multilingual/multi-dataset/xtts_v2", "Royston Min", "en")
        self.max_chunk_tokens = 200

        self.enable_dynamic_volume = True
        self.enable_library_extender = False
        self.enable_long_track_splitting = False
        self.show_videos_in_main_window = False
        self.long_track_splitting_time_cutoff_minutes = 20
        self.play_videos_in_separate_window = False
        self.playlist_recently_played_check_count = 1000
        self.max_search_results = 200
        self.max_recent_searches = 200

        self.server_port = 6000
        self.server_password = "<PASSWORD>"
        self.server_host = "localhost"

        configs =  [ f.path for f in os.scandir(Config.CONFIGS_DIR_LOC) if f.is_file() and f.path.endswith(".json") ]
        self.config_path = config_path

        if self.config_path is None:
            for c in configs:
                if os.path.basename(c) == "config.json":
                    self.config_path = c
                    break
                elif os.path.basename(c) != "config_example.json":
                    self.config_path = c

            if self.config_path is None:
                self.config_path = os.path.join(Config.CONFIGS_DIR_LOC, "config_example.json")

        try:
            self.dict = json.load(open(self.config_path, "r", encoding="utf-8"))
        except Exception as e:
            logger.error(e)
            logger.warning("Unable to load config. Ensure config.json file settings are correct.")

        self.set_values(str,
            "foreground_color",
            "background_color",
            "artists_file",
            "composers_file",
            "forms_file",
            "genres_file",
            "instruments_file",
            "open_weather_city",
            "open_weather_api_key",
            "news_api_key",
            "llm_model_name",
            "muse_language_learning_language",
            "muse_language_learning_language_level",
        )
        self.set_values(int,
            "max_chunk_tokens",
            "long_track_splitting_time_cutoff_minutes",
            "playlist_recently_played_check_count",
            "max_recent_searches",
            "max_search_results",
        )
        self.set_values(list,
            "directories",
            "text_cleaner_ruleset",
            "coqui_tts_model",
            "save_tts_output_topics",
            "dj_personas",
        )
        self.set_values(bool,
            "enable_dynamic_volume",
            "enable_library_extender",
            "enable_long_track_splitting",
            "play_videos_in_separate_window",
            "dj_persona_refresh_context",
        )
        self.set_values(dict,
            "muse_config",
            "news_api_source_trustworthiness",
            "number_words",
        )
        self.set_directories(
            "prompts_directory",
            "tongue_twisters_dir",
            "coqui_tts_location",
        )
        self.set_filepaths(
            "artists_file",
            "composers_file",
            "forms_file",
            "genres_file",
            "instruments_file",
        )

        i = 0
        while i < len(self.directories):
            d = self.directories[i]
            try:
                if sys.platform == "win32" and not d.startswith("C:\\") and not d.startswith("{HOME}"):
                    pass
                elif not os.path.isdir(d):
                    d = self.validate_and_set_directory(d, override=True)
                    self.directories[i] = d if d is None else os.path.normpath(os.path.realpath(d))
            except Exception as e:
                pass
            i += 1

        self.coqui_tts_model = tuple(self.coqui_tts_model)

    def get_config_value(self, key):
        """Get a configuration value by key"""
        return getattr(self, key, None)

    def set_config_value(self, key, value):
        """Set a configuration value by key"""
        if hasattr(self, key):
            current_value = getattr(self, key)
            if current_value != value:  # Only update if value actually changed
                setattr(self, key, value)
                self.dict[key] = value
                self.changed_values.add(key)
                return True
        return False

    def has_changes(self):
        """Check if there are any unsaved changes"""
        return len(self.changed_values) > 0

    def clear_changes(self):
        """Clear the changed values tracking"""
        self.changed_values.clear()

    def save_config(self):
        """Save updated configuration to file"""
        # Create temporary swap file path
        swap_path = os.path.join(Config.CONFIGS_DIR_LOC, f"config_swap_{int(time.time())}.json")
        
        # Write to swap file
        try:
            with open(swap_path, 'w', encoding='utf-8') as f:
                json.dump(self.dict, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to write temporary configuration: {e}")
            if os.path.exists(swap_path):
                os.remove(swap_path)
            return False

        # Validate the swap file by creating a new Config instance
        try:
            test_config = Config(config_path=swap_path)
        except Exception as e:
            logger.error(f"Invalid configuration in swap file: {e}")
            os.remove(swap_path)
            return False

        # Write to actual config file
        try:
            Utils.copy_file(swap_path, self.config_path, overwrite_existing=True)
        except Exception as e:
            logger.error(f"Failed to write final configuration: {e}")
            os.remove(swap_path)
            return False

        # Clean up swap file and clear changes
        os.remove(swap_path)
        self.clear_changes()
        return True

    def create_from_example(self):
        """Create a new config.json from config_example.json"""
        try:
            example_path = os.path.join(Config.CONFIGS_DIR_LOC, "config_example.json")
            with open(example_path, 'r', encoding='utf-8') as f:
                self.dict = json.load(f)
            self.config_path = os.path.join(Config.CONFIGS_DIR_LOC, "config.json")
            return self.save_config()
        except Exception as e:
            logger.error(f"Failed to create config from example: {e}")
            return False

    def get_all_config_values(self):
        """Get all configuration values as a dictionary"""
        return {key: getattr(self, key) for key in self.dict.keys() if hasattr(self, key)}

    def validate_and_set_directory(self, key, override=False):
        loc = key if override else self.dict[key]
        if loc and loc.strip() != "":
            if "{HOME}" in loc:
                loc = loc.strip().replace("{HOME}", os.path.expanduser("~"))
            if not sys.platform == "win32" and "\\" in loc:
                loc = loc.replace("\\", "/")
            if not os.path.isdir(loc):
                raise Exception(f"Invalid location provided for {key}: {loc}")
            return loc
        return None

    def validate_and_set_filepath(self, key):
        filepath = self.dict[key]
        if filepath and filepath.strip() != "":
            if "{HOME}" in filepath:
                filepath = filepath.strip().replace("{HOME}", os.path.expanduser("~"))
            elif not os.path.isfile(filepath):
                try_path = os.path.join(configs_dir, filepath)
                if os.path.isfile(try_path):
                    filepath = try_path
                else:
                    try_path = os.path.join(library_data_dir, filepath)
                    if os.path.isfile(try_path):
                        filepath = try_path
            if not os.path.isfile(filepath):
                raise Exception(f"Invalid location provided for {key}: {filepath}")
            return filepath
        return None

    def set_directories(self, *directories):
        for directory in directories:
            try:
                setattr(self, directory, self.validate_and_set_directory(directory))
            except Exception as e:
                logger.warning(e)
                logger.warning(f"Failed to set {directory} from config.json file. Ensure the key is set.")

    def set_filepaths(self, *filepaths):
        for filepath in filepaths:
            try:
                setattr(self, filepath, self.validate_and_set_filepath(filepath))
            except Exception as e:
               logger.warning(e)
               logger.warning(f"Failed to set {filepath} from config.json file. Ensure the key is set.")

    def set_values(self, type, *names):
        for name in names:
            if type:
                try:
                    setattr(self, name, type(self.dict[name]))
                except Exception as e:
                    logger.error(e)
                    logger.warning(f"Failed to set {name} from config.json file. Ensure the value is set and of the correct type.")
            else:
                try:
                    setattr(self, name, self.dict[name])
                except Exception as e:
                    logger.error(e)
                    logger.warning(f"Failed to set {name} from config.json file. Ensure the key is set.")


    def get_subdirectories(self):
        subdirectories = {}
        for directory in self.directories:
            try:
                this_dir_subdirs = [os.path.join(directory, d) for d in os.listdir(directory) if os .path.isdir(os.path.join(directory, d))]
                if len(this_dir_subdirs) == 0:
                    subdirectories[directory] = os.path.basename(directory)
                else:
                    for d in this_dir_subdirs:
                        subdirectories[d] = os.path.join(os.path.basename(directory), os.path.basename(d))
            except Exception:
                pass
        return subdirectories

    def get_all_directories(self):
        subdirectories_map = self.get_subdirectories()
        return list(subdirectories_map.keys())

    def matches_master_directory(self, directory):
        directory = os.path.normpath(os.path.realpath(directory))
        for d in self.directories:
            if d == directory:
                return True
        return False



config = Config()
