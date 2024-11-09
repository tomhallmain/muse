
import datetime

tts_runner_imported = False

try:
    print(f"Importing tts_runner...")
    from tts.tts_runner import TextToSpeechRunner
    tts_runner_imported = True
except Exception as e:
    print(e)
    print("Failed to import tts_runner.")

class Voice:
    MULTI_MODEL = ("tts_models/multilingual/multi-dataset/xtts_v2", "Royston Min", "en")

    def __init__(self):
        self.can_speak = tts_runner_imported
        self._tts = TextToSpeechRunner(Voice.MULTI_MODEL, filepath="test") if self.can_speak else None

    def say(self, text, topic=""):
        if not self.can_speak or self._tts is None:
            print("Cannot speak.")
            return
        current_time_str = str(datetime.datetime.now().timestamp())
        if "." in current_time_str:
            current_time_str = current_time_str.split(".")[0]
        self._tts.set_output_path(topic + "_" + current_time_str + "_")
        return self._tts.speak(text)

