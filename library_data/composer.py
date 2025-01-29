
import json
import re

from library_data.work import Work
from utils.config import config
from utils.utils import Utils


class Composer:
    def __init__(self, id, name, indicators=[], start_date=-1, end_date=-1,
                 dates_are_lifespan=True, dates_uncertain=False, genres=[], works=[], notes={}):
        self.id = id
        self.name = name
        self.indicators = indicators if len(indicators) > 0 else [name]
        self.start_date = start_date
        self.end_date = end_date
        self.dates_are_lifespan = dates_are_lifespan
        self.dates_uncertain = dates_uncertain
        self.genres = genres
        self.works = works
        self.notes = notes

        for work in works:
            self.add_work(work)

    def add_work(self, work):
        self.works.append(Work(work, self))

    def new_note(self, key="New Note", value=""):
        self.notes[key] = value

    @staticmethod
    def from_json(json):
        return Composer(**json)



class ComposersDataSearch:
    def __init__(self, composer="", genre="", max_results=200):
        self.composer = composer.lower()
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

    def test(self, composer, strict=True):
        if len(self.results) > self.max_results:
            return None
        if len(self.composer) > 0:
            pattern = re.compile(f"(^|\\W){self.composer}") if strict else ""
            for indicator in composer.indicators:
                indicator_lower = indicator.lower()
                if strict:
                    if indicator_lower == self.composer or re.search(pattern, indicator_lower):
                        self.results.append(composer)
                        return True
                else:
                    if self.composer in indicator_lower:
                        self.results.append(composer)
                        return True
        if len(self.genre) > 0 and strict:
            for genre in composer.genres:
                genre_lower = genre.lower()
                if genre_lower == self.genre or self.genre in genre_lower:
                    self.results.append(composer)
                    return True
        return False

    def sort_results_by_indicators(self):
        self.results.sort(key=lambda composer: len(composer.indicators), reverse=True)

    def get_results(self):
        return self.results



class ComposersData:
    def __init__(self):
        self._composers = {}
        self._get_composers()

    def _get_composers(self):
        with open(config.composers_file, 'r', encoding="utf-8") as f:
            composers = json.load(f)
        for name, composer in composers.items():
            self._composers[name] = Composer.from_json(composer)

    def get_composer_names(self):
        return [composer.name for composer in self._composers.values()]

    def get_data(self, composer_name):
        if composer_name in self._composers:
            return self._composers[composer_name]
        for composer in self._composers.values():
            for value in composer.indicators:
                if composer_name in value or value in composer_name:
                    return composer
        return None

    def get_composers(self, audio_track):
        matches = []
        for composer in self._composers.values():
            for value in composer.indicators:
                if value in audio_track.title or \
                        (audio_track.album is not None and value in audio_track.album) or \
                        (audio_track.artist is not None and value in audio_track.artist):
                    matches += [composer.name]
                    break
                elif audio_track.composer is not None and value in audio_track.composer:
                    Utils.log("Found composer match on " + audio_track.filepath)
                    matches += [composer.name]
                    break
        return matches

    def do_search(self, data_search):
        if not isinstance(data_search, ComposersDataSearch):
            raise TypeError('Composers data search must be of type ComposersDataSearch')
        if not data_search.is_valid():
            Utils.log_yellow('Invalid search query')
            return data_search

        full_results = False
        for composer in self._composers.values():
            if data_search.test(composer) is None:
                full_results = True
                break

        data_search.sort_results_by_indicators() # The composers with the most indicators are probably the most well-known

        if not full_results:
            for composer in self._composers.values():
                if not composer in data_search.results and \
                        data_search.test(composer, strict=False) is None:
                    break

        return data_search


composers_data = ComposersData()

