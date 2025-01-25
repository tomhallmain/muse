import random

from library_data.media_track import MediaTrack
from utils.globals import PlaylistSortType


class Playlist:
    def __init__(self, tracks=[], _type=PlaylistSortType.SEQUENCE):
        self.in_sequence = list(tracks)
        self.sorted_tracks = list(tracks)
        self.sort_type = _type
        self.sort()
        self.pending_tracks = list(tracks)
        self.played_tracks = []
        self.current_song_index = -1

    def size(self):
        return len(self.in_sequence)

    def remaining_count(self):
        return len(self.pending_tracks)

    def is_valid(self):
        return len(self.in_sequence) > 0

    def next_track(self):
        if len(self.sorted_tracks) == 0 or self.current_song_index >= len(self.sorted_tracks):
            return None
        self.current_song_index += 1
        next_track_path = self.sorted_tracks[self.current_song_index]
        self.pending_tracks.remove(next_track_path)
        self.played_tracks.append(next_track_path)
        return MediaTrack(next_track_path)

    def upcoming_track(self):
        if len(self.sorted_tracks) == 0 or (self.current_song_index + 1) >= len(self.sorted_tracks):
            return None
        return MediaTrack(self.sorted_tracks[self.current_song_index + 1])

    def sort(self):
        if self.sort_type == PlaylistSortType.RANDOM:
            random.shuffle(self.sorted_tracks)
        elif self.sort_type == PlaylistSortType.ALBUM_SHUFFLE:
            album_set = set()
            for track in self.sorted_tracks:
                album_set.add(track.album)
            all_albums_list = list(album_set)
            self.sorted_tracks.sort(key=lambda t: (all_albums_list.index(t.album), t.filepath))
        elif self.sort_type == PlaylistSortType.ARTIST_SHUFFLE:
            artist_set = set()
            for track in self.sorted_tracks:
                artist_set.add(track.artist)
            all_artists_list = list(artist_set)
            self.sorted_tracks.sort(key=lambda t: (all_artists_list.index(t.artist), t.filepath))
        elif self.sort_type == PlaylistSortType.COMPOSER_SHUFFLE:
            composer_set = set()
            for track in self.sorted_tracks:
                composer_set.add(track.composer)
            all_composers_list  = list(composer_set)
            self.sorted_tracks.sort(key=lambda t: (all_composers_list.index(t.composer), t.filepath))
        elif self.sort_type == PlaylistSortType.GENRE_SHUFFLE:
            genre_set = set()
            for track in self.sorted_tracks:
                genre_set.add(track.genre)
            all_genres_list = list(genre_set)
            self.sorted_tracks.sort(key=lambda t: (all_genres_list.index(t.genre), t.filepath))
        elif self.sort_type == PlaylistSortType.FORM_SHUFFLE:
            form_set = set()
            for track in self.sorted_tracks:
                form_set.add(track.get_form())
            all_forms_list = list(form_set)
            self.sorted_tracks.sort(key=lambda t: (all_forms_list.index(t.get_form()), t.filepath))
        elif self.sort_type == PlaylistSortType.INSTRUMENT_SHUFFLE:
            instrument_set = set()
            for track in self.sorted_tracks:
                instrument_set.add(track.get_instrument())
            all_instruments_list  = list(instrument_set)
            self.sorted_tracks.sort(key=lambda t: (all_instruments_list.index(t.get_instrument()), t.filepath))






