"""
Library statistics and browsing window (PySide6).
Port of ui/library_window.py; logic preserved, UI uses Qt.
"""

from PySide6.QtWidgets import (
    QDialog,
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
from PySide6.QtCore import Qt

from ui_qt.app_style import AppStyle
from utils.globals import TrackAttribute
from utils.logging_setup import get_logger
from utils.translations import I18N

_ = I18N._
logger = get_logger(__name__)


class LibraryWindow(QDialog):
    """Window to display and manage library statistics and browsing."""

    CURRENT_LIBRARY_TEXT = _("Library")
    top_level = None

    def __init__(self, master, app_actions, library_data):
        super().__init__(master)
        LibraryWindow.top_level = self
        self.setWindowTitle(_("Library"))
        self.resize(1000, 600)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Window)

        self.master = master
        self.app_actions = app_actions
        self.library_data = library_data

        self.setStyleSheet(AppStyle.get_stylesheet())
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        self._init_sidebar(layout)
        self._init_content(layout)
        self._update_statistics()
        self.show()

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
        self.table = QTableWidget(self)
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels([_("Name"), _("Count")])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.setColumnWidth(1, 100)
        main_layout.addWidget(self.table, 1)

    def _update_statistics(self):
        all_tracks = self.library_data.get_all_tracks()

        self.total_tracks_label.setText(_("Total Tracks: {}").format(len(all_tracks)))

        albums = set()
        for track in all_tracks:
            if track.album:
                albums.add(track.album)
        self.total_albums_label.setText(_("Total Albums: {}").format(len(albums)))

        artists = set()
        for track in all_tracks:
            if track.artist:
                artists.add(track.artist)
        self.total_artists_label.setText(_("Total Artists: {}").format(len(artists)))

        composers = set()
        for track in all_tracks:
            if track.composer:
                composers.add(track.composer)
        self.total_composers_label.setText(_("Total Composers: {}").format(len(composers)))

        instruments = set()
        for track in all_tracks:
            instrument = track.get_instrument()
            if instrument:
                instruments.add(instrument)
        self.total_instruments_label.setText(
            _("Total Instruments: {}").format(len(instruments))
        )

        forms = set()
        for track in all_tracks:
            form = track.get_form()
            if form:
                forms.add(form)
        self.total_forms_label.setText(_("Total Forms: {}").format(len(forms)))

        cache_time = self.library_data.get_cache_update_time()
        if cache_time:
            cache_text = _("Cache Updated: {}").format(
                cache_time.strftime("%Y-%m-%d %H:%M")
            )
        else:
            cache_text = _("No Cache Available")
        self.cache_update_label.setText(cache_text)

        self._update_treeview()

    def _update_treeview(self):
        self.table.setRowCount(0)
        attr = TrackAttribute.get_from_translation(self.attribute_combo.currentText())
        all_tracks = self.library_data.get_all_tracks()

        counts = {}
        for track in all_tracks:
            if attr == TrackAttribute.TITLE:
                value = track.title
            elif attr == TrackAttribute.ALBUM:
                value = track.album
            elif attr == TrackAttribute.ARTIST:
                value = track.artist
            elif attr == TrackAttribute.COMPOSER:
                value = track.composer
            elif attr == TrackAttribute.GENRE:
                value = track.genre
            elif attr == TrackAttribute.FORM:
                value = track.get_form()
            elif attr == TrackAttribute.INSTRUMENT:
                value = track.get_instrument()
            else:
                value = None
            if value:
                counts[value] = counts.get(value, 0) + 1

        search_term = self.search_entry.text().strip().lower()
        if search_term:
            counts = {k: v for k, v in counts.items() if search_term in k.lower()}

        sorted_items = sorted(counts.items(), key=lambda x: (-x[1], x[0]))

        self.table.setRowCount(len(sorted_items))
        for row, (name, count) in enumerate(sorted_items):
            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem(str(count)))

    def _on_attribute_change(self, text):
        self._update_treeview()

    def _on_search_change(self, text):
        self._update_treeview()

    def closeEvent(self, event):
        if LibraryWindow.top_level is self:
            LibraryWindow.top_level = None
        event.accept()

    def update(self):
        self._update_statistics()
