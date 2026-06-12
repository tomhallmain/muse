import os
import re
from typing import Optional

from utils.logging_setup import get_logger

logger = get_logger(__name__)

# Unnamed interim WAV files from Voice.set_output_path("_{timestamp}_") and chunk counters.
_ORPHANED_OUTPUT_WAV_RE = re.compile(
    r"^_\d+_(?:\d+)?\.wav$"  # e.g. _1734567890_.wav or _1734567890_1.wav
    r"|"
    r"^_\d+\.wav$"  # e.g. _0.wav
)

# Interim outputs from integration tests using filepath="tts_test" in TextToSpeechRunner.
_TEST_OUTPUT_FILE_RE = re.compile(r"^tts_test\d+\.(?:wav|mp3)$")


def is_orphaned_output_wav(filename: str) -> bool:
    """Return True if *filename* looks like an unnamed interim TTS WAV."""
    return bool(_ORPHANED_OUTPUT_WAV_RE.match(filename))


def is_removable_output_file(filename: str) -> bool:
    """Return True if *filename* is a disposable TTS output artifact."""
    return is_orphaned_output_wav(filename) or bool(_TEST_OUTPUT_FILE_RE.match(filename))


def cleanup_orphaned_output_files(directory: str) -> int:
    """Remove disposable interim TTS output files from *directory*."""
    if not os.path.isdir(directory):
        return 0

    removed = 0
    for name in os.listdir(directory):
        if not is_removable_output_file(name):
            continue
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        try:
            os.remove(path)
            removed += 1
            logger.info("Removed disposable TTS output file: %s", name)
        except OSError as e:
            logger.warning("Failed to remove disposable TTS output file %s: %s", name, e)

    if removed:
        logger.info(
            "Cleaned up %d disposable TTS output file(s) from %s",
            removed,
            directory,
        )
    return removed


def default_output_directory() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "tts_output")


def cleanup_default_output_directory(directory: Optional[str] = None) -> int:
    """Remove orphaned interim WAV files from the default tts_output directory."""
    return cleanup_orphaned_output_files(directory or default_output_directory())
