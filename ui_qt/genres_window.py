"""
Musical genres search and details windows (PySide6).
"""
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QWidget,
    QFrame,
)
from PySide6.QtCore import Qt, QTimer

from lib.multi_display_qt import SmartWindow
from library_data.genre import Genre, GenresDataSearch, genre_data
from ui_qt.app_style import AppStyle
from ui_qt.auth.password_utils import require_password
from utils.app_info_cache import app_info_cache
from utils.globals import ProtectedActions
from utils.logging_setup import get_logger
from utils.translations import I18N

logger = get_logger(__name__)
_ = I18N._


class GenreDetailsWindow(SmartWindow):
    """Window to show and edit musical genre details."""

    top_level = None

    def __init__(
        self,
        master: QWidget,
        genres_window: "GenresWindow",
        genre: Genre = None,
        dimensions: str = "550x450",
    ):
        is_new = genre is None
        genre_obj = genre if genre is not None else Genre("")
        title = (
            _("New Genre")
            if is_new
            else _("Modify Genre: {0}").format(genre_obj.name)
        )
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=title,
            geometry=dimensions,
            offset_x=50,
            offset_y=50,
        )
        GenreDetailsWindow.top_level = self
        self.master = master
        self.genres_window = genres_window
        self.app_actions = genres_window.app_actions
        self.genre = genre_obj
        self.is_new = is_new
        self.original_name = None if is_new else genre_obj.name

        self.setStyleSheet(AppStyle.get_stylesheet())

        self.note_key_edits = []
        self.note_value_edits = []
        self.note_delete_btns = []

        self._build_ui()

    def _build_ui(self):
        layout = QGridLayout(self)

        row = 0
        layout.addWidget(
            QLabel(_("Modify Genre"), self), row, 0, 1, -1, Qt.AlignmentFlag.AlignLeft
        )
        row += 1

        layout.addWidget(QLabel(_("Name"), self), row, 0, Qt.AlignmentFlag.AlignLeft)
        self.name_edit = QLineEdit(self)
        self.name_edit.setText("" if self.is_new else str(self.genre.name or ""))
        self.name_edit.setMinimumWidth(300)
        layout.addWidget(self.name_edit, row, 1, 1, -1)
        row += 1

        layout.addWidget(
            QLabel(_("Transliterations"), self), row, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.transliterations_edit = QLineEdit(self)
        self.transliterations_edit.setPlaceholderText(
            _("colon-separated, e.g. baroque:barock:barocco")
        )
        self.transliterations_edit.setText(
            ""
            if self.is_new
            else ":".join(str(t) for t in (self.genre.transliterations or []) if t)
        )
        self.transliterations_edit.setMinimumWidth(300)
        layout.addWidget(self.transliterations_edit, row, 1, 1, -1)
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
        self.save_btn.clicked.connect(self.finalize_genre)
        btn_row.addWidget(self.save_btn)
        if not self.is_new:
            self.delete_btn = QPushButton(_("Delete"), self)
            self.delete_btn.clicked.connect(self.delete_genre)
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

        for r, (note_key, note_value) in enumerate(self.genre.notes.items()):
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
        self.genre.notes.pop(key, None)
        self.refresh()

    def add_note(self):
        self.genre.new_note(key=_("New note"))
        self.refresh()

    def refresh(self):
        self._add_note_widgets()

    @require_password(ProtectedActions.EDIT_GENRES)
    def finalize_genre(self, event=None):
        temp_genre = Genre(
            name=self.name_edit.text().strip(),
            transliterations=[
                t.strip()
                for t in self.transliterations_edit.text().split(":")
                if t.strip()
            ],
        )
        temp_genre.notes = {}
        for i in range(len(self.note_key_edits)):
            key = self.note_key_edits[i].text().strip()
            value = self.note_value_edits[i].text().strip()
            if key:
                temp_genre.notes[key] = value

        is_valid, error_message, fixes = temp_genre.validate()
        if fixes.get("name"):
            self.name_edit.setText(fixes["name"])
        if fixes.get("transliterations"):
            self.transliterations_edit.setText(":".join(fixes["transliterations"]))

        if not is_valid:
            self.app_actions.alert(
                _("Validation Error"), error_message, kind="warning", master=self
            )
            return

        if (
            not self.is_new
            and temp_genre.to_json() == self.genre.to_json()
            and self.original_name == temp_genre.name
        ):
            self.close()
            return

        if (
            self.is_new
            and temp_genre.name in self.genres_window.genre_data._genres
        ):
            self.app_actions.alert(
                _("Validation Error"),
                _("A genre named \"{0}\" already exists").format(temp_genre.name),
                kind="warning",
                master=self,
            )
            return

        self.genre = temp_genre
        success, error_msg = self.genres_window.genre_data.save_genre(
            self.genre, original_name=self.original_name
        )
        if success:
            self.close()
            if self.is_new:
                self.genres_window.set_genre_query(self.genre.name)
                self.genres_window.do_search()
            else:
                self.genres_window._refresh_widgets()
        else:
            self.app_actions.alert(
                _("Error"),
                _("Failed to save genre:") + "\n\n" + error_msg,
                kind="error",
                master=self,
            )

    @require_password(ProtectedActions.EDIT_GENRES)
    def delete_genre(self, event=None):
        res = self.app_actions.alert(
            _("Delete genre"),
            _(
                "Are you sure you want to delete {0}? This action cannot be undone."
            ).format(self.genre.name),
            kind="askokcancel",
            master=self,
        )
        if res:
            success, error_msg = self.genres_window.genre_data.delete_genre(self.genre)
            if success:
                self.close()
                self.genres_window._refresh_widgets()
            else:
                self.app_actions.alert(
                    _("Error"),
                    _("Failed to delete genre:") + "\n\n" + error_msg,
                    kind="error",
                    master=self,
                )


class GenresWindow(SmartWindow):
    """Window to search and edit musical genre vocabulary."""

    top_level = None
    MAX_RESULTS = 500
    MAX_RECENT_SEARCHES = 50
    details_window = None
    recent_searches = []

    @staticmethod
    def load_recent_searches():
        GenresWindow.recent_searches.clear()
        json_searches = app_info_cache.get("recent_genre_searches", [])
        if not isinstance(json_searches, list):
            return
        for search_details in json_searches:
            try:
                search = GenresDataSearch(**search_details)
            except TypeError:
                continue
            if search.stored_results_count > 0:
                GenresWindow.recent_searches.append(search)
        if len(GenresWindow.recent_searches) > GenresWindow.MAX_RECENT_SEARCHES:
            GenresWindow.recent_searches = GenresWindow.recent_searches[
                : GenresWindow.MAX_RECENT_SEARCHES
            ]

    @staticmethod
    def store_recent_searches():
        unique = []
        seen = set()
        for search in GenresWindow.recent_searches:
            if search.genre in seen:
                continue
            if search.stored_results_count > 0:
                unique.append(search)
                seen.add(search.genre)
        if len(unique) > GenresWindow.MAX_RECENT_SEARCHES:
            unique = unique[: GenresWindow.MAX_RECENT_SEARCHES]
        app_info_cache.set(
            "recent_genre_searches", [s.get_dict() for s in unique]
        )

    def __init__(self, master: QWidget, app_actions, dimensions: str = "650x600"):
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("Genre Search") + " - " + _("Search Genres"),
            geometry=dimensions,
            offset_x=50,
            offset_y=50,
        )
        GenresWindow.top_level = self
        self.master = master
        self.app_actions = app_actions
        self.genre_data = genre_data
        self.genre_data.reload()
        self.genre_data_search = None
        self.has_closed = False

        GenresWindow.load_recent_searches()

        self.setStyleSheet(AppStyle.get_stylesheet())
        self._build_ui()
        self.show()
        QTimer.singleShot(0, self.show_recent_searches)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        inner = QFrame(self)
        inner_layout = QGridLayout(inner)

        inner_layout.addWidget(
            QLabel(_("Search Genre"), self), 0, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.genre_entry = QLineEdit(self)
        self.genre_entry.setPlaceholderText("")
        self.genre_entry.returnPressed.connect(self.do_search)
        inner_layout.addWidget(self.genre_entry, 0, 1)

        self.search_btn = QPushButton(_("Search"), self)
        self.search_btn.clicked.connect(self.do_search)
        inner_layout.addWidget(self.search_btn, 1, 0, 1, 2)

        self.new_genre_btn = QPushButton(_("New Genre"), self)
        self.new_genre_btn.clicked.connect(self.new_genre)
        inner_layout.addWidget(self.new_genre_btn, 0, 2)

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
        self.translit_labels = []
        self.details_btns = []
        self.search_btn_list = []

    def set_genre_query(self, text: str):
        self.genre_entry.setText(text)

    def show_recent_searches(self):
        self._clear_results_widgets()
        if len(GenresWindow.recent_searches) == 0:
            lbl = QLabel(_("No recent searches found."), self.results_widget)
            self.results_layout.addWidget(lbl, 0, 1)
            self.name_labels.append(lbl)
            return
        for i, search in enumerate(GenresWindow.recent_searches):
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
            self.translit_labels.append(count_label)

            search_btn = QPushButton(_("Search"), self.results_widget)
            self.search_btn_list.append(search_btn)
            self.results_layout.addWidget(search_btn, row, 3)
            search_btn.clicked.connect(
                lambda checked=False, s=search: self._run_stored_search(s)
            )

    def _run_stored_search(self, search: GenresDataSearch):
        self.genre_entry.setText(search.genre)
        self.genre_data_search = search
        self._do_search()

    def _list_all(self):
        """Browse all genres in the UI without going through search matching."""
        self.genre_entry.setText("")
        self._refresh_widgets(add_results=False)
        self.genre_data_search = GenresDataSearch(
            genre="",
            max_results=GenresWindow.MAX_RESULTS,
        )
        self.genre_data_search.results = self.genre_data.get_all_genres()[
            : GenresWindow.MAX_RESULTS
        ]
        self.genre_data_search.set_stored_results_count()
        self.setWindowTitle(
            _("Genre Search") + " - " + self.genre_data_search.get_title()
        )
        self._refresh_widgets()

    def _clear_results_widgets(self):
        while self.results_layout.count():
            child = self.results_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.name_labels.clear()
        self.translit_labels.clear()
        self.details_btns.clear()
        self.search_btn_list.clear()

    def do_search(self, event=None):
        query = self.genre_entry.text().strip()
        if not query:
            self._refresh_widgets(add_results=False)
            self.show_recent_searches()
            return

        self.genre_data_search = GenresDataSearch(
            genre=query,
            max_results=GenresWindow.MAX_RESULTS,
        )
        self._do_search()

    def _do_search(self):
        if self.genre_data_search is None:
            return
        self._refresh_widgets(add_results=False)
        self.genre_data.do_search(self.genre_data_search)
        GenresWindow.recent_searches = [
            s for s in GenresWindow.recent_searches if s != self.genre_data_search
        ]
        GenresWindow.recent_searches.insert(0, self.genre_data_search)
        if len(GenresWindow.recent_searches) > GenresWindow.MAX_RECENT_SEARCHES:
            GenresWindow.recent_searches = GenresWindow.recent_searches[
                : GenresWindow.MAX_RECENT_SEARCHES
            ]
        self.setWindowTitle(
            _("Genre Search") + " - " + self.genre_data_search.get_title()
        )
        self._refresh_widgets()

    def add_widgets_for_results(self):
        if self.genre_data_search is None:
            return
        results = self.genre_data_search.get_results()
        logger.info("Found %s genre results", len(results))
        for i, genre in enumerate(results):
            row = i + 1
            name_label = QLabel(genre.name, self.results_widget)
            self.results_layout.addWidget(name_label, row, 0)
            self.name_labels.append(name_label)

            translit_text = ", ".join(genre.transliterations or [])
            translit_label = QLabel(translit_text, self.results_widget)
            translit_label.setWordWrap(True)
            self.results_layout.addWidget(translit_label, row, 1)
            self.translit_labels.append(translit_label)

            details_btn = QPushButton(_("Details"), self.results_widget)
            self.details_btns.append(details_btn)
            self.results_layout.addWidget(details_btn, row, 2)
            details_btn.clicked.connect(
                lambda checked=False, g=genre: self.open_details(g)
            )

    @require_password(ProtectedActions.EDIT_GENRES)
    def open_details(self, genre: Genre):
        if GenresWindow.details_window is not None:
            try:
                GenresWindow.details_window.close()
            except Exception:
                pass
        GenresWindow.details_window = GenreDetailsWindow(self, self, genre)
        GenresWindow.details_window.show()

    @require_password(ProtectedActions.EDIT_GENRES)
    def new_genre(self):
        if GenresWindow.details_window is not None:
            try:
                GenresWindow.details_window.close()
            except Exception:
                pass
        GenresWindow.details_window = GenreDetailsWindow(self, self, None)
        GenresWindow.details_window.show()

    def _refresh_widgets(self, add_results: bool = True):
        self._clear_results_widgets()
        if add_results:
            self.add_widgets_for_results()

    def closeEvent(self, event):
        self.has_closed = True
        GenresWindow.store_recent_searches()
        if GenresWindow.top_level is self:
            GenresWindow.top_level = None
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)
