"""Tests for the spinning-record stand-in artwork clips."""

import os

import pytest

from utils.spinning_record import SpinningRecordVideos


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    """Point the clip cache at a temp dir and reset the class-level state it keeps."""
    monkeypatch.setattr(SpinningRecordVideos, "_cache_dir", str(tmp_path))
    monkeypatch.setattr(SpinningRecordVideos, "_generating", None)
    monkeypatch.setattr(SpinningRecordVideos, "_encoder_index", 0)
    return str(tmp_path)


def _args_for(image_path="/assets/record1_.png", output_path="/cache/record1_.png.mp4"):
    encoder, _extension, quality_args = SpinningRecordVideos.ENCODERS[0]
    return SpinningRecordVideos.ffmpeg_args(image_path, output_path, encoder, quality_args)


def test_clip_turns_exactly_once_so_repeats_are_seamless():
    """The rotation must complete 2*PI over the clip, or looping shows a jump."""
    args = _args_for()
    video_filter = args[args.index("-vf") + 1]
    assert f"rotate=angle='2*PI*t/{SpinningRecordVideos.CLIP_SECONDS}'" in video_filter
    assert args[args.index("-t") + 1] == str(SpinningRecordVideos.CLIP_SECONDS)


def test_input_framerate_precedes_input():
    """-framerate is an input option; after -i it would duplicate frames instead of
    giving each frame its own rotation angle."""
    args = _args_for()
    assert args.index("-framerate") < args.index("-i")
    assert args[args.index("-framerate") + 1] == str(SpinningRecordVideos.FPS)


def test_filter_crops_square_and_never_upscales():
    args = _args_for()
    video_filter = args[args.index("-vf") + 1]
    assert video_filter.startswith("crop='min(iw,ih)':'min(iw,ih)'")
    assert f"min({SpinningRecordVideos.MAX_SIDE},iw)" in video_filter
    assert f"min({SpinningRecordVideos.MAX_SIDE},ih)" in video_filter


def test_scaled_dimensions_are_even():
    """yuv420p encoders reject odd dimensions, which a record asset with an odd
    short side would otherwise produce."""
    args = _args_for()
    video_filter = args[args.index("-vf") + 1]
    assert f"scale=w='2*trunc(min({SpinningRecordVideos.MAX_SIDE},iw)/2)'" in video_filter
    assert f"h='2*trunc(min({SpinningRecordVideos.MAX_SIDE},ih)/2)'" in video_filter


def test_clip_carries_no_audio_stream():
    """The clip plays alongside the track's own audio, so it must be silent."""
    assert "-an" in _args_for()


def test_cached_clip_maps_back_to_its_source_image(cache_dir):
    asset_path = SpinningRecordVideos.record_assets()[0]
    _encoder, extension, _quality_args = SpinningRecordVideos.ENCODERS[0]
    clip_path = os.path.join(cache_dir, os.path.basename(asset_path) + extension)

    assert SpinningRecordVideos.cached_video(asset_path) is None
    open(clip_path, "wb").close()

    assert SpinningRecordVideos.cached_video(asset_path) == clip_path
    assert SpinningRecordVideos.is_spinning_record_video(clip_path)
    assert not SpinningRecordVideos.is_spinning_record_video(asset_path)
    assert SpinningRecordVideos.source_image_for(clip_path) == asset_path


def test_no_cached_clip_yields_still_image_and_starts_one_encode(cache_dir, monkeypatch):
    """Playback must never wait on ffmpeg: the first track falls back to the image."""
    started = []
    monkeypatch.setattr(SpinningRecordVideos, "enabled", classmethod(lambda cls: True))
    monkeypatch.setattr(
        SpinningRecordVideos, "_start_background_generation",
        classmethod(lambda cls, asset_path: started.append(asset_path)),
    )

    assert SpinningRecordVideos.get_random_record_video() is None
    assert len(started) == 1
    assert os.path.basename(started[0]).startswith(SpinningRecordVideos.RECORD_ASSET_PATTERN)


def test_cached_clip_is_used(cache_dir, monkeypatch):
    monkeypatch.setattr(SpinningRecordVideos, "enabled", classmethod(lambda cls: True))
    monkeypatch.setattr(SpinningRecordVideos, "_start_background_generation", classmethod(lambda cls, p: None))
    asset_path = SpinningRecordVideos.record_assets()[0]
    _encoder, extension, _quality_args = SpinningRecordVideos.ENCODERS[0]
    clip_path = os.path.join(cache_dir, os.path.basename(asset_path) + extension)
    open(clip_path, "wb").close()

    assert SpinningRecordVideos.get_random_record_video() == clip_path


def test_disabled_config_never_encodes(cache_dir, monkeypatch):
    """The opt-out must stop generation, not just hide the result."""
    from utils.config import config

    started = []
    monkeypatch.setattr(config, "spinning_record_videos", False, raising=False)
    monkeypatch.setattr(
        SpinningRecordVideos, "_start_background_generation",
        classmethod(lambda cls, asset_path: started.append(asset_path)),
    )

    assert SpinningRecordVideos.get_random_record_video() is None
    assert started == []


def test_generate_falls_back_to_the_next_encoder(cache_dir, monkeypatch):
    """ffmpeg builds differ in which encoders they ship."""
    attempted = []

    def fake_run(args):
        encoder = args[args.index("-c:v") + 1]
        attempted.append(encoder)
        if encoder == SpinningRecordVideos.ENCODERS[0][0]:
            return False
        open(args[-1], "wb").close()
        return True

    monkeypatch.setattr(SpinningRecordVideos, "_run_ffmpeg", staticmethod(fake_run))
    asset_path = SpinningRecordVideos.record_assets()[0]

    result = SpinningRecordVideos.generate(asset_path)

    assert attempted == [encoder for encoder, _ext, _q in SpinningRecordVideos.ENCODERS]
    assert result == os.path.join(cache_dir, os.path.basename(asset_path) + SpinningRecordVideos.ENCODERS[1][1])
    assert os.path.exists(result)
    # The partial file must not survive as a seemingly-cached clip.
    assert [f for f in os.listdir(cache_dir) if SpinningRecordVideos.PARTIAL_MARKER in f] == []
