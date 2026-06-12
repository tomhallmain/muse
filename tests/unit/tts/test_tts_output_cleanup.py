import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from tts.output_cleanup import (
    cleanup_orphaned_output_files,
    is_orphaned_output_wav,
    is_removable_output_file,
)


class TestOrphanedOutputWavMatching:
    def test_matches_unnamed_interim_chunks(self):
        assert is_orphaned_output_wav("_1734567890_0.wav")
        assert is_orphaned_output_wav("_1734567890_1.wav")
        assert is_orphaned_output_wav("_1734567890_.wav")
        assert is_orphaned_output_wav("_0.wav")

    def test_does_not_match_named_outputs(self):
        assert not is_orphaned_output_wav("muse_voice0.wav")
        assert not is_orphaned_output_wav("muse_voice.wav")
        assert not is_orphaned_output_wav("NEWS_1734567890_0.wav")
        assert not is_orphaned_output_wav("muse_voice - TTS.mp3")
        assert not is_orphaned_output_wav("playlist_context.wav")


class TestRemovableTestOutputFiles:
    def test_matches_tts_test_artifacts(self):
        assert is_removable_output_file("tts_test0.wav")
        assert is_removable_output_file("tts_test12.wav")
        assert is_removable_output_file("tts_test3.mp3")

    def test_does_not_match_unrelated_files(self):
        assert not is_removable_output_file("tts_test.wav")
        assert not is_removable_output_file("my_tts_test0.wav")


class TestCleanupOrphanedOutputFiles:
    def test_removes_only_orphaned_wavs(self, tmp_path):
        keep = tmp_path / "muse_voice0.wav"
        remove = tmp_path / "_1734567890_1.wav"
        keep.write_bytes(b"keep")
        remove.write_bytes(b"remove")

        removed = cleanup_orphaned_output_files(str(tmp_path))

        assert removed == 1
        assert keep.exists()
        assert not remove.exists()

    def test_removes_tts_test_artifacts(self, tmp_path):
        keep = tmp_path / "muse_voice.wav"
        remove_wav = tmp_path / "tts_test0.wav"
        remove_mp3 = tmp_path / "tts_test1.mp3"
        keep.write_bytes(b"keep")
        remove_wav.write_bytes(b"wav")
        remove_mp3.write_bytes(b"mp3")

        removed = cleanup_orphaned_output_files(str(tmp_path))

        assert removed == 2
        assert keep.exists()
        assert not remove_wav.exists()
        assert not remove_mp3.exists()
