
import json
import re

from utils.config import config
from utils.utils import Utils


class Artist:
    def __init__(self, id, name, indicators=[], start_date=-1, end_date=-1,
                 dates_are_lifespan=True, dates_uncertain=False, genres=[], albums=[], notes={}):
        self.id = id
        self.name = name
        self.indicators = indicators if len(indicators) > 0 else [name]
        self.start_date = start_date
        self.end_date = end_date
        self.dates_are_lifespan = dates_are_lifespan
        self.dates_uncertain = dates_uncertain
        self.genres = genres
        self.albums = albums
        self.notes = notes

    def new_note(self, key="New Note", value=""):
        self.notes[key] = value

    @staticmethod
    def from_json(json):
        return Artist(**json)



class ArtistsDataSearch:
    def __init__(self, artist="", genre="", max_results=200):
        self.artist = artist.lower()
        self.genre = genre.lower()
        self.max_results = max_results

        self.results = []

    def is_valid(self):
        for name in ["artist", "genre"]:
            field = getattr(self, name)
            if field is not None and field.strip()!= "":
                print(f"{name} - \"{field}\"")
                return True
        return False

    def test(self, artist, strict=True):
        if len(self.results) > self.max_results:
            return None
        if len(self.artist) > 0:
            pattern = re.compile(f"(^|\\W){self.artist}") if strict else ""
            for indicator in artist.indicators:
                indicator_lower = indicator.lower()
                if strict:
                    if indicator_lower == self.artist or re.search(pattern, indicator_lower):
                        self.results.append(artist)
                        return True
                else:
                    if self.artist in indicator_lower:
                        self.results.append(artist)
                        return True
        if len(self.genre) > 0 and strict:
            for genre in artist.genres:
                genre_lower = genre.lower()
                if genre_lower == self.genre or self.genre in genre_lower:
                    self.results.append(artist)
                    return True
        return False

    def sort_results_by_indicators(self):
        self.results.sort(key=lambda artist: len(artist.indicators), reverse=True)

    def get_results(self):
        return self.results



class ArtistsData:
    def __init__(self):
        self._artists = {}
        self._get_artists()

    def _get_artists(self):
        with open(config.artists_file, 'r', encoding="utf-8") as f:
            artists = json.load(f)
        for name, artist in artists.items():
            self._artists[name] = Artist.from_json(artist)

    def get_artist_names(self):
        return [artist.name for artist in self._artists.values()]

    def get_data(self, artist_name):
        if artist_name in self._artists:
            return self._artists[artist_name]
        for artist in self._artists.values():
            for value in artist.indicators:
                if artist_name in value or value in artist_name:
                    return artist
        return None

    def get_artists(self, audio_track):
        matches = []
        for artist in self._artists.values():
            for value in artist.indicators:
                if value in audio_track.title or \
                        (audio_track.album is not None and value in audio_track.album) or \
                        (audio_track.artist is not None and value in audio_track.artist):
                    matches += [artist.name]
                    break
                elif audio_track.artist is not None and value in audio_track.artist:
                    Utils.log("Found artist match on " + audio_track.filepath)
                    matches += [artist.name]
                    break
        return matches

    def do_search(self, data_search):
        if not isinstance(data_search, ArtistsDataSearch):
            raise TypeError('Artists data search must be of type ArtistsDataSearch')
        if not data_search.is_valid():
            Utils.log_yellow('Invalid search query')
            return data_search

        full_results = False
        for artist in self._artists.values():
            if data_search.test(artist) is None:
                full_results = True
                break

        data_search.sort_results_by_indicators() # The artists with the most indicators are probably the most well-known

        if not full_results:
            for artist in self._artists.values():
                if not artist in data_search.results and \
                        data_search.test(artist, strict=False) is None:
                    break

        return data_search


artists_data = ArtistsData()

