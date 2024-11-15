import json
import os

from library_data.composer import Composer
from library_data.work import Work


libary_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)))
configs_dir = os.path.join(os.path.dirname(libary_dir), 'configs')


class LibraryData:
    def __init__(self):
        self._composers = []

        with open(os.path.join(configs_dir,'composers_dict.json'), 'r', encoding="utf-8") as f:
            composers = json.load(f)
        for composer in composers.values():
            self._composers.append(Composer.from_json(composer))

    def get_composer_names(self):
        return [composer.name for composer in self._composers]

    def get_composers(self, audio_track):
        matches = []
        for composer in self._composers:
            for value in composer.indicators:
                if value in audio_track.title or value in audio_track.album or value in audio_track.artist:
                    matches += [composer.name]
                elif audio_track.composer is not None and value in audio_track.composer:
                    print("Found composer match on " + audio_track.filepath)
                    matches += [composer.name]
        return matches

