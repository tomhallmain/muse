# Muse

Muse is a media player with an integrated voice synthesizer attached to an LLM. Essentially, a robot DJ for your music and other media.


## Installation steps

- Download Coqui-TTS source from https://github.com/coqui-ai/TTS
- Install Coqui-TTS using `pip install -e.`
- Set `coqui_tts_location` in config.json to the path of Coqui-TTS source (see [User data](#user-data) for where config.json lives).
- Download and install Ollama following the instructions at https://github.com/ollama/ollama
- Ensure Ollama is operational and serving with `ollama serve`
- In a virtual environment, run `pip install -r requirements.txt` on this directory.
- Optional (platform-specific): `pip install -r requirements-optional.txt` installs extras for your OS only (e.g. on macOS, Foundation/Cocoa for keychain integration). Note: For keyboard media key support (previous, play/pause, next), install `pynput` via the optional requirements (required for PySide6 on macOS/Linux; Windows has native Qt fallback without `pynput`).
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
- `save_tts_output_topics` - Set the topics to retain MP3 files for in the `tts_output` directory (see [User data](#user-data)).
- `news_api_source_trustworthiness` - Set the trustworthiness of news sources from News API.
- `artists_file`, `composers_file`, `forms_file`, `genres_file`, `instruments_file` - Modify these and place your desired file in the `library_data` folder of your configs directory (see [User data](#user-data)), following the formats in the example files in `library_data/data` in this repository.
- `enable_dynamic_volume` - Attempts to normalize track loudness by reducing or increasing the master volume above the base volume level.
- `play_videos_in_separate_window` - If the track is a video, play it in a separate window from the main window
- `playlist_recently_played_check_count` - As each track is played, the attributes are stored in lists of recently-played attributes. Set this to a higher value to reduce the chance that you hear recently-played tracks after a random sort has been applied.
- `enable_long_track_splitting`, `long_track_splitting_time_cutoff_minutes` - If playing tracks randomly, usually we don't want to dive into a long track. Muse will attempt to detect individual portions of long tracks to play rather than play the entire track to keep things fresh.
- `enable_library_extender`, `library_extender_key` - Enables the library extender feature, which periodically searches for and downloads new tracks to extend the library. Requires an API key.
- `radio_watchlist_enabled` - Turns on watching of the radio stations in the Internet Radio watch-list (off by default). See [Radio discovery](#radio-discovery).
- `auto_file_extensions` - Automatically move downloaded extension tracks into a genre/artist/album subdirectory structure under the first configured directory.
- `auto_file_extensions_genres` - List of genre directory names to use as filing targets for auto-filed extensions. If empty, all Title-Case subdirectories of the root directory are treated as candidates.
- `muse_language_learning_languages` - List of `{"language_code": ..., "level": ...}` you are currently learning; Muse will teach one at random each time the topic comes up (so you can learn several languages at once). The persona speaking picks only among the ones its `can_teach_languages` allows (see `dj_personas`). Replaces the older single `muse_language_learning_language`/`muse_language_learning_language_level` fields, which are still read once to migrate existing configs. Note that Coqui models don't support many languages.
- `llm_model_name` - The name of the LLM to use, exactly the same as Ollama model name.
- `llm_stream_redundancy`, `llm_thinking_budget_chars` - Enable streaming redundancy elimination to detect and stop repetitive or stalled LLM output early. For thinking models (e.g. DeepSeek-R1, Qwen3), `llm_thinking_budget_chars` sets a character budget for the internal reasoning block before generation is cut off (default: 8000).
- `text_cleaner_ruleset` - Add rules to this list to edit text before it is spoken by muse.
- `tongue_twisters_dir` - If using the "tongue_twister" topic, set this to a directory containing audio files of tongue twisters (or any other set of audio files!) for muse to play intermittently.
- `prompts_directory` - Directory containing prompts for different topics and languages. Supports:
  - System prompts in root directory
  - Language-specific prompts in subdirectories (e.g., 'en/', 'de/')
  - Automatic translation fallback when language-specific prompts aren't available
- `dj_personas` - Configure different DJ personas with unique voices, tones, and characteristics. Each persona can have its own language settings, plus `can_teach_languages` (which of `muse_language_learning_languages` this persona is allowed to teach -- `"*"` for any, or specific codes) and `prompt_overrides` (persona-specific text for a given topic, replacing the shared `prompts/<lang>/<topic>.txt` file). The "voice_name" must match one of the Coqui speakers, see `tts/speakers.py` for the full list.


## User data

Muse keeps its settings, data and logs outside the source tree, in one folder: `%APPDATA%\muse\` on Windows and `~/.local/share/muse/` elsewhere, where Muse has always written its logs (set `MUSE_APP_DATA_DIR` to use another folder):

- `configs/`: `config.json`, the library database, and your own library data files under `configs/library_data/`. A new install starts from `library_data/data/config_example.json`.
- `cache/`: caches Muse can rebuild, such as the media track caches, DJ memory and downloaded wiki articles.
- `tts_output/`: generated speech, including the recordings kept for `save_tts_output_topics`.
- `logs/`: log files.

Files that earlier versions kept in the repository (`configs/`, `library_data/data/`, the caches in the repository root, `tts_output/`) are moved there on first start; a file that already exists there is never overwritten.


## Usage

- In your virtual environment, run `python app_qt.py` to start the application (Qt/PySide6 UI). On Windows you can use `start.bat`, which launches the Qt version.
- Keyboard media keys (previous, play/pause, next) are supported when the optional `pynput` dependency is installed. With `pynput`, media keys work globally (even when the window doesn't have focus).

The keys encrypting the cache are backed up automatically to an external drive
(set `MUSE_KEY_BACKUP_DIR` to choose where). Run `python scripts/key_material.py`
to check that backup's state, or `backup` to take one by hand.


## Radio discovery

Muse can watch radio stations in the background and suggest tracks that are new to you.

1. Set `radio_watchlist_enabled` to `true` in `config.json` and restart Muse.
2. Open View > Internet Radio, search for a station and click Watch. On the Watch-list tab, set Mode to "Discover new tracks" and click Add Entry. Entries added while Muse is running start after "Reload Watch Service".
3. New tracks appear in a "New on the Radio" window with Switch, Dismiss and Don't Suggest Again. Playback never switches on its own.

Each watched station is streamed in the background, so watch only a few (`radio_watchlist_max_stations` caps it). The `radio_novelty_*` settings tune what counts as new.


## Build

`python build_exe.py` builds Muse into a single executable with [Nuitka](https://nuitka.net): `dist/Muse.exe` on Windows, `dist/Muse` on macOS and Linux. Build on each operating system you want an executable for; Nuitka does not cross-compile.

Prerequisites:

- Python with `venv` and `pip`. The script creates `.venv-build` from `requirements-build.txt` so nothing else in your environment is bundled; `--current-env` builds with the running interpreter instead.
- A C compiler: Visual Studio Build Tools on Windows (or let Nuitka download MinGW), Xcode Command Line Tools on macOS, `gcc` on Linux.
- A Coqui-TTS source checkout, which is compiled into the executable: pass `--coqui-path=<dir>`, or the build uses `coqui_tts_location` from your `config.json`.
- VLC installed on the build machine. The build checks itself with `Muse --smoke-test` before finishing, which loads Muse's playback code and with it libvlc.
- Several GB of free disk space: the executable contains PyTorch.
- Memory: the last step of the compile compresses the payload, with one compression thread per Nuitka job. Before it starts, the build estimates how much memory that needs and, if less is free, waits until it is (close other programs, or press Enter to go ahead). The wait needs app-release installed (see [Releases](#releases)), which ships the plugin that does it; without it the build warns and does not wait. `--min-free-memory=<GiB>` sets the amount, and 0 turns the wait off. `--jobs=N` uses fewer threads, which needs less memory but also makes the C compile slower.

Extra arguments are passed to Nuitka, e.g. `python build_exe.py --jobs=4`. Each step's duration is logged, to the console and to `build/logs/build_exe-<build id>.log`.

The executable's version is the `VERSION` file at the repository root. Each build records what it was built with in `build/nuitka/`: `build_info.json` (version, build time, whether it has OQS, Python, PySide6, Nuitka, torch and transformers versions, the Coqui checkout's commit, and the commit, its tree and the uncommitted changes of the checkout it was built from), which the executable logs at startup, and `build-requirements.lock.txt`, the build environment's `pip freeze`. At startup the executable also compares itself with that checkout, if it still exists, and logs a warning when the checkout has moved on (with the number of commits, using `git` when it is on `PATH`) or its uncommitted changes differ. Keep the lock file of a build that works: `python build_exe.py --lock=<file>` installs the build environment from it to repeat that build. Packages installed in `.venv-build` that the file does not list stay installed; delete `.venv-build` first for an exact copy. `--with-oqs` adds quantum-safe key encapsulation from [liboqs](https://github.com/open-quantum-safe/liboqs-python): the build installs liboqs-python and bundles the liboqs library it loads. A build without OQS cannot read data that a source checkout with liboqs encrypted using OQS keys: it starts without that cache and leaves it untouched, saves its own changes to `app_info_cache.no_oqs.json` in the cache folder, and refuses password-protected actions.

What the executable includes and leaves out:

- Coqui is the only TTS provider in the executable. Its models download on first use, as in a source checkout.
- Install separately: VLC, ffmpeg (on `PATH`) and Ollama.
- The executable shares its user data (see [User data](#user-data)) with a source checkout on the same machine and account.
- The first start unpacks the executable to `unpacked\muse-<build time>` in the user data folder above. This takes a while and several GB for an executable of this size. Each start removes the folders of older builds that are not running.
- Started from a terminal on Windows, the executable prints its log there, but the terminal does not wait for it. Use `start /wait dist\Muse.exe` to make it wait.

### Releases

Releases are made with [app-release](https://github.com/tomhallmain/release-tools), a separate tool installed with `pipx`: `app-release <checkout>` rebuilds the executable in `dist/` if it is behind `HEAD`, stages it in `dist/release/v<version>/` and publishes it as a GitHub release. See its README for the options.


## Testing

- `python -m pytest` runs the suite. Live-API tests are excluded by default.
- `python -m pytest -m api` runs those instead: they call external sources over the network. Other markers are `unit`, `integration` and `ui`.
- Append a path to run one file, or `path::Class::test_name` for a single test.


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
- `reddit` - Top posts from the subreddits in `reddit_subreddits`. Works with no account; `reddit_client_id`/`reddit_client_secret` lift the rate limit.
- `bluesky` - Posts from the feeds in `bluesky_feeds`. Works with no account; `bluesky_handle`/`bluesky_app_password` if the public API refuses anonymous reads.
- `mastodon` - Trending posts from `mastodon_instance`. No account needed.
- `poem` - Have the LLM generate a poem from its memory.
- `quote` - Have the LLM share a famous quote.
- `random_wiki_article` - Have the LLM summarize a random Wikipedia article.
- `truth_and_lie` - Small game to test both your and the LLM's knowledge.
- `fact` - Again, test the LLM's knowledge.
- `joke` - This one is still challenging for some of the local LLMs.
- `aphorism` - Have the LLM share an aphorism.
- `motivation` - The LLM should share an inspirational message of some sort.
- `language_learning` - If `muse_language_learning_languages` is set, the LLM will attempt to teach one of them (the current persona's `can_teach_languages` decides which).
- `fable` - Have the LLM share a fable. Unfortunately it usually seems to get stuck talking about kings or ants.
- `calendar` - Have the LLM tell you something interesting about the calendar day.

Since there is currently very limited capacity to prompt LLMs negatively, a blacklist feature was implemented. This feature will run your blacklist on any text generated by Muse and call the LLM until it finds a response that is not blacklisted, unless any of the blacklisted strings were found in the prompt. This is definitely not a perfect solution so it is recommended to modify the prompts to fit your purposes and use a model that can best handle your requests. The social sources above are filtered harder still -- only the configured communities are read, and a fetch that loses too much of itself to the blacklist is dropped rather than spoken from, so those topics sometimes pass silently.






