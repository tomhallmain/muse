"""
F5-TTS provider.

F5-TTS is a zero-shot voice cloning model released under MIT license.
Install: pip install f5-tts

A reference audio file (3–10 s of clean speech) is required.  Reference text
is optional — F5-TTS will auto-transcribe via faster-whisper if left empty.
Model weights are downloaded from HuggingFace on first use.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from tts.providers import BaseTTSProvider
from utils.logging_setup import get_logger

logger = get_logger(__name__)


class F5TTSProvider(BaseTTSProvider):
    """F5-TTS zero-shot voice cloning provider."""

    def __init__(
        self,
        reference_audio: Optional[str],
        reference_text: str = "",
        model: str = "F5TTS_v1_Base",
    ) -> None:
        self.reference_audio = reference_audio or ""
        self.reference_text = reference_text or ""
        self.model_name = model or "F5TTS_v1_Base"
        self._model = None

        if self.reference_audio and not os.path.isfile(self.reference_audio):
            logger.warning(
                'F5-TTS reference audio not found: "%s". '
                "Set f5tts_reference_audio in config to a valid WAV file path.",
                self.reference_audio,
            )

    # ------------------------------------------------------------------
    # BaseTTSProvider interface
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        try:
            import importlib.util
            return importlib.util.find_spec("f5_tts") is not None
        except Exception:
            return False

    def load(self) -> None:
        try:
            from f5_tts.api import F5TTS
            self._model = F5TTS(model_type=self.model_name)
            logger.info("F5-TTS loaded: %s", self.model_name)
        except Exception as exc:
            raise ImportError(
                "Failed to load F5-TTS. "
                "Install with: pip install f5-tts"
            ) from exc

    def generate_speech_file(self, text: str, output_path: str, **kwargs) -> None:
        if self._model is None:
            self.load()

        if not self.reference_audio or not os.path.isfile(self.reference_audio):
            raise ValueError(
                "F5-TTS requires a reference audio file (3–10 s WAV). "
                "Set f5tts_reference_audio in config."
            )

        self._model.infer(
            ref_file=self.reference_audio,
            ref_text=self.reference_text,  # empty → auto-transcribed
            gen_text=text,
            file_wave=output_path,
        )

    @property
    def supports_voice_cloning(self) -> bool:
        return True

    @property
    def supported_languages(self) -> List[str]:
        # EN is flagship; ZH is experimental
        return ["en", "zh"]

    def voices(self) -> List[str]:
        # File-path based — no enumerable voice list
        return []

    def metadata_info(self) -> Dict[str, Any]:
        ref_name = os.path.splitext(os.path.basename(self.reference_audio))[0] if self.reference_audio else "unknown"
        return {
            "artist":      f"{ref_name} (F5-TTS)",
            "albumartist": "F5-TTS",
            "comment":     f"Generated using F5-TTS model: {self.model_name}, ref: {self.reference_audio}",
        }
