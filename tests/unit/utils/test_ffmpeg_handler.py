"""Tests for the long-track loudness short-circuit in FFmpegHandler.get_volume."""

from unittest.mock import MagicMock, patch

from utils.ffmpeg_handler import FFmpegHandler


def test_long_track_loudness_capped_at_20_minutes():
    """A track longer than LOUDNESS_ANALYZE_MAX_SECONDS must pass -t before -i to ffmpeg.

    Regression guard: without the cap, a 4-hour opera causes ffmpeg to decode
    the entire file before returning volume data.
    """
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = (
        b"[Parsed_volumedetect_0 @ 0xabc] mean_volume: -20.5 dB\n"
        b"[Parsed_volumedetect_0 @ 0xabc] max_volume: -10.3 dB\n",
        None,
    )

    from library_data.media_track import MediaTrack

    track = MediaTrack.__new__(MediaTrack)
    track.filepath = "/fake/opera.mp3"
    track.mean_volume = -9999.0
    track.max_volume = -9999.0
    track.length = 4 * 3600.0  # 4-hour opera

    with patch("utils.ffmpeg_handler.subprocess.Popen", return_value=mock_proc) as mock_popen, \
         patch.object(FFmpegHandler, "sanitize_filename", side_effect=lambda p: p):
        track.get_volume()

    args = mock_popen.call_args[0][0]
    assert "-t" in args, "ffmpeg must receive -t to limit decoding of long tracks"
    t_idx = args.index("-t")
    i_idx = args.index("-i")
    assert t_idx < i_idx, "-t must precede -i (input option, not output option)"
    assert args[t_idx + 1] == str(int(FFmpegHandler.LOUDNESS_ANALYZE_MAX_SECONDS))
