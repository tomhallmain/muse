import re
from typing import Optional, Set, Tuple

from utils.name_ops import NameOps

# A catalogue reference anywhere in free text: "BWV 1007", "Op. 24 No. 3",
# "K. 525", "KV 525", "Hob. XVI:52", "D. 960", "RV 269", "HWV 56", "WoO 59",
# with or without a space before the number. D needs two digits so a key such
# as "in D 2" is not read as one.
_CATALOGUE_SEARCH_RE = re.compile(
    r"\b(opus|op|bwv|kv|k|hob|woo|rv|hwv|d)(?![a-z])\.?\s*"
    r"((?:[ivxlc]+[:.]?\s*)?\d+[a-z]?)"
    r"(?:\s*,?\s*no\.?\s*(\d+))?",
    re.IGNORECASE,
)
_PREFIX_ALIASES = {"kv": "k", "opus": "op"}


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

    @staticmethod
    def catalogue_keys(text: Optional[str]) -> Set[Tuple[str, str, Optional[str]]]:
        """Catalogue references in text as (prefix, number, "No." part or None).

        Normalised so "KV 525" and "K. 525", or "Hob. XVI:52" and "hob xvi 52",
        give the same key.
        """
        keys = set()
        for match in _CATALOGUE_SEARCH_RE.finditer(text or ""):
            prefix = match.group(1).lower()
            prefix = _PREFIX_ALIASES.get(prefix, prefix)
            number = re.sub(r"[\s:.]+", " ", match.group(2).lower()).strip()
            if prefix == "d" and not re.search(r"\d{2}", number):
                continue
            keys.add((prefix, number, match.group(3)))
        return keys

    def matches_title(self, title: Optional[str]) -> bool:
        """Whether a track or broadcast title names this work.

        By catalogue number when both carry one: the same prefix and number,
        and the same "No." where both give one, so "Op. 10 No. 3" matches a
        work listed as "Op. 10". Otherwise by the work's whole name appearing
        in the title, for names long enough not to be generic ("Suite").
        """
        title_keys = Work.catalogue_keys(title)
        work_keys = Work.catalogue_keys(self.catalogue_number) | Work.catalogue_keys(self.name)
        if title_keys and work_keys:
            return any(
                t[0] == w[0] and t[1] == w[1] and (t[2] is None or w[2] is None or t[2] == w[2])
                for t in title_keys for w in work_keys
            )
        name = NameOps.fold(self.name)
        if len(name) < 8 or " " not in name:
            return False
        return f" {name} " in f" {NameOps.fold(title)} "
