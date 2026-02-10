"""
Composers search and details windows (PySide6).
Port of ui/composers_window.py; logic preserved, UI uses Qt.
"""
import time

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QCheckBox,
    QPushButton,
    QScrollArea,
    QWidget,
    QFrame,
)
from PySide6.QtCore import Qt, QTimer

from lib.multi_display_qt import SmartWindow
from library_data.composer import Composer, ComposersDataSearch, ComposersData
from ui_qt.app_style import AppStyle
from ui_qt.auth.password_utils import require_password
from utils.app_info_cache_qt import app_info_cache
from utils.globals import ProtectedActions
from utils.logging_setup import get_logger
from utils.translations import I18N

logger = get_logger(__name__)
_ = I18N._

COL_0_WIDTH = 600


class ComposerDetailsWindow(SmartWindow):
    """Window to show and edit composer details."""

    top_level = None

    def __init__(
        self,
        master: QWidget,
        composers_window: "ComposersWindow",
        composer: Composer = None,
        dimensions: str = "600x600",
    ):
        comp = composer if composer is not None else Composer(None, None)
        is_new = composer is None
        title = (
            _("New Composer")
            if is_new
            else _("Modify Composer: {0}").format(comp.name)
        )
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=title,
            geometry=dimensions,
            offset_x=50,
            offset_y=50,
        )
        ComposerDetailsWindow.top_level = self
        self.master = master
        self.composers_window = composers_window
        self.app_actions = composers_window.app_actions
        self.composer = comp
        self.is_new = is_new

        self.setStyleSheet(AppStyle.get_stylesheet())

        self.note_key_edits = []
        self.note_value_edits = []
        self.note_delete_btns = []

        self._build_ui()

    def _build_ui(self):
        layout = QGridLayout(self)

        row = 0
        layout.addWidget(
            QLabel(_("Modify Composer"), self), row, 0, 1, -1, Qt.AlignmentFlag.AlignLeft
        )
        row += 1

        layout.addWidget(QLabel(_("Name"), self), row, 0, Qt.AlignmentFlag.AlignLeft)
        self.new_composer_name_edit = QLineEdit(self)
        self.new_composer_name_edit.setPlaceholderText("")
        self.new_composer_name_edit.setText(
            _("New Composer") if self.composer is None else self.composer.name
        )
        self.new_composer_name_edit.setMinimumWidth(300)
        layout.addWidget(self.new_composer_name_edit, row, 1, 1, -1)
        row += 1

        layout.addWidget(QLabel(_("Indicators"), self), row, 0, Qt.AlignmentFlag.AlignLeft)
        self.indicators_edit = QLineEdit(self)
        self.indicators_edit.setText(
            "" if self.composer is None else ":".join(self.composer.indicators)
        )
        self.indicators_edit.setMinimumWidth(300)
        layout.addWidget(self.indicators_edit, row, 1, 1, -1)
        row += 1

        layout.addWidget(QLabel(_("Start Date"), self), row, 0, Qt.AlignmentFlag.AlignLeft)
        self.start_date_edit = QLineEdit(self)
        self.start_date_edit.setText(
            "" if self.composer is None else str(self.composer.start_date)
        )
        layout.addWidget(self.start_date_edit, row, 1, 1, -1)
        row += 1

        layout.addWidget(QLabel(_("End Date"), self), row, 0, Qt.AlignmentFlag.AlignLeft)
        self.end_date_edit = QLineEdit(self)
        self.end_date_edit.setText(
            "" if self.composer is None else str(self.composer.end_date)
        )
        layout.addWidget(self.end_date_edit, row, 1, 1, -1)
        row += 1

        layout.addWidget(
            QLabel(_("Dates are lifespan"), self), row, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.dates_are_lifespan_check = QCheckBox(_("Dates are lifespan"), self)
        self.dates_are_lifespan_check.setChecked(
            True if self.composer is None else self.composer.dates_are_lifespan
        )
        layout.addWidget(self.dates_are_lifespan_check, row, 1)
        row += 1

        layout.addWidget(
            QLabel(_("Dates uncertain"), self), row, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.dates_uncertain_check = QCheckBox(_("Dates are uncertain"), self)
        self.dates_uncertain_check.setChecked(
            True if self.composer is None else self.composer.dates_uncertain
        )
        layout.addWidget(self.dates_uncertain_check, row, 1)
        row += 1

        layout.addWidget(QLabel(_("Genres"), self), row, 0, Qt.AlignmentFlag.AlignLeft)
        self.genres_edit = QLineEdit(self)
        self.genres_edit.setText(
            "" if self.composer is None else ":".join(self.composer.genres)
        )
        self.genres_edit.setMinimumWidth(300)
        layout.addWidget(self.genres_edit, row, 1, 1, -1)
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
        self._notes_start_row = row
        row += 1

        self._add_note_widgets()

        btn_row = QHBoxLayout()
        self.save_btn = QPushButton(_("Save"), self)
        self.save_btn.clicked.connect(self.finalize_composer)
        btn_row.addWidget(self.save_btn)
        if not self.is_new:
            self.delete_btn = QPushButton(_("Delete"), self)
            self.delete_btn.clicked.connect(self.delete_composer)
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

        for r, (note_key, note_value) in enumerate(self.composer.notes.items()):
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
        self.composer.notes.pop(key, None)
        self.refresh()

    def add_note(self):
        self.composer.new_note(key=_("New note"))
        self.refresh()

    def refresh(self):
        self._add_note_widgets()

    def apply_fixes(self, fixes=None):
        if fixes:
            if "name" in fixes:
                self.new_composer_name_edit.setText(fixes["name"])
            if "indicators" in fixes:
                self.indicators_edit.setText(":".join(fixes["indicators"]))
            if "start_date" in fixes:
                self.start_date_edit.setText(fixes["start_date"])
            if "end_date" in fixes:
                self.end_date_edit.setText(fixes["end_date"])

    @require_password(ProtectedActions.EDIT_COMPOSERS)
    def finalize_composer(self, event=None):
        start_val = self.start_date_edit.text().strip()
        end_val = self.end_date_edit.text().strip()
        temp_composer = Composer(
            id=self.composer.id,
            name=self.new_composer_name_edit.text().strip(),
            indicators=[
                i.strip()
                for i in self.indicators_edit.text().split(":")
                if i.strip()
            ],
            start_date=int(start_val) if start_val else -1,
            end_date=int(end_val) if end_val else -1,
            dates_are_lifespan=self.dates_are_lifespan_check.isChecked(),
            dates_uncertain=self.dates_uncertain_check.isChecked(),
            genres=[
                g.strip() for g in self.genres_edit.text().split(":") if g.strip()
            ],
        )
        temp_composer.notes = {}
        for i in range(len(self.note_key_edits)):
            key = self.note_key_edits[i].text().strip()
            value = self.note_value_edits[i].text().strip()
            if key:
                temp_composer.notes[key] = value

        is_valid, error_message, fixes = temp_composer.validate()
        self.apply_fixes(fixes)

        if not is_valid:
            self.app_actions.alert(
                _("Validation Error"), error_message, kind="warning", master=self
            )
            return

        if not self.is_new and temp_composer.to_json() == self.composer.to_json():
            self.close()
            return

        self.composer = temp_composer
        success, error_msg = self.composers_window.composers_data.save_composer(
            self.composer
        )
        if success:
            if fixes:
                self.app_actions.alert(
                    _("Fixes applied"),
                    "\n".join(fixes.values()),
                    kind="info",
                    master=self,
                )
                time.sleep(2)
            self.close()
            if self.is_new:
                self.composers_window.set_composer(self.composer.name)
                self.composers_window.set_genre("")
                self.composers_window.do_search()
            else:
                self.composers_window._refresh_widgets()
        else:
            self.app_actions.alert(
                _("Error"),
                _("Failed to save composer:") + "\n\n" + error_msg,
                kind="error",
                master=self,
            )

    @require_password(ProtectedActions.EDIT_COMPOSERS)
    def delete_composer(self, event=None):
        res = self.app_actions.alert(
            _("Delete composer"),
            _(
                "Are you sure you want to delete {0}? This action cannot be undone."
            ).format(self.composer.name),
            kind="askokcancel",
            master=self,
        )
        if res:
            success, error_msg = self.composers_window.composers_data.delete_composer(
                self.composer
            )
            if success:
                self.close()
                self.composers_window._refresh_widgets()
            else:
                self.app_actions.alert(
                    _("Error"),
                    _("Failed to delete composer:") + "\n\n" + error_msg,
                    kind="error",
                    master=self,
                )


class ComposersWindow(SmartWindow):
    """Window to search composers data."""

    COL_0_WIDTH = 150
    top_level = None
    MAX_RESULTS = 200
    MAX_RECENT_SEARCHES = 200
    details_window = None
    recent_searches = []

    @staticmethod
    def load_recent_searches():
        ComposersWindow.recent_searches.clear()
        json_searches = app_info_cache.get("recent_composer_searches", [])
        if not isinstance(json_searches, list):
            return
        seen_searches = set()
        skip_count = 0
        for search_details in json_searches:
            search = ComposersDataSearch(**search_details)
            if search.is_valid() and search.stored_results_count > 0:
                if search not in seen_searches:
                    ComposersWindow.recent_searches.append(search)
                    seen_searches.add(search)
                else:
                    skip_count += 1
        if skip_count > 0:
            logger.warning("Skipped %s duplicate composer searches", skip_count)
        if len(ComposersWindow.recent_searches) > ComposersWindow.MAX_RECENT_SEARCHES:
            ComposersWindow.recent_searches = ComposersWindow.recent_searches[
                : ComposersWindow.MAX_RECENT_SEARCHES
            ]

    @staticmethod
    def store_recent_searches():
        seen_searches = set()
        unique_searches = []
        for search in ComposersWindow.recent_searches:
            if search.is_valid() and search.stored_results_count > 0:
                if search not in seen_searches:
                    unique_searches.append(search)
                    seen_searches.add(search)
        if len(unique_searches) > ComposersWindow.MAX_RECENT_SEARCHES:
            unique_searches = unique_searches[: ComposersWindow.MAX_RECENT_SEARCHES]
        json_searches = [s.get_dict() for s in unique_searches]
        app_info_cache.set("recent_composer_searches", json_searches)

    def __init__(self, master: QWidget, app_actions, dimensions: str = "600x600"):
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("Composer Search") + " - " + _("Search Composers"),
            geometry=dimensions,
            offset_x=50,
            offset_y=50,
        )
        ComposersWindow.top_level = self
        self.master = master
        self.app_actions = app_actions
        self.composers_data = ComposersData()
        self.composer_data_search = None
        self.has_closed = False

        self.setStyleSheet(AppStyle.get_stylesheet())
        self._build_ui()
        self.show()
        QTimer.singleShot(0, self.show_recent_searches)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        inner = QFrame(self)
        inner_layout = QGridLayout(inner)

        self.new_composer_btn = QPushButton(_("New Composer"), self)
        self.new_composer_btn.clicked.connect(self.new_composer)
        inner_layout.addWidget(
            QLabel(_("Search Composer"), self), 0, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.composer_entry = QLineEdit(self)
        self.composer_entry.setPlaceholderText("")
        self.composer_entry.returnPressed.connect(self.do_search)
        inner_layout.addWidget(self.composer_entry, 0, 1)

        inner_layout.addWidget(
            QLabel(_("Search Genre"), self), 1, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.genre_entry = QLineEdit(self)
        self.genre_entry.returnPressed.connect(self.do_search)
        inner_layout.addWidget(self.genre_entry, 1, 1)

        inner_layout.addWidget(
            QLabel(_("Start Date After"), self), 2, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.start_date_greater_edit = QLineEdit(self)
        self.start_date_greater_edit.returnPressed.connect(self.do_search)
        inner_layout.addWidget(self.start_date_greater_edit, 2, 1)

        inner_layout.addWidget(
            QLabel(_("Start Date Before"), self), 3, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.start_date_less_edit = QLineEdit(self)
        self.start_date_less_edit.returnPressed.connect(self.do_search)
        inner_layout.addWidget(self.start_date_less_edit, 3, 1)

        inner_layout.addWidget(
            QLabel(_("End Date After"), self), 4, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.end_date_greater_edit = QLineEdit(self)
        self.end_date_greater_edit.returnPressed.connect(self.do_search)
        inner_layout.addWidget(self.end_date_greater_edit, 4, 1)

        inner_layout.addWidget(
            QLabel(_("End Date Before"), self), 5, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.end_date_less_edit = QLineEdit(self)
        self.end_date_less_edit.returnPressed.connect(self.do_search)
        inner_layout.addWidget(self.end_date_less_edit, 5, 1)

        self.search_btn = QPushButton(_("Search"), self)
        self.search_btn.clicked.connect(self.do_search)
        inner_layout.addWidget(self.search_btn, 6, 0, 1, -1)

        inner_layout.addWidget(self.new_composer_btn, 0, 2)

        layout.addWidget(inner)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.results_widget = QWidget(self.scroll)
        self.results_layout = QGridLayout(self.results_widget)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll.setWidget(self.results_widget)
        layout.addWidget(self.scroll, 1)

        self.composer_list = []
        self.start_date_list = []
        self.end_date_list = []
        self.open_details_btn_list = []
        self.search_btn_list = []

    def set_composer(self, text: str):
        self.composer_entry.setText(text)

    def set_genre(self, text: str):
        self.genre_entry.setText(text)

    def show_recent_searches(self):
        self._clear_results_widgets()
        if len(ComposersWindow.recent_searches) == 0:
            lbl = QLabel(_("No recent searches found."), self.results_widget)
            self.results_layout.addWidget(lbl, 0, 1)
            self.composer_list.append(lbl)
            return
        for i, search in enumerate(ComposersWindow.recent_searches):
            if search is None:
                continue
            row = i + 1
            title_label = QLabel(search.get_title(), self.results_widget)
            title_label.setWordWrap(True)
            self.results_layout.addWidget(title_label, row, 1)
            self.composer_list.append(title_label)

            genre_label = QLabel(search.genre, self.results_widget)
            genre_label.setWordWrap(True)
            self.results_layout.addWidget(genre_label, row, 2)
            self.open_details_btn_list.append(genre_label)

            count_label = QLabel(
                search.get_readable_stored_results_count(), self.results_widget
            )
            self.results_layout.addWidget(count_label, row, 3)
            self.composer_list.append(count_label)

            search_btn = QPushButton(_("Search"), self.results_widget)
            self.search_btn_list.append(search_btn)
            self.results_layout.addWidget(search_btn, row, 4)
            search_btn.clicked.connect(
                lambda checked=False, s=search: self._run_stored_search(s)
            )

    def _run_stored_search(self, search: ComposersDataSearch):
        self.load_stored_search(search)
        self._do_search()

    def _clear_results_widgets(self):
        while self.results_layout.count():
            child = self.results_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.composer_list.clear()
        self.start_date_list.clear()
        self.end_date_list.clear()
        self.open_details_btn_list.clear()
        self.search_btn_list.clear()

    def load_stored_search(self, composer_data_search: ComposersDataSearch):
        self.composer_entry.setText(composer_data_search.composer)
        self.genre_entry.setText(composer_data_search.genre)
        self.start_date_greater_edit.setText(
            str(composer_data_search.start_date_greater_than)
            if composer_data_search.start_date_greater_than is not None
            else ""
        )
        self.start_date_less_edit.setText(
            str(composer_data_search.start_date_less_than)
            if composer_data_search.start_date_less_than is not None
            else ""
        )
        self.end_date_greater_edit.setText(
            str(composer_data_search.end_date_greater_than)
            if composer_data_search.end_date_greater_than is not None
            else ""
        )
        self.end_date_less_edit.setText(
            str(composer_data_search.end_date_less_than)
            if composer_data_search.end_date_less_than is not None
            else ""
        )
        self.composer_data_search = composer_data_search

    def _parse_date(self, date_str: str) -> int:
        if not date_str:
            return -1
        try:
            return int(date_str)
        except ValueError:
            return -1

    def do_search(self, event=None):
        composer = self.composer_entry.text().strip()
        genre = self.genre_entry.text().strip()
        start_date_greater = self._parse_date(self.start_date_greater_edit.text().strip())
        start_date_less = self._parse_date(self.start_date_less_edit.text().strip())
        end_date_greater = self._parse_date(self.end_date_greater_edit.text().strip())
        end_date_less = self._parse_date(self.end_date_less_edit.text().strip())

        if not any([composer, genre]) and sum(
            [start_date_greater, start_date_less, end_date_greater, end_date_less]
        ) == -4:
            self._refresh_widgets(add_results=False)
            self.show_recent_searches()
            return

        self.composer_data_search = ComposersDataSearch(
            composer=composer,
            genre=genre,
            max_results=ComposersWindow.MAX_RESULTS,
            start_date_greater_than=start_date_greater,
            start_date_less_than=start_date_less,
            end_date_greater_than=end_date_greater,
            end_date_less_than=end_date_less,
        )
        self._do_search()

    def _do_search(self, event=None):
        if self.composer_data_search is None:
            return
        self._refresh_widgets(add_results=False)
        self.composers_data.do_search(self.composer_data_search)
        ComposersWindow.recent_searches = [
            s for s in ComposersWindow.recent_searches if s != self.composer_data_search
        ]
        ComposersWindow.recent_searches.insert(0, self.composer_data_search)
        if len(ComposersWindow.recent_searches) > ComposersWindow.MAX_RECENT_SEARCHES:
            ComposersWindow.recent_searches = ComposersWindow.recent_searches[
                : ComposersWindow.MAX_RECENT_SEARCHES
            ]
        self._refresh_widgets()

    def add_widgets_for_results(self):
        if self.composer_data_search is None:
            return
        results = self.composer_data_search.get_results()
        logger.info("Found %s results", len(results))
        for i, composer in enumerate(results):
            row = i + 1
            composer_label = QLabel(composer.name, self.results_widget)
            self.results_layout.addWidget(composer_label, row, 0)
            self.composer_list.append(composer_label)

            start_date_text = ""
            if composer.start_date is not None and composer.start_date != -1:
                start_date_text = str(composer.start_date)
            start_date_label = QLabel(start_date_text, self.results_widget)
            self.results_layout.addWidget(start_date_label, row, 1)
            self.start_date_list.append(start_date_label)

            end_date_text = ""
            if composer.end_date is not None and composer.end_date != -1:
                end_date_text = str(composer.end_date)
            end_date_label = QLabel(end_date_text, self.results_widget)
            self.results_layout.addWidget(end_date_label, row, 2)
            self.end_date_list.append(end_date_label)

            details_btn = QPushButton(_("Details"), self.results_widget)
            self.open_details_btn_list.append(details_btn)
            self.results_layout.addWidget(details_btn, row, 3)
            details_btn.clicked.connect(
                lambda checked=False, c=composer: self.open_details(c)
            )

    @require_password(ProtectedActions.EDIT_COMPOSERS)
    def open_details(self, composer: Composer):
        if ComposersWindow.details_window is not None:
            try:
                ComposersWindow.details_window.close()
            except Exception:
                pass
        ComposersWindow.details_window = ComposerDetailsWindow(
            self, self, composer
        )
        ComposersWindow.details_window.show()

    @require_password(ProtectedActions.EDIT_COMPOSERS)
    def new_composer(self):
        if ComposersWindow.details_window is not None:
            try:
                ComposersWindow.details_window.close()
            except Exception:
                pass
        ComposersWindow.details_window = ComposerDetailsWindow(self, self, None)
        ComposersWindow.details_window.show()

    def _refresh_widgets(self, add_results: bool = True):
        self._clear_results_widgets()
        if add_results:
            self.add_widgets_for_results()

    def set_title(self, extra_text: str):
        self.setWindowTitle(_("Composer Search") + " - " + extra_text)

    def closeEvent(self, event):
        self.has_closed = True
        if ComposersWindow.top_level is self:
            ComposersWindow.top_level = None
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)
