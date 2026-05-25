"""Generate and load the pytest audio fixture library (100+ tagged MP3 files)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

MANIFEST_VERSION = 1
MIN_TRACK_COUNT = 100
FIXTURES_ROOT = Path(__file__).resolve().parent
AUDIO_LIBRARY_DIR = FIXTURES_ROOT / "audio_library"
MANIFEST_PATH = FIXTURES_ROOT / "manifest.json"

# Seconds — mostly short clips; occasional long track for splitting tests.
DURATION_POOL = [
    6, 8, 10, 12, 15, 18, 22, 28, 35, 42, 55, 70, 95, 130, 180, 240, 300, 360, 420,
]
LONG_TRACK_DURATION = 1260  # 21 minutes — above default 20 min splitting cutoff
LONG_TRACK_EVERY_N = 40

FORM_WORDS = [
    "Symphony",
    "Concerto",
    "Sonata",
    "Prelude",
    "Suite",
    "Fugue",
    "Cantata",
    "Quartet",
]

COMPOSER_PROFILES = [
    ("Beethoven", "Classical", "Berlin Philharmonic", "Orchestra"),
    ("Bach", "Classical", "Glenn Gould", "Piano"),
    ("Mozart", "Classical", "Vienna Philharmonic", "Orchestra"),
    ("Vivaldi", "Classical", "Academy of St Martin", "Violin"),
    ("Haydn", "Classical", "Franz Joseph Haydn Orchestra", "Orchestra"),
    ("Schubert", "Classical", "Wiener Symphoniker", "Orchestra"),
    ("Brahms", "Classical", "Leipzig Gewandhaus", "Orchestra"),
    ("Debussy", "Classical", "Orchestre de Paris", "Orchestra"),
    ("Dave Brubeck", "Jazz", "Dave Brubeck Quartet", "Piano"),
    ("Miles Davis", "Jazz", "Miles Davis", "Trumpet"),
    ("John Coltrane", "Jazz", "John Coltrane Quartet", "Saxophone"),
    ("Led Zeppelin", "Rock", "Led Zeppelin", "Guitar"),
]

KEYS = ["C major", "D minor", "E flat major", "F major", "G minor", "A major", "B minor"]
MOVEMENTS = ["Allegro", "Andante", "Scherzo", "Finale", "Adagio", "Vivace"]

LEGACY_SAMPLES = [
    ("sample_100KB.mp3", 32, 22050, 12),
    ("sample_500KB.mp3", 64, 44100, 45),
    ("sample_1MB.mp3", 96, 44100, 75),
]


@dataclass(frozen=True)
class TrackSpec:
    relative_path: str
    title: str
    album: str
    artist: str
    composer: str
    genre: str
    form_hint: str
    instrument_hint: str
    duration_seconds: float
    tracknumber: int
    discnumber: int = 1


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _run_ffmpeg(args: List[str]) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", *args]
    subprocess.run(cmd, check=True)


def _write_mp3(
    dest: Path,
    duration_seconds: float,
    frequency: int = 440,
    bitrate_k: int = 32,
    sample_rate: int = 22050,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(
        [
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:duration={duration_seconds}",
            "-c:a",
            "libmp3lame",
            "-b:a",
            f"{bitrate_k}k",
            "-ar",
            str(sample_rate),
            "-ac",
            "1",
            str(dest),
        ]
    )


def _tag_mp3(path: Path, spec: TrackSpec) -> None:
    from mutagen.easyid3 import EasyID3
    from mutagen.id3 import ID3NoHeaderError
    from mutagen.mp3 import MP3

    try:
        audio = MP3(path, ID3=EasyID3)
    except ID3NoHeaderError:
        audio = MP3(path)
        audio.add_tags()
        audio = MP3(path, ID3=EasyID3)

    audio["title"] = spec.title
    audio["artist"] = spec.artist
    audio["album"] = spec.album
    audio["composer"] = spec.composer
    audio["genre"] = spec.genre
    audio["tracknumber"] = str(spec.tracknumber)
    audio["discnumber"] = str(spec.discnumber)
    audio.save()


def build_track_catalog(count: int = 120) -> List[TrackSpec]:
    """Build at least ``MIN_TRACK_COUNT`` tracks with varied metadata and lengths."""
    if count < MIN_TRACK_COUNT:
        count = MIN_TRACK_COUNT

    specs: List[TrackSpec] = []
    idx = 0
    for composer, genre, artist, instrument in COMPOSER_PROFILES:
        for album_idx in range(3):
            form = FORM_WORDS[(idx + album_idx) % len(FORM_WORDS)]
            album = f"{composer}: {form} No. {album_idx + 1}"
            for track_idx in range(1, 4):
                if len(specs) >= count:
                    return specs
                n = len(specs)
                duration = (
                    LONG_TRACK_DURATION
                    if n > 0 and n % LONG_TRACK_EVERY_N == 0
                    else DURATION_POOL[n % len(DURATION_POOL)]
                )
                key = KEYS[len(specs) % len(KEYS)]
                movement = MOVEMENTS[track_idx % len(MOVEMENTS)]
                title = f"{form} in {key} - {movement}"
                genre_folder = genre.replace(" ", "_")
                rel = (
                    f"{genre_folder}/{composer}/{album}/"
                    f"{track_idx:02d} {title}.mp3"
                ).replace(":", " -")
                specs.append(
                    TrackSpec(
                        relative_path=rel,
                        title=title,
                        album=album,
                        artist=artist,
                        composer=composer,
                        genre=genre,
                        form_hint=form,
                        instrument_hint=instrument,
                        duration_seconds=float(duration),
                        tracknumber=track_idx,
                        discnumber=1,
                    )
                )
                idx += 1

    while len(specs) < count:
        n = len(specs)
        composer, genre, artist, instrument = COMPOSER_PROFILES[n % len(COMPOSER_PROFILES)]
        form = FORM_WORDS[n % len(FORM_WORDS)]
        album = f"{composer}: Extra {form}"
        title = f"{form} fragment {n + 1}"
        rel = f"Misc/{composer}/{album}/{n:03d} {title}.mp3".replace(":", " -")
        specs.append(
            TrackSpec(
                relative_path=rel,
                title=title,
                album=album,
                artist=artist,
                composer=composer,
                genre=genre,
                form_hint=form,
                instrument_hint=instrument,
                duration_seconds=float(
                    LONG_TRACK_DURATION
                    if n > 0 and n % LONG_TRACK_EVERY_N == 0
                    else DURATION_POOL[n % len(DURATION_POOL)]
                ),
                tracknumber=1,
            )
        )
    return specs


def write_manifest(specs: List[TrackSpec]) -> None:
    payload = {
        "version": MANIFEST_VERSION,
        "track_count": len(specs),
        "tracks": [asdict(s) for s in specs],
    }
    MANIFEST_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def manifest_track_count() -> int:
    if not MANIFEST_PATH.is_file():
        return 0
    data = read_manifest()
    return int(data.get("track_count", len(data.get("tracks", []))))


def library_is_complete() -> bool:
    if manifest_track_count() < MIN_TRACK_COUNT:
        return False
    data = read_manifest()
    for entry in data.get("tracks", []):
        path = AUDIO_LIBRARY_DIR / entry["relative_path"]
        if not path.is_file():
            return False
    for name, *_ in LEGACY_SAMPLES:
        if not (FIXTURES_ROOT / name).is_file():
            return False
    return True


def generate_audio_library(
    count: int = 120,
    force: bool = False,
) -> Path:
    """Generate MP3 library + manifest under ``tests/fixtures``."""
    if not ffmpeg_available():
        raise RuntimeError("ffmpeg not found on PATH; required to generate audio fixtures")

    specs = build_track_catalog(count)
    if force or not library_is_complete():
        if AUDIO_LIBRARY_DIR.exists() and force:
            shutil.rmtree(AUDIO_LIBRARY_DIR)
        AUDIO_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)

        for i, spec in enumerate(specs):
            dest = AUDIO_LIBRARY_DIR / spec.relative_path
            freq = 220 + (i * 17) % 500
            bitrate = 16 if spec.duration_seconds >= 300 else 32
            _write_mp3(
                dest,
                spec.duration_seconds,
                frequency=freq,
                bitrate_k=bitrate,
            )
            _tag_mp3(dest, spec)

        write_manifest(specs)

        for name, bitrate_k, sample_rate, duration in LEGACY_SAMPLES:
            dest = FIXTURES_ROOT / name
            _write_mp3(
                dest,
                float(duration),
                frequency=330,
                bitrate_k=bitrate_k,
                sample_rate=sample_rate,
            )

    return AUDIO_LIBRARY_DIR


def ensure_legacy_samples() -> None:
    """Create size-named root samples without building the full library."""
    if not ffmpeg_available():
        raise RuntimeError("ffmpeg not found on PATH; required to generate audio fixtures")
    for name, bitrate_k, sample_rate, duration in LEGACY_SAMPLES:
        dest = FIXTURES_ROOT / name
        if dest.is_file():
            continue
        _write_mp3(
            dest,
            float(duration),
            frequency=330,
            bitrate_k=bitrate_k,
            sample_rate=sample_rate,
        )


def ensure_audio_library() -> Path:
    ensure_legacy_samples()
    if library_is_complete():
        return AUDIO_LIBRARY_DIR
    return generate_audio_library()


def load_track_specs() -> List[TrackSpec]:
    ensure_audio_library()
    data = read_manifest()
    return [TrackSpec(**entry) for entry in data["tracks"]]


def load_media_tracks():
    """Return ``MediaTrack`` instances for every manifest entry."""
    from library_data.media_track import MediaTrack

    tracks = []
    for spec in load_track_specs():
        path = AUDIO_LIBRARY_DIR / spec.relative_path
        tracks.append(MediaTrack(str(path)))
    return tracks


def build_fixture_callbacks():
    """``LibraryDataCallbacks``-compatible object backed by the fixture library."""
    from library_data.library_data_callbacks import LibraryDataCallbacks

    tracks = load_media_tracks()
    by_path = {t.filepath: t for t in tracks}
    root = str(AUDIO_LIBRARY_DIR.resolve())

    class _Callbacks:
        def get_track(self, track_id: str):
            return by_path.get(track_id)

        def get_all_tracks(self):
            return tracks

        def get_all_filepaths(self, directories, overwrite=False):
            del directories, overwrite
            return list(by_path.keys())

        def identify_compilation_name(self, track, all_tracks=None):
            return None

        def identify_compilation_tracks(self, tracks):
            return tracks

    inner = _Callbacks()
    return LibraryDataCallbacks(
        get_all_filepaths=inner.get_all_filepaths,
        get_all_tracks=inner.get_all_tracks,
        get_track=inner.get_track,
        instance=inner,
    )


def main(argv: Optional[List[str]] = None) -> int:
    force = "--force" in (argv or sys.argv[1:])
    generate_audio_library(force=force)
    print(f"Generated {manifest_track_count()} tracks under {AUDIO_LIBRARY_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
