import datetime
import traceback

from utils.config import config as app_config
from utils.logging_setup import get_logger

logger = get_logger(__name__)

tts_runner_imported = False

try:
    logger.info("Importing tts_runner...")
    from tts.tts_runner import TextToSpeechRunner, TTSConfig
    from tts.providers import TTSProviderType
    tts_runner_imported = True
except Exception as e:
    logger.error(e)
    logger.warning("Failed to import tts_runner.")


def _resolve_provider() -> "TTSProviderType":
    """Read the active TTS provider from config, defaulting to Coqui."""
    provider_str = getattr(app_config, "tts_provider", "coqui") or "coqui"
    try:
        return TTSProviderType(provider_str.lower())
    except (ValueError, NameError):
        logger.warning("Unknown tts_provider '%s', falling back to coqui.", provider_str)
        return TTSProviderType.COQUI


class Voice:
    # Coqui model name kept as a class constant for backward compatibility.
    MULTI_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"

    def __init__(
        self,
        voice_name: str = "Royston Min",
        language: str = "en",
        run_context=None,
    ) -> None:
        self._voice_name = voice_name
        self._language = language
        self.run_context = run_context
        self._tts = None
        self.can_speak = False

        if tts_runner_imported:
            try:
                self._provider = _resolve_provider()
                tts_config = self._make_config(
                    delete_interim_files=False,
                    auto_play=False,
                )
                self._tts = TextToSpeechRunner(tts_config)
                self.can_speak = True
            except Exception as e:
                logger.error("Failed to initialise TTS runner: %s", e)
                logger.warning("Voice synthesis disabled.")
        else:
            self._provider = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_config(self, overwrite: bool = False, **extra) -> "TTSConfig":
        """Build a TTSConfig for the active provider and this persona's voice."""
        coqui_model = None
        if self._provider == TTSProviderType.COQUI:
            coqui_tuple = getattr(app_config, "coqui_tts_model", None)
            model_name = coqui_tuple[0] if coqui_tuple else Voice.MULTI_MODEL
            lang = self._language or (coqui_tuple[2] if coqui_tuple else "en")
            coqui_model = (model_name, self._voice_name, lang)

        return TTSConfig(
            model=coqui_model,
            provider=self._provider,
            voice=self._voice_name,
            language=self._language,
            filepath="muse_voice",
            overwrite=overwrite,
            run_context=self.run_context,
            **extra,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def say(self, text: str = "", topic: str = "", save_mp3: bool = False, locale=None):
        """Synthesise *text* immediately and play it."""
        if not self.can_speak or self._tts is None:
            logger.warning("Cannot speak.")
            return
        logger.info("Saying: %s", text)
        temp_tts = TextToSpeechRunner(self._make_config(overwrite=True))
        current_time_str = str(datetime.datetime.now().timestamp()).split(".")[0]
        self._tts.set_output_path(topic + "_" + current_time_str + "_")
        try:
            return temp_tts.speak(text, save_mp3=save_mp3, locale=locale)
        except Exception as e:
            logger.error(e)
            traceback.print_exc()

    def prepare_to_say(
        self,
        text: str = "",
        topic: str = "",
        save_mp3: bool = False,
        save_for_last: bool = False,
        locale=None,
    ):
        """Pre-generate speech for *text* without blocking playback."""
        if not self.can_speak or self._tts is None:
            logger.warning("Cannot speak.")
            return
        logger.info("Preparing to say: %s", text)
        if save_for_last:
            self._tts.await_pending_speech_jobs(run_jobs=False)
        current_time_str = str(datetime.datetime.now().timestamp()).split(".")[0]
        self._tts.set_output_path(topic + "_" + current_time_str + "_")
        try:
            return self._tts.speak(text, save_mp3=save_mp3, locale=locale)
        except Exception as e:
            logger.error(e)
            traceback.print_exc()

    def speak_file(
        self,
        filepath: str,
        topic: str = "",
        save_mp3: bool = False,
        split_on_each_line: bool = False,
        locale=None,
    ):
        """Synthesise the contents of *filepath* and play them."""
        if not self.can_speak or self._tts is None:
            logger.warning("Cannot speak.")
            return
        logger.info("Speaking file: %s", filepath)
        temp_tts = TextToSpeechRunner(self._make_config(overwrite=True))
        current_time_str = str(datetime.datetime.now().timestamp()).split(".")[0]
        self._tts.set_output_path(topic + "_" + current_time_str + "_")
        try:
            return temp_tts.speak_file(
                filepath,
                save_mp3=save_mp3,
                split_on_each_line=split_on_each_line,
                locale=locale,
            )
        except Exception as e:
            logger.error(e)
            traceback.print_exc()

    def finish_speaking(self):
        """Block until all pending speech jobs complete."""
        if not self.can_speak or self._tts is None:
            logger.warning("Cannot speak.")
            return
        self._tts.await_pending_speech_jobs()

    def clear_queue(self):
        """Cancel all pending speech jobs so priority speech plays immediately."""
        if not self.can_speak or self._tts is None:
            return
        self._tts.speech_queue.cancel()

    def add_speech_file_to_queue(self, filepath: str):
        if not self.can_speak or self._tts is None:
            logger.warning("Cannot speak.")
            return
        self._tts.add_speech_file_to_queue(filepath)
