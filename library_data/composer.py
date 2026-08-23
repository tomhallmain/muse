import datetime
import json
import os
import re
import unicodedata

from library_data.work import Work
from library_data.works_data import works_data
from utils.db import get_connection, delim_to_list, list_to_delim
from utils.name_ops import NameOps
from utils.logging_setup import get_logger
from utils.translations import I18N

logger = get_logger(__name__)

_ = I18N._

try:
    from anyascii import anyascii as _ascii_fold
except ImportError:
    def _ascii_fold(s):
        return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')

_en_dictionary = None

def _get_en_dictionary():
    global _en_dictionary
    if _en_dictionary is None:
        dict_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tts', 'dictionary_en.txt')
        try:
            with open(dict_path, 'r', encoding='utf-8') as f:
                _en_dictionary = {line.strip().lower() for line in f if line.strip()}
        except OSError:
            _en_dictionary = set()
    return _en_dictionary


class Composer:
    def __init__(self, id, name, indicators=[], start_date=-1, end_date=-1,
                 dates_are_lifespan=True, dates_uncertain=False, genres=[], works=[], notes={},
                 date_added=None):
        self.id = id
        self.name = name
        self.indicators = indicators if len(indicators) > 0 else [name]
        self.start_date = start_date
        self.end_date = end_date
        self.dates_are_lifespan = dates_are_lifespan
        self.dates_uncertain = dates_uncertain
        self.genres = genres
        # A fresh list rather than aliasing the argument, matching indicators/genres.
        self.works = list(works)
        self.notes = notes
        self.date_added = date_added

    def validate(self):
        """Validate the composer data and fix common issues.
        
        Returns:
            tuple: (bool, str, dict) - (is_valid, error_message, fixes_applied)
        """
        fixes = {}
        
        # Name validation and fixes
        if not self.name or self.name.strip() == "":
            return False, _("Composer name cannot be empty"), fixes
            
        # Fix whitespace issues
        if "\t" in self.name or "  " in self.name or self.name.startswith(" ") or self.name.endswith(" "):
            self.name = " ".join(self.name.split())  # This handles all whitespace cases
            fixes['name'] = str(self.name)
            
        # Indicators validation and fixes
        # First clean up any empty or whitespace-only indicators
        cleaned_indicators = [i.strip() for i in self.indicators if i.strip()]
        if cleaned_indicators != self.indicators:
            self.indicators = cleaned_indicators
            fixes['indicators'] = self.indicators[:]
            
        if not self.indicators:
            self.indicators = [self.name]
            fixes['indicators'] = self.indicators[:]
        elif self.name != self.indicators[0]:
            if self.name in self.indicators:
                self.indicators.remove(self.name)
            self.indicators.insert(0, self.name)
            fixes['indicators'] = self.indicators[:]
            
        # Date validation and fixes
        try:
            if self.start_date is not None:
                if type(self.start_date) == str and len(self.start_date) > 0:
                    if " " in self.start_date or "\t" in self.start_date:
                        self.start_date = "".join(self.start_date.split())
                        fixes['start_date'] = str(self.start_date)
                    while not self.start_date[0].isdigit():
                        self.start_date = self.start_date[1:]
                        fixes['start_date'] = str(self.start_date)
                    while not self.start_date[-1].isdigit():
                        self.start_date = self.start_date[:-1]
                        fixes['start_date'] = str(self.start_date)
                if self.start_date != -1:
                    self.start_date = int(self.start_date)
            if self.end_date is not None:
                if type(self.end_date) == str and len(self.end_date) > 0:
                    if " " in self.end_date or "\t" in self.end_date:
                        self.end_date = "".join(self.end_date.split())
                        fixes['end_date'] = str(self.end_date)
                    while not self.end_date[0].isdigit():
                        self.end_date = self.end_date[1:]
                        fixes['end_date'] = str(self.end_date)
                    while not self.end_date[-1].isdigit():
                        self.end_date = self.end_date[:-1]
                        fixes['end_date'] = str(self.end_date)
                if self.end_date != -1:
                    self.end_date = int(self.end_date)
        except (ValueError, TypeError):
            return False, _("Dates must be valid integers"), fixes
            
        current_year = datetime.datetime.now().year
        if self.start_date is not None and self.start_date > 0 and self.start_date > current_year:
            return False, _("Start date cannot be in the future"), fixes
        if self.end_date is not None and self.end_date > 0 and self.end_date > current_year:
            return False, _("End date cannot be in the future"), fixes
            
        # If both dates are provided, validate their relationship
        if self.start_date is not None and self.end_date is not None and self.start_date > 0 and self.end_date > 0:
            if self.start_date > self.end_date:
                return False, _("Start date cannot be after end date"), fixes
            
        return True, "", fixes

    def add_work(self, work):
        self.works.append(Work(work, self.name))

    def new_note(self, key="New Note", value=""):
        """Add a new note, ensuring the key is unique by adding a number suffix if needed.
        
        Args:
            key: The key for the note (default: "New Note")
            value: The value for the note (default: empty string)
        """
        base_key = key
        counter = 1
        while key in self.notes:
            key = f"{base_key} ({counter})"
            counter += 1
        self.notes[key] = value

    def to_json(self):
        """Convert the composer to a JSON-serializable dictionary.
        
        Returns:
            dict: A dictionary containing the composer's data in a format suitable for JSON serialization
        """
        return {
            'id': self.id,
            'name': self.name,
            'indicators': self.indicators,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'dates_are_lifespan': self.dates_are_lifespan,
            'dates_uncertain': self.dates_uncertain,
            'genres': self.genres,
            'works': [w.to_dict() for w in self.works],
            'notes': self.notes,
            'date_added': self.date_added.isoformat() if isinstance(self.date_added, datetime.datetime) else None,
        }

    @staticmethod
    def from_json(data):
        date_added = data.get('date_added')
        if isinstance(date_added, str):
            try:
                date_added = datetime.datetime.fromisoformat(date_added)
            except ValueError:
                date_added = None
        return Composer(
            id=data['id'],
            name=data['name'],
            indicators=data.get('indicators', []),
            start_date=data.get('start_date', -1),
            end_date=data.get('end_date', -1),
            dates_are_lifespan=data.get('dates_are_lifespan', True),
            dates_uncertain=data.get('dates_uncertain', False),
            genres=data.get('genres', []),
            works=[Work.from_dict(w) for w in data.get('works', []) if isinstance(w, dict)],
            notes=data.get('notes', {}),
            date_added=date_added,
        )



class ComposersDataSearch:
    def __init__(self, composer="", genre="", stored_results_count=0, max_results=200,
                 start_date_greater_than=-1, start_date_less_than=-1,
                 end_date_greater_than=-1, end_date_less_than=-1,
                 date_added_after=None, date_added_before=None):
        self.composer = composer.lower()
        self.genre = genre.lower()
        self.max_results = max_results
        self.stored_results_count = stored_results_count
        self.start_date_greater_than = start_date_greater_than
        self.start_date_less_than = start_date_less_than
        self.end_date_greater_than = end_date_greater_than
        self.end_date_less_than = end_date_less_than
        self.dates_specified = any([start_date_greater_than > -1, start_date_less_than > -1,
                                    end_date_greater_than > -1, end_date_less_than > -1])

        if isinstance(date_added_after, str):
            try:
                date_added_after = datetime.datetime.fromisoformat(date_added_after)
            except ValueError:
                date_added_after = None
        if isinstance(date_added_before, str):
            try:
                date_added_before = datetime.datetime.fromisoformat(date_added_before)
            except ValueError:
                date_added_before = None
        self.date_added_after = date_added_after
        self.date_added_before = date_added_before

        self.results = []

    def is_valid(self):
        # Check if any search criteria is provided
        for name in ["composer", "genre"]:
            field = getattr(self, name)
            if field is not None and field != "":
                return True
        if self.date_added_after is not None or self.date_added_before is not None:
            return True
        for name in ["start_date_greater_than", "start_date_less_than",
                    "end_date_greater_than", "end_date_less_than"]:
            field = getattr(self, name)
            if not isinstance(field, int):
                return False
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
        """Get a human-readable title describing the search criteria.
        
        Returns:
            str: A formatted title string
        """
        parts = []
        
        # Add name/genre criteria
        if self.composer:
            parts.append(_("Composer: {0}").format(self.composer))
        if self.genre:
            parts.append(_("Genre: {0}").format(self.genre))
            
        # Add date criteria
        date_parts = []
        if self.start_date_greater_than != -1:
            date_parts.append(_("Start after {0}").format(self.start_date_greater_than))
        if self.start_date_less_than != -1:
            date_parts.append(_("Start before {0}").format(self.start_date_less_than))
        if self.end_date_greater_than != -1:
            date_parts.append(_("End after {0}").format(self.end_date_greater_than))
        if self.end_date_less_than != -1:
            date_parts.append(_("End before {0}").format(self.end_date_less_than))
            
        if date_parts:
            parts.append(_("Dates: {0}").format(", ".join(date_parts)))

        if self.date_added_after is not None:
            parts.append(_("Added after {0}").format(self.date_added_after.strftime("%Y-%m-%d")))
        if self.date_added_before is not None:
            parts.append(_("Added before {0}").format(self.date_added_before.strftime("%Y-%m-%d")))

        # If no criteria specified, return default title
        if not parts:
            return _("All Composers")
            
        return " | ".join(parts)

    def test(self, composer, strict=True):
        if len(self.results) > self.max_results:
            return None

        if self.date_added_after is not None or self.date_added_before is not None:
            da = composer.date_added
            if da is None:
                return False
            if self.date_added_after is not None and da < self.date_added_after:
                return False
            if self.date_added_before is not None and da > self.date_added_before:
                return False
            if not self.dates_specified and len(self.composer) == 0 and len(self.genre) == 0:
                self.results.append(composer)
                return True

        # Check dates first since integer comparisons are fast
        if self.dates_specified:
            date_tests_passed = [self.start_date_greater_than == -1,
                                 self.start_date_less_than == -1,
                                 self.end_date_greater_than == -1,
                                 self.end_date_less_than == -1]

            if composer.start_date != -1 and composer.start_date is not None:
                if self.start_date_greater_than != -1:
                    if composer.start_date < self.start_date_greater_than:
                        return False
                    date_tests_passed[0] = True
                if self.start_date_less_than != -1:
                    if composer.start_date > self.start_date_less_than:
                        return False
                    date_tests_passed[1] = True

            if composer.end_date != -1 and composer.end_date is not None:
                if self.end_date_greater_than != -1:
                    if composer.end_date < self.end_date_greater_than:
                        return False
                    date_tests_passed[2] = True
                if self.end_date_less_than != -1:
                    if composer.end_date > self.end_date_less_than:
                        return False
                    date_tests_passed[3] = True
            else:
                # Composer could still be alive, or very old with little information
                date_tests_passed[2] = True
                date_tests_passed[3] = True
            
            if not all(date_tests_passed):
                print(f"Date tests failed: {date_tests_passed}")
                return False
            elif len(self.composer) == 0 and len(self.genre) == 0:
                print(f"Date tests passed: {date_tests_passed}")
                self.results.append(composer)
                return True

        # Test name/indicator matches. Leading boundary only: this is a search
        # box, so "bach" should still find "Bachschmid". re.escape because
        # indicators and queries contain regex metacharacters (`B.W.V.`, `Sr.`).
        if len(self.composer) > 0:
            pattern = re.compile(f"(^|\\W){re.escape(self.composer)}") if strict else ""
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

        # Test genre matches
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

    def get_dict(self):
        return {
            "composer": self.composer,
            "genre": self.genre,
            "stored_results_count": self.stored_results_count,
            "start_date_greater_than": self.start_date_greater_than,
            "start_date_less_than": self.start_date_less_than,
            "end_date_greater_than": self.end_date_greater_than,
            "end_date_less_than": self.end_date_less_than,
            "date_added_after": self.date_added_after.isoformat() if self.date_added_after else None,
            "date_added_before": self.date_added_before.isoformat() if self.date_added_before else None,
        }

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, ComposersDataSearch):
            return False
        return (self.composer == value.composer and
                self.genre == value.genre and
                self.start_date_greater_than == value.start_date_greater_than and
                self.start_date_less_than == value.start_date_less_than and
                self.end_date_greater_than == value.end_date_greater_than and
                self.end_date_less_than == value.end_date_less_than and
                self.date_added_after == value.date_added_after and
                self.date_added_before == value.date_added_before)

    def __hash__(self) -> int:
        return hash((self.composer, self.genre,
                    self.start_date_greater_than, self.start_date_less_than,
                    self.end_date_greater_than, self.end_date_less_than,
                    self.date_added_after, self.date_added_before))




class ComposersData:
    def __init__(self):
        # Composer data is loaded on first access rather than here. Building the
        # full set means a query plus several thousand object constructions, and
        # plenty of code paths never read composer data at all.
        self.__composers = None

    @property
    def _composers(self):
        if self.__composers is None:
            self._get_composers()
        return self.__composers

    def _get_composers(self):
        composers = {}
        rows = get_connection().execute(
            "SELECT id, name, indicators, start_date, end_date, "
            "dates_are_lifespan, dates_uncertain, genres, notes, date_added FROM composers"
        ).fetchall()
        needs_backfill = []
        for row in rows:
            composer = self._composer_from_row(row)
            if composer.date_added is None:
                needs_backfill.append(composer)
            composers[composer.name] = composer
        self.__composers = composers
        if needs_backfill:
            now = datetime.datetime.now()
            for composer in needs_backfill:
                composer.date_added = now
            self._persist_composers(needs_backfill)
            logger.info("Backfilled date_added for %d composer(s) with no recorded value", len(needs_backfill))

    @staticmethod
    def _composer_from_row(row):
        date_added = row["date_added"]
        if isinstance(date_added, str):
            try:
                date_added = datetime.datetime.fromisoformat(date_added)
            except ValueError:
                date_added = None
        return Composer(
            id=row["id"],
            name=row["name"],
            indicators=delim_to_list(row["indicators"]),
            start_date=row["start_date"] if row["start_date"] is not None else -1,
            end_date=row["end_date"] if row["end_date"] is not None else -1,
            dates_are_lifespan=bool(row["dates_are_lifespan"]),
            dates_uncertain=bool(row["dates_uncertain"]),
            genres=delim_to_list(row["genres"]),
            works=works_data.get_works_for_composer(row["id"]),
            notes=json.loads(row["notes"] or "{}"),
            date_added=date_added,
        )

    def reload(self):
        self.__composers = None

    def _get_next_available_id(self):
        """Find the next available ID in the composers collection.
        
        Returns:
            int: The next available ID
        """
        max_id = 0
        for comp in self._composers.values():
            if comp.id is not None and comp.id > max_id:
                max_id = comp.id
        return max_id + 1

    def _assign_next_id(self, composer):
        """Assign the next available ID to a composer if they don't have one.
        
        Args:
            composer: The Composer object to assign an ID to
            
        Returns:
            None
        """
        if composer.id is None:
            composer.id = self._get_next_available_id()

    # name is the identity here; id is a surrogate no other table references.
    # id is therefore never updated on conflict -- the stored row keeps its own,
    # so an incoming record carrying an id another row already holds cannot fail
    # the primary-key constraint. mbid is absent for the same reason in reverse:
    # nothing populates it yet, so leaving it out preserves any external value.
    _UPSERT_SQL = """
        INSERT INTO composers (id, name, indicators, start_date, end_date,
            dates_are_lifespan, dates_uncertain, genres, notes, date_added)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            indicators = excluded.indicators,
            start_date = excluded.start_date,
            end_date = excluded.end_date,
            dates_are_lifespan = excluded.dates_are_lifespan,
            dates_uncertain = excluded.dates_uncertain,
            genres = excluded.genres,
            notes = excluded.notes,
            date_added = excluded.date_added
    """

    @staticmethod
    def _composer_to_row_params(composer):
        date_added = composer.date_added
        date_added_str = date_added.isoformat() if isinstance(date_added, datetime.datetime) else date_added
        return (
            composer.id,
            composer.name,
            list_to_delim(composer.indicators),
            composer.start_date,
            composer.end_date,
            int(bool(composer.dates_are_lifespan)),
            int(bool(composer.dates_uncertain)),
            list_to_delim(composer.genres),
            json.dumps(composer.notes or {}),
            date_added_str,
        )

    def _persist_composers(self, composers):
        """Upsert one or more composers into the DB in a single transaction.

        Returns:
            tuple: (bool, str) - (success, error_message)
        """
        try:
            conn = get_connection()
            conn.executemany(
                ComposersData._UPSERT_SQL,
                [ComposersData._composer_to_row_params(c) for c in composers],
            )
            conn.commit()
            return True, ""
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error saving composers: {error_msg}")
            try:
                get_connection().rollback()
            except Exception:
                pass
            return False, error_msg

    def save_composer(self, composer):
        """Persist a composer to the database and update in-memory data.

        Args:
            composer: The Composer object to save

        Returns:
            tuple: (bool, str) - (success, error_message)
        """
        if not composer or not composer.name:
            return False, _("Invalid composer data")

        self._assign_next_id(composer)
        if composer.date_added is None:
            composer.date_added = datetime.datetime.now()

        success, error_msg = self._persist_composers([composer])
        if not success:
            return False, error_msg

        if composer.works:
            works_data.save_works(composer.id, composer.works)

        self._composers[composer.name] = composer
        return True, ""

    def add_composer_indicators(self, composer_name, indicators):
        """Add one or more indicators to an existing composer if not already present, then save.

        Returns:
            tuple: (bool, str) - (success, error_message)
        """
        composer = self._composers.get(composer_name)
        if composer is None:
            return False, _("Composer not found")
        to_add = [ind for ind in indicators if ind not in composer.indicators]
        if not to_add:
            return True, ""
        composer.indicators.extend(to_add)
        return self.save_composer(composer)

    def delete_composer(self, composer):
        """Delete a composer from the database and in-memory data.

        Args:
            composer: The Composer object to delete

        Returns:
            tuple: (bool, str) - (success, error_message)
        """
        if not composer or not composer.name:
            return False, _("Invalid composer data")

        try:
            conn = get_connection()
            cur = conn.execute("DELETE FROM composers WHERE name = ?", (composer.name,))
            conn.commit()
            if cur.rowcount == 0 and composer.name not in self._composers:
                return False, _("Composer not found")
            self._composers.pop(composer.name, None)
            works_data.reload()  # composer.id's works were cascade-deleted with the row
            return True, ""
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error deleting composer: {error_msg}")
            try:
                get_connection().rollback()
            except Exception:
                pass
            return False, error_msg

    def get_composer_names(self):
        return [composer.name for composer in self._composers.values()]

    def get_all_composers(self):
        return sorted(self._composers.values(), key=lambda c: NameOps.get_full_name_sort_key(c.name))

    def get_data(self, composer_name):
        if composer_name in self._composers:
            return self._composers[composer_name]
        for composer in self._composers.values():
            for value in composer.indicators:
                if composer_name in value or value in composer_name:
                    return composer
        return None

    def get_composers(self, audio_track):
        # Indicators must land on word boundaries: a plain substring test attaches
        # "Bach" to Erbach and Bachschmid, and "Barth" to Bartholomäus. The `in`
        # test gates the boundary check because this runs for every indicator
        # against every track, and a miss then costs one C-level scan as before.
        on_boundary = NameOps.contains_on_word_boundary
        title = audio_track.title
        album = audio_track.album
        artist = audio_track.artist
        track_composer = audio_track.composer
        matches = []
        for composer in self._composers.values():
            for value in composer.indicators:
                if (value in title and on_boundary(title, value)) or \
                        (album is not None and value in album and on_boundary(album, value)) or \
                        (artist is not None and value in artist and on_boundary(artist, value)):
                    matches += [composer.name]
                    break
                elif track_composer is not None and value in track_composer \
                        and on_boundary(track_composer, value):
                    logger.info("Found composer match on " + audio_track.filepath)
                    matches += [composer.name]
                    break
        return matches

    def do_search(self, data_search):
        if not isinstance(data_search, ComposersDataSearch):
            raise TypeError('Composers data search must be of type ComposersDataSearch')
        if not data_search.is_valid():
            logger.warning('Invalid search query')
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

        data_search.set_stored_results_count()
        return data_search

    @staticmethod
    def _generate_import_indicators(name):
        indicators = [name]

        folded_name = _ascii_fold(name)
        if folded_name != name and folded_name not in indicators:
            indicators.append(folded_name)

        tokens = name.split()
        last_word = tokens[-1]

        # If last token is a name appendix (Jr., Sr., Roman numerals, etc.),
        # add a "RealLastName Appendix" combined indicator and use the real last name
        # for quality-filtered standalone indicator generation.
        if last_word in NameOps.probable_name_appendices and len(tokens) >= 2:
            real_last_word = tokens[-2]
            last_name = NameOps.get_capitalized_part_of_last_name(real_last_word)
            combined = f"{real_last_word} {last_word}"
            if combined not in indicators:
                indicators.append(combined)
                folded_combined = _ascii_fold(combined)
                if folded_combined != combined and folded_combined not in indicators:
                    indicators.append(folded_combined)
        else:
            last_name = NameOps.get_capitalized_part_of_last_name(last_word)

        # Add standalone last-name indicator only if it passes quality filters:
        # must be longer than 4 characters and not a common English word.
        if last_name and len(last_name) > 4:
            en_dict = _get_en_dictionary()
            if last_name.lower() not in en_dict:
                if last_name not in indicators:
                    indicators.append(last_name)
                folded_last = _ascii_fold(last_name)
                if folded_last != last_name and folded_last not in indicators:
                    indicators.append(folded_last)

        return indicators

    _IMPORT_AUTO_MERGE_THRESHOLD = 0.92
    _IMPORT_REVIEW_THRESHOLD = 0.75

    def _find_similar_composer(self, name):
        """Return (best_matching_Composer, similarity_ratio) by folded last-name pre-filter."""
        from difflib import SequenceMatcher
        last_key = _ascii_fold(name.split()[-1]).lower()
        folded_name = _ascii_fold(name).lower()

        candidates = [
            c for c in self._composers.values()
            if _ascii_fold(c.name.split()[-1]).lower() == last_key
        ]
        best_match = None
        best_ratio = 0.0
        for candidate in candidates:
            ratio = SequenceMatcher(None, folded_name, _ascii_fold(candidate.name).lower()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = candidate
        return best_match, best_ratio

    def _find_existing_composer(self, name):
        if name in self._composers:
            return self._composers[name]

        folded = _ascii_fold(name)
        if folded != name and folded in self._composers:
            return self._composers[folded]

        name_lower = name.lower()
        folded_lower = folded.lower()
        for composer in self._composers.values():
            for indicator in composer.indicators:
                ind_lower = indicator.lower()
                if ind_lower == name_lower or (folded != name and ind_lower == folded_lower):
                    return composer
        return None

    def _check_duplicate_indicators(self):
        seen = {}  # lowercase -> (original_indicator, composer_name)
        duplicates = {}  # original_indicator -> set of composer names
        for name, composer in self._composers.items():
            for indicator in composer.indicators:
                key = indicator.lower()
                if key in seen:
                    orig_indicator, other_name = seen[key]
                    if other_name != name:
                        if orig_indicator not in duplicates:
                            duplicates[orig_indicator] = {other_name}
                        duplicates[orig_indicator].add(name)
                else:
                    seen[key] = (indicator, name)
        return duplicates

    def bulk_import_composers(self, names):
        clean_names = [name.strip() for name in names if name.strip()]

        added = []
        skipped = []       # exact indicator match → already in library
        auto_merged = []   # similarity >= AUTO_MERGE_THRESHOLD → treated as existing
        needs_review = []  # REVIEW_THRESHOLD <= similarity < AUTO_MERGE_THRESHOLD
        modified_existing = []  # existing composers whose indicators grew via auto-merge
        import_time = datetime.datetime.now()

        for name in clean_names:
            existing = self._find_existing_composer(name)
            if existing is not None:
                skipped.append((name, existing.name))
                continue

            best_match, ratio = self._find_similar_composer(name)

            def _try_auto_merge(match, import_name):
                auto_merged.append((import_name, match.name, ratio))
                if import_name not in match.indicators:
                    match.indicators.append(import_name)
                    if match not in modified_existing:
                        modified_existing.append(match)

            if best_match is not None and ratio >= ComposersData._IMPORT_AUTO_MERGE_THRESHOLD:
                _try_auto_merge(best_match, name)
                continue

            # Auto-merge when one name is FirstName LastName and the other adds middle
            # names — same first and last token, one name has exactly 2 tokens.
            if best_match is not None:
                import_tokens = name.split()
                existing_tokens = best_match.name.split()
                if (min(len(import_tokens), len(existing_tokens)) == 2
                        and _ascii_fold(import_tokens[0]).lower() == _ascii_fold(existing_tokens[0]).lower()
                        and _ascii_fold(import_tokens[-1]).lower() == _ascii_fold(existing_tokens[-1]).lower()):
                    _try_auto_merge(best_match, name)
                    continue

            if best_match is not None and ratio >= ComposersData._IMPORT_REVIEW_THRESHOLD:
                needs_review.append((name, best_match.name, ratio))
                continue

            indicators = ComposersData._generate_import_indicators(name)
            composer = Composer(
                id=None,
                name=name,
                indicators=indicators,
                start_date=-1,
                end_date=-1,
                dates_are_lifespan=True,
                dates_uncertain=False,
                genres=[],
                works=[],
                notes={},
                date_added=import_time,
            )
            self._assign_next_id(composer)
            self._composers[name] = composer
            added.append(composer)

        if added or modified_existing:
            success, error_msg = self._persist_composers(added + modified_existing)
            if not success:
                for composer in added:
                    self._composers.pop(composer.name, None)
                return {
                    'added': [], 'skipped': skipped, 'auto_merged': auto_merged,
                    'needs_review': needs_review, 'error': error_msg, 'quality_issues': {},
                }

        quality_issues = self._check_duplicate_indicators()
        return {
            'added': added,
            'skipped': skipped,
            'auto_merged': auto_merged,
            'needs_review': needs_review,
            'error': None,
            'quality_issues': quality_issues,
        }


composers_data = ComposersData()

