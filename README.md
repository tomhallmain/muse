
# Muse

Muse is a media player with an integrated voice synthesizer attached to an LLM. Essentially, a robot DJ for your music and other media.


## Installation steps

- Download Coqui-TTS source from https://github.com/coqui-ai/TTS
- Install Coqui-TTS using `pip install -e.`
- Set `coqui_tts_location` in config.json in configs folder to the path of Coqui-TTS source.
- Download and install Ollama following the instructions at https://github.com/ollama/ollama
- Ensure Ollama is operational and serving with `ollama serve`
- In a virtual environment, run `pip install -r requirements.txt` on this directory.
- Note: To run TTS by itself, run the run_tts.py file with a text file.


## Configuration

- Set `LANGUAGE` environment variable to desired i18n code. If not supported, the language will default to English.
- `directories` - Add the paths of any audio or video file directories Muse should be playing to this list.
- `text_cleaner_ruleset` - Add a dictionary of text cleaning rules to be run on text before Muse speaks it.
- `coqui_tts_model` - Set the TTS model and speaker to be used by Muse.
- For weather, news, calendar data etc set the appropriate API keys.
- `open_weather_city` - Set the city for Muse to use for weather data.
- `muse_config`
    - `enable_preparation` - Allows Muse to begin text-to-speech generation before songs end to minimize delays between songs.
    - `preparation_starts_minutes_from_end` - Set the number of minutes from the end of a song that Muse should begin text-to-speech generation.
    - `preparation_starts_after_seconds_sleep` - Set the number of seconds into a song to wait before starting text-to-speech generation.
    - `chance_speak_after_track` - Set the chance that Muse will speak after each track identifying the previous song or other media.
    - `chance_speak_before_track` - Set the chance that Muse will speak before each track identifying the upcoming song or other media.
    - `chance_speak_about_other_topics` - Set the chance that Muse will speak about other topics.
- `news_api_source_trustworthiness` - Set the trustworthiness of news sources from News API.


## Directory Structure

In the absence of track details found on the music file itself, Muse will attempt to infer track details from the file path. If artists or composers are predefined in the library_data/data folder, the `indicators` list on each will test the track name and path for a string match, and assign the appropriate attribute if a match is found. If no matches are found, the basic logic assumes the following directory structure:
- Root folder
    - Artist
        - Album
            - Track 1
            - Track 2

## Scheduling

A default voice is set for Muse, but any of the Coqui voice options can be used by creating a schedule. In a schedule you can also set an hour for the application to shut down automatically on given days of the week.

## Usage

- In your virtual environment, run `python app.py` to start the application.


