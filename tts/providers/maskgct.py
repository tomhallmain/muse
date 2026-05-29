"""
MaskGCT (Amphion) TTS provider.

MaskGCT is a zero-shot voice cloning model from CUHK / Tencent released for
non-commercial use.  It requires the Amphion library, which can be installed
via pip or by cloning the repository.

Install options:
    pip install amphion                         # pip package (may lag behind repo)
    git clone https://github.com/open-mmlab/Amphion && pip install -e Amphion/

Model weights are downloaded from HuggingFace on first use.

A reference audio file (3–10 s of clean speech) is required.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from tts.providers import BaseTTSProvider
from utils.logging_setup import get_logger

logger = get_logger(__name__)

# BCP-47 → MaskGCT language tag
_LANG_MAP: Dict[str, str] = {
    "en": "en",
    "zh": "zh",
    "fr": "fr",
    "de": "de",
    "ja": "ja",
    "ko": "ko",
    "es": "es",
    "pt": "pt",
}


def _try_import_maskgct():
    """Return the MaskGCTInference class, trying both install styles."""
    # 1. pip-installed amphion package
    try:
        from amphion.models.tts.maskgct.maskgct_inference import MaskGCTInference
        return MaskGCTInference
    except ImportError:
        pass
    # 2. Amphion repo cloned and added to sys.path
    try:
        from models.tts.maskgct.maskgct_inference import MaskGCTInference
        return MaskGCTInference
    except ImportError:
        pass
    return None


class MaskGCTProvider(BaseTTSProvider):
    """MaskGCT / Amphion zero-shot voice cloning provider (non-commercial)."""

    def __init__(
        self,
        reference_audio: Optional[str],
        language: str = "en",
    ) -> None:
        self.reference_audio = reference_audio or ""
        self.language = _LANG_MAP.get(language, "en")
        self._runner = None

        if self.reference_audio and not os.path.isfile(self.reference_audio):
            logger.warning(
                'MaskGCT reference audio not found: "%s". '
                "Set maskgct_reference_audio in config to a valid WAV file path.",
                self.reference_audio,
            )

    # ------------------------------------------------------------------
    # BaseTTSProvider interface
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        return _try_import_maskgct() is not None

    def load(self) -> None:
        MaskGCTInference = _try_import_maskgct()
        if MaskGCTInference is None:
            raise ImportError(
                "Failed to import MaskGCT. Install Amphion:\n"
                "    pip install amphion\n"
                "or clone: git clone https://github.com/open-mmlab/Amphion"
            )
        try:
            self._runner = MaskGCTInference(target_lang=self.language)
            self._runner.load_model()
            logger.info("MaskGCT loaded (lang=%s)", self.language)
        except Exception as exc:
            raise RuntimeError(
                f"MaskGCT model load failed: {exc}\n"
                "Ensure model weights are accessible (downloaded via HuggingFace Hub)."
            ) from exc

    def generate_speech_file(self, text: str, output_path: str, **kwargs) -> None:
        if self._runner is None:
            self.load()

        if not self.reference_audio or not os.path.isfile(self.reference_audio):
            raise ValueError(
                "MaskGCT requires a reference audio file (3–10 s WAV). "
                "Set maskgct_reference_audio in config."
            )

        target_lang = _LANG_MAP.get(kwargs.get("language", self.language), "en")

        # MaskGCT returns the path to the generated file or raw audio bytes
        # depending on the Amphion version.  We normalise both cases to a WAV
        # at output_path.
        result = self._runner.maskgct_inference(
            prompt_speech_path=self.reference_audio,
            target_text=text,
            target_lang=target_lang,
            prompt_lang=self.language,
            target_len=None,  # auto-predict duration
        )

        # result may be: a file path (str), a numpy array, or (array, sr) tuple
        if isinstance(result, str) and os.path.isfile(result):
            if os.path.abspath(result) != os.path.abspath(output_path):
                import shutil
                shutil.move(result, output_path)
        elif isinstance(result, tuple):
            wav, sr = result[0], result[1]
            import numpy as np
            import scipy.io.wavfile as wavfile
            wavfile.write(output_path, sr, (wav * 32767).astype(np.int16))
        else:
            # Assume raw numpy array; use a default sample rate
            import numpy as np
            import scipy.io.wavfile as wavfile
            wavfile.write(output_path, 24000, (result * 32767).astype(np.int16))

    @property
    def supports_voice_cloning(self) -> bool:
        return True

    @property
    def supported_languages(self) -> List[str]:
        return ["en", "zh", "fr", "de", "ja", "ko", "es", "pt"]

    def voices(self) -> List[str]:
        return []

    def metadata_info(self) -> Dict[str, Any]:
        ref_name = os.path.splitext(os.path.basename(self.reference_audio))[0] if self.reference_audio else "unknown"
        return {
            "artist":      f"{ref_name} (MaskGCT)",
            "albumartist": "MaskGCT / Amphion",
            "comment":     f"Generated using MaskGCT, ref: {self.reference_audio}",
        }
