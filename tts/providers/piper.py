"""
Piper TTS provider.

Piper is a fast, CPU-friendly neural TTS engine with pre-built voices for
35+ languages, released under Apache 2.0 / MIT.
Install: pip install piper-tts

Voice registry
--------------
All official voices are indexed at:
  https://huggingface.co/rhasspy/piper-voices/resolve/main/voices.json

Each entry is keyed by "{lang_region}-{name}-{quality}" (e.g.
"de_DE-thorsten-medium") and contains language metadata and relative file
paths under the same HuggingFace repo.  Every voice consists of two files:
  {lang}/{lang_region}/{name}/{quality}/{lang_region}-{name}-{quality}.onnx
  {lang}/{lang_region}/{name}/{quality}/{lang_region}-{name}-{quality}.onnx.json

Quality tiers (ascending): x_low < low < medium < high

Auto-download
-------------
If piper_model_path is not set (or does not exist), the provider will
auto-download a voice for the requested language code, provided
piper_auto_download is True in config.  Models are cached in
piper_voices_dir (default: configs/piper_voices/).

Manual use
----------
Set piper_model_path in config.json to the full path of any downloaded
.onnx file to bypass auto-selection entirely.
"""

from __future__ import annotations

import json
import os
import urllib.request
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tts.providers import BaseTTSProvider
from utils.logging_setup import get_logger

logger = get_logger(__name__)

_VOICES_INDEX_URL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/voices.json"
)
_HF_BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"

# Quality preference order when selecting a voice automatically.
_QUALITY_PREFERENCE = ("medium", "high", "low", "x_low")


# ---------------------------------------------------------------------------
# Voices-index helpers
# ---------------------------------------------------------------------------

def _fetch_voices_index(cache_dir: Path) -> Dict[str, Any]:
    """Return the parsed voices.json, using a local cache if present."""
    cache_file = cache_dir / "voices.json"
    if cache_file.is_file():
        try:
            with cache_file.open(encoding="utf-8") as fh:
                return json.load(fh)
        except Exception as exc:
            logger.warning("Could not read cached voices.json: %s", exc)

    logger.info("Fetching Piper voices index from HuggingFace…")
    try:
        with urllib.request.urlopen(_VOICES_INDEX_URL, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        cache_dir.mkdir(parents=True, exist_ok=True)
        with cache_file.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        return data
    except Exception as exc:
        raise RuntimeError(
            f"Failed to fetch Piper voices index: {exc}\n"
            "Check your internet connection or set piper_model_path manually."
        ) from exc


def _pick_voice(
    index: Dict[str, Any],
    language_code: str,
    quality: str = "medium",
) -> Tuple[str, List[str]]:
    """Return (voice_key, [file_path, …]) for the best matching voice.

    Matches on the language *family* code (e.g. 'de' matches 'de_DE',
    'de_CH', etc.).  Falls back through quality tiers if the preferred
    quality is unavailable.
    """
    lang_lower = language_code.lower().split("-")[0]  # 'de_DE' → 'de'

    candidates: Dict[str, Dict] = {
        k: v for k, v in index.items()
        if v.get("language", {}).get("family", "").lower() == lang_lower
    }
    if not candidates:
        raise ValueError(
            f"No Piper voices found for language '{language_code}'. "
            "Check https://huggingface.co/rhasspy/piper-voices for available voices."
        )

    # Build quality preference order starting from the requested quality.
    prefs = [quality] + [q for q in _QUALITY_PREFERENCE if q != quality]
    for q in prefs:
        for key, meta in candidates.items():
            if meta.get("quality") == q:
                file_paths = list(meta.get("files", {}).keys())
                logger.info(
                    "Selected Piper voice: %s (quality=%s, lang=%s)",
                    key, q, language_code,
                )
                return key, file_paths

    # Should not happen if candidates is non-empty
    key = next(iter(candidates))
    return key, list(candidates[key].get("files", {}).keys())


def _download_voice(
    file_paths: List[str],
    cache_dir: Path,
) -> Path:
    """Download voice files to *cache_dir* and return the .onnx path."""
    onnx_path: Optional[Path] = None
    cache_dir.mkdir(parents=True, exist_ok=True)

    for rel_path in file_paths:
        url = _HF_BASE_URL + rel_path
        dest = cache_dir / Path(rel_path).name
        if dest.is_file():
            logger.info("Piper: already cached %s", dest.name)
        else:
            logger.info("Downloading Piper voice file: %s", dest.name)
            try:
                urllib.request.urlretrieve(url, dest)
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to download Piper voice file '{rel_path}': {exc}"
                ) from exc
        if dest.suffix == ".onnx":
            onnx_path = dest

    if onnx_path is None:
        raise RuntimeError("Downloaded Piper files contain no .onnx model.")
    return onnx_path


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class PiperTTSProvider(BaseTTSProvider):
    """Piper TTS — fast, CPU-only, multi-language provider with auto-download."""

    def __init__(
        self,
        model_path: Optional[str],
        language: str = "en",
        quality: str = "medium",
        voices_dir: Optional[str] = None,
        auto_download: bool = True,
    ) -> None:
        self.model_path = model_path or ""
        self.language = language
        self.quality = quality or "medium"
        self.voices_dir = Path(voices_dir) if voices_dir else None
        self.auto_download = auto_download
        self._voice = None

        if self.model_path and not os.path.isfile(self.model_path):
            logger.warning(
                'Piper model file not found: "%s".',
                self.model_path,
            )

    # ------------------------------------------------------------------
    # BaseTTSProvider interface
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        try:
            import importlib.util
            if importlib.util.find_spec("piper") is None:
                return False
            # Available if a model is already on disk OR auto-download is enabled.
            return bool(self.model_path and os.path.isfile(self.model_path)) or self.auto_download
        except Exception:
            return False

    def load(self) -> None:
        resolved = self._resolve_model_path()
        try:
            from piper.voice import PiperVoice
            self._voice = PiperVoice.load(str(resolved))
            logger.info("Piper TTS loaded: %s", resolved.name)
        except Exception as exc:
            raise ImportError(
                f"Failed to load Piper TTS from '{resolved}'. "
                "Install with: pip install piper-tts"
            ) from exc

    def generate_speech_file(self, text: str, output_path: str, **kwargs) -> None:
        if self._voice is None:
            self.load()
        with wave.open(output_path, "w") as wav_file:
            self._voice.synthesize(text, wav_file)

    @property
    def supports_voice_cloning(self) -> bool:
        return False

    @property
    def supported_languages(self) -> List[str]:
        return [
            "en", "de", "fr", "es", "it", "pt", "nl", "pl", "ru", "cs",
            "sk", "hu", "ro", "fi", "sv", "nb", "da", "uk", "zh", "ko",
            "ja", "ar", "fa", "tr", "vi", "ca", "sr", "hr", "sl", "bg",
        ]

    def voices(self) -> List[str]:
        return []

    def metadata_info(self) -> Dict[str, Any]:
        name = self.model_path or self.language
        model_name = os.path.splitext(os.path.basename(name))[0] if name else "unknown"
        return {
            "artist":      f"{model_name} (Piper)",
            "albumartist": "Piper TTS",
            "comment":     f"Generated using Piper TTS model: {name}",
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_model_path(self) -> Path:
        """Return the .onnx path to use, downloading if necessary."""
        # 1. Explicit path that exists — use as-is.
        if self.model_path and os.path.isfile(self.model_path):
            return Path(self.model_path)

        # 2. Auto-download disabled and no valid path — fail clearly.
        if not self.auto_download:
            raise ValueError(
                f"Piper model not found at '{self.model_path}' and "
                "piper_auto_download is disabled. Set piper_model_path in config "
                "or enable piper_auto_download."
            )

        # 3. Auto-download: select a voice from the index and download it.
        cache_dir = self._cache_dir()
        index = _fetch_voices_index(cache_dir)
        _, file_paths = _pick_voice(index, self.language, self.quality)
        onnx_path = _download_voice(file_paths, cache_dir)

        # Cache the resolved path so the next load() call skips re-downloading.
        self.model_path = str(onnx_path)
        return onnx_path

    def _cache_dir(self) -> Path:
        if self.voices_dir:
            return self.voices_dir
        # Default: configs/piper_voices/ relative to the project root.
        from utils.config import config as app_config
        configs_dir = Path(getattr(app_config, "CONFIGS_DIR_LOC",
                                   Path(__file__).resolve().parents[2] / "configs"))
        return configs_dir / "piper_voices"

    @staticmethod
    def list_available_voices(
        language_code: Optional[str] = None,
        voices_dir: Optional[Path] = None,
    ) -> List[Dict[str, Any]]:
        """Return voice metadata from the index, optionally filtered by language.

        Useful for building UI pickers.  Fetches/caches the index the first time.
        """
        cache_dir = voices_dir or (
            Path(__file__).resolve().parents[2] / "configs" / "piper_voices"
        )
        index = _fetch_voices_index(cache_dir)
        results = []
        for key, meta in index.items():
            lang_family = meta.get("language", {}).get("family", "")
            if language_code and lang_family.lower() != language_code.lower().split("-")[0]:
                continue
            results.append({
                "key":      key,
                "language": lang_family,
                "region":   meta.get("language", {}).get("code", ""),
                "name":     meta.get("name", ""),
                "quality":  meta.get("quality", ""),
                "speakers": meta.get("num_speakers", 1),
            })
        return sorted(results, key=lambda v: (v["language"], v["quality"], v["name"]))
