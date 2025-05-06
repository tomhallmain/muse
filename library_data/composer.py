import datetime
import json
import os
import re

from library_data.work import Work
from utils.config import config
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._


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
            'notes': self.notes
        }

    @staticmethod
    def from_json(json):
        return Composer(**json)



class ComposersDataSearch:
    def __init__(self, composer="", genre="", stored_results_count=0, max_results=200):
        self.composer = composer.lower()
        self.genre = genre.lower()
        self.max_results = max_results
        self.stored_results_count = stored_results_count

        self.results = []

    def is_valid(self):
        for name in ["composer", "genre"]:
            field = getattr(self, name)
            if field is not None and field.strip()!= "":
                #print(f"{name} - \"{field}\"")
                return True
        return isinstance(self.max_results, int) and self.max_results > 0

    def set_stored_results_count(self):
        self.stored_results_count = len(self.results)
        Utils.log(f"Stored count for {self}: {self.get_readable_stored_results_count()}")

    def get_readable_stored_results_count(self) -> str:
        if self.stored_results_count > self.max_results:
            results_str = f"{self.max_results}+"
        else:
            results_str = str(self.stored_results_count)
        return _("({0} results)").format(results_str)

    def test(self, composer, strict=True):
        if len(self.results) > self.max_results:
            return None
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
        }

    def __eq__(self, value: object) -> bool:
        return isinstance(value, ComposersDataSearch) and \
               self.composer == value.composer and \
               self.genre == value.genre

    def __hash__(self) -> int:
        return hash((self.composer, self.genre))




class ComposersData:
    def __init__(self):
        self._composers = {}
        self._get_composers()

    def _get_composers(self):
        with open(config.composers_file, 'r', encoding="utf-8") as f:
            composers = json.load(f)
        for name, composer in composers.items():
            self._composers[name] = Composer.from_json(composer)

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
            
            # Update in-memory data
            self._composers[composer.name] = composer
            
            # Convert composers to JSON format
            composers_json = {}
            for name, comp in self._composers.items():
                composers_json[name] = comp.to_json()
            
            # Write to file
            with open(config.composers_file, 'w', encoding="utf-8") as f:
                json.dump(composers_json, f, indent=4, ensure_ascii=False)
                
            # Remove backup if successful
            import os
            os.remove(backup_file)
            return True, ""
            
        except Exception as e:
            error_msg = str(e)
            Utils.log_red(f"Error saving composer: {error_msg}")
            # Restore from backup if it exists
            if os.path.exists(backup_file):
                shutil.copy2(backup_file, config.composers_file)
                os.remove(backup_file)
            return False, error_msg

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
            
            # Convert composers to JSON format
            composers_json = {}
            for name, comp in self._composers.items():
                composers_json[name] = comp.to_json()
            
            # Write to file
            with open(config.composers_file, 'w', encoding="utf-8") as f:
                json.dump(composers_json, f, indent=4, ensure_ascii=False)
                
            # Remove backup if successful
            os.remove(backup_file)
            return True, ""
            
        except Exception as e:
            error_msg = str(e)
            Utils.log_red(f"Error deleting composer: {error_msg}")
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
                    Utils.log("Found composer match on " + audio_track.filepath)
                    matches += [composer.name]
                    break
        return matches

    def do_search(self, data_search):
        if not isinstance(data_search, ComposersDataSearch):
            raise TypeError('Composers data search must be of type ComposersDataSearch')
        if not data_search.is_valid():
            Utils.log_yellow('Invalid search query')
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


composers_data = ComposersData()

