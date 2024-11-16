
import json
import os

from library_data.work import Work



class Composer:
    def __init__(self, id, name, indicators=[], dob=-1, dod=-1, genres=[], works=[]):
        self.id = id
        self.name = name
        self.indicators = indicators if len(indicators) > 0 else [name]
        self.dob = dob
        self.dod = dod
        self.genres = genres
        self.works = works

        for work in works:
            self.add_work(work)

    def add_work(self, work):
        self.works.append(Work(work, self))

    @staticmethod
    def from_json(json):
        return Composer(**json)



libary_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)))
configs_dir = os.path.join(os.path.dirname(libary_dir), 'configs')


class ComposersData:
    def __init__(self):
        self._composers = {}
        self._get_composers()

    def _get_composers(self):
        with open(os.path.join(configs_dir,'composers_dict.json'), 'r', encoding="utf-8") as f:
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
                    print("Found composer match on " + audio_track.filepath)
                    matches += [composer.name]
        return matches


composers_data = ComposersData()

