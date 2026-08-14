
import datetime
import json
import re

from utils.db import get_connection, delim_to_list, list_to_delim
from utils.logging_setup import get_logger
from utils.translations import I18N

logger = get_logger(__name__)
_ = I18N._


class Artist:
    def __init__(self, id, name, indicators=[], start_date=-1, end_date=-1,
                 dates_are_lifespan=True, dates_uncertain=False, genres=[], albums=[], notes={}):
        self.id = id
        self.name = name
        self.indicators = indicators if len(indicators) > 0 else ([name] if name else [])
        self.start_date = start_date
        self.end_date = end_date
        self.dates_are_lifespan = dates_are_lifespan
        self.dates_uncertain = dates_uncertain
        self.genres = genres
        self.albums = albums
        self.notes = notes if notes is not None else {}

    def new_note(self, key="New Note", value=""):
        self.notes[key] = value

    def to_json(self):
        return {
            "id": self.id,
            "name": self.name,
            "indicators": list(self.indicators),
            "start_date": self.start_date,
            "end_date": self.end_date,
            "dates_are_lifespan": self.dates_are_lifespan,
            "dates_uncertain": self.dates_uncertain,
            "genres": list(self.genres),
            "albums": list(self.albums),
            "notes": dict(self.notes),
        }

    def validate(self):
        """Validate artist data and apply light fixes.

        Returns:
            tuple: (is_valid, error_message, fixes_applied)
        """
        fixes = {}

        if not self.name or not str(self.name).strip():
            return False, _("Artist name cannot be empty"), fixes

        cleaned_name = " ".join(str(self.name).split())
        if cleaned_name != self.name:
            self.name = cleaned_name
            fixes["name"] = self.name

        cleaned = [i.strip() for i in self.indicators if i and str(i).strip()]
        if cleaned != list(self.indicators):
            self.indicators = cleaned
            fixes["indicators"] = self.indicators[:]

        if not self.indicators:
            self.indicators = [self.name]
            fixes["indicators"] = self.indicators[:]
        elif self.name not in self.indicators:
            self.indicators.insert(0, self.name)
            fixes["indicators"] = self.indicators[:]
        elif self.indicators[0] != self.name:
            self.indicators = [self.name] + [
                i for i in self.indicators if i != self.name
            ]
            fixes["indicators"] = self.indicators[:]

        try:
            self.start_date = int(self.start_date) if self.start_date not in (None, "") else -1
            self.end_date = int(self.end_date) if self.end_date not in (None, "") else -1
        except (ValueError, TypeError):
            return False, _("Dates must be valid integers"), fixes

        current_year = datetime.datetime.now().year
        if self.start_date > 0 and self.start_date > current_year:
            return False, _("Start date cannot be in the future"), fixes
        if self.end_date > 0 and self.end_date > current_year:
            return False, _("End date cannot be in the future"), fixes
        if self.start_date > 0 and self.end_date > 0 and self.start_date > self.end_date:
            return False, _("Start date cannot be after end date"), fixes

        if self.notes is None:
            self.notes = {}
            fixes["notes"] = {}

        return True, "", fixes

    @staticmethod
    def from_json(json):
        return Artist(**json)



class ArtistsDataSearch:
    def __init__(self, artist="", genre="", stored_results_count=0, max_results=200):
        self.artist = artist.lower()
        self.genre = genre.lower()
        self.max_results = max_results
        self.stored_results_count = stored_results_count
        self.results = []

    def is_valid(self):
        for name in ["artist", "genre"]:
            field = getattr(self, name)
            if field is not None and field.strip()!= "":
                #print(f"{name} - \"{field}\"")
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
        if self.artist and self.genre:
            return _("Artist: {0}, Genre: {1}").format(self.artist, self.genre)
        if self.artist:
            return _("Artist: {0}").format(self.artist)
        if self.genre:
            return _("Genre: {0}").format(self.genre)
        return _("All Artists")

    def test(self, artist, strict=True):
        if len(self.results) > self.max_results:
            return None
        if len(self.artist) > 0:
            pattern = re.compile(f"(^|\\W){self.artist}") if strict else ""
            for indicator in artist.indicators:
                indicator_lower = indicator.lower()
                if strict:
                    if indicator_lower == self.artist or re.search(pattern, indicator_lower):
                        self.results.append(artist)
                        return True
                else:
                    if self.artist in indicator_lower:
                        self.results.append(artist)
                        return True
        if len(self.genre) > 0 and strict:
            for genre in artist.genres:
                genre_lower = genre.lower()
                if genre_lower == self.genre or self.genre in genre_lower:
                    self.results.append(artist)
                    return True
        return False

    def sort_results_by_indicators(self):
        self.results.sort(key=lambda artist: len(artist.indicators), reverse=True)

    def get_results(self):
        return self.results

    def get_dict(self):
        return {
            "artist": self.artist,
            "genre": self.genre,
            "stored_results_count": self.stored_results_count,
            "max_results": self.max_results,
        }

    def __eq__(self, other):
        if not isinstance(other, ArtistsDataSearch):
            return False
        return self.artist == other.artist and self.genre == other.genre

    def __hash__(self):
        return hash((self.artist, self.genre))



class ArtistsData:
    def __init__(self):
        self._artists = {}
        self._get_artists()

    def _get_artists(self):
        self._artists = {}
        rows = get_connection().execute(
            "SELECT id, name, indicators, start_date, end_date, "
            "dates_are_lifespan, dates_uncertain, genres, albums, notes FROM artists"
        ).fetchall()
        for row in rows:
            self._artists[row["name"]] = Artist(
                id=row["id"],
                name=row["name"],
                indicators=delim_to_list(row["indicators"]),
                start_date=row["start_date"] if row["start_date"] is not None else -1,
                end_date=row["end_date"] if row["end_date"] is not None else -1,
                dates_are_lifespan=bool(row["dates_are_lifespan"]),
                dates_uncertain=bool(row["dates_uncertain"]),
                genres=delim_to_list(row["genres"]),
                albums=delim_to_list(row["albums"]),
                notes=json.loads(row["notes"] or "{}"),
            )

    def reload(self):
        self._get_artists()

    def get_artist_names(self):
        return [artist.name for artist in self._artists.values()]

    def get_all_artists(self):
        return sorted(self._artists.values(), key=lambda a: a.name.lower())

    def get_data(self, artist_name):
        if artist_name in self._artists:
            return self._artists[artist_name]
        for artist in self._artists.values():
            for value in artist.indicators:
                if artist_name in value or value in artist_name:
                    return artist
        return None

    def get_artists(self, audio_track):
        matches = []
        for artist in self._artists.values():
            for value in artist.indicators:
                if value in audio_track.title or \
                        (audio_track.album is not None and value in audio_track.album) or \
                        (audio_track.artist is not None and value in audio_track.artist):
                    matches += [artist.name]
                    break
                elif audio_track.artist is not None and value in audio_track.artist:
                    logger.info("Found artist match on " + audio_track.filepath)
                    matches += [artist.name]
                    break
        return matches

    def _get_next_available_id(self):
        max_id = 0
        for artist in self._artists.values():
            if artist.id is not None and artist.id > max_id:
                max_id = artist.id
        return max_id + 1

    def _assign_next_id(self, artist):
        if artist.id is None:
            artist.id = self._get_next_available_id()

    def save_artist(self, artist, original_name=None):
        """Persist an artist to the database and update in-memory data.

        Args:
            artist: Artist instance to save.
            original_name: Previous primary key when renaming; None for new/same name.

        Returns:
            tuple: (success, error_message)
        """
        if not artist or not artist.name:
            return False, _("Invalid artist data")

        is_valid, error_msg, _fixes = artist.validate()
        if not is_valid:
            return False, error_msg

        self._assign_next_id(artist)

        old_name = original_name if original_name else artist.name
        renaming = old_name != artist.name

        try:
            conn = get_connection()
            if renaming:
                if artist.name in self._artists and artist.name != old_name:
                    return False, _("An artist named \"{0}\" already exists").format(artist.name)
                conn.execute("DELETE FROM artists WHERE name = ?", (old_name,))
                if old_name in self._artists:
                    self._artists.pop(old_name)

            conn.execute(
                """
                INSERT INTO artists (id, name, indicators, start_date, end_date,
                    dates_are_lifespan, dates_uncertain, genres, albums, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    id = excluded.id,
                    indicators = excluded.indicators,
                    start_date = excluded.start_date,
                    end_date = excluded.end_date,
                    dates_are_lifespan = excluded.dates_are_lifespan,
                    dates_uncertain = excluded.dates_uncertain,
                    genres = excluded.genres,
                    albums = excluded.albums,
                    notes = excluded.notes
                """,
                (
                    artist.id,
                    artist.name,
                    list_to_delim(artist.indicators),
                    artist.start_date if artist.start_date not in (None, -1) else None,
                    artist.end_date if artist.end_date not in (None, -1) else None,
                    int(bool(artist.dates_are_lifespan)),
                    int(bool(artist.dates_uncertain)),
                    list_to_delim(artist.genres),
                    list_to_delim(artist.albums),
                    json.dumps(artist.notes or {}),
                ),
            )
            conn.commit()
            self._artists[artist.name] = artist
            return True, ""
        except Exception as e:
            error_msg = str(e)
            logger.error("Error saving artist: %s", error_msg)
            try:
                get_connection().rollback()
            except Exception:
                pass
            return False, error_msg

    def delete_artist(self, artist):
        """Delete an artist from the database and in-memory data.

        Returns:
            tuple: (success, error_message)
        """
        if not artist or not artist.name:
            return False, _("Invalid artist data")

        try:
            conn = get_connection()
            cur = conn.execute("DELETE FROM artists WHERE name = ?", (artist.name,))
            conn.commit()
            if cur.rowcount == 0 and artist.name not in self._artists:
                return False, _("Artist not found")
            self._artists.pop(artist.name, None)
            return True, ""
        except Exception as e:
            error_msg = str(e)
            logger.error("Error deleting artist: %s", error_msg)
            try:
                get_connection().rollback()
            except Exception:
                pass
            return False, error_msg

    def do_search(self, data_search):
        if not isinstance(data_search, ArtistsDataSearch):
            raise TypeError('Artists data search must be of type ArtistsDataSearch')
        if not data_search.is_valid():
            logger.warning('Invalid search query')
            return data_search

        full_results = False
        for artist in self._artists.values():
            if data_search.test(artist) is None:
                full_results = True
                break

        data_search.sort_results_by_indicators() # The artists with the most indicators are probably the most well-known

        if not full_results:
            for artist in self._artists.values():
                if not artist in data_search.results and \
                        data_search.test(artist, strict=False) is None:
                    break

        data_search.set_stored_results_count()
        return data_search


artists_data = ArtistsData()

