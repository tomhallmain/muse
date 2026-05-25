#!/usr/bin/env python3
"""Generate tagged MP3 fixtures for the Muse test suite.

Requires ``ffmpeg`` on PATH and project deps (``mutagen``).

Usage::

    python tests/fixtures/generate_audio_library.py
    python tests/fixtures/generate_audio_library.py --force
"""

import sys
from pathlib import Path

_fixtures_dir = Path(__file__).resolve().parent
if str(_fixtures_dir) not in sys.path:
    sys.path.insert(0, str(_fixtures_dir))

from audio_fixtures import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
