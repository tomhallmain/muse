"""Tests for the spinning-record stand-in artwork clips."""

import os

import pytest

from utils.spinning_record import SpinningRecordVideos


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    """Point the clip cache at a temp dir and reset the class-level state it keeps."""
    monkeypatch.setattr(SpinningRecordVideos, "_cache_dir", str(tmp_path))
    monkeypatch.setattr(SpinningRecordVideos, "_encoder_index", 0)
    monkeypatch.setattr(SpinningRecordVideos, "_last_video", None)
    monkeypatch.setattr(SpinningRecordVideos, "_clips_ensured", False)
    return str(tmp_path)


@pytest.fixture
def no_encoding(monkeypatch):
    """Stand in for a session whose encode pass has already run.

    Selection tests must not shell out to ffmpeg for the assets they leave
    uncached, which get_random_record_video would otherwise block on.
    """
    monkeypatch.setattr(SpinningRecordVideos, "enabled", classmethod(lambda cls: True))
    monkeypatch.setattr(SpinningRecordVideos, "_clips_ensured", True)


def _args_for(image_path="/assets/record1_.png", output_path="/cache/record1_.png.mp4",
              fill_color=None):
    encoder, _extension, quality_args = SpinningRecordVideos.ENCODERS[0]
    return SpinningRecordVideos.ffmpeg_args(image_path, output_path, encoder, quality_args, fill_color)


def _cache_clips(cache_dir, count):
    """Pretend the first *count* record assets already have encoded clips."""
    _encoder, extension, _quality_args = SpinningRecordVideos.ENCODERS[0]
    paths = []
    for asset_path in SpinningRecordVideos.record_assets()[:count]:
        clip_path = os.path.join(cache_dir, os.path.basename(asset_path) + extension)
        open(clip_path, "wb").close()
        paths.append(clip_path)
    return paths


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


def test_every_missing_clip_is_encoded_in_one_pass(cache_dir, monkeypatch):
    """One clip per art-less track would need as many tracks as there are assets
    before the cache is full, cycling the same record until then."""
    encoded = []
    monkeypatch.setattr(SpinningRecordVideos, "enabled", classmethod(lambda cls: True))
    monkeypatch.setattr(
        SpinningRecordVideos, "generate",
        classmethod(lambda cls, asset_path: encoded.append(asset_path) or asset_path),
    )

    SpinningRecordVideos.ensure_clips()

    assert encoded == SpinningRecordVideos.record_assets()
    assert len(encoded) > 1


def test_the_encode_pass_announces_how_much_work_it_will_do(cache_dir, monkeypatch):
    announced = []
    monkeypatch.setattr(SpinningRecordVideos, "generate", classmethod(lambda cls, p: p))

    SpinningRecordVideos.ensure_clips(notify=announced.append)

    assert announced == [len(SpinningRecordVideos.record_assets())]


def test_nothing_is_announced_when_every_clip_is_already_cached(cache_dir, monkeypatch):
    announced = []
    monkeypatch.setattr(SpinningRecordVideos, "generate", classmethod(lambda cls, p: p))
    _cache_clips(cache_dir, len(SpinningRecordVideos.record_assets()))

    SpinningRecordVideos.ensure_clips(notify=announced.append)

    assert announced == []


def test_an_asset_no_encoder_can_handle_is_not_retried(cache_dir, monkeypatch):
    """Retrying would block playback again on every later art-less track."""
    attempts = []
    monkeypatch.setattr(SpinningRecordVideos, "enabled", classmethod(lambda cls: True))
    monkeypatch.setattr(
        SpinningRecordVideos, "generate",
        classmethod(lambda cls, asset_path: attempts.append(asset_path) and None),
    )

    SpinningRecordVideos.ensure_clips()
    first_pass = len(attempts)
    SpinningRecordVideos.ensure_clips()

    assert first_pass == len(SpinningRecordVideos.record_assets())
    assert len(attempts) == first_pass
    assert SpinningRecordVideos.get_random_record_video() is None


def test_cached_clip_is_used(cache_dir, no_encoding):
    asset_path = SpinningRecordVideos.record_assets()[0]
    _encoder, extension, _quality_args = SpinningRecordVideos.ENCODERS[0]
    clip_path = os.path.join(cache_dir, os.path.basename(asset_path) + extension)
    open(clip_path, "wb").close()

    assert SpinningRecordVideos.get_random_record_video() == clip_path


def test_disabled_config_never_encodes(cache_dir, monkeypatch):
    """The opt-out must stop generation, not just hide the result."""
    from utils.config import config

    encoded = []
    monkeypatch.setattr(config, "spinning_record_videos", False, raising=False)
    monkeypatch.setattr(
        SpinningRecordVideos, "generate",
        classmethod(lambda cls, asset_path: encoded.append(asset_path)),
    )

    assert SpinningRecordVideos.get_random_record_video() is None
    assert encoded == []


def test_rotation_fills_the_corners_with_the_assets_own_background():
    """A fixed fill makes the whole square read as turning. The record assets are
    opaque and carry backdrops from near-white to near-black, so the corners the
    rotation empties have to take the colour of the asset being turned."""
    args = _args_for(fill_color="0xf5f0e5")
    video_filter = args[args.index("-vf") + 1]

    assert "fillcolor=0xf5f0e5" in video_filter


def test_fill_defaults_to_black_when_no_colour_was_sampled():
    args = _args_for()
    video_filter = args[args.index("-vf") + 1]

    assert f"fillcolor={SpinningRecordVideos.DEFAULT_FILL_COLOR}" in video_filter


def test_background_colour_comes_from_the_sampled_pixel(monkeypatch):
    import utils.spinning_record as spinning_record_mod

    class _Finished:
        returncode = 0
        stdout = bytes([245, 240, 229])   # record10_'s near-white backdrop
        stderr = b""

    monkeypatch.setattr(spinning_record_mod.subprocess, "run", lambda *a, **k: _Finished())
    assert SpinningRecordVideos.background_color("/assets/record10_.png") == "0xf5f0e5"


def test_background_colour_falls_back_when_sampling_fails(monkeypatch):
    import utils.spinning_record as spinning_record_mod

    class _Finished:
        returncode = 1
        stdout = b""
        stderr = b"no such file"

    monkeypatch.setattr(spinning_record_mod.subprocess, "run", lambda *a, **k: _Finished())
    assert SpinningRecordVideos.background_color("/nope.png") == SpinningRecordVideos.DEFAULT_FILL_COLOR


def test_generate_encodes_with_the_sampled_background(cache_dir, monkeypatch):
    filters = []

    def fake_run(args):
        filters.append(args[args.index("-vf") + 1])
        open(args[-1], "wb").close()
        return True

    monkeypatch.setattr(SpinningRecordVideos, "background_color", classmethod(lambda cls, path: "0x123456"))
    monkeypatch.setattr(SpinningRecordVideos, "_run_ffmpeg", staticmethod(fake_run))

    SpinningRecordVideos.generate(SpinningRecordVideos.record_assets()[0])

    assert "fillcolor=0x123456" in filters[0]


def test_the_same_clip_is_not_shown_twice_running(cache_dir, no_encoding):
    """An unconstrained random choice keeps landing on the same record."""
    _cache_clips(cache_dir, 2)

    shown = [SpinningRecordVideos.get_random_record_video() for _ in range(6)]

    assert all(shown)
    assert all(earlier != later for earlier, later in zip(shown, shown[1:]))


def test_a_lone_cached_clip_is_still_shown(cache_dir, no_encoding):
    """Where only one asset could be encoded, repeating it beats showing none."""
    only_clip = _cache_clips(cache_dir, 1)[0]

    assert SpinningRecordVideos.get_random_record_video() == only_clip
    assert SpinningRecordVideos.get_random_record_video() == only_clip


def test_generate_falls_back_to_the_next_encoder(cache_dir, monkeypatch):
    """ffmpeg builds differ in which encoders they ship."""
    monkeypatch.setattr(SpinningRecordVideos, "background_color", classmethod(lambda cls, path: "0x000000"))
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
