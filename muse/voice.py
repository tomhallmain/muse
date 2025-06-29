import datetime
import traceback

from utils.logging_setup import get_logger

logger = get_logger(__name__)

tts_runner_imported = False

try:
    logger.info(f"Importing tts_runner...")
    from tts.tts_runner import TextToSpeechRunner, TTSConfig
    tts_runner_imported = True
except Exception as e:
    logger.error(e)
    logger.warning("Failed to import tts_runner.")


class Voice:
    MULTI_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"

    def __init__(self, coqui_named_voice="Royston Min", run_context=None):
        self.can_speak = tts_runner_imported
        self._coqui_named_voice = coqui_named_voice
        self.model_args = (Voice.MULTI_MODEL, self._coqui_named_voice, "en")
        self.run_context = run_context
        if self.can_speak:
            config = TTSConfig(
                model=self.model_args,
                filepath="muse_voice",
                delete_interim_files=False,
                auto_play=False,
                run_context=self.run_context
            )
            self._tts = TextToSpeechRunner(config)
        else:
            self._tts = None

    def say(self, text="", topic="", save_mp3=False, locale=None):
        # Say immediately
        if not self.can_speak or self._tts is None:
            logger.warning("Cannot speak.")
            return
        logger.info(f"Saying: {text}")
        config = TTSConfig(
            model=self.model_args,
            filepath="muse_voice",
            overwrite=True,
            run_context=self.run_context
        )
        temp_tts = TextToSpeechRunner(config)
        current_time_str = str(datetime.datetime.now().timestamp())
        if "." in current_time_str:
            current_time_str = current_time_str.split(".")[0]
        self._tts.set_output_path(topic + "_" + current_time_str + "_")
        try:
            return temp_tts.speak(text, save_mp3=save_mp3, locale=locale)
        except Exception as e:
            logger.error(e)
            traceback.print_exc()

    def prepare_to_say(self, text="", topic="", save_mp3=False, save_for_last=False, locale=None):
        # Generate speech files from text, but don't play them yet
        if not self.can_speak or self._tts is None:
            logger.warning("Cannot speak.")
            return
        logger.info(f"Preparing to say: {text}")
        if save_for_last:
            self._tts.await_pending_speech_jobs(run_jobs=False)
        current_time_str = str(datetime.datetime.now().timestamp())
        if "." in current_time_str:
            current_time_str = current_time_str.split(".")[0]
        self._tts.set_output_path(topic + "_" + current_time_str + "_")
        try:
            return self._tts.speak(text, save_mp3=save_mp3, locale=locale)
        except Exception as e:
            logger.error(e)
            traceback.print_exc()

    def speak_file(self, filepath, topic="", save_mp3=False, split_on_each_line=False, locale=None):
        # Process a file and speak its contents
        if not self.can_speak or self._tts is None:
            logger.warning("Cannot speak.")
            return
        logger.info(f"Speaking file: {filepath}")
        config = TTSConfig(
            model=self.model_args,
            filepath="muse_voice",
            overwrite=True,
            run_context=self.run_context
        )
        temp_tts = TextToSpeechRunner(config)
        current_time_str = str(datetime.datetime.now().timestamp())
        if "." in current_time_str:
            current_time_str = current_time_str.split(".")[0]
        self._tts.set_output_path(topic + "_" + current_time_str + "_")
        try:
            return temp_tts.speak_file(filepath, save_mp3=save_mp3, split_on_each_line=split_on_each_line, locale=locale)
        except Exception as e:
            logger.error(e)
            traceback.print_exc()

    def finish_speaking(self):
        # Wait for all pending speech to complete
        if not self.can_speak or self._tts is None:
            logger.warning("Cannot speak.")
            return
        self._tts.await_pending_speech_jobs()

    def add_speech_file_to_queue(self, filepath):
        if not self.can_speak or self._tts is None:
            logger.warning("Cannot speak.")
            return
        self._tts.add_speech_file_to_queue(filepath)


