
import json
import re

from library_data.work import Work
from utils.config import config
from utils.utils import Utils


class Form:
    def __init__(self, name, transliterations=[], notes={}):
        self.name = name
        self.transliterations = transliterations if len(transliterations) > 0 else [name]
        self.notes = notes

    def new_note(self, key="New Note", value=""):
        self.notes[key] = value

    @staticmethod
    def from_json(json):
        return Form(**json)



class FormsDataSearch:
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
            for indicator in composer.transliterations:
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
                if genre_lower == self.composer or self.composer in genre_lower:
                    self.results.append(composer)
                    return True
        return False

    def sort_results_by_transliterations(self):
        self.results.sort(key=lambda composer: len(composer.transliterations), reverse=True)

    def get_results(self):
        return self.results



class FormsData:
    def __init__(self):
        self._forms = {}
        self._get_forms()

    def _get_forms(self):
        with open(config.forms_file, 'r', encoding="utf-8") as f:
            forms = json.load(f)
        for name, form in forms.items():
            self._forms[name] = Form.from_json(form)

    def get_composer_names(self):
        return [composer.name for composer in self._forms.values()]

    def get_data(self, composer_name):
        if composer_name in self._forms:
            return self._forms[composer_name]
        for composer in self._forms.values():
            for value in composer.transliterations:
                if composer_name in value or value in composer_name:
                    return composer
        return None

    def get_forms(self, audio_track):
        matches = []
        for form in self._forms.values():
            for value in form.transliterations:
                if value in audio_track.title:
                    matches += [form.name]
        return matches

    def do_search(self, data_search):
        if not isinstance(data_search, FormsDataSearch):
            raise TypeError('Forms data search must be of type FormsDataSearch')
        if not data_search.is_valid():
            Utils.log_yellow('Invalid search query')
            return data_search

        full_results = False
        for form in self._forms.values():
            if data_search.test(form) is None:
                full_results = True
                break

        data_search.sort_results_by_transliterations() # The composers with the most transliterations are probably the most well-known

        if not full_results:
            for form in self._forms.values():
                if not form in data_search.results and \
                        data_search.test(form, strict=False) is None:
                    break

        return data_search


forms_data = FormsData()

