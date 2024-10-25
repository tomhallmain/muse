
import os
import sys
import datetime
sys.path.insert(0, os.path.join(os.path.expanduser('~'), "TTS-dev"))
from my_tts_runner import TextToSpeechRunner

class Voice:
    MULTI_MODEL = ("tts_models/multilingual/multi-dataset/xtts_v2", "Royston Min", "en")

    def __init__(self):
        self._tts = TextToSpeechRunner(Voice.MULTI_MODEL, filepath="test")
    
    def say(self, text, topic=""):
        current_time_str = str(datetime.datetime.now().timestamp())
        if "." in current_time_str:
            current_time_str = current_time_str.split(".")[0]
        self._tts.set_output_path(topic + "_" + current_time_str + "_")
        return self._tts.speak(text)

