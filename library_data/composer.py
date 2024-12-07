
import json

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

    @staticmethod
    def from_json(json):
        return Composer(**json)





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
                elif audio_track.composer is not None and value in audio_track.composer:
                    Utils.log("Found composer match on " + audio_track.filepath)
                    matches += [composer.name]
        return matches


composers_data = ComposersData()

