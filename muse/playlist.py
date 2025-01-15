import random

from library_data.audio_track import AudioTrack
from utils.globals import WorkflowType


class Playlist:
    def __init__(self, tracks=[], type=WorkflowType.SEQUENCE):
        self.all_tracks = list(tracks)
        self.in_sequence = list(tracks)
        if type == WorkflowType.RANDOM:
            random.shuffle(self.in_sequence)
        self.pending_tracks = list(tracks)
        self.played_tracks = []
        self.current_song_index = -1

    def size(self):
        return len(self.all_tracks)

    def remaining_count(self):
        return len(self.pending_tracks)

    def is_valid(self):
        return len(self.all_tracks) > 0

    def next_track(self):
        if len(self.in_sequence) == 0 or self.current_song_index >= len(self.in_sequence):
            return None
        self.current_song_index += 1
        next_track_path = self.in_sequence[self.current_song_index]
        self.pending_tracks.remove(next_track_path)
        self.played_tracks.append(next_track_path)
        return AudioTrack(next_track_path)

    def upcoming_track(self):
        if len(self.in_sequence) == 0 or (self.current_song_index + 1) >= len(self.in_sequence):
            return None
        return AudioTrack(self.in_sequence[self.current_song_index + 1])

