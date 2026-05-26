"""Sanity checks for the generated audio fixture library."""

import pytest
from tests.fixtures.audio_fixtures import (
    AUDIO_LIBRARY_DIR,
    MIN_TRACK_COUNT,
    load_media_tracks,
    load_track_specs,
    manifest_track_count,
)


@pytest.mark.unit
class TestAudioFixtures:
    def test_manifest_meets_minimum_track_count(self, audio_library_manifest):
        assert manifest_track_count() >= MIN_TRACK_COUNT
        assert audio_library_manifest["track_count"] >= MIN_TRACK_COUNT

    def test_all_manifest_files_exist(self, audio_library_dir, audio_library_manifest):
        for entry in audio_library_manifest["tracks"]:
            path = audio_library_dir / entry["relative_path"]
            assert path.is_file(), entry["relative_path"]

    def test_media_tracks_load_metadata_from_tags(self, audio_library_media_tracks):
        assert len(audio_library_media_tracks) >= MIN_TRACK_COUNT
        sample = audio_library_media_tracks[0]
        assert sample.title
        assert sample.album
        assert sample.artist
        assert sample.composer
        assert sample.get_track_length() > 0

    def test_varied_durations_and_albums(self):
        specs = load_track_specs()
        durations = {s.duration_seconds for s in specs}
        albums = {s.album for s in specs}
        assert len(durations) >= 10
        assert len(albums) >= 30
