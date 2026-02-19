# Muse

Muse is a media player with an integrated voice synthesizer attached to an LLM. Essentially, a robot DJ for your music and other media.


## Installation steps

- Download Coqui-TTS source from https://github.com/coqui-ai/TTS
- Install Coqui-TTS using `pip install -e.`
- Set `coqui_tts_location` in config.json in configs folder to the path of Coqui-TTS source.
- Download and install Ollama following the instructions at https://github.com/ollama/ollama
- Ensure Ollama is operational and serving with `ollama serve`
- In a virtual environment, run `pip install -r requirements.txt` on this directory.
- Optional (platform-specific): `pip install -r requirements-optional.txt` installs extras for your OS only (e.g. on macOS, Foundation/Cocoa for keychain integration). Note: For keyboard media key support (previous, play/pause, next), install `pynput` via the optional requirements (required for Tkinter on all platforms, and for PySide6 on macOS/Linux).
- Note: To run TTS by itself, run the run_tts.py file with a text file.


## Configuration

- Set `LANGUAGE` environment variable to desired i18n code. If not supported, the language will default to English.
    - NOTE: I haven't fully surveyed their models, but in my experience besides some languages that use Cyrillic the default universal xtts_v2 model does not do very well with non-Roman characters, so languages that do not use them will not be supported until I can find an open source TTS solution that does. I have found that Russian is functional, so that is one option provided.
    - Supported UI languages: en (English), de (Deutsh), fr (Français), es (Español), it (Italiano), pt (Português), ru (русский)
- `directories` - Add the paths of any audio or video file directories Muse should be playing to this list.
- `text_cleaner_ruleset` - Add a dictionary of text cleaning rules to be run on text before Muse speaks it. Use a JSON object for each replacement set if using personas with different languages.
- `coqui_tts_model` - Set the TTS model and speaker to be used by Muse.
- For weather, news, calendar data etc set the appropriate API keys.
- `open_weather_city` - Set the city for Muse to use for weather data.
- `muse_config`
    - `enable_preparation` - Allows Muse to begin text-to-speech generation before songs end to minimize delays between songs.
    - `preparation_starts_minutes_from_end` - Set the number of minutes from the end of a song that Muse should begin text-to-speech generation.
    - `preparation_starts_after_seconds_sleep` - Set the number of seconds into a song to wait before starting text-to-speech generation.
    - `chance_speak_after_track` - Set the chance that Muse will speak after each track identifying the previous song or other media.
    - `chance_speak_before_track` - Set the chance that Muse will speak before each track identifying the upcoming song or other media.
    - `topic_discussion_chance_factor` - Base probability (0-1) for the DJ to discuss topics between songs. This chance increases over time if the DJ hasn't spoken recently, up to the base rate after 15 minutes of silence.
    - `min_seconds_between_spots` - Minimum time between DJ spots to prevent too frequent interruptions.
- `save_tts_output_topics` - Set the topics to retain MP3 files for in the `tts_ouput` directory.
- `news_api_source_trustworthiness` - Set the trustworthiness of news sources from News API.
- `artists_file`, `composers_file`, `forms_file`, `genres_file`, `instruments_file` - Modify these and place your desired file in the `library_data/data` directory following the formats in the example files found there.
- `enable_dynamic_volume` - Attempts to normalize track loudness by reducing or increasing the master volume above the base volume level.
- `play_videos_in_separate_window` - If the track is a video, play it in a separate window from the main window
- `playlist_recently_played_check_count` - As each track is played, the attributes are stored in lists of recently-played attributes. Set this to a higher value to reduce the chance that you hear recently-played tracks after a random sort has been applied.
- `enable_long_track_splitting`, `long_track_splitting_time_cutoff_minutes` - If playing tracks randomly, usually we don't want to dive into a long track. Muse will attempt to detect individual portions of long tracks to play rather than play the entire track to keep things fresh.
- `muse_language_learning_language`, `muse_language_learning_language_level` - If you are learning a language, set these values to a desired language and language level to have Muse attemp to teach it. Note that Coqui models don't support many languages.
- `llm_model_name` - The name of the LLM to use, exactly the same as Ollama model name.
- `text_cleaner_ruleset` - Add rules to this list to edit text before it is spoken by muse.
- `tongue_twisters_dir` - If using the "tongue_twister" topic, set this to a directory containing audio files of tongue twisters (or any other set of audio files!) for muse to play intermittently.
- `prompts_directory` - Directory containing prompts for different topics and languages. Supports:
  - System prompts in root directory
  - Language-specific prompts in subdirectories (e.g., 'en/', 'de/')
  - Automatic translation fallback when language-specific prompts aren't available
- `dj_personas` - Configure different DJ personas with unique voices, tones, and characteristics. Each persona can have its own language settings. The "voice_name" must match one of the Coqui speakers, see `tts/speakers.py` for the full list.


## Usage

- In your virtual environment, run `python app_qt.py` to start the application (Qt/PySide6 UI). On Windows you can use `start.bat`, which launches the Qt version. The legacy Tkinter UI (`app.py`) is deprecated and will be removed in a future release -- use the PySide6 version.
- Keyboard media keys (previous, play/pause, next) are supported when the optional `pynput` dependency is installed. Media keys work globally (even when the window doesn't have focus) in both UI versions when `pynput` is installed.


## Directory Structure

In the absence of track details found on the music file itself, Muse will attempt to infer track details from the file path. If artists or composers are predefined in the library_data/data folder, the `indicators` list on each will test the track name and path for a string match, and assign the appropriate attribute if a match is found. If no matches are found, the basic logic assumes the following directory structure:
- Root folder
    - Artist
        - Album
            - Track 1
            - Track 2


## Scheduling

A default voice is set for Muse, but any of the Coqui voice options can be used by creating a schedule. In a schedule you can also set an hour for the application to shut down automatically on given days of the week.


## Prompting

The following prompts are located in the prompts folder, and are used to generate Muse DJ spots between songs:

- `track_context_prior` - Prompt that is used before each track.
- `track_context_post` - Prompt that is used after each track.
- `weather` - Uses OpenWeatherAPI to get weather information.
- `news` - Prompt that is used to ask for news, from any of multiple sources.
- `poem` - Have the LLM generate a poem from its memory.
- `quote` - Have the LLM share a famous quote.
- `random_wiki_article` - Have the LLM summarize a random Wikipedia article.
- `truth_and_lie` - Small game to test both your and the LLM's knowledge.
- `fact` - Again, test the LLM's knowledge.
- `joke` - This one is still challenging for some of the local LLMs.
- `aphorism` - Have the LLM share an aphorism.
- `motivation` - The LLM should share an inspirational message of some sort.
- `language_learning` - If the `muse_language_learning_language` config option is set, the LLM will attempt to teach the language.
- `fable` - Have the LLM share a fable. Unfortunately it usually seems to get stuck talking about kings or ants.
- `calendar` - Have the LLM tell you something interesting about the calendar day.

Since there is currently very limited capacity to prompt LLMs negatively, a blacklist feature was implemented. This feature will run your blacklist on any text generated by Muse and call the LLM until it finds a response that is not blacklisted, unless any of the blacklisted strings were found in the prompt. This is definitely not a perfect solution so it is recommended to modify the prompts to fit your purposes and use a model that can best handle your requests.






