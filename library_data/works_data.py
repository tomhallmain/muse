from typing import Dict, List, Optional

from library_data.work import Work
from utils.db import get_connection
from utils.logging_setup import get_logger

logger = get_logger(__name__)


class WorksData:
    """Persistence for Work rows, keyed by the owning composer's id.

    Mirrors ComposersData's shape (library_data/composer.py): a lazily
    loaded, per-composer cache backed by an upsert into a dedicated table --
    works outgrew composers.works's bare delimited-name string once a
    catalogue number, date and library-match link needed to survive a
    save/reload cycle.
    """

    def __init__(self):
        self.__by_composer: Optional[Dict[int, List[Work]]] = None

    @property
    def _by_composer(self) -> Dict[int, List[Work]]:
        if self.__by_composer is None:
            self._load_all()
        return self.__by_composer

    _SELECT_JOINED = (
        "SELECT works.id, works.composer_id, composers.name AS composer_name, "
        "works.name, works.catalogue_number, works.date, works.source, "
        "works.matched_track_filepath "
        "FROM works JOIN composers ON works.composer_id = composers.id"
    )

    def _load_all(self) -> None:
        by_composer: Dict[int, List[Work]] = {}
        rows = get_connection().execute(WorksData._SELECT_JOINED).fetchall()
        for row in rows:
            by_composer.setdefault(row["composer_id"], []).append(self._work_from_row(row))
        self.__by_composer = by_composer

    @staticmethod
    def _work_from_row(row) -> Work:
        return Work(
            id=row["id"],
            name=row["name"],
            composer=row["composer_name"],
            date=row["date"],
            catalogue_number=row["catalogue_number"],
            source=row["source"],
            matched_track_filepath=row["matched_track_filepath"],
        )

    def reload(self) -> None:
        self.__by_composer = None

    def _refresh_composer(self, composer_id: int) -> None:
        """Refetch one composer's works rather than the whole table -- this
        runs on every save/match, so it has to stay cheap as entries grow."""
        if self.__by_composer is None:
            return  # nothing cached yet; the next access loads fresh from DB
        rows = get_connection().execute(
            WorksData._SELECT_JOINED + " WHERE works.composer_id = ?", (composer_id,)
        ).fetchall()
        self.__by_composer[composer_id] = [self._work_from_row(row) for row in rows]

    def get_works_for_composer(self, composer_id: Optional[int]) -> List[Work]:
        if composer_id is None:
            return []
        return list(self._by_composer.get(composer_id, []))

    _UPSERT_SQL = """
        INSERT INTO works (composer_id, name, catalogue_number, date, source)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(composer_id, name) DO UPDATE SET
            catalogue_number = excluded.catalogue_number,
            date = excluded.date,
            source = excluded.source
    """

    def save_works(self, composer_id: int, works: List[Work]) -> None:
        """Upsert works for one composer. Existing matched_track_filepath links
        are left untouched -- re-ingesting a composer must not throw away a
        match found separately (see set_matched_track)."""
        if not works:
            return
        try:
            conn = get_connection()
            conn.executemany(
                WorksData._UPSERT_SQL,
                [(composer_id, w.name, w.catalogue_number, w.date, w.source) for w in works],
            )
            conn.commit()
            self._refresh_composer(composer_id)
        except Exception as e:
            logger.error(f"Error saving works for composer {composer_id}: {e}")
            try:
                get_connection().rollback()
            except Exception:
                pass

    def set_matched_track(self, work_id: int, filepath: Optional[str]) -> None:
        try:
            conn = get_connection()
            row = conn.execute(
                "SELECT composer_id FROM works WHERE id = ?", (work_id,)
            ).fetchone()
            if row is None:
                return
            conn.execute(
                "UPDATE works SET matched_track_filepath = ? WHERE id = ?",
                (filepath, work_id),
            )
            conn.commit()
            self._refresh_composer(row["composer_id"])
        except Exception as e:
            logger.error(f"Error setting matched track for work {work_id}: {e}")
            try:
                get_connection().rollback()
            except Exception:
                pass


works_data = WorksData()
