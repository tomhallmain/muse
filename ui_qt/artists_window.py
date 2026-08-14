"""
Artist search and details windows (PySide6).
"""
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QCheckBox,
    QScrollArea,
    QWidget,
    QFrame,
)
from PySide6.QtCore import Qt, QTimer

from lib.multi_display_qt import SmartWindow
from library_data.artist import Artist, ArtistsDataSearch, artists_data
from ui_qt.app_style import AppStyle
from ui_qt.auth.password_utils import require_password
from utils.app_info_cache import app_info_cache
from utils.globals import ProtectedActions
from utils.logging_setup import get_logger
from utils.translations import I18N

logger = get_logger(__name__)
_ = I18N._


class ArtistDetailsWindow(SmartWindow):
    """Window to show and edit artist details."""

    top_level = None

    def __init__(
        self,
        master: QWidget,
        artists_window: "ArtistsWindow",
        artist: Artist = None,
        dimensions: str = "600x600",
    ):
        art = artist if artist is not None else Artist(None, None)
        is_new = artist is None
        title = (
            _("New Artist")
            if is_new
            else _("Modify Artist: {0}").format(art.name)
        )
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=title,
            geometry=dimensions,
            offset_x=50,
            offset_y=50,
        )
        ArtistDetailsWindow.top_level = self
        self.master = master
        self.artists_window = artists_window
        self.app_actions = artists_window.app_actions
        self.artist = art
        self.is_new = is_new
        self.original_name = None if is_new else art.name

        self.setStyleSheet(AppStyle.get_stylesheet())

        self.note_key_edits = []
        self.note_value_edits = []
        self.note_delete_btns = []

        self._build_ui()

    def _build_ui(self):
        layout = QGridLayout(self)

        row = 0
        layout.addWidget(
            QLabel(_("Modify Artist"), self), row, 0, 1, -1, Qt.AlignmentFlag.AlignLeft
        )
        row += 1

        layout.addWidget(QLabel(_("Name"), self), row, 0, Qt.AlignmentFlag.AlignLeft)
        self.name_edit = QLineEdit(self)
        self.name_edit.setText("" if self.is_new else str(self.artist.name or ""))
        self.name_edit.setMinimumWidth(300)
        layout.addWidget(self.name_edit, row, 1, 1, -1)
        row += 1

        layout.addWidget(QLabel(_("Indicators"), self), row, 0, Qt.AlignmentFlag.AlignLeft)
        self.indicators_edit = QLineEdit(self)
        self.indicators_edit.setText(
            ""
            if self.is_new
            else ":".join(str(i) for i in (self.artist.indicators or []) if i)
        )
        self.indicators_edit.setMinimumWidth(300)
        layout.addWidget(self.indicators_edit, row, 1, 1, -1)
        row += 1

        layout.addWidget(QLabel(_("Start Date"), self), row, 0, Qt.AlignmentFlag.AlignLeft)
        self.start_date_edit = QLineEdit(self)
        self.start_date_edit.setText(
            "" if self.is_new or self.artist.start_date == -1 else str(self.artist.start_date)
        )
        layout.addWidget(self.start_date_edit, row, 1, 1, -1)
        row += 1

        layout.addWidget(QLabel(_("End Date"), self), row, 0, Qt.AlignmentFlag.AlignLeft)
        self.end_date_edit = QLineEdit(self)
        self.end_date_edit.setText(
            "" if self.is_new or self.artist.end_date == -1 else str(self.artist.end_date)
        )
        layout.addWidget(self.end_date_edit, row, 1, 1, -1)
        row += 1

        layout.addWidget(
            QLabel(_("Dates are lifespan"), self), row, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.dates_are_lifespan_check = QCheckBox(_("Dates are lifespan"), self)
        self.dates_are_lifespan_check.setChecked(
            True if self.is_new else self.artist.dates_are_lifespan
        )
        layout.addWidget(self.dates_are_lifespan_check, row, 1)
        row += 1

        layout.addWidget(
            QLabel(_("Dates uncertain"), self), row, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.dates_uncertain_check = QCheckBox(_("Dates are uncertain"), self)
        self.dates_uncertain_check.setChecked(
            False if self.is_new else self.artist.dates_uncertain
        )
        layout.addWidget(self.dates_uncertain_check, row, 1)
        row += 1

        layout.addWidget(QLabel(_("Genres"), self), row, 0, Qt.AlignmentFlag.AlignLeft)
        self.genres_edit = QLineEdit(self)
        self.genres_edit.setText(
            ""
            if self.is_new
            else ":".join(str(g) for g in (self.artist.genres or []) if g)
        )
        self.genres_edit.setMinimumWidth(300)
        layout.addWidget(self.genres_edit, row, 1, 1, -1)
        row += 1

        layout.addWidget(QLabel(_("Albums"), self), row, 0, Qt.AlignmentFlag.AlignLeft)
        self.albums_edit = QLineEdit(self)
        self.albums_edit.setText(
            ""
            if self.is_new
            else ":".join(str(a) for a in (self.artist.albums or []) if a)
        )
        self.albums_edit.setMinimumWidth(300)
        layout.addWidget(self.albums_edit, row, 1, 1, -1)
        row += 1

        layout.addWidget(QLabel(_("Notes"), self), row, 0, Qt.AlignmentFlag.AlignLeft)
        self.add_note_btn = QPushButton(_("Add Note"), self)
        self.add_note_btn.clicked.connect(self.add_note)
        layout.addWidget(self.add_note_btn, row, 1)
        row += 1

        self.notes_container = QWidget(self)
        self.notes_layout = QGridLayout(self.notes_container)
        self.notes_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.notes_container, row, 0, 1, -1)
        row += 1

        self._add_note_widgets()

        btn_row = QHBoxLayout()
        self.save_btn = QPushButton(_("Save"), self)
        self.save_btn.clicked.connect(self.finalize_artist)
        btn_row.addWidget(self.save_btn)
        if not self.is_new:
            self.delete_btn = QPushButton(_("Delete"), self)
            self.delete_btn.clicked.connect(self.delete_artist)
            btn_row.addWidget(self.delete_btn)
        layout.addLayout(btn_row, row, 0, 1, -1)

    def _add_note_widgets(self):
        while self.notes_layout.count():
            child = self.notes_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.note_key_edits.clear()
        self.note_value_edits.clear()
        for btn in self.note_delete_btns:
            btn.deleteLater()
        self.note_delete_btns.clear()

        for r, (note_key, note_value) in enumerate(self.artist.notes.items()):
            key_edit = QLineEdit(self.notes_container)
            key_edit.setText(str(note_key))
            key_edit.setMinimumWidth(200)
            self.notes_layout.addWidget(key_edit, r, 0)
            self.note_key_edits.append(key_edit)

            value_edit = QLineEdit(self.notes_container)
            value_edit.setText(str(note_value))
            value_edit.setMinimumWidth(200)
            self.notes_layout.addWidget(value_edit, r, 1)
            self.note_value_edits.append(value_edit)

            delete_btn = QPushButton(_("Delete"), self.notes_container)
            self.note_delete_btns.append(delete_btn)
            self.notes_layout.addWidget(delete_btn, r, 2)
            delete_btn.clicked.connect(
                lambda checked=False, k=note_key: self._delete_note(k)
            )

    def _delete_note(self, key):
        self.artist.notes.pop(key, None)
        self.refresh()

    def add_note(self):
        self.artist.new_note(key=_("New note"))
        self.refresh()

    def refresh(self):
        self._add_note_widgets()

    @require_password(ProtectedActions.EDIT_LIBRARY_VOCABULARY)
    def finalize_artist(self, event=None):
        start_val = self.start_date_edit.text().strip()
        end_val = self.end_date_edit.text().strip()
        try:
            start_date = int(start_val) if start_val else -1
            end_date = int(end_val) if end_val else -1
        except ValueError:
            self.app_actions.alert(
                _("Validation Error"),
                _("Dates must be valid integers"),
                kind="warning",
                master=self,
            )
            return

        temp_artist = Artist(
            id=self.artist.id,
            name=self.name_edit.text().strip(),
            indicators=[
                i.strip()
                for i in self.indicators_edit.text().split(":")
                if i.strip()
            ],
            start_date=start_date,
            end_date=end_date,
            dates_are_lifespan=self.dates_are_lifespan_check.isChecked(),
            dates_uncertain=self.dates_uncertain_check.isChecked(),
            genres=[
                g.strip() for g in self.genres_edit.text().split(":") if g.strip()
            ],
            albums=[
                a.strip() for a in self.albums_edit.text().split(":") if a.strip()
            ],
        )
        temp_artist.notes = {}
        for i in range(len(self.note_key_edits)):
            key = self.note_key_edits[i].text().strip()
            value = self.note_value_edits[i].text().strip()
            if key:
                temp_artist.notes[key] = value

        is_valid, error_message, fixes = temp_artist.validate()
        if fixes.get("name"):
            self.name_edit.setText(fixes["name"])
        if fixes.get("indicators"):
            self.indicators_edit.setText(":".join(fixes["indicators"]))

        if not is_valid:
            self.app_actions.alert(
                _("Validation Error"), error_message, kind="warning", master=self
            )
            return

        if (
            not self.is_new
            and temp_artist.to_json() == self.artist.to_json()
            and self.original_name == temp_artist.name
        ):
            self.close()
            return

        if (
            self.is_new
            and temp_artist.name in self.artists_window.artists_data._artists
        ):
            self.app_actions.alert(
                _("Validation Error"),
                _("An artist named \"{0}\" already exists").format(temp_artist.name),
                kind="warning",
                master=self,
            )
            return

        self.artist = temp_artist
        success, error_msg = self.artists_window.artists_data.save_artist(
            self.artist, original_name=self.original_name
        )
        if success:
            self.close()
            if self.is_new:
                self.artists_window.set_artist_query(self.artist.name)
                self.artists_window.set_genre_query("")
                self.artists_window.do_search()
            else:
                self.artists_window._refresh_widgets()
        else:
            self.app_actions.alert(
                _("Error"),
                _("Failed to save artist:") + "\n\n" + error_msg,
                kind="error",
                master=self,
            )

    @require_password(ProtectedActions.EDIT_LIBRARY_VOCABULARY)
    def delete_artist(self, event=None):
        res = self.app_actions.alert(
            _("Delete artist"),
            _(
                "Are you sure you want to delete {0}? This action cannot be undone."
            ).format(self.artist.name),
            kind="askokcancel",
            master=self,
        )
        if res:
            success, error_msg = self.artists_window.artists_data.delete_artist(
                self.artist
            )
            if success:
                self.close()
                self.artists_window._refresh_widgets()
            else:
                self.app_actions.alert(
                    _("Error"),
                    _("Failed to delete artist:") + "\n\n" + error_msg,
                    kind="error",
                    master=self,
                )


class ArtistsWindow(SmartWindow):
    """Window to search and edit artist vocabulary."""

    top_level = None
    MAX_RESULTS = 500
    MAX_RECENT_SEARCHES = 50
    details_window = None
    recent_searches = []

    @staticmethod
    def load_recent_searches():
        ArtistsWindow.recent_searches.clear()
        json_searches = app_info_cache.get("recent_artist_searches", [])
        if not isinstance(json_searches, list):
            return
        for search_details in json_searches:
            try:
                search = ArtistsDataSearch(**search_details)
            except TypeError:
                continue
            if search.stored_results_count > 0:
                ArtistsWindow.recent_searches.append(search)
        if len(ArtistsWindow.recent_searches) > ArtistsWindow.MAX_RECENT_SEARCHES:
            ArtistsWindow.recent_searches = ArtistsWindow.recent_searches[
                : ArtistsWindow.MAX_RECENT_SEARCHES
            ]

    @staticmethod
    def store_recent_searches():
        unique = []
        seen = set()
        for search in ArtistsWindow.recent_searches:
            key = (search.artist, search.genre)
            if key in seen:
                continue
            if search.stored_results_count > 0:
                unique.append(search)
                seen.add(key)
        if len(unique) > ArtistsWindow.MAX_RECENT_SEARCHES:
            unique = unique[: ArtistsWindow.MAX_RECENT_SEARCHES]
        app_info_cache.set(
            "recent_artist_searches", [s.get_dict() for s in unique]
        )

    def __init__(self, master: QWidget, app_actions, dimensions: str = "650x600"):
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("Artist Search") + " - " + _("Search Artists"),
            geometry=dimensions,
            offset_x=50,
            offset_y=50,
        )
        ArtistsWindow.top_level = self
        self.master = master
        self.app_actions = app_actions
        self.artists_data = artists_data
        self.artists_data.reload()
        self.artist_data_search = None
        self.has_closed = False

        ArtistsWindow.load_recent_searches()

        self.setStyleSheet(AppStyle.get_stylesheet())
        self._build_ui()
        self.show()
        QTimer.singleShot(0, self.show_recent_searches)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        inner = QFrame(self)
        inner_layout = QGridLayout(inner)

        inner_layout.addWidget(
            QLabel(_("Search Artist"), self), 0, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.artist_entry = QLineEdit(self)
        self.artist_entry.setPlaceholderText("")
        self.artist_entry.returnPressed.connect(self.do_search)
        inner_layout.addWidget(self.artist_entry, 0, 1)

        inner_layout.addWidget(
            QLabel(_("Search Genre"), self), 1, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.genre_entry = QLineEdit(self)
        self.genre_entry.returnPressed.connect(self.do_search)
        inner_layout.addWidget(self.genre_entry, 1, 1)

        self.search_btn = QPushButton(_("Search"), self)
        self.search_btn.clicked.connect(self.do_search)
        inner_layout.addWidget(self.search_btn, 2, 0, 1, 2)

        self.new_artist_btn = QPushButton(_("New Artist"), self)
        self.new_artist_btn.clicked.connect(self.new_artist)
        inner_layout.addWidget(self.new_artist_btn, 0, 2)

        self.list_all_btn = QPushButton(_("List All"), self)
        self.list_all_btn.clicked.connect(self._list_all)
        inner_layout.addWidget(self.list_all_btn, 1, 2)

        layout.addWidget(inner)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.results_widget = QWidget(self.scroll)
        self.results_layout = QGridLayout(self.results_widget)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll.setWidget(self.results_widget)
        layout.addWidget(self.scroll, 1)

        self.name_labels = []
        self.indicator_labels = []
        self.details_btns = []
        self.search_btn_list = []

    def set_artist_query(self, text: str):
        self.artist_entry.setText(text)

    def set_genre_query(self, text: str):
        self.genre_entry.setText(text)

    def show_recent_searches(self):
        self._clear_results_widgets()
        if len(ArtistsWindow.recent_searches) == 0:
            lbl = QLabel(_("No recent searches found."), self.results_widget)
            self.results_layout.addWidget(lbl, 0, 1)
            self.name_labels.append(lbl)
            return
        for i, search in enumerate(ArtistsWindow.recent_searches):
            if search is None:
                continue
            row = i + 1
            title_label = QLabel(search.get_title(), self.results_widget)
            title_label.setWordWrap(True)
            self.results_layout.addWidget(title_label, row, 1)
            self.name_labels.append(title_label)

            count_label = QLabel(
                search.get_readable_stored_results_count(), self.results_widget
            )
            self.results_layout.addWidget(count_label, row, 2)
            self.indicator_labels.append(count_label)

            search_btn = QPushButton(_("Search"), self.results_widget)
            self.search_btn_list.append(search_btn)
            self.results_layout.addWidget(search_btn, row, 3)
            search_btn.clicked.connect(
                lambda checked=False, s=search: self._run_stored_search(s)
            )

    def _run_stored_search(self, search: ArtistsDataSearch):
        self.artist_entry.setText(search.artist)
        self.genre_entry.setText(search.genre)
        self.artist_data_search = search
        self._do_search()

    def _list_all(self):
        """Browse all artists in the UI without going through search matching."""
        self.artist_entry.setText("")
        self.genre_entry.setText("")
        self._refresh_widgets(add_results=False)
        self.artist_data_search = ArtistsDataSearch(
            max_results=ArtistsWindow.MAX_RESULTS,
        )
        self.artist_data_search.results = self.artists_data.get_all_artists()[
            : ArtistsWindow.MAX_RESULTS
        ]
        self.artist_data_search.set_stored_results_count()
        self.setWindowTitle(
            _("Artist Search") + " - " + self.artist_data_search.get_title()
        )
        self._refresh_widgets()

    def _clear_results_widgets(self):
        while self.results_layout.count():
            child = self.results_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.name_labels.clear()
        self.indicator_labels.clear()
        self.details_btns.clear()
        self.search_btn_list.clear()

    def do_search(self, event=None):
        artist_query = self.artist_entry.text().strip()
        genre_query = self.genre_entry.text().strip()
        if not artist_query and not genre_query:
            self._refresh_widgets(add_results=False)
            self.show_recent_searches()
            return

        self.artist_data_search = ArtistsDataSearch(
            artist=artist_query,
            genre=genre_query,
            max_results=ArtistsWindow.MAX_RESULTS,
        )
        self._do_search()

    def _do_search(self):
        if self.artist_data_search is None:
            return
        self._refresh_widgets(add_results=False)
        self.artists_data.do_search(self.artist_data_search)
        ArtistsWindow.recent_searches = [
            s for s in ArtistsWindow.recent_searches if s != self.artist_data_search
        ]
        ArtistsWindow.recent_searches.insert(0, self.artist_data_search)
        if len(ArtistsWindow.recent_searches) > ArtistsWindow.MAX_RECENT_SEARCHES:
            ArtistsWindow.recent_searches = ArtistsWindow.recent_searches[
                : ArtistsWindow.MAX_RECENT_SEARCHES
            ]
        self.setWindowTitle(
            _("Artist Search") + " - " + self.artist_data_search.get_title()
        )
        self._refresh_widgets()

    def add_widgets_for_results(self):
        if self.artist_data_search is None:
            return
        results = self.artist_data_search.get_results()
        logger.info("Found %s artist results", len(results))
        for i, artist in enumerate(results):
            row = i + 1
            name_label = QLabel(artist.name, self.results_widget)
            self.results_layout.addWidget(name_label, row, 0)
            self.name_labels.append(name_label)

            indicator_text = ", ".join(artist.indicators or [])
            indicator_label = QLabel(indicator_text, self.results_widget)
            indicator_label.setWordWrap(True)
            self.results_layout.addWidget(indicator_label, row, 1)
            self.indicator_labels.append(indicator_label)

            details_btn = QPushButton(_("Details"), self.results_widget)
            self.details_btns.append(details_btn)
            self.results_layout.addWidget(details_btn, row, 2)
            details_btn.clicked.connect(
                lambda checked=False, a=artist: self.open_details(a)
            )

    @require_password(ProtectedActions.EDIT_LIBRARY_VOCABULARY)
    def open_details(self, artist: Artist):
        if ArtistsWindow.details_window is not None:
            try:
                ArtistsWindow.details_window.close()
            except Exception:
                pass
        ArtistsWindow.details_window = ArtistDetailsWindow(self, self, artist)
        ArtistsWindow.details_window.show()

    @require_password(ProtectedActions.EDIT_LIBRARY_VOCABULARY)
    def new_artist(self):
        if ArtistsWindow.details_window is not None:
            try:
                ArtistsWindow.details_window.close()
            except Exception:
                pass
        ArtistsWindow.details_window = ArtistDetailsWindow(self, self, None)
        ArtistsWindow.details_window.show()

    def _refresh_widgets(self, add_results: bool = True):
        self._clear_results_widgets()
        if add_results:
            self.add_widgets_for_results()

    def closeEvent(self, event):
        self.has_closed = True
        ArtistsWindow.store_recent_searches()
        if ArtistsWindow.top_level is self:
            ArtistsWindow.top_level = None
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)
