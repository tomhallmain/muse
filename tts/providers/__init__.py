"""
TTS provider abstraction layer.

BaseTTSProvider is the interface every synthesis backend must implement.
TTSProviderType enumerates supported backends.
get_provider() is the factory used by TextToSpeechRunner.

See docs/tts-provider-abstraction.md for the full implementation plan.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List


class TTSProviderType(str, Enum):
    COQUI   = "coqui"
    KOKORO  = "kokoro"
    F5TTS   = "f5tts"
    MASKGCT = "maskgct"
    PIPER   = "piper"
    ZONOS   = "zonos"


class BaseTTSProvider(ABC):

    @abstractmethod
    def load(self) -> None:
        """Load model weights into memory (called once lazily before first synthesis)."""

    @abstractmethod
    def generate_speech_file(self, text: str, output_path: str, **kwargs) -> None:
        """Synthesise *text* and write the result to *output_path* as a WAV file."""

    @property
    @abstractmethod
    def supports_voice_cloning(self) -> bool:
        """True if this provider accepts a reference audio path as the voice."""

    @property
    @abstractmethod
    def supported_languages(self) -> List[str]:
        """BCP-47 language codes this provider handles reliably."""

    def is_available(self) -> bool:
        """Lightweight check that required packages/files are present on this system.

        Called during TextToSpeechRunner initialisation.  Should not load model
        weights — just verify that the provider *could* run if asked.
        """
        return True

    def voices(self) -> List[str]:
        """Enumerable voice names or IDs.

        Returns an empty list for file-path-based providers (F5-TTS, MaskGCT,
        Piper) where the voice is identified by a path rather than a name.
        """
        return []

    def metadata_info(self) -> Dict[str, Any]:
        """Provider-specific MP3 metadata fields.

        Keys understood by TextToSpeechRunner.add_metadata:
            "artist"      — credited voice/speaker string
            "albumartist" — TTS engine name
            "comment"     — model/version details
        """
        return {}


def get_provider(tts_config: Any) -> BaseTTSProvider:
    """Factory: return the correct BaseTTSProvider for *tts_config*.

    *tts_config* is a TTSConfig instance.  Uses Any to avoid a circular import
    (TTSConfig lives in tts.tts_runner which imports from this package).
    Provider-specific settings (voice, model paths) are read from
    utils.config.config so TTSConfig itself stays minimal.
    """
    from utils.config import config as app_config

    provider_type = getattr(tts_config, "provider", TTSProviderType.COQUI)

    # tts_config.voice is a per-invocation override (e.g. a persona's voice_name).
    # When set it takes precedence over the app-level config for the active provider.
    per_voice = getattr(tts_config, "voice", None) or None

    if provider_type == TTSProviderType.COQUI:
        from tts.providers.coqui import CoquiTTSProvider
        model = tts_config.model
        if per_voice and model and per_voice != model[1]:
            model = (model[0], per_voice, model[2])
        return CoquiTTSProvider(model=model)

    if provider_type == TTSProviderType.KOKORO:
        from tts.providers.kokoro import KokoroTTSProvider
        return KokoroTTSProvider(
            voice=per_voice or getattr(app_config, "kokoro_voice", "af_heart"),
            model=getattr(app_config, "kokoro_model", "kokoro-v1.0"),
        )

    if provider_type == TTSProviderType.F5TTS:
        from tts.providers.f5tts import F5TTSProvider
        return F5TTSProvider(
            reference_audio=per_voice or getattr(app_config, "f5tts_reference_audio", None),
            reference_text=getattr(app_config, "f5tts_reference_text", ""),
            model=getattr(app_config, "f5tts_model", "F5TTS_v1_Base"),
        )

    if provider_type == TTSProviderType.MASKGCT:
        from tts.providers.maskgct import MaskGCTProvider
        return MaskGCTProvider(
            reference_audio=per_voice or getattr(app_config, "maskgct_reference_audio", None),
            language=getattr(app_config, "maskgct_language", "en"),
        )

    if provider_type == TTSProviderType.PIPER:
        from tts.providers.piper import PiperTTSProvider
        return PiperTTSProvider(
            model_path=per_voice or getattr(app_config, "piper_model_path", None),
            language=getattr(tts_config, "language", "en"),
            quality=getattr(app_config, "piper_quality", "medium"),
            voices_dir=getattr(app_config, "piper_voices_dir", None),
            auto_download=getattr(app_config, "piper_auto_download", True),
        )

    if provider_type == TTSProviderType.ZONOS:
        from tts.providers.zonos import ZonosTTSProvider
        return ZonosTTSProvider(
            reference_audio=per_voice or getattr(app_config, "zonos_reference_audio", None),
            model=getattr(app_config, "zonos_model", "Zyphra/Zonos-v0.1-transformer"),
            language=getattr(app_config, "zonos_language", "en")
            or getattr(tts_config, "language", "en"),
        )

    raise ValueError(
        f"Unknown TTS provider: '{provider_type}'. "
        f"Valid options: {[t.value for t in TTSProviderType]}"
    )
