
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

- `directories` - Add the paths of any audio or video file directories Muse should be playing to this list.
- `text_cleaner_ruleset` - Add a dictionary of text cleaning rules to be run on text before Muse speaks it.
- `coqui_tts_model` - Set the TTS model and speaker to be used by Muse.
- For weather, news, calendar data etc set the appropriate API keys.


## Usage

- In your virtual environment, run `python app.py` to start the application.

