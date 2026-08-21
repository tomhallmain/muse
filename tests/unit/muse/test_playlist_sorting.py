import pytest
from muse import Playlist
from tests.conftest import MockDataCallbacks, MockMediaTrack
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
        self.original_catalogues = Playlist.recently_played_catalogues.copy()
        self.original_main_artists = Playlist.recently_played_main_artists.copy()

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
        Playlist.recently_played_catalogues = [
            "Mozart: Symphonies",
            "Bach: Complete Organ Works",
            "The Riverbend Sessions",
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
        Playlist.recently_played_catalogues = self.original_catalogues
        Playlist.recently_played_main_artists = self.original_main_artists

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

    def test_catalogue_shuffle(self, mock_data_callbacks, mock_tracks):
        """Test catalogue shuffle - tracks from different albums in the same catalogue
        (e.g. different Vol. N releases) should stay together."""
        playlist = Playlist(
            tracks=[t.filepath for t in mock_tracks],
            _type=PlaylistSortType.CATALOGUE_SHUFFLE,
            data_callbacks=mock_data_callbacks
        )

        # Sanity check the fixture actually has a catalogue spanning multiple albums.
        vivaldi_tracks = [t for t in mock_tracks if t.get_catalogue() == "Vivaldi Operas"]
        assert len({t.album for t in vivaldi_tracks}) > 1

        # Get all unique catalogues and their tracks
        catalogues = {}
        for track in playlist.sorted_tracks:
            catalogue = track.get_catalogue()
            if catalogue not in catalogues:
                catalogues[catalogue] = []
            catalogues[catalogue].append(track)

        # Verify tracks from the same catalogue are consecutive
        for catalogue_tracks in catalogues.values():
            if len(catalogue_tracks) > 1:
                for i in range(len(catalogue_tracks) - 1):
                    assert catalogue_tracks[i].get_catalogue() == catalogue_tracks[i + 1].get_catalogue()

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
        assert track.get_catalogue() == Playlist.recently_played_catalogues[0]
    def test_main_artist_list_not_updated_for_other_sort_types(self, mock_tracks):
        """The main artist is only resolved for the grouping that uses it."""
        Playlist.recently_played_main_artists = []
        track = mock_tracks[0]

        Playlist.update_recently_played_lists(track, sort_type=PlaylistSortType.ARTIST_SHUFFLE)
        assert Playlist.recently_played_main_artists == []

        Playlist.update_recently_played_lists(track)
        assert Playlist.recently_played_main_artists == []

        # the other lists still update regardless of sort type
        assert track.artist == Playlist.recently_played_artists[0]

    def test_main_artist_list_updated_for_main_artist_shuffle(self, mock_tracks):
        Playlist.recently_played_main_artists = []
        track = mock_tracks[0]

        Playlist.update_recently_played_lists(track, sort_type=PlaylistSortType.MAIN_ARTIST_SHUFFLE)

        assert Playlist.recently_played_main_artists[0] == track.get_main_artist()

    def _resolved_artist_tracks(self):
        """Tracks whose raw artist values differ but whose main artist matches.

        This is the case the sort type exists for: grouping on the raw artist
        field would scatter these across separate groups.
        """
        def _track(filepath, artist, main_artist, album):
            return MockMediaTrack(
                filepath=filepath, title=filepath, album=album, artist=artist,
                composer="Composer", _genre="Classical", _form="Symphony",
                _instrument="Orchestra", _catalogue=album, _main_artist=main_artist)

        return [
            _track("ma1.mp3", "Karajan; Berlin Philharmonic", "Karajan", "Album A"),
            _track("ma2.mp3", "Berlin Philharmonic feat. Mutter", "Karajan", "Album B"),
            _track("ma3.mp3", "Karajan & Vienna Philharmonic", "Karajan", "Album C"),
            _track("ma4.mp3", "Gould; CBC Symphony", "Gould", "Album D"),
            _track("ma5.mp3", "Gould, Toronto Symphony", "Gould", "Album E"),
        ]

    def test_main_artist_shuffle_groups_by_resolved_artist(self):
        # Cleared so the memory shuffle cannot reorder groups unpredictably here;
        # the autouse fixture restores it afterwards.
        Playlist.recently_played_main_artists = []
        tracks = self._resolved_artist_tracks()
        playlist = Playlist(
            tracks=[t.filepath for t in tracks],
            _type=PlaylistSortType.MAIN_ARTIST_SHUFFLE,
            data_callbacks=MockDataCallbacks(tracks),
        )

        assert len(playlist.sorted_tracks) == len(tracks)

        # Every main artist must occupy one contiguous run, not several.
        keys = [t.get_main_artist() for t in playlist.sorted_tracks]
        run_starts = [k for i, k in enumerate(keys) if i == 0 or keys[i - 1] != k]
        assert len(run_starts) == len(set(run_starts)), f"groups are not contiguous: {keys}"
        assert set(keys) == {"Karajan", "Gould"}

    def test_raw_artist_shuffle_would_not_group_these_tracks(self):
        """Contrast case: the same tracks under ARTIST_SHUFFLE have five distinct
        groups, which is the fragmentation this sort type exists to fix."""
        tracks = self._resolved_artist_tracks()
        assert len({t.artist for t in tracks}) == 5
        assert len({t.get_main_artist() for t in tracks}) == 2

    def test_main_artist_shuffle_uses_the_resolved_getter(self):
        assert PlaylistSortType.MAIN_ARTIST_SHUFFLE.getter_name_mapping() == "get_main_artist"
        # the existing type is untouched
        assert PlaylistSortType.ARTIST_SHUFFLE.getter_name_mapping() == "artist"

    def test_main_artist_shuffle_translation_round_trip(self):
        """get_translation indexes positionally into get_translated_names, so a
        missing entry would raise rather than merely read oddly."""
        translation = PlaylistSortType.MAIN_ARTIST_SHUFFLE.get_translation()
        assert PlaylistSortType.get_from_translation(translation) == PlaylistSortType.MAIN_ARTIST_SHUFFLE
        assert PlaylistSortType.MAIN_ARTIST_SHUFFLE.get_grouping_readable_name()
        assert PlaylistSortType.MAIN_ARTIST_SHUFFLE.is_grouping_type()
