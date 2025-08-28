import pytest
import os
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Any

# Add the project root directory to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.globals import PlaylistSortType

class MockArgs:
    """Mock command line arguments for testing."""
    def __init__(self):
        self.enable_preparation = True
        self.enable_dynamic_volume = True
        self.enable_long_track_splitting = False
        self.long_track_splitting_time_cutoff_minutes = 20
        self.total = -1
        self.playlist_sort_type = PlaylistSortType.RANDOM
        self.directories = None
        self.overwrite = False
        self.track = None
        self.placeholder = False

@pytest.fixture
def mock_args():
    """Provide mock command line arguments for testing."""
    args = MockArgs()
    return args

@dataclass
class MockMediaTrack:
    """Mock MediaTrack for testing."""
    filepath: str
    title: str
    album: str
    artist: str
    composer: str
    _genre: str
    _form: str
    _instrument: str
    _is_extended: bool = False

    def get_genre(self):
        return self._genre

    def get_form(self):
        return self._form

    def get_instrument(self):
        return self._instrument

@dataclass
class MockDataCallbacks:
    """Mock data callbacks for testing."""
    def __init__(self, tracks=None):
        self.tracks = tracks or []
        self.track_dict = {track.filepath: track for track in self.tracks}

    def get_track(self, track_id: str) -> Optional[dict]:
        """Mock implementation of get_track."""
        return self.track_dict.get(track_id)
    
    def get_all_tracks(self) -> List[dict]:
        """Mock implementation of get_all_tracks."""
        return self.tracks

    def get_all_filepaths(self, directories: List[str], overwrite: bool = False) -> List[str]:
        """Mock implementation of get_all_filepaths."""
        return [str(Path(__file__).parent / "fixtures" / "sample_100KB.mp3")]

@pytest.fixture
def mock_tracks():
    """Provide a set of mock tracks for testing."""
    return [
        # Album 1 - Classical
        MockMediaTrack(
            filepath="track1.mp3",
            title="Symphony No. 5 - I",
            album="Beethoven: Symphony No. 5",
            artist="Berlin Philharmonic",
            composer="Beethoven",
            _genre="Classical",
            _form="Symphony",
            _instrument="Orchestra"
        ),
        MockMediaTrack(
            filepath="track2.mp3",
            title="Symphony No. 5 - II",
            album="Beethoven: Symphony No. 5",
            artist="Berlin Philharmonic",
            composer="Beethoven",
            _genre="Classical",
            _form="Symphony",
            _instrument="Orchestra"
        ),
        # Album 2 - Different Classical
        MockMediaTrack(
            filepath="track3.mp3",
            title="The Four Seasons - Spring",
            album="Vivaldi: The Four Seasons",
            artist="Academy of St Martin",
            composer="Vivaldi",
            _genre="Classical",
            _form="Concerto",
            _instrument="Violin"
        ),
        # Album 3 - Jazz
        MockMediaTrack(
            filepath="track4.mp3",
            title="Take Five",
            album="Time Out",
            artist="Dave Brubeck",
            composer="Paul Desmond",
            _genre="Jazz",
            _form="Jazz Standard",
            _instrument="Piano"
        ),
        MockMediaTrack(
            filepath="track5.mp3",
            title="Blue Rondo à la Turk",
            album="Time Out",
            artist="Dave Brubeck",
            composer="Dave Brubeck",
            _genre="Jazz",
            _form="Jazz Standard",
            _instrument="Piano"
        ),
        # Album 4 - Rock
        MockMediaTrack(
            filepath="track6.mp3",
            title="Stairway to Heaven",
            album="Led Zeppelin IV",
            artist="Led Zeppelin",
            composer="Page/Plant",
            _genre="Rock",
            _form="Rock Song",
            _instrument="Guitar"
        )
    ]

@pytest.fixture
def mock_data_callbacks(mock_tracks):
    """Provide mock data callbacks with test tracks."""
    return MockDataCallbacks(mock_tracks)

@pytest.fixture
def test_data_dir():
    """Return the path to the test data directory."""
    return Path(__file__).parent / "fixtures"

@pytest.fixture
def sample_audio_file(test_data_dir):
    """Return the path to a sample audio file for testing."""
    return test_data_dir / "sample_100KB.mp3"

@pytest.fixture
def temp_dir(tmp_path):
    """Provide a temporary directory that's cleaned up after each test."""
    return tmp_path 