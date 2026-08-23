from typing import Optional


class Work:
    """A composition by a composer, e.g. from an IMSLP/Wikipedia work list.

    ``composer`` is the composer's name (a plain string), not a ``Composer``
    object -- a Composer is rebuilt fresh on every reload, so comparing by
    object identity would break equality across sessions.

    ``catalogue_number``/``date`` are free text and often absent -- the
    scraped sources are too inconsistent to always extract them.
    ``matched_track_filepath`` is a best-effort, cached library-track link;
    never assume it is populated.
    """

    def __init__(self, name: str, composer: str, date: Optional[str] = None,
                 catalogue_number: Optional[str] = None, source: Optional[str] = None,
                 matched_track_filepath: Optional[str] = None, id: Optional[int] = None):
        self.id = id
        self.name = name
        self.composer = composer
        self.date = date
        self.catalogue_number = catalogue_number
        self.source = source
        self.matched_track_filepath = matched_track_filepath

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, Work):
            return False
        return self.composer == value.composer and self.name == value.name

    def __hash__(self):
        return hash((self.composer, self.name))

    def __repr__(self) -> str:
        return f"Work({self.name!r}, {self.composer!r})"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "composer": self.composer,
            "date": self.date,
            "catalogue_number": self.catalogue_number,
            "source": self.source,
            "matched_track_filepath": self.matched_track_filepath,
        }

    @staticmethod
    def from_dict(data: dict) -> 'Work':
        return Work(
            name=data["name"],
            composer=data["composer"],
            date=data.get("date"),
            catalogue_number=data.get("catalogue_number"),
            source=data.get("source"),
            matched_track_filepath=data.get("matched_track_filepath"),
            id=data.get("id"),
        )
