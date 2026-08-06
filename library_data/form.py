import json
import re

from utils.db import get_connection, delim_to_list, list_to_delim
from utils.logging_setup import get_logger
from utils.translations import I18N

logger = get_logger(__name__)
_ = I18N._


class Form:
    def __init__(self, name, transliterations=[], notes={}):
        self.name = name
        self.transliterations = transliterations if len(transliterations) > 0 else ([name] if name else [])
        self.notes = notes if notes is not None else {}

    def new_note(self, key="New Note", value=""):
        self.notes[key] = value

    def to_json(self):
        return {
            "name": self.name,
            "transliterations": list(self.transliterations),
            "notes": dict(self.notes),
        }

    def validate(self):
        """Validate form data and apply light fixes.

        Returns:
            tuple: (is_valid, error_message, fixes_applied)
        """
        fixes = {}

        if not self.name or not str(self.name).strip():
            return False, _("Form name cannot be empty"), fixes

        cleaned_name = " ".join(str(self.name).split())
        if cleaned_name != self.name:
            self.name = cleaned_name
            fixes["name"] = self.name

        cleaned = [t.strip() for t in self.transliterations if t and str(t).strip()]
        if cleaned != list(self.transliterations):
            self.transliterations = cleaned
            fixes["transliterations"] = self.transliterations[:]

        if not self.transliterations:
            self.transliterations = [self.name]
            fixes["transliterations"] = self.transliterations[:]
        elif self.name not in self.transliterations:
            self.transliterations.insert(0, self.name)
            fixes["transliterations"] = self.transliterations[:]
        elif self.transliterations[0] != self.name:
            self.transliterations = [self.name] + [
                t for t in self.transliterations if t != self.name
            ]
            fixes["transliterations"] = self.transliterations[:]

        if self.notes is None:
            self.notes = {}
            fixes["notes"] = {}

        return True, "", fixes

    @staticmethod
    def from_json(json_data):
        return Form(**json_data)


class FormsDataSearch:
    def __init__(self, form="", stored_results_count=0, max_results=200):
        self.form = form.lower()
        self.max_results = max_results
        self.stored_results_count = stored_results_count
        self.results = []

    def is_valid(self):
        if self.form is not None and self.form != "":
            return True
        return isinstance(self.max_results, int) and self.max_results > 0

    def set_stored_results_count(self):
        self.stored_results_count = len(self.results)
        logger.info(f"Stored count for {self}: {self.get_readable_stored_results_count()}")

    def get_readable_stored_results_count(self) -> str:
        if self.stored_results_count > self.max_results:
            results_str = f"{self.max_results}+"
        else:
            results_str = str(self.stored_results_count)
        return _("({0} results)").format(results_str)

    def get_title(self) -> str:
        if self.form:
            return _("Form: {0}").format(self.form)
        return _("All Forms")

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

        return False

    def sort_results_by_transliterations(self):
        self.results.sort(key=lambda form: len(form.transliterations), reverse=True)

    def get_results(self):
        return self.results

    def get_dict(self):
        return {
            "form": self.form,
            "stored_results_count": self.stored_results_count,
            "max_results": self.max_results,
        }

    def __eq__(self, other):
        if not isinstance(other, FormsDataSearch):
            return False
        return self.form == other.form

    def __hash__(self):
        return hash(self.form)


class FormsData:
    def __init__(self):
        self._forms = {}
        self._get_forms()

    def _get_forms(self):
        self._forms = {}
        rows = get_connection().execute(
            "SELECT name, transliterations, notes FROM forms"
        ).fetchall()
        for row in rows:
            self._forms[row["name"]] = Form(
                name=row["name"],
                transliterations=delim_to_list(row["transliterations"]),
                notes=json.loads(row["notes"] or "{}"),
            )

    def reload(self):
        self._get_forms()

    def get_form_names(self):
        return [form.name for form in self._forms.values()]

    def get_all_forms(self):
        return sorted(self._forms.values(), key=lambda f: f.name.lower())

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

    def save_form(self, form, original_name=None):
        """Persist a form to the database and update in-memory data.

        Args:
            form: Form instance to save.
            original_name: Previous primary key when renaming; None for new/same name.

        Returns:
            tuple: (success, error_message)
        """
        if not form or not form.name:
            return False, _("Invalid form data")

        is_valid, error_msg, _fixes = form.validate()
        if not is_valid:
            return False, error_msg

        old_name = original_name if original_name else form.name
        renaming = old_name != form.name

        try:
            conn = get_connection()
            if renaming:
                if form.name in self._forms and form.name != old_name:
                    return False, _("A form named \"{0}\" already exists").format(form.name)
                conn.execute("DELETE FROM forms WHERE name = ?", (old_name,))
                if old_name in self._forms:
                    self._forms.pop(old_name)

            conn.execute(
                """
                INSERT INTO forms (name, transliterations, notes)
                VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    transliterations = excluded.transliterations,
                    notes = excluded.notes
                """,
                (
                    form.name,
                    list_to_delim(form.transliterations),
                    json.dumps(form.notes or {}),
                ),
            )
            conn.commit()
            self._forms[form.name] = form
            return True, ""
        except Exception as e:
            error_msg = str(e)
            logger.error("Error saving form: %s", error_msg)
            try:
                get_connection().rollback()
            except Exception:
                pass
            return False, error_msg

    def delete_form(self, form):
        """Delete a form from the database and in-memory data.

        Returns:
            tuple: (success, error_message)
        """
        if not form or not form.name:
            return False, _("Invalid form data")

        try:
            conn = get_connection()
            cur = conn.execute("DELETE FROM forms WHERE name = ?", (form.name,))
            conn.commit()
            if cur.rowcount == 0 and form.name not in self._forms:
                return False, _("Form not found")
            self._forms.pop(form.name, None)
            return True, ""
        except Exception as e:
            error_msg = str(e)
            logger.error("Error deleting form: %s", error_msg)
            try:
                get_connection().rollback()
            except Exception:
                pass
            return False, error_msg

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

        data_search.set_stored_results_count()
        return data_search


forms_data = FormsData()
