"""Spinning-record clips shown in place of a still image when a track has no album art.

A record image turned through a full circle over the length of the clip ends where
it started, so one short clip per record asset can simply be repeated by VLC for as
long as the track plays.  Clips are therefore encoded once per asset, cached on
disk between runs, and never re-encoded per track -- encoding a clip as long as the
track itself would cost minutes of CPU for every song.

The whole set is encoded in one pass the first time a track needs it, holding up
that one track. Encoding a clip per track instead would spread the same one-time
cost over as many songs as there are record assets, leaving the first couple of
dozen tracks cycling the one or two clips that happened to be ready.
"""

import os
import subprocess
from random import choice
from typing import Callable, List, Optional

from utils.config import config
from utils.ffmpeg_handler import FFmpegHandler
from utils.logging_setup import get_logger
from utils.utils import Utils

logger = get_logger(__name__)


class SpinningRecordVideos:
    """Cache of looping record-rotation clips built from the ``record*`` assets."""

    RECORD_ASSET_PATTERN = "record"
    # Clips live beside the record images they are made from, under assets/.
    CACHE_DIRNAME = "spinning_record_videos"
    SIGNATURE_FILENAME = "signature.txt"
    PARTIAL_MARKER = ".part"

    # One full turn spread across the clip: the last frame stops just short of the
    # first, so repeated playback has no visible seam.
    CLIP_SECONDS = 10
    FPS = 30
    # The frame renders far smaller than the 1024px source art, so encoding at full
    # size only costs time. Never upscales -- smaller assets are left alone.
    MAX_SIDE = 720
    # Encoders tried in order; the first that works is reused for the rest of the
    # session. ffmpeg builds vary in which encoders they ship.
    ENCODERS = (
        ("libx264", ".mp4", ("-crf", "23", "-preset", "veryfast")),
        ("libxvid", ".avi", ("-qscale:v", "3")),
    )
    # Used when the asset's own background colour cannot be sampled.
    DEFAULT_FILL_COLOR = "0x000000"
    # Bump when the encode parameters change so clips from an older version are discarded.
    CACHE_SIGNATURE = "2|720px|10s|30fps|asset-background-fill"

    _encoder_index = 0
    _cache_dir: Optional[str] = None
    _warned_no_ffmpeg = False
    _last_video: Optional[str] = None
    _clips_ensured = False

    # ── Selection ────────────────────────────────────────────────────────────

    @classmethod
    def get_random_record_video(cls, notify: Optional[Callable[[int], None]] = None) -> Optional[str]:
        """Return a cached clip to show for a track with no album art, or None.

        Encodes any clips still missing first, which blocks. None means the caller
        should use a still record image instead: either the feature is off, or
        nothing could be encoded.
        """
        if not cls.enabled():
            return None
        cls.ensure_clips(notify=notify)
        videos = [video for video in (cls.cached_video(asset) for asset in cls.record_assets())
                  if video is not None]
        if len(videos) == 0:
            return None
        # Avoid handing back the clip that just played.
        unplayed = [video for video in videos if video != cls._last_video]
        cls._last_video = choice(unplayed or videos)
        return cls._last_video

    @classmethod
    def ensure_clips(cls, notify: Optional[Callable[[int], None]] = None) -> None:
        """Encode every asset that has no clip yet, blocking until they are done.

        Runs at most once per session: an asset no encoder can handle would otherwise
        be retried, and block again, on every later track that finds no album art.

        notify, when given, is called with the number of clips about to be encoded,
        so the caller can tell the user why playback is waiting.
        """
        if cls._clips_ensured:
            return
        missing = [asset for asset in cls.record_assets() if cls.cached_video(asset) is None]
        if len(missing) == 0:
            cls._clips_ensured = True
            return
        if notify is not None:
            try:
                notify(len(missing))
            except Exception as e:
                logger.warning(f"Could not announce spinning record encoding: {e}")
        logger.info(f"Encoding {len(missing)} spinning record clip(s); playback waits for this once.")
        encoded = 0
        for asset_path in missing:
            try:
                if cls.generate(asset_path) is not None:
                    encoded += 1
            except Exception as e:
                logger.warning(f"Failed to generate spinning record video for {asset_path}: {e}")
        cls._clips_ensured = True
        logger.info(f"Encoded {encoded} of {len(missing)} spinning record clip(s).")

    @classmethod
    def enabled(cls) -> bool:
        if not bool(getattr(config, "spinning_record_videos", False)):
            return False
        if not FFmpegHandler.ffmpeg_available:
            if not cls._warned_no_ffmpeg:
                cls._warned_no_ffmpeg = True
                logger.warning("Spinning record videos are enabled but ffmpeg was not found on PATH.")
            return False
        return True

    # ── Cache layout ─────────────────────────────────────────────────────────

    @staticmethod
    def record_assets() -> List[str]:
        filenames = Utils.get_assets_filenames(filename_filter=[SpinningRecordVideos.RECORD_ASSET_PATTERN])
        return [Utils.get_asset(filename) for filename in filenames]

    @classmethod
    def cache_dir(cls) -> str:
        if cls._cache_dir is not None:
            return cls._cache_dir
        path = os.path.join(Utils.get_assets_dir(), cls.CACHE_DIRNAME)
        try:
            os.makedirs(path, exist_ok=True)
            cls._discard_stale_clips(path)
        except Exception as e:
            # A read-only install can't hold clips. Keep the path so lookups simply
            # find nothing and callers fall back to the still images.
            logger.warning(f"Could not prepare the spinning record clip directory {path}: {e}")
        cls._cache_dir = path
        return path

    @classmethod
    def _discard_stale_clips(cls, path: str) -> None:
        """Empty the cache when it was built with different encode parameters."""
        signature_path = os.path.join(path, cls.SIGNATURE_FILENAME)
        try:
            with open(signature_path, "r", encoding="utf-8") as f:
                if f.read().strip() == cls.CACHE_SIGNATURE:
                    return
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning(f"Could not read spinning record cache signature: {e}")
        for filename in os.listdir(path):
            if filename != cls.SIGNATURE_FILENAME:
                cls._remove_quietly(os.path.join(path, filename))
        try:
            with open(signature_path, "w", encoding="utf-8") as f:
                f.write(cls.CACHE_SIGNATURE)
        except Exception as e:
            logger.warning(f"Could not write spinning record cache signature: {e}")

    @classmethod
    def cached_video(cls, asset_path: str) -> Optional[str]:
        """Path of the clip encoded from *asset_path*, or None if not encoded yet."""
        basename = os.path.basename(asset_path)
        for _encoder, extension, _quality_args in cls.ENCODERS:
            candidate = os.path.join(cls.cache_dir(), basename + extension)
            if os.path.exists(candidate):
                return candidate
        return None

    @classmethod
    def is_spinning_record_video(cls, path: Optional[str]) -> bool:
        """Whether *path* is one of these clips rather than an image to display."""
        if not path:
            return False
        return os.path.dirname(os.path.abspath(path)) == os.path.abspath(cls.cache_dir())

    @classmethod
    def source_image_for(cls, video_path: Optional[str]) -> Optional[str]:
        """The record asset a clip was encoded from, for falling back to the still image."""
        if not cls.is_spinning_record_video(video_path):
            return None
        # Clips are named "<asset filename><video extension>", e.g. "record10_.png.mp4".
        asset_path = Utils.get_asset(os.path.splitext(os.path.basename(video_path))[0])
        return asset_path if os.path.exists(asset_path) else None

    # ── Encoding ─────────────────────────────────────────────────────────────

    @classmethod
    def generate(cls, asset_path: str) -> Optional[str]:
        """Encode the looping clip for one record asset. Returns its cached path."""
        existing = cls.cached_video(asset_path)
        if existing is not None:
            return existing
        basename = os.path.basename(asset_path)
        fill_color = cls.background_color(asset_path)
        for index in range(cls._encoder_index, len(cls.ENCODERS)):
            encoder, extension, quality_args = cls.ENCODERS[index]
            output_path = os.path.join(cls.cache_dir(), basename + extension)
            # Encode aside and rename, so an interrupted run leaves no half-written
            # clip that later runs would treat as cached.
            partial_path = os.path.join(cls.cache_dir(), basename + cls.PARTIAL_MARKER + extension)
            logger.info(f"Generating spinning record video with {encoder}: {basename}")
            if cls._run_ffmpeg(cls.ffmpeg_args(asset_path, partial_path, encoder, quality_args, fill_color)):
                os.replace(partial_path, output_path)
                cls._encoder_index = index
                return output_path
            cls._remove_quietly(partial_path)
            logger.warning(f"Encoder {encoder} could not produce a spinning record video for {basename}.")
        return None

    @classmethod
    def background_color(cls, image_path: str) -> str:
        """The asset's own corner colour, as an ffmpeg hex literal.

        Rotation empties the frame's corners, and filling them with anything but the
        asset's own background makes the whole square read as turning instead of just
        the record. The record assets are opaque and each carries its own backdrop,
        from near-white to near-black, so one fixed colour cannot suit them.

        Sampled through ffmpeg rather than an image library: this feature already
        requires ffmpeg, and it reads every asset format without a further dependency.
        """
        args = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", image_path,
            # Same centred square the clip is built from, then average its top-left
            # corner patch down to the single pixel whose colour is wanted.
            "-vf", "crop='min(iw,ih)':'min(iw,ih)',crop=iw/16:ih/16:0:0,scale=1:1:flags=area",
            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
        ]
        try:
            finished = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            if finished.returncode == 0 and len(finished.stdout) >= 3:
                red, green, blue = finished.stdout[0], finished.stdout[1], finished.stdout[2]
                return f"0x{red:02x}{green:02x}{blue:02x}"
            logger.warning(f"Could not sample the background colour of {os.path.basename(image_path)}: "
                           f"{(finished.stderr or b'').decode(errors='replace').strip()[-200:]}")
        except Exception as e:
            logger.warning(f"Could not sample the background colour of {image_path}: {e}")
        return cls.DEFAULT_FILL_COLOR

    @classmethod
    def ffmpeg_args(cls, image_path: str, output_path: str, encoder: str, quality_args,
                    fill_color: Optional[str] = None) -> List[str]:
        # crop defaults to centred, and rotate's output defaults to its input size,
        # so cropping square up front keeps the turning record framed and leaves only
        # the corners for fillcolor. Sides are rounded down to an even number because
        # yuv420p encoders reject odd dimensions.
        even_side = f"2*trunc(min({cls.MAX_SIDE},{{0}})/2)"
        video_filter = ",".join([
            "crop='min(iw,ih)':'min(iw,ih)'",
            f"scale=w='{even_side.format('iw')}':h='{even_side.format('ih')}'",
            f"rotate=angle='2*PI*t/{cls.CLIP_SECONDS}':fillcolor={fill_color or cls.DEFAULT_FILL_COLOR}",
        ])
        return [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            # -framerate applies to the still input, so every frame gets its own
            # angle; setting only the output rate would duplicate frames instead.
            "-framerate", str(cls.FPS),
            "-loop", "1",
            "-i", image_path,
            "-t", str(cls.CLIP_SECONDS),
            "-vf", video_filter,
            "-c:v", encoder,
            *quality_args,
            "-pix_fmt", "yuv420p",
            "-an",
            output_path,
        ]

    @staticmethod
    def _run_ffmpeg(args: List[str]) -> bool:
        try:
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            output, _unused = process.communicate()
            if process.returncode != 0:
                logger.warning(f"ffmpeg exited with {process.returncode}: {(output or '').strip()[-500:]}")
                return False
            return True
        except Exception as e:
            logger.warning(f"Error running ffmpeg: {e}")
            return False

    @staticmethod
    def _remove_quietly(path: str) -> None:
        try:
            if os.path.isfile(path):
                os.remove(path)
        except Exception as e:
            logger.warning(f"Could not remove {path}: {e}")
