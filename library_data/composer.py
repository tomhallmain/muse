import datetime
import json
import os
import re
import unicodedata

from library_data.work import Work
from utils.config import config
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
        self.works = works
        self.notes = notes
        self.date_added = date_added

        for work in works:
            self.add_work(work)

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
        self.works.append(Work(work, self))

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
            'works': self.works,
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
            works=data.get('works', []),
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

        # Test name/indicator matches
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
        self._composers = {}
        self._get_composers()

    def _get_composers(self):
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(config.composers_file))
        with open(config.composers_file, 'r', encoding="utf-8") as f:
            composers = json.load(f)
        needs_migration = False
        for name, composer_data in composers.items():
            composer = Composer.from_json(composer_data)
            if composer.date_added is None:
                composer.date_added = mtime
                needs_migration = True
            self._composers[name] = composer
        if needs_migration:
            self._write_sorted_composers_to_file()
            logger.info("Stored date_added for composer data where missing")

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

    def _write_sorted_composers_to_file(self):
        """Write the composers dictionary to file in sorted order.
        
        Returns:
            tuple: (bool, str) - (success, error_message)
        """
        try:
            # Convert composers to JSON format and sort by name
            composers_json = {}
            sorted_composers = sorted(self._composers.items(), 
                                   key=lambda x: NameOps.get_name_sort_key(x[0]))
            for name, comp in sorted_composers:
                composers_json[name] = comp.to_json()
            
            # Write to file
            with open(config.composers_file, 'w', encoding="utf-8") as f:
                json.dump(composers_json, f, indent=4, ensure_ascii=True)
            return True, ""
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error writing composers file: {error_msg}")
            return False, error_msg

    def save_composer(self, composer):
        """Save a composer to the JSON file.
        
        Args:
            composer: The Composer object to save
            
        Returns:
            tuple: (bool, str) - (success, error_message)
        """
        if not composer or not composer.name:
            return False, _("Invalid composer data")
            
        # Create backup of current file
        backup_file = config.composers_file + '.bak'
        try:
            import shutil
            shutil.copy2(config.composers_file, backup_file)
            
            # Assign ID and date_added if needed (new composer)
            self._assign_next_id(composer)
            if composer.date_added is None:
                composer.date_added = datetime.datetime.now()

            # Update in-memory data
            self._composers[composer.name] = composer
            
            # Write sorted composers to file
            success, error_msg = self._write_sorted_composers_to_file()
            if not success:
                raise Exception(error_msg)
                
            # Remove backup if successful
            import os
            os.remove(backup_file)
            return True, ""
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error saving composer: {error_msg}")
            # Restore from backup if it exists
            if os.path.exists(backup_file):
                shutil.copy2(backup_file, config.composers_file)
                os.remove(backup_file)
            return False, error_msg

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
        """Delete a composer from the JSON file.
        
        Args:
            composer: The Composer object to delete
            
        Returns:
            tuple: (bool, str) - (success, error_message)
        """
        if not composer or not composer.name:
            return False, _("Invalid composer data")
            
        # Create backup of current file
        backup_file = config.composers_file + '.bak'
        try:
            import shutil
            shutil.copy2(config.composers_file, backup_file)
            
            # Remove from in-memory data
            if composer.name in self._composers:
                self._composers.pop(composer.name)
            else:
                return False, _("Composer not found")
            
            # Write sorted composers to file
            success, error_msg = self._write_sorted_composers_to_file()
            if not success:
                raise Exception(error_msg)
                
            # Remove backup if successful
            os.remove(backup_file)
            return True, ""
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error deleting composer: {error_msg}")
            # Restore from backup if it exists
            if os.path.exists(backup_file):
                shutil.copy2(backup_file, config.composers_file)
                os.remove(backup_file)
            return False, error_msg

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

        if added or auto_merged:
            import shutil
            backup_file = config.composers_file + '.bak'
            try:
                shutil.copy2(config.composers_file, backup_file)
                success, error_msg = self._write_sorted_composers_to_file()
                if not success:
                    raise Exception(error_msg)
                os.remove(backup_file)
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error in bulk import: {error_msg}")
                if os.path.exists(backup_file):
                    shutil.copy2(backup_file, config.composers_file)
                    os.remove(backup_file)
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

