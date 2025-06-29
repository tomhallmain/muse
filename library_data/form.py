
import json
import re

from utils.config import config
from utils.logging_setup import get_logger

logger = get_logger(__name__)

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
    def __init__(self, form="", genre="", max_results=200):
        self.form = form.lower()
        self.genre = genre.lower()
        self.max_results = max_results

        self.results = []

    def is_valid(self):
        for name in ["composer", "genre"]:
            field = getattr(self, name)
            if field is not None and field.strip()!= "":
                #print(f"{name} - \"{field}\"")
                return True
        return False

    def test(self, form, strict=True):
        if len(self.results) > self.max_results:
            return None
        if len(self.form) > 0:
            pattern = re.compile(f"(^|\\W){self.form}") if strict else ""
            for indicator in form.transliterations:
                indicator_lower = indicator.lower()
                if strict:
                    if indicator_lower == self.form or re.search(pattern, indicator_lower):
                        self.results.append(form)
                        return True
                else:
                    if self.form in indicator_lower:
                        self.results.append(form)
                        return True
        if len(self.genre) > 0 and strict:
            for genre in form.genres:
                genre_lower = genre.lower()
                if genre_lower == self.form or self.form in genre_lower:
                    self.results.append(form)
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

    def get_form_names(self):
        return [form.name for form in self._forms.values()]

    def get_data(self, form_name):
        if form_name in self._forms:
            return self._forms[form_name]
        for form in self._forms.values():
            for value in form.transliterations:
                if form_name in value or value in form_name:
                    return form
        return None

    def get_forms(self, audio_track):
        matches = []
        title_lower = audio_track.title.lower()
        album_lower = audio_track.album.lower() if audio_track.album is not None else ""
        for form in self._forms.values():
            for value in form.transliterations:
                if value in title_lower or value in album_lower:
                    matches += [form.name]
        return matches

    def do_search(self, data_search):
        if not isinstance(data_search, FormsDataSearch):
            raise TypeError('Forms data search must be of type FormsDataSearch')
        if not data_search.is_valid():
            logger.warning('Invalid search query')
            return data_search

        full_results = False
        for form in self._forms.values():
            if data_search.test(form) is None:
                full_results = True
                break

        data_search.sort_results_by_transliterations() # The forms with the most transliterations are probably the most well-known

        if not full_results:
            for form in self._forms.values():
                if not form in data_search.results and \
                        data_search.test(form, strict=False) is None:
                    break

        return data_search


forms_data = FormsData()

