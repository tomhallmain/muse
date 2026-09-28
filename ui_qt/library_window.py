"""
Library statistics and browsing window (PySide6).
Port of ui/library_window.py; logic preserved, UI uses Qt.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QWidget,
    QFrame,
)
from PySide6.QtCore import Qt, Signal

from lib.multi_display_qt import SmartWindow
from ui_qt.app_style import AppStyle
from utils.globals import TrackAttribute
from utils.logging_setup import get_logger
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._
logger = get_logger(__name__)

# How each browsable attribute is read off a track.
_VALUE_GETTERS: Dict[TrackAttribute, Callable] = {
    TrackAttribute.TITLE: lambda t: t.title,
    TrackAttribute.ALBUM: lambda t: t.album,
    TrackAttribute.ARTIST: lambda t: t.artist,
    TrackAttribute.COMPOSER: lambda t: t.composer,
    TrackAttribute.GENRE: lambda t: t.genre,
    TrackAttribute.FORM: lambda t: t.get_form(),
    TrackAttribute.INSTRUMENT: lambda t: t.get_instrument(),
}

_COL_NAME, _COL_TRACKS, _COL_PLAYS, _COL_LAST_PLAYED = range(4)


@dataclass
class _TrackRow:
    values: Dict[TrackAttribute, Optional[str]]
    plays: int
    last_played: Optional[datetime]


@dataclass
class _LibrarySnapshot:
    """Everything the window shows, gathered off the UI thread in one pass."""

    rows: List[_TrackRow] = field(default_factory=list)
    distinct: Dict[TrackAttribute, int] = field(default_factory=dict)
    cache_time: Optional[datetime] = None


def _load_snapshot(library_data) -> _LibrarySnapshot:
    tracks = library_data.get_all_tracks()
    try:
        from library_data import play_counts
        plays = play_counts.get_all_play_info()
    except Exception as e:
        logger.warning(f"Could not read play counts for the library window: {e}")
        plays = {}
    snapshot = _LibrarySnapshot(cache_time=library_data.get_cache_update_time())
    distinct_values: Dict[TrackAttribute, set] = {attr: set() for attr in _VALUE_GETTERS}
    for track in tracks:
        values = {}
        for attr, getter in _VALUE_GETTERS.items():
            value = getter(track)
            values[attr] = value
            if value:
                distinct_values[attr].add(value)
        info = plays.get(track.filepath)
        snapshot.rows.append(_TrackRow(
            values,
            info.play_count if info else 0,
            info.last_played if info else None,
        ))
    snapshot.distinct = {attr: len(found) for attr, found in distinct_values.items()}
    return snapshot


def _numeric_item(value: int) -> QTableWidgetItem:
    """An item that sorts by number rather than by its text."""
    item = QTableWidgetItem()
    item.setData(Qt.ItemDataRole.DisplayRole, value)
    return item


class LibraryWindow(SmartWindow):
    """Window to display and manage library statistics and browsing.

    The window opens empty with a loading message; the library is read on a
    worker thread and the result delivered through _snapshot_ready. Switching
    attribute or searching then only regroups that snapshot.
    """

    CURRENT_LIBRARY_TEXT = _("Library")
    top_level = None

    # (snapshot or None, error text, load generation)
    _snapshot_ready = Signal(object, str, int)

    def __init__(self, master, app_actions, library_data):
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("Library"),
            geometry="1000x600",
            offset_x=50,
            offset_y=50,
        )
        LibraryWindow.top_level = self
        self.master = master
        self.app_actions = app_actions
        self.library_data = library_data
        self._snapshot: Optional[_LibrarySnapshot] = None
        # A reload started while another is running supersedes it; only the
        # newest generation's result is shown.
        self._load_generation = 0

        self.setStyleSheet(AppStyle.get_stylesheet())
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        self._init_sidebar(layout)
        self._init_content(layout)
        self._snapshot_ready.connect(self._on_snapshot_ready)
        self.show()
        self._start_loading()

    def _init_sidebar(self, main_layout):
        sidebar = QFrame(self)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        sidebar_layout.addWidget(QLabel(_("Library Statistics"), sidebar))
        self.total_tracks_label = QLabel(sidebar)
        sidebar_layout.addWidget(self.total_tracks_label)
        self.total_albums_label = QLabel(sidebar)
        sidebar_layout.addWidget(self.total_albums_label)
        self.total_artists_label = QLabel(sidebar)
        sidebar_layout.addWidget(self.total_artists_label)
        self.total_composers_label = QLabel(sidebar)
        sidebar_layout.addWidget(self.total_composers_label)
        self.total_instruments_label = QLabel(sidebar)
        sidebar_layout.addWidget(self.total_instruments_label)
        self.total_forms_label = QLabel(sidebar)
        sidebar_layout.addWidget(self.total_forms_label)
        self.total_plays_label = QLabel(sidebar)
        sidebar_layout.addWidget(self.total_plays_label)
        self.cache_update_label = QLabel(sidebar)
        sidebar_layout.addWidget(self.cache_update_label)

        sidebar_layout.addWidget(QLabel(_("Browse By"), sidebar))
        self.attribute_combo = QComboBox(sidebar)
        translations = [attr.get_translation() for attr in TrackAttribute]
        self.attribute_combo.addItems(translations)
        idx = self.attribute_combo.findText(TrackAttribute.ARTIST.get_translation())
        if idx >= 0:
            self.attribute_combo.setCurrentIndex(idx)
        self.attribute_combo.currentTextChanged.connect(self._on_attribute_change)
        sidebar_layout.addWidget(self.attribute_combo)

        sidebar_layout.addWidget(QLabel(_("Search:"), sidebar))
        self.search_entry = QLineEdit(sidebar)
        self.search_entry.setPlaceholderText("")
        self.search_entry.textChanged.connect(self._on_search_change)
        sidebar_layout.addWidget(self.search_entry)

        main_layout.addWidget(sidebar)

    def _init_content(self, main_layout):
        content = QWidget(self)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)

        self.loading_label = QLabel(_("Loading library data..."), content)
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(self.loading_label)

        self.table = QTableWidget(content)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([_("Name"), _("Tracks"), _("Plays"), _("Last Played")])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(_COL_TRACKS, 100)
        self.table.setColumnWidth(_COL_PLAYS, 100)
        self.table.setColumnWidth(_COL_LAST_PLAYED, 120)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        # Sorting is switched on only once rows are filled; see _update_table.
        header.setSortIndicator(_COL_TRACKS, Qt.SortOrder.DescendingOrder)
        header.setSortIndicatorShown(True)
        self.table.hide()
        content_layout.addWidget(self.table, 1)

        main_layout.addWidget(content, 1)

    # ── Loading ────────────────────────────────────────────────────────────────

    def _start_loading(self):
        self._load_generation += 1
        self.loading_label.setText(_("Loading library data..."))
        self.loading_label.show()
        self.attribute_combo.setEnabled(False)
        self.search_entry.setEnabled(False)
        Utils.start_thread(self._load_in_background, use_asyncio=False, args=[self._load_generation])

    def _load_in_background(self, generation):
        try:
            snapshot, error = _load_snapshot(self.library_data), ""
        except Exception as e:
            logger.error(f"Error loading library window data: {e}")
            snapshot, error = None, str(e)
        try:
            self._snapshot_ready.emit(snapshot, error, generation)
        except RuntimeError:
            # The window was closed and destroyed while this was loading.
            pass

    def _on_snapshot_ready(self, snapshot, error, generation):
        if generation != self._load_generation:
            return
        self.attribute_combo.setEnabled(True)
        self.search_entry.setEnabled(True)
        if snapshot is None:
            self.loading_label.setText(_("Could not load library data: {0}").format(error))
            return
        self._snapshot = snapshot
        self.loading_label.hide()
        self._update_statistics()
        self._update_table()
        self.table.show()

    # ── Display ────────────────────────────────────────────────────────────────

    def _update_statistics(self):
        snapshot = self._snapshot
        distinct = snapshot.distinct
        self.total_tracks_label.setText(_("Total Tracks: {}").format(len(snapshot.rows)))
        self.total_albums_label.setText(_("Total Albums: {}").format(distinct[TrackAttribute.ALBUM]))
        self.total_artists_label.setText(_("Total Artists: {}").format(distinct[TrackAttribute.ARTIST]))
        self.total_composers_label.setText(_("Total Composers: {}").format(distinct[TrackAttribute.COMPOSER]))
        self.total_instruments_label.setText(
            _("Total Instruments: {}").format(distinct[TrackAttribute.INSTRUMENT])
        )
        self.total_forms_label.setText(_("Total Forms: {}").format(distinct[TrackAttribute.FORM]))
        self.total_plays_label.setText(
            _("Total Plays: {}").format(sum(row.plays for row in snapshot.rows))
        )

        cache_time = snapshot.cache_time
        if cache_time:
            cache_text = _("Cache Updated: {}").format(
                cache_time.strftime("%Y-%m-%d %H:%M")
            )
        else:
            cache_text = _("No Cache Available")
        self.cache_update_label.setText(cache_text)

    def _update_table(self):
        if self._snapshot is None:
            return
        attr = TrackAttribute.get_from_translation(self.attribute_combo.currentText())

        # value -> [tracks, plays, last played]
        groups: Dict[str, list] = {}
        for row in self._snapshot.rows:
            value = row.values.get(attr)
            if not value:
                continue
            group = groups.setdefault(value, [0, 0, None])
            group[0] += 1
            group[1] += row.plays
            if row.last_played and (group[2] is None or row.last_played > group[2]):
                group[2] = row.last_played

        search_term = self.search_entry.text().strip().lower()
        if search_term:
            groups = {k: v for k, v in groups.items() if search_term in k.lower()}

        # Filling a sorted table re-sorts after every item, so rows would move
        # while being written. Fill unsorted, then let the header's current
        # indicator order the result. Qt's sort is stable, so rows filled in
        # name order stay in name order among equal values.
        self.table.setSortingEnabled(False)
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(0)
            self.table.setRowCount(len(groups))
            for index, (name, (tracks, plays, last_played)) in enumerate(sorted(groups.items())):
                self.table.setItem(index, _COL_NAME, QTableWidgetItem(name))
                self.table.setItem(index, _COL_TRACKS, _numeric_item(tracks))
                self.table.setItem(index, _COL_PLAYS, _numeric_item(plays))
                # ISO dates sort correctly as text; never-played rows stay blank.
                self.table.setItem(index, _COL_LAST_PLAYED, QTableWidgetItem(
                    last_played.date().isoformat() if last_played else ""))
        finally:
            self.table.setSortingEnabled(True)
            self.table.setUpdatesEnabled(True)

    def _on_attribute_change(self, text):
        self._update_table()

    def _on_search_change(self, text):
        self._update_table()

    def closeEvent(self, event):
        if LibraryWindow.top_level is self:
            LibraryWindow.top_level = None
        event.accept()

    def update(self):
        self._start_loading()
