
import datetime
import traceback

from utils.utils import Utils

tts_runner_imported = False

try:
    Utils.log(f"Importing tts_runner...")
    from tts.tts_runner import TextToSpeechRunner
    tts_runner_imported = True
except Exception as e:
    Utils.log_red(e)
    Utils.log_yellow("Failed to import tts_runner.")

class Voice:
    MULTI_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"

    def __init__(self, coqui_named_voice="Royston Min"):
        self.can_speak = tts_runner_imported
        self._coqui_named_voice = coqui_named_voice
        self.model_args = (Voice.MULTI_MODEL, self._coqui_named_voice, "en")
        self._tts = TextToSpeechRunner(self.model_args, filepath="muse_voice", delete_interim_files=False, auto_play=False) if self.can_speak else None

    def say(self, text="", topic="", save_mp3=False):
        # Say immediately
        if not self.can_speak or self._tts is None:
            Utils.log_yellow("Cannot speak.")
            return
        temp_tts = TextToSpeechRunner(self.model_args, filepath="muse_voice", overwrite=True)
        current_time_str = str(datetime.datetime.now().timestamp())
        if "." in current_time_str:
            current_time_str = current_time_str.split(".")[0]
        self._tts.set_output_path(topic + "_" + current_time_str + "_")
        try:
            return temp_tts.speak(text, save_mp3=save_mp3)
        except Exception as e:
            Utils.log_red(e)
            traceback.print_exc()

    def prepare_to_say(self, text="", topic="", save_mp3=False):
        # Generate speech files from text, but don't play them yet
        if not self.can_speak or self._tts is None:
            Utils.log_yellow("Cannot speak.")
            return
        current_time_str = str(datetime.datetime.now().timestamp())
        if "." in current_time_str:
            current_time_str = current_time_str.split(".")[0]
        self._tts.set_output_path(topic + "_" + current_time_str + "_")
        try:
            return self._tts.speak(text, save_mp3=save_mp3)
        except Exception as e:
            Utils.log_red(e)
            traceback.print_exc()

    def finish_speaking(self):
        if not self.can_speak or self._tts is None:
            Utils.log_yellow("Cannot speak.")
            return
        self._tts.await_pending_speech_jobs()

