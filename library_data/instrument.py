
import json
import re

from utils.db import get_connection, delim_to_list, list_to_delim
from utils.logging_setup import get_logger
from utils.translations import I18N

logger = get_logger(__name__)
_ = I18N._


class Instrument:
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
        """Validate instrument data and apply light fixes.

        Returns:
            tuple: (is_valid, error_message, fixes_applied)
        """
        fixes = {}

        if not self.name or not str(self.name).strip():
            return False, _("Instrument name cannot be empty"), fixes

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
    def from_json(json):
        return Instrument(**json)



class InstrumentsDataSearch:
    def __init__(self, instrument="", stored_results_count=0, max_results=200):
        self.instrument = instrument.lower()
        self.max_results = max_results
        self.stored_results_count = stored_results_count
        self.results = []

    def is_valid(self):
        if self.instrument is not None and self.instrument != "":
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
        if self.instrument:
            return _("Instrument: {0}").format(self.instrument)
        return _("All Instruments")

    def test(self, instrument, strict=True):
        if len(self.results) > self.max_results:
            return None

        if len(self.instrument) > 0:
            pattern = re.compile(f"(^|\\W){self.instrument}") if strict else ""
            for indicator in instrument.transliterations:
                indicator_lower = indicator.lower()
                if strict:
                    if indicator_lower == self.instrument or re.search(pattern, indicator_lower):
                        self.results.append(instrument)
                        return True
                else:
                    if self.instrument in indicator_lower:
                        self.results.append(instrument)
                        return True

        return False

    def sort_results_by_transliterations(self):
        self.results.sort(key=lambda instrument: len(instrument.transliterations), reverse=True)

    def get_results(self):
        return self.results

    def get_dict(self):
        return {
            "instrument": self.instrument,
            "stored_results_count": self.stored_results_count,
            "max_results": self.max_results,
        }

    def __eq__(self, other):
        if not isinstance(other, InstrumentsDataSearch):
            return False
        return self.instrument == other.instrument

    def __hash__(self):
        return hash(self.instrument)



class InstrumentsData:
    def __init__(self):
        self._instruments = {}
        self._get_instruments()

    def _get_instruments(self):
        self._instruments = {}
        rows = get_connection().execute(
            "SELECT name, transliterations, notes FROM instruments"
        ).fetchall()
        for row in rows:
            self._instruments[row["name"]] = Instrument(
                name=row["name"],
                transliterations=delim_to_list(row["transliterations"]),
                notes=json.loads(row["notes"] or "{}"),
            )

    def reload(self):
        self._get_instruments()

    def get_instrument_names(self):
        return [instrument.name for instrument in self._instruments.values()]

    def get_all_instruments(self):
        return sorted(self._instruments.values(), key=lambda i: i.name.lower())

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

    def save_instrument(self, instrument, original_name=None):
        """Persist an instrument to the database and update in-memory data.

        Args:
            instrument: Instrument instance to save.
            original_name: Previous primary key when renaming; None for new/same name.

        Returns:
            tuple: (success, error_message)
        """
        if not instrument or not instrument.name:
            return False, _("Invalid instrument data")

        is_valid, error_msg, _fixes = instrument.validate()
        if not is_valid:
            return False, error_msg

        old_name = original_name if original_name else instrument.name
        renaming = old_name != instrument.name

        try:
            conn = get_connection()
            if renaming:
                if instrument.name in self._instruments and instrument.name != old_name:
                    return False, _("An instrument named \"{0}\" already exists").format(instrument.name)
                conn.execute("DELETE FROM instruments WHERE name = ?", (old_name,))
                if old_name in self._instruments:
                    self._instruments.pop(old_name)

            conn.execute(
                """
                INSERT INTO instruments (name, transliterations, notes)
                VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    transliterations = excluded.transliterations,
                    notes = excluded.notes
                """,
                (
                    instrument.name,
                    list_to_delim(instrument.transliterations),
                    json.dumps(instrument.notes or {}),
                ),
            )
            conn.commit()
            self._instruments[instrument.name] = instrument
            return True, ""
        except Exception as e:
            error_msg = str(e)
            logger.error("Error saving instrument: %s", error_msg)
            try:
                get_connection().rollback()
            except Exception:
                pass
            return False, error_msg

    def delete_instrument(self, instrument):
        """Delete an instrument from the database and in-memory data.

        Returns:
            tuple: (success, error_message)
        """
        if not instrument or not instrument.name:
            return False, _("Invalid instrument data")

        try:
            conn = get_connection()
            cur = conn.execute("DELETE FROM instruments WHERE name = ?", (instrument.name,))
            conn.commit()
            if cur.rowcount == 0 and instrument.name not in self._instruments:
                return False, _("Instrument not found")
            self._instruments.pop(instrument.name, None)
            return True, ""
        except Exception as e:
            error_msg = str(e)
            logger.error("Error deleting instrument: %s", error_msg)
            try:
                get_connection().rollback()
            except Exception:
                pass
            return False, error_msg

    def do_search(self, data_search):
        if not isinstance(data_search, InstrumentsDataSearch):
            raise TypeError('Instruments data search must be of type InstrumentsDataSearch')
        if not data_search.is_valid():
            logger.warning('Invalid search query')
            return data_search

        full_results = False
        for instrument in self._instruments.values():
            if data_search.test(instrument) is None:
                full_results = True
                break

        data_search.sort_results_by_transliterations() # The instruments with the most transliterations are probably the most well-known

        if not full_results:
            for instrument in self._instruments.values():
                if not instrument in data_search.results and \
                        data_search.test(instrument, strict=False) is None:
                    break

        data_search.set_stored_results_count()
        return data_search


instruments_data = InstrumentsData()
