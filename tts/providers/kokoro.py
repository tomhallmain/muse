"""
Kokoro ONNX TTS provider.

Kokoro is a lightweight (~82M parameter) TTS model released under Apache 2.0.
Install: pip install kokoro-onnx

Model weights are downloaded automatically from HuggingFace on first use.
Voice is a fixed named ID (no reference audio required).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from tts.providers import BaseTTSProvider
from utils.logging_setup import get_logger

logger = get_logger(__name__)

# Known voice IDs for Kokoro v1.0.
# Prefix legend: a=American, b=British, j=Japanese, z=Mandarin,
#                e=Spanish, f=French, h=Hindi, i=Italian, p=Portuguese, k=Korean
# Second letter: f=Female, m=Male
KOKORO_VOICES: List[str] = [
    # American English
    "af", "af_bella", "af_heart", "af_nicole", "af_sarah", "af_sky",
    "am_adam", "am_michael",
    # British English
    "bf_emma", "bf_isabella",
    "bm_george", "bm_lewis",
    # Japanese
    "jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro",
    "jm_kumo",
    # Mandarin Chinese
    "zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi",
    "zm_yunxi", "zm_yunjian", "zm_yunxia",
    # Spanish
    "ef_dora", "em_alex", "em_santa",
    # French
    "ff_siwis",
    # Hindi
    "hf_alpha", "hf_beta", "hm_omega", "hm_psi",
    # Italian
    "if_sara", "im_nicola",
    # Brazilian Portuguese
    "pf_dora", "pm_alex", "pm_santa",
    # Korean
    "kf_alpha", "kf_beta", "km_omega",
]

# Map from our BCP-47 language_code to Kokoro's lang parameter.
_LANG_MAP: Dict[str, str] = {
    "en":    "en-us",
    "en-us": "en-us",
    "en-gb": "en-gb",
    "ja":    "ja",
    "zh":    "zh",
    "es":    "es",
    "fr":    "fr",
    "hi":    "hi",
    "it":    "it",
    "pt":    "pt-br",
    "ko":    "ko",
}


class KokoroTTSProvider(BaseTTSProvider):
    """Kokoro ONNX TTS — fast, high-quality named-voice synthesis."""

    def __init__(self, voice: str = "af_heart", model: str = "kokoro-v1.0") -> None:
        self.voice = voice or "af_heart"
        self.model_name = model or "kokoro-v1.0"
        self._kokoro = None

        if self.voice not in KOKORO_VOICES:
            logger.warning(
                'Unknown Kokoro voice "%s". '
                "Run KokoroTTSProvider().voices() for the full list.",
                self.voice,
            )

    # ------------------------------------------------------------------
    # BaseTTSProvider interface
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        try:
            import importlib.util
            return importlib.util.find_spec("kokoro_onnx") is not None
        except Exception:
            return False

    def load(self) -> None:
        try:
            from kokoro_onnx import Kokoro
            self._kokoro = Kokoro.from_pretrained(self.model_name)
            logger.info("Kokoro TTS loaded: %s", self.model_name)
        except Exception as exc:
            raise ImportError(
                "Failed to load Kokoro TTS. "
                "Install with: pip install kokoro-onnx"
            ) from exc

    def generate_speech_file(self, text: str, output_path: str, **kwargs) -> None:
        if self._kokoro is None:
            self.load()
        language = kwargs.get("language", "en")
        lang_code = _LANG_MAP.get(language, "en-us")

        samples, sample_rate = self._kokoro.create(
            text,
            voice=self.voice,
            speed=1.0,
            lang=lang_code,
        )

        import numpy as np
        import scipy.io.wavfile as wavfile
        wavfile.write(output_path, sample_rate, (samples * 32767).astype(np.int16))

    @property
    def supports_voice_cloning(self) -> bool:
        return False

    @property
    def supported_languages(self) -> List[str]:
        return ["en", "ja", "zh", "es", "fr", "hi", "it", "pt", "ko"]

    def voices(self) -> List[str]:
        return list(KOKORO_VOICES)

    def metadata_info(self) -> Dict[str, Any]:
        return {
            "artist":      f"{self.voice} (Kokoro)",
            "albumartist": "Kokoro TTS",
            "comment":     f"Generated using Kokoro model: {self.model_name}, voice: {self.voice}",
        }
