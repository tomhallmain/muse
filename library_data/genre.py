
import json
import re

from utils.config import config
from utils.utils import Utils


class Genre:
    def __init__(self, name, transliterations=[], notes={}):
        self.name = name
        self.transliterations = transliterations if len(transliterations) > 0 else [name]
        self.notes = notes

    def new_note(self, key="New Note", value=""):
        self.notes[key] = value

    @staticmethod
    def from_json(json):
        return Genre(**json)



class GenresDataSearch:
    def __init__(self, genre="", max_results=200):
        self.genre = genre.lower()
        self.max_results = max_results

        self.results = []

    def is_valid(self):
        for name in ["composer", "genre"]:
            field = getattr(self, name)
            if field is not None and field.strip()!= "":
                print(f"{name} - \"{field}\"")
                return True
        return False

    def test(self, genre, strict=True):
        if len(self.results) > self.max_results:
            return None
        if len(self.genre) > 0:
            pattern = re.compile(f"(^|\\W){self.genre}") if strict else ""
            for indicator in genre.transliterations:
                indicator_lower = indicator.lower()
                if strict:
                    if indicator_lower == self.genre or re.search(pattern, indicator_lower):
                        self.results.append(genre)
                        return True
                else:
                    if self.genre in indicator_lower:
                        self.results.append(genre)
                        return True
        if len(self.genre) > 0 and strict:
            for genre in genre.genres:
                genre_lower = genre.lower()
                if genre_lower == self.genre or self.genre in genre_lower:
                    self.results.append(genre)
                    return True
        return False

    def sort_results_by_transliterations(self):
        self.results.sort(key=lambda composer: len(composer.transliterations), reverse=True)

    def get_results(self):
        return self.results



class GenresData:
    def __init__(self):
        self._genres = {}
        self._get_genres()

    def _get_genres(self):
        with open(config.genres_file, 'r', encoding="utf-8") as f:
            genres = json.load(f)
        for name, genre in genres.items():
            self._genres[name] = Genre.from_json(genre)

    def get_genre_names(self):
        return [genre.name for genre in self._genres.values()]

    def get_data(self, genre_name):
        if genre_name in self._genres:
            return self._genres[genre_name]
        for genre in self._genres.values():
            for value in genre.transliterations:
                if genre_name in value or value in genre_name:
                    return genre
        return None

    def get_genres(self, audio_track):
        matches = []
        title_lower = audio_track.title.lower()
        album_lower = audio_track.album.lower() if audio_track.album is not None else ""
        for genre in self._genres.values():
            for value in genre.transliterations:
                if value in title_lower or value in album_lower:
                    matches += [genre.name]
        return matches

    def do_search(self, data_search):
        if not isinstance(data_search, GenresDataSearch):
            raise TypeError('Genres data search must be of type GenresDataSearch')
        if not data_search.is_valid():
            Utils.log_yellow('Invalid search query')
            return data_search

        full_results = False
        for genre in self._genres.values():
            if data_search.test(genre) is None:
                full_results = True
                break

        data_search.sort_results_by_transliterations() # The genres with the most transliterations are probably the most well-known

        if not full_results:
            for genre in self._genres.values():
                if not genre in data_search.results and \
                        data_search.test(genre, strict=False) is None:
                    break

        return data_search


genre_data = GenresData()

