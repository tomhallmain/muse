"""
Zonos TTS provider (Zyphra).

Zonos-v0.1 is an open-weight multilingual TTS model (Apache 2.0) with zero-shot
voice cloning from a short reference clip (10–30 s recommended).

Install:
    pip install git+https://github.com/Zyphra/Zonos.git
    # or: pip install zonos   (PyPI dev release, may lag behind GitHub)

System dependency (phonemization):
    espeak-ng on PATH  (https://github.com/espeak-ng/espeak-ng)

Model weights download from HuggingFace on first use. GPU with 6 GB+ VRAM is
recommended; CPU works but is slow. Official support is Linux/macOS; Windows
users may need https://github.com/sdbds/Zonos-for-windows .
"""

from __future__ import annotations

import os
import shutil
from typing import Any, Dict, List, Optional

from tts.providers import BaseTTSProvider
from utils.logging_setup import get_logger

logger = get_logger(__name__)

# HuggingFace model IDs accepted by Zonos.from_pretrained()
ZONOS_MODELS: List[str] = [
    "Zyphra/Zonos-v0.1-transformer",
    "Zyphra/Zonos-v0.1-hybrid",
]

# Muse BCP-47 language_code → Zonos language tag (see zonos.conditioning)
_LANG_MAP: Dict[str, str] = {
    "en":    "en-us",
    "en-us": "en-us",
    "en-gb": "en-gb",
    "de":    "de",
    "fr":    "fr-fr",
    "ja":    "ja",
    "zh":    "cmn",
    "cmn":   "cmn",
}


def _espeak_available() -> bool:
    return bool(shutil.which("espeak-ng") or shutil.which("espeak"))


class ZonosTTSProvider(BaseTTSProvider):
    """Zonos zero-shot voice cloning provider."""

    def __init__(
        self,
        reference_audio: Optional[str],
        model: str = "Zyphra/Zonos-v0.1-transformer",
        language: str = "en",
    ) -> None:
        self.reference_audio = reference_audio or ""
        self.model_name = model or "Zyphra/Zonos-v0.1-transformer"
        self.language = language or "en"
        self._model = None
        self._speaker = None
        self._speaker_source: str = ""

        if self.model_name not in ZONOS_MODELS:
            logger.warning(
                'Unknown Zonos model "%s". Known models: %s',
                self.model_name,
                ", ".join(ZONOS_MODELS),
            )

        if self.reference_audio and not os.path.isfile(self.reference_audio):
            logger.warning(
                'Zonos reference audio not found: "%s". '
                "Set zonos_reference_audio in config to a valid audio file.",
                self.reference_audio,
            )

    # ------------------------------------------------------------------
    # BaseTTSProvider interface
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        try:
            import importlib.util
            return importlib.util.find_spec("zonos.model") is not None
        except Exception:
            return False

    def load(self) -> None:
        if not _espeak_available():
            logger.warning(
                "espeak-ng not found on PATH. Zonos requires espeak-ng for phonemization."
            )
        try:
            from zonos.model import Zonos
            from zonos.utils import DEFAULT_DEVICE as device

            self._model = Zonos.from_pretrained(self.model_name, device=device)
            logger.info("Zonos loaded: %s (device=%s)", self.model_name, device)
        except Exception as exc:
            raise ImportError(
                "Failed to load Zonos. Install with:\n"
                "    pip install git+https://github.com/Zyphra/Zonos.git\n"
                "Also install espeak-ng and ensure PyTorch/torchaudio are available."
            ) from exc

    def _speaker_embedding(self):
        if self._model is None:
            self.load()

        if not self.reference_audio or not os.path.isfile(self.reference_audio):
            raise ValueError(
                "Zonos requires a reference audio clip (10–30 s WAV/MP3/FLAC). "
                "Set zonos_reference_audio in config."
            )

        if self._speaker is not None and self._speaker_source == self.reference_audio:
            return self._speaker

        import torchaudio

        wav, sampling_rate = torchaudio.load(self.reference_audio)
        self._speaker = self._model.make_speaker_embedding(wav, sampling_rate)
        self._speaker_source = self.reference_audio
        return self._speaker

    def generate_speech_file(self, text: str, output_path: str, **kwargs) -> None:
        if self._model is None:
            self.load()

        from zonos.conditioning import make_cond_dict
        import torchaudio

        language = kwargs.get("language", self.language)
        lang_code = _LANG_MAP.get(language, "en-us")

        speaker = self._speaker_embedding()
        cond_dict = make_cond_dict(text=text, speaker=speaker, language=lang_code)
        conditioning = self._model.prepare_conditioning(cond_dict)
        codes = self._model.generate(conditioning)
        wavs = self._model.autoencoder.decode(codes).cpu()
        torchaudio.save(output_path, wavs[0], self._model.autoencoder.sampling_rate)

    @property
    def supports_voice_cloning(self) -> bool:
        return True

    @property
    def supported_languages(self) -> List[str]:
        return ["en", "de", "fr", "ja", "zh"]

    def voices(self) -> List[str]:
        return []

    def metadata_info(self) -> Dict[str, Any]:
        ref_name = (
            os.path.splitext(os.path.basename(self.reference_audio))[0]
            if self.reference_audio
            else "unknown"
        )
        return {
            "artist":      f"{ref_name} (Zonos)",
            "albumartist": "Zonos / Zyphra",
            "comment":     (
                f"Generated using Zonos model: {self.model_name}, "
                f"ref: {self.reference_audio}"
            ),
        }
