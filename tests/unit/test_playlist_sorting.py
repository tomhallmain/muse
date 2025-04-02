import pytest
from muse import Playlist
from utils.globals import PlaylistSortType

@pytest.mark.unit
class TestPlaylistSorting:
    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup and teardown for each test."""
        # Store original recently played lists
        self.original_filepaths = Playlist.recently_played_filepaths.copy()
        self.original_albums = Playlist.recently_played_albums.copy()
        self.original_artists = Playlist.recently_played_artists.copy()
        self.original_composers = Playlist.recently_played_composers.copy()
        self.original_genres = Playlist.recently_played_genres.copy()
        self.original_forms = Playlist.recently_played_forms.copy()
        self.original_instruments = Playlist.recently_played_instruments.copy()

        # Set up mock historical data
        Playlist.recently_played_filepaths = [
            "recent_track1.mp3",
            "recent_track2.mp3",
            "recent_track3.mp3",
        ]
        Playlist.recently_played_albums = [
            "Mozart: Symphony No. 40",
            "Bach: Well-Tempered Clavier",
            "Kind of Blue",
        ]
        Playlist.recently_played_artists = [
            "Vienna Philharmonic",
            "Glenn Gould",
            "Miles Davis",
        ]
        Playlist.recently_played_composers = [
            "Mozart",
            "Bach",
            "Miles Davis",
        ]
        Playlist.recently_played_genres = [
            "Classical",
            "Jazz",
            "Rock",
        ]
        Playlist.recently_played_forms = [
            "Symphony",
            "Concerto",
            "Jazz Standard",
        ]
        Playlist.recently_played_instruments = [
            "Piano",
            "Orchestra",
            "Trumpet",
        ]

        yield

        # Restore original recently played lists
        Playlist.recently_played_filepaths = self.original_filepaths
        Playlist.recently_played_albums = self.original_albums
        Playlist.recently_played_artists = self.original_artists
        Playlist.recently_played_composers = self.original_composers
        Playlist.recently_played_genres = self.original_genres
        Playlist.recently_played_forms = self.original_forms
        Playlist.recently_played_instruments = self.original_instruments

    def test_sequence_sort(self, mock_data_callbacks, mock_tracks):
        """Test sequential sorting (no randomization)."""
        playlist = Playlist(
            tracks=[t.filepath for t in mock_tracks],
            _type=PlaylistSortType.SEQUENCE,
            data_callbacks=mock_data_callbacks
        )
        
        # Verify all tracks are present
        assert len(playlist.sorted_tracks) == len(mock_tracks)
        track_filepaths = {t.filepath for t in playlist.sorted_tracks}
        mock_filepaths = {t.filepath for t in mock_tracks}
        assert track_filepaths == mock_filepaths
        
        # Verify sequence order is maintained after start point
        # Find the index of the first track in the original order
        first_track = mock_tracks[0]
        start_idx = playlist.sorted_tracks.index(first_track)
        
        # Verify the sequence after the start point matches the original order
        for i in range(len(mock_tracks)):
            expected_idx = (start_idx + i) % len(mock_tracks)
            assert playlist.sorted_tracks[expected_idx].filepath == mock_tracks[i].filepath

    def test_album_shuffle_with_history(self, mock_data_callbacks, mock_tracks):
        """Test album shuffle considering recently played albums."""
        playlist = Playlist(
            tracks=[t.filepath for t in mock_tracks],
            _type=PlaylistSortType.ALBUM_SHUFFLE,
            data_callbacks=mock_data_callbacks
        )
        
        # Get all unique albums and their tracks
        albums = {}
        for track in playlist.sorted_tracks:
            if track.album not in albums:
                albums[track.album] = []
            albums[track.album].append(track)
        
        # Verify tracks from same album are consecutive
        for album_tracks in albums.values():
            if len(album_tracks) > 1:
                for i in range(len(album_tracks) - 1):
                    assert album_tracks[i].album == album_tracks[i + 1].album
        
        # Verify recently played albums are not at the start
        if playlist.sorted_tracks:
            first_album = playlist.sorted_tracks[0].album
            assert first_album not in Playlist.recently_played_albums[:3]

    def test_artist_shuffle(self, mock_data_callbacks, mock_tracks):
        """Test artist shuffle - tracks from same artist should stay together."""
        playlist = Playlist(
            tracks=[t.filepath for t in mock_tracks],
            _type=PlaylistSortType.ARTIST_SHUFFLE,
            data_callbacks=mock_data_callbacks
        )
        
        # Get all unique artists and their tracks
        artists = {}
        for track in playlist.sorted_tracks:
            if track.artist not in artists:
                artists[track.artist] = []
            artists[track.artist].append(track)
        
        # Verify tracks from same artist are consecutive
        for artist_tracks in artists.values():
            if len(artist_tracks) > 1:
                for i in range(len(artist_tracks) - 1):
                    assert artist_tracks[i].artist == artist_tracks[i + 1].artist

    def test_composer_shuffle(self, mock_data_callbacks, mock_tracks):
        """Test composer shuffle - tracks from same composer should stay together."""
        playlist = Playlist(
            tracks=[t.filepath for t in mock_tracks],
            _type=PlaylistSortType.COMPOSER_SHUFFLE,
            data_callbacks=mock_data_callbacks
        )
        
        # Get all unique composers and their tracks
        composers = {}
        for track in playlist.sorted_tracks:
            if track.composer not in composers:
                composers[track.composer] = []
            composers[track.composer].append(track)
        
        # Verify tracks from same composer are consecutive
        for composer_tracks in composers.values():
            if len(composer_tracks) > 1:
                for i in range(len(composer_tracks) - 1):
                    assert composer_tracks[i].composer == composer_tracks[i + 1].composer

    def test_genre_shuffle(self, mock_data_callbacks, mock_tracks):
        """Test genre shuffle - tracks from same genre should stay together."""
        playlist = Playlist(
            tracks=[t.filepath for t in mock_tracks],
            _type=PlaylistSortType.GENRE_SHUFFLE,
            data_callbacks=mock_data_callbacks
        )
        
        # Get all unique genres and their tracks
        genres = {}
        for track in playlist.sorted_tracks:
            genre = track.get_genre()
            if genre not in genres:
                genres[genre] = []
            genres[genre].append(track)
        
        # Verify tracks from same genre are consecutive
        for genre_tracks in genres.values():
            if len(genre_tracks) > 1:
                for i in range(len(genre_tracks) - 1):
                    assert genre_tracks[i].get_genre() == genre_tracks[i + 1].get_genre()

    def test_form_shuffle(self, mock_data_callbacks, mock_tracks):
        """Test form shuffle - tracks of same form should stay together."""
        playlist = Playlist(
            tracks=[t.filepath for t in mock_tracks],
            _type=PlaylistSortType.FORM_SHUFFLE,
            data_callbacks=mock_data_callbacks
        )
        
        # Get all unique forms and their tracks
        forms = {}
        for track in playlist.sorted_tracks:
            form = track.get_form()
            if form not in forms:
                forms[form] = []
            forms[form].append(track)
        
        # Verify tracks of same form are consecutive
        for form_tracks in forms.values():
            if len(form_tracks) > 1:
                for i in range(len(form_tracks) - 1):
                    assert form_tracks[i].get_form() == form_tracks[i + 1].get_form()

    def test_instrument_shuffle(self, mock_data_callbacks, mock_tracks):
        """Test instrument shuffle - tracks with same instrument should stay together."""
        playlist = Playlist(
            tracks=[t.filepath for t in mock_tracks],
            _type=PlaylistSortType.INSTRUMENT_SHUFFLE,
            data_callbacks=mock_data_callbacks
        )
        
        # Get all unique instruments and their tracks
        instruments = {}
        for track in playlist.sorted_tracks:
            instrument = track.get_instrument()
            if instrument not in instruments:
                instruments[instrument] = []
            instruments[instrument].append(track)
        
        # Verify tracks with same instrument are consecutive
        for instrument_tracks in instruments.values():
            if len(instrument_tracks) > 1:
                for i in range(len(instrument_tracks) - 1):
                    assert instrument_tracks[i].get_instrument() == instrument_tracks[i + 1].get_instrument()

    def test_random_shuffle(self, mock_data_callbacks, mock_tracks):
        """Test random shuffle."""
        playlist = Playlist(
            tracks=[t.filepath for t in mock_tracks],
            _type=PlaylistSortType.RANDOM,
            data_callbacks=mock_data_callbacks
        )
        
        # Verify all tracks are present
        assert len(playlist.sorted_tracks) == len(mock_tracks)
        track_filepaths = {t.filepath for t in playlist.sorted_tracks}
        mock_filepaths = {t.filepath for t in mock_tracks}
        assert track_filepaths == mock_filepaths 

    def test_recently_played_update(self, mock_data_callbacks, mock_tracks):
        """Test that recently played lists are updated correctly."""
        playlist = Playlist(
            tracks=[t.filepath for t in mock_tracks],
            _type=PlaylistSortType.SEQUENCE,
            data_callbacks=mock_data_callbacks
        )
        
        # Get a track and update recently played
        track = mock_tracks[0]
        Playlist.update_recently_played_lists(track)
        
        # Verify lists are updated
        assert track.filepath == Playlist.recently_played_filepaths[0]
        assert track.album == Playlist.recently_played_albums[0]
        assert track.artist == Playlist.recently_played_artists[0]
        assert track.composer == Playlist.recently_played_composers[0]
        assert track.get_genre() == Playlist.recently_played_genres[0]
        assert track.get_form() == Playlist.recently_played_forms[0]
        assert track.get_instrument() == Playlist.recently_played_instruments[0] 