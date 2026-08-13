
import json
import re

from utils.db import get_connection, delim_to_list, list_to_delim
from utils.logging_setup import get_logger
from utils.translations import I18N

logger = get_logger(__name__)
_ = I18N._

class Genre:
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
        """Validate genre data and apply light fixes.

        Returns:
            tuple: (is_valid, error_message, fixes_applied)
        """
        fixes = {}

        if not self.name or not str(self.name).strip():
            return False, _("Genre name cannot be empty"), fixes

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
        return Genre(**json)



class GenresDataSearch:
    def __init__(self, genre="", stored_results_count=0, max_results=200):
        self.genre = genre.lower()
        self.max_results = max_results
        self.stored_results_count = stored_results_count
        self.results = []

    def is_valid(self):
        if self.genre is not None and self.genre != "":
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
        if self.genre:
            return _("Genre: {0}").format(self.genre)
        return _("All Genres")

    def test(self, genre, strict=True):
        if len(self.results) > self.max_results:
            return None

        if len(self.genre) > 0:
            pattern = re.compile(f"(^|\\W){self.genre}") if strict else ""
            for indicator in genre.transliterations:
                indicator_lower = indicator.lower()
                if strict:
                    if indicator_lower == self.genre or re.search(pattern, indicator_lower):
                        self.results.append(genre)
                        return True
                else:
                    if self.genre in indicator_lower:
                        self.results.append(genre)
                        return True

        return False

    def sort_results_by_transliterations(self):
        self.results.sort(key=lambda genre: len(genre.transliterations), reverse=True)

    def get_results(self):
        return self.results

    def get_dict(self):
        return {
            "genre": self.genre,
            "stored_results_count": self.stored_results_count,
            "max_results": self.max_results,
        }

    def __eq__(self, other):
        if not isinstance(other, GenresDataSearch):
            return False
        return self.genre == other.genre

    def __hash__(self):
        return hash(self.genre)



class GenresData:
    def __init__(self):
        self._genres = {}
        self._get_genres()

    def _get_genres(self):
        self._genres = {}
        rows = get_connection().execute(
            "SELECT name, transliterations, notes FROM genres"
        ).fetchall()
        for row in rows:
            self._genres[row["name"]] = Genre(
                name=row["name"],
                transliterations=delim_to_list(row["transliterations"]),
                notes=json.loads(row["notes"] or "{}"),
            )

    def reload(self):
        self._get_genres()

    def get_genre_names(self):
        return [genre.name for genre in self._genres.values()]

    def get_all_genres(self):
        return sorted(self._genres.values(), key=lambda g: g.name.lower())

    def get_data(self, genre_name):
        if genre_name in self._genres:
            return self._genres[genre_name]
        for genre in self._genres.values():
            for value in genre.transliterations:
                if genre_name in value or value in genre_name:
                    return genre
        return None

    def get_genres(self, audio_track):
        matches = []
        title_lower = audio_track.title.lower()
        album_lower = audio_track.album.lower() if audio_track.album is not None else ""
        for genre in self._genres.values():
            for value in genre.transliterations:
                if value in title_lower or value in album_lower:
                    matches += [genre.name]
        return matches

    def save_genre(self, genre, original_name=None):
        """Persist a genre to the database and update in-memory data.

        Args:
            genre: Genre instance to save.
            original_name: Previous primary key when renaming; None for new/same name.

        Returns:
            tuple: (success, error_message)
        """
        if not genre or not genre.name:
            return False, _("Invalid genre data")

        is_valid, error_msg, _fixes = genre.validate()
        if not is_valid:
            return False, error_msg

        old_name = original_name if original_name else genre.name
        renaming = old_name != genre.name

        try:
            conn = get_connection()
            if renaming:
                if genre.name in self._genres and genre.name != old_name:
                    return False, _("A genre named \"{0}\" already exists").format(genre.name)
                conn.execute("DELETE FROM genres WHERE name = ?", (old_name,))
                if old_name in self._genres:
                    self._genres.pop(old_name)

            conn.execute(
                """
                INSERT INTO genres (name, transliterations, notes)
                VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    transliterations = excluded.transliterations,
                    notes = excluded.notes
                """,
                (
                    genre.name,
                    list_to_delim(genre.transliterations),
                    json.dumps(genre.notes or {}),
                ),
            )
            conn.commit()
            self._genres[genre.name] = genre
            return True, ""
        except Exception as e:
            error_msg = str(e)
            logger.error("Error saving genre: %s", error_msg)
            try:
                get_connection().rollback()
            except Exception:
                pass
            return False, error_msg

    def delete_genre(self, genre):
        """Delete a genre from the database and in-memory data.

        Returns:
            tuple: (success, error_message)
        """
        if not genre or not genre.name:
            return False, _("Invalid genre data")

        try:
            conn = get_connection()
            cur = conn.execute("DELETE FROM genres WHERE name = ?", (genre.name,))
            conn.commit()
            if cur.rowcount == 0 and genre.name not in self._genres:
                return False, _("Genre not found")
            self._genres.pop(genre.name, None)
            return True, ""
        except Exception as e:
            error_msg = str(e)
            logger.error("Error deleting genre: %s", error_msg)
            try:
                get_connection().rollback()
            except Exception:
                pass
            return False, error_msg

    def do_search(self, data_search):
        if not isinstance(data_search, GenresDataSearch):
            raise TypeError('Genres data search must be of type GenresDataSearch')
        if not data_search.is_valid():
            logger.warning('Invalid search query')
            return data_search

        full_results = False
        for genre in self._genres.values():
            if data_search.test(genre) is None:
                full_results = True
                break

        data_search.sort_results_by_transliterations() # The genres with the most transliterations are probably the most well-known

        if not full_results:
            for genre in self._genres.values():
                if not genre in data_search.results and \
                        data_search.test(genre, strict=False) is None:
                    break

        data_search.set_stored_results_count()
        return data_search


genre_data = GenresData()

