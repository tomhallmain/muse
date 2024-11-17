import json
import os
import sys

from utils.utils import Utils

root_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
configs_dir = os.path.join(root_dir, "configs")


class Config:
    CONFIGS_DIR_LOC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "configs")

    def __init__(self):
        self.dict = {}
        self.foreground_color = "white"
        self.background_color = "#2596BE"
        self.directories = []
        self.muse_config = {
            "enable_preparation": True,
            "preparation_starts_minutes_from_end": 2,
            "preparation_starts_after_seconds_sleep": 10,
            "chance_speak_after_track": 0.3,
            "chance_speak_before_track": 0.3,
            "chance_speak_about_other_topics": 0.3,
        }
        self.prompts_directory = "prompts"
        self.tongue_twisters_dir = None
        self.artists_file = "artists.json"
        self.composers_file = "composers.json"
        self.open_weather_city = "Washington"
        self.open_weather_api_key = None
        self.news_api_key = None
        self.news_api_source_trustworthiness = {}
        self.debug = False

        self.text_cleaner_ruleset = []
        self.coqui_tts_location = ""
        self.coqui_tts_model = ("tts_models/multilingual/multi-dataset/xtts_v2", "Royston Min", "en")
        self.max_chunk_tokens = 200

        self.enable_dynamic_volume = True
        self.enable_library_extender = False

        self.server_port = 6000
        self.server_password = "<PASSWORD>"
        self.server_host = "localhost"

        configs =  [ f.path for f in os.scandir(Config.CONFIGS_DIR_LOC) if f.is_file() and f.path.endswith(".json") ]
        self.config_path = None

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
            Utils.log_red(e)
            Utils.log_yellow("Unable to load config. Ensure config.json file settings are correct.")

        self.set_values(str,
            "foreground_color",
            "background_color",
            "artists_file",
            "composers_file",
            "open_weather_city",
            "open_weather_api_key",
            "news_api_key",
        )
        self.set_values(int,
            "max_chunk_tokens",
        )
        self.set_values(list,
            "directories",
            "text_cleaner_ruleset",
            "coqui_tts_model",
        )
        self.set_values(bool,
            "enable_dynamic_volume",
            "enable_library_extender"
        )
        self.set_values(dict,
            "muse_config",
            "news_api_source_trustworthiness",
        )
        self.set_directories(
            "prompts_directory",
            "tongue_twisters_dir",
            "coqui_tts_location",
        )
        self.set_filepaths(
            "artists_file",
            "composers_file",
        )

        i = 0
        while i < len(self.directories):
            d = self.directories[i]
            try:
                if sys.platform == "win32" and not d.startswith("C:\\") and not d.startswith("{HOME}"):
                    pass
                elif not os.path.isdir(d):
                    self.directories[i] = self.validate_and_set_directory(d, override=True)
            except Exception as e:
                pass
            i += 1

        self.coqui_tts_model = tuple(self.coqui_tts_model)


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
            if not os.path.isfile(filepath):
                raise Exception(f"Invalid location provided for {key}: {filepath}")
            return filepath
        return None

    def set_directories(self, *directories):
        for directory in directories:
            try:
                setattr(self, directory, self.validate_and_set_directory(directory))
            except Exception as e:
                Utils.log_yellow(e)
                Utils.log_yellow(f"Failed to set {directory} from config.json file. Ensure the key is set.")

    def set_filepaths(self, *filepaths):
        for filepath in filepaths:
            try:
                setattr(self, filepath, self.validate_and_set_filepath(filepath))
            except Exception as e:
                pass
#                Utils.log_yellow(e)
#                Utils.log_yellow(f"Failed to set {filepath} from config.json file. Ensure the key is set.")

    def set_values(self, type, *names):
        for name in names:
            if type:
                try:
                    setattr(self, name, type(self.dict[name]))
                except Exception as e:
                    Utils.log_red(e)
                    Utils.log_yellow(f"Failed to set {name} from config.json file. Ensure the value is set and of the correct type.")
            else:
                try:
                    setattr(self, name, self.dict[name])
                except Exception as e:
                    Utils.log_red(e)
                    Utils.log_yellow(f"Failed to set {name} from config.json file. Ensure the key is set.")


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



config = Config()
