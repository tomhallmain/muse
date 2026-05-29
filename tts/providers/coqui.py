"""
Coqui XTTS v2 TTS provider.

Wraps the abandoned-but-still-functional Coqui TTS library.  All Coqui-
specific logic (sys.path manipulation, TTS import, device detection, fuzzy
speaker matching) lives here so tts_runner.py has no direct Coqui dependency.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

from tts.providers import BaseTTSProvider
from tts.speakers import speakers as COQUI_SPEAKERS
from utils.config import config
from utils.logging_setup import get_logger
from utils.utils import Utils

logger = get_logger(__name__)


class CoquiTTSProvider(BaseTTSProvider):
    """Coqui XTTS v2 provider.  Maintained for backward compatibility."""

    def __init__(self, model: tuple) -> None:
        # model = (model_name, speaker_name, language_code)
        # Resolve the speaker name at construction time so misconfigured
        # voice names are caught early and the fuzzy fallback is applied
        # before any TTS model is loaded.
        model_name, speaker, language = model[0], model[1], model[2]
        resolved = self.resolve_voice_name(speaker) if speaker else speaker
        self.model = (model_name, resolved, language)
        self._TTS = None  # lazy-loaded by load()

    # ------------------------------------------------------------------
    # BaseTTSProvider interface
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return True if the TTS package can be imported from coqui_tts_location."""
        try:
            location = config.coqui_tts_location
            if location and location not in sys.path:
                sys.path.insert(0, location)
            import importlib.util
            return importlib.util.find_spec("TTS") is not None
        except Exception:
            return False

    def load(self) -> None:
        location = config.coqui_tts_location
        if location and location not in sys.path:
            sys.path.insert(0, location)
        try:
            from TTS.api import TTS
            self._TTS = TTS
            logger.info("Coqui TTS loaded successfully")
        except ImportError as exc:
            raise ImportError(
                "Failed to import Coqui TTS. Ensure the library is downloaded "
                "and \"coqui_tts_location\" is set correctly in the config."
            ) from exc

    def generate_speech_file(self, text: str, output_path: str, **kwargs) -> None:
        if self._TTS is None:
            self.load()
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        tts = self._TTS(model_name=self.model[0], progress_bar=False).to(device)
        try:
            tts.tts_to_file(
                text=text,
                speaker=self.model[1],
                file_path=output_path,
                language=self.model[2],
            )
        except Exception as exc:
            logger.error("Coqui TTS generation failed: %s", exc)
            if not os.path.exists(output_path):
                raise Exception("Coqui TTS failed to generate audio file") from exc
            # File was created despite the error — continue.
            logger.info("Coqui TTS wrote file despite error, continuing...")

    @property
    def supports_voice_cloning(self) -> bool:
        return True

    @property
    def supported_languages(self) -> List[str]:
        return [
            "en", "de", "fr", "es", "it", "pt", "pl", "tr", "ru",
            "nl", "cs", "ar", "zh", "hu", "ko", "ja", "hi",
        ]

    def voices(self) -> List[str]:
        return list(COQUI_SPEAKERS)

    def metadata_info(self) -> Dict[str, Any]:
        speaker = self.model[1] or "Unknown Speaker"
        comment = f"Generated using CoquiAI TTS model: {self.model[0]}"
        if self.model[2]:
            comment += f" (Language: {self.model[2]})"
        return {
            "artist":      f"{speaker} (CoquiAI)",
            "albumartist": "CoquiAI TTS",
            "comment":     comment,
        }

    # ------------------------------------------------------------------
    # Coqui-specific helpers
    # ------------------------------------------------------------------

    def resolve_voice_name(self, voice_name: str) -> str:
        """Return *voice_name* if valid, or the closest fuzzy match from COQUI_SPEAKERS."""
        if voice_name in COQUI_SPEAKERS:
            return voice_name
        for speaker in COQUI_SPEAKERS:
            if Utils.is_similar_strings(speaker, voice_name):
                logger.warning(
                    'Fuzzy-matched Coqui voice "%s" → "%s"', voice_name, speaker
                )
                return speaker
        logger.warning('Unknown Coqui voice "%s", using as-is.', voice_name)
        return voice_name
