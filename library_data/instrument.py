
import json
import re

from utils.config import config
from utils.utils import Utils


class Instrument:
    def __init__(self, name, transliterations=[], notes={}):
        self.name = name
        self.transliterations = transliterations if len(transliterations) > 0 else [name]
        self.notes = notes

    def new_note(self, key="New Note", value=""):
        self.notes[key] = value

    @staticmethod
    def from_json(json):
        return Instrument(**json)



class InstrumentsDataSearch:
    def __init__(self, instrument="", max_results=200):
        self.instrument = instrument.lower()
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
        if len(self.instrument) > 0:
            pattern = re.compile(f"(^|\\W){self.instrument}") if strict else ""
            for indicator in composer.transliterations:
                indicator_lower = indicator.lower()
                if strict:
                    if indicator_lower == self.instrument or re.search(pattern, indicator_lower):
                        self.results.append(composer)
                        return True
                else:
                    if self.instrument in indicator_lower:
                        self.results.append(composer)
                        return True
        return False

    def sort_results_by_transliterations(self):
        self.results.sort(key=lambda composer: len(composer.transliterations), reverse=True)

    def get_results(self):
        return self.results



class InstrumentsData:
    def __init__(self):
        self._instruments = {}
        self._get_instruments()

    def _get_instruments(self):
        with open(config.forms_file, 'r', encoding="utf-8") as f:
            forms = json.load(f)
        for name, form in forms.items():
            self._instruments[name] = Instrument.from_json(form)

    def get_instrument_names(self):
        return [instrument.name for instrument in self._instruments.values()]

    def get_data(self, instrument_name):
        if instrument_name in self._instruments:
            return self._instruments[instrument_name]
        for instrument in self._instruments.values():
            for value in instrument.transliterations:
                if instrument_name in value or value in instrument_name:
                    return instrument
        return None

    def get_instruments(self, audio_track):
        matches = []
        title_lower = audio_track.title.lower()
        album_lower = audio_track.album.lower() if audio_track.album is not None else ""
        for instrument in self._instruments.values():
            for value in instrument.transliterations:
                if value in title_lower or value in album_lower:
                    matches += [instrument.name]
        return matches

    def do_search(self, data_search):
        if not isinstance(data_search, InstrumentsDataSearch):
            raise TypeError('Forms data search must be of type FormsDataSearch')
        if not data_search.is_valid():
            Utils.log_yellow('Invalid search query')
            return data_search

        full_results = False
        for instrument in self._instruments.values():
            if data_search.test(instrument) is None:
                full_results = True
                break

        data_search.sort_results_by_transliterations() # The composers with the most transliterations are probably the most well-known

        if not full_results:
            for instrument in self._instruments.values():
                if not instrument in data_search.results and \
                        data_search.test(instrument, strict=False) is None:
                    break

        return data_search


instruments_data = InstrumentsData()

