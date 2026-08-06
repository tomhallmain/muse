"""
Musical forms search and details windows (PySide6).
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
from library_data.form import Form, FormsDataSearch, forms_data
from ui_qt.app_style import AppStyle
from ui_qt.auth.password_utils import require_password
from utils.app_info_cache import app_info_cache
from utils.globals import ProtectedActions
from utils.logging_setup import get_logger
from utils.translations import I18N

logger = get_logger(__name__)
_ = I18N._


class FormDetailsWindow(SmartWindow):
    """Window to show and edit musical form details."""

    top_level = None

    def __init__(
        self,
        master: QWidget,
        forms_window: "FormsWindow",
        form: Form = None,
        dimensions: str = "550x450",
    ):
        is_new = form is None
        form_obj = form if form is not None else Form("")
        title = (
            _("New Form")
            if is_new
            else _("Modify Form: {0}").format(form_obj.name)
        )
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=title,
            geometry=dimensions,
            offset_x=50,
            offset_y=50,
        )
        FormDetailsWindow.top_level = self
        self.master = master
        self.forms_window = forms_window
        self.app_actions = forms_window.app_actions
        self.form = form_obj
        self.is_new = is_new
        self.original_name = None if is_new else form_obj.name

        self.setStyleSheet(AppStyle.get_stylesheet())

        self.note_key_edits = []
        self.note_value_edits = []
        self.note_delete_btns = []

        self._build_ui()

    def _build_ui(self):
        layout = QGridLayout(self)

        row = 0
        layout.addWidget(
            QLabel(_("Modify Form"), self), row, 0, 1, -1, Qt.AlignmentFlag.AlignLeft
        )
        row += 1

        layout.addWidget(QLabel(_("Name"), self), row, 0, Qt.AlignmentFlag.AlignLeft)
        self.name_edit = QLineEdit(self)
        self.name_edit.setText("" if self.is_new else str(self.form.name or ""))
        self.name_edit.setMinimumWidth(300)
        layout.addWidget(self.name_edit, row, 1, 1, -1)
        row += 1

        layout.addWidget(
            QLabel(_("Transliterations"), self), row, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.transliterations_edit = QLineEdit(self)
        self.transliterations_edit.setPlaceholderText(
            _("colon-separated, e.g. sonata:sonate:suonata")
        )
        self.transliterations_edit.setText(
            ""
            if self.is_new
            else ":".join(str(t) for t in (self.form.transliterations or []) if t)
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
        self.save_btn.clicked.connect(self.finalize_form)
        btn_row.addWidget(self.save_btn)
        if not self.is_new:
            self.delete_btn = QPushButton(_("Delete"), self)
            self.delete_btn.clicked.connect(self.delete_form)
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

        for r, (note_key, note_value) in enumerate(self.form.notes.items()):
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
        self.form.notes.pop(key, None)
        self.refresh()

    def add_note(self):
        self.form.new_note(key=_("New note"))
        self.refresh()

    def refresh(self):
        self._add_note_widgets()

    @require_password(ProtectedActions.EDIT_FORMS)
    def finalize_form(self, event=None):
        temp_form = Form(
            name=self.name_edit.text().strip(),
            transliterations=[
                t.strip()
                for t in self.transliterations_edit.text().split(":")
                if t.strip()
            ],
        )
        temp_form.notes = {}
        for i in range(len(self.note_key_edits)):
            key = self.note_key_edits[i].text().strip()
            value = self.note_value_edits[i].text().strip()
            if key:
                temp_form.notes[key] = value

        is_valid, error_message, fixes = temp_form.validate()
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
            and temp_form.to_json() == self.form.to_json()
            and self.original_name == temp_form.name
        ):
            self.close()
            return

        if (
            self.is_new
            and temp_form.name in self.forms_window.forms_data._forms
        ):
            self.app_actions.alert(
                _("Validation Error"),
                _("A form named \"{0}\" already exists").format(temp_form.name),
                kind="warning",
                master=self,
            )
            return

        self.form = temp_form
        success, error_msg = self.forms_window.forms_data.save_form(
            self.form, original_name=self.original_name
        )
        if success:
            self.close()
            if self.is_new:
                self.forms_window.set_form_query(self.form.name)
                self.forms_window.do_search()
            else:
                self.forms_window._refresh_widgets()
        else:
            self.app_actions.alert(
                _("Error"),
                _("Failed to save form:") + "\n\n" + error_msg,
                kind="error",
                master=self,
            )

    @require_password(ProtectedActions.EDIT_FORMS)
    def delete_form(self, event=None):
        res = self.app_actions.alert(
            _("Delete form"),
            _(
                "Are you sure you want to delete {0}? This action cannot be undone."
            ).format(self.form.name),
            kind="askokcancel",
            master=self,
        )
        if res:
            success, error_msg = self.forms_window.forms_data.delete_form(self.form)
            if success:
                self.close()
                self.forms_window._refresh_widgets()
            else:
                self.app_actions.alert(
                    _("Error"),
                    _("Failed to delete form:") + "\n\n" + error_msg,
                    kind="error",
                    master=self,
                )


class FormsWindow(SmartWindow):
    """Window to search and edit musical forms vocabulary."""

    top_level = None
    MAX_RESULTS = 500
    MAX_RECENT_SEARCHES = 50
    details_window = None
    recent_searches = []

    @staticmethod
    def load_recent_searches():
        FormsWindow.recent_searches.clear()
        json_searches = app_info_cache.get("recent_form_searches", [])
        if not isinstance(json_searches, list):
            return
        for search_details in json_searches:
            try:
                search = FormsDataSearch(**search_details)
            except TypeError:
                continue
            if search.stored_results_count > 0:
                FormsWindow.recent_searches.append(search)
        if len(FormsWindow.recent_searches) > FormsWindow.MAX_RECENT_SEARCHES:
            FormsWindow.recent_searches = FormsWindow.recent_searches[
                : FormsWindow.MAX_RECENT_SEARCHES
            ]

    @staticmethod
    def store_recent_searches():
        unique = []
        seen = set()
        for search in FormsWindow.recent_searches:
            if search.form in seen:
                continue
            if search.stored_results_count > 0:
                unique.append(search)
                seen.add(search.form)
        if len(unique) > FormsWindow.MAX_RECENT_SEARCHES:
            unique = unique[: FormsWindow.MAX_RECENT_SEARCHES]
        app_info_cache.set(
            "recent_form_searches", [s.get_dict() for s in unique]
        )

    def __init__(self, master: QWidget, app_actions, dimensions: str = "650x600"):
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("Form Search") + " - " + _("Search Forms"),
            geometry=dimensions,
            offset_x=50,
            offset_y=50,
        )
        FormsWindow.top_level = self
        self.master = master
        self.app_actions = app_actions
        self.forms_data = forms_data
        self.forms_data.reload()
        self.form_data_search = None
        self.has_closed = False

        self.setStyleSheet(AppStyle.get_stylesheet())
        self._build_ui()
        self.show()
        QTimer.singleShot(0, self.show_recent_searches)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        inner = QFrame(self)
        inner_layout = QGridLayout(inner)

        inner_layout.addWidget(
            QLabel(_("Search Form"), self), 0, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.form_entry = QLineEdit(self)
        self.form_entry.setPlaceholderText("")
        self.form_entry.returnPressed.connect(self.do_search)
        inner_layout.addWidget(self.form_entry, 0, 1)

        self.search_btn = QPushButton(_("Search"), self)
        self.search_btn.clicked.connect(self.do_search)
        inner_layout.addWidget(self.search_btn, 1, 0, 1, 2)

        self.new_form_btn = QPushButton(_("New Form"), self)
        self.new_form_btn.clicked.connect(self.new_form)
        inner_layout.addWidget(self.new_form_btn, 0, 2)

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

    def set_form_query(self, text: str):
        self.form_entry.setText(text)

    def show_recent_searches(self):
        self._clear_results_widgets()
        if len(FormsWindow.recent_searches) == 0:
            lbl = QLabel(_("No recent searches found."), self.results_widget)
            self.results_layout.addWidget(lbl, 0, 1)
            self.name_labels.append(lbl)
            return
        for i, search in enumerate(FormsWindow.recent_searches):
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

    def _run_stored_search(self, search: FormsDataSearch):
        self.form_entry.setText(search.form)
        self.form_data_search = search
        self._do_search()

    def _list_all(self):
        """Browse all forms in the UI without going through search matching."""
        self.form_entry.setText("")
        self._refresh_widgets(add_results=False)
        self.form_data_search = FormsDataSearch(
            form="",
            max_results=FormsWindow.MAX_RESULTS,
        )
        self.form_data_search.results = self.forms_data.get_all_forms()[
            : FormsWindow.MAX_RESULTS
        ]
        self.form_data_search.set_stored_results_count()
        self.setWindowTitle(
            _("Form Search") + " - " + self.form_data_search.get_title()
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
        query = self.form_entry.text().strip()
        if not query:
            self._refresh_widgets(add_results=False)
            self.show_recent_searches()
            return

        self.form_data_search = FormsDataSearch(
            form=query,
            max_results=FormsWindow.MAX_RESULTS,
        )
        self._do_search()

    def _do_search(self):
        if self.form_data_search is None:
            return
        self._refresh_widgets(add_results=False)
        self.forms_data.do_search(self.form_data_search)
        FormsWindow.recent_searches = [
            s for s in FormsWindow.recent_searches if s != self.form_data_search
        ]
        FormsWindow.recent_searches.insert(0, self.form_data_search)
        if len(FormsWindow.recent_searches) > FormsWindow.MAX_RECENT_SEARCHES:
            FormsWindow.recent_searches = FormsWindow.recent_searches[
                : FormsWindow.MAX_RECENT_SEARCHES
            ]
        self.setWindowTitle(
            _("Form Search") + " - " + self.form_data_search.get_title()
        )
        self._refresh_widgets()

    def add_widgets_for_results(self):
        if self.form_data_search is None:
            return
        results = self.form_data_search.get_results()
        logger.info("Found %s form results", len(results))
        for i, form in enumerate(results):
            row = i + 1
            name_label = QLabel(form.name, self.results_widget)
            self.results_layout.addWidget(name_label, row, 0)
            self.name_labels.append(name_label)

            translit_text = ", ".join(form.transliterations or [])
            translit_label = QLabel(translit_text, self.results_widget)
            translit_label.setWordWrap(True)
            self.results_layout.addWidget(translit_label, row, 1)
            self.translit_labels.append(translit_label)

            details_btn = QPushButton(_("Details"), self.results_widget)
            self.details_btns.append(details_btn)
            self.results_layout.addWidget(details_btn, row, 2)
            details_btn.clicked.connect(
                lambda checked=False, f=form: self.open_details(f)
            )

    @require_password(ProtectedActions.EDIT_FORMS)
    def open_details(self, form: Form):
        if FormsWindow.details_window is not None:
            try:
                FormsWindow.details_window.close()
            except Exception:
                pass
        FormsWindow.details_window = FormDetailsWindow(self, self, form)
        FormsWindow.details_window.show()

    @require_password(ProtectedActions.EDIT_FORMS)
    def new_form(self):
        if FormsWindow.details_window is not None:
            try:
                FormsWindow.details_window.close()
            except Exception:
                pass
        FormsWindow.details_window = FormDetailsWindow(self, self, None)
        FormsWindow.details_window.show()

    def _refresh_widgets(self, add_results: bool = True):
        self._clear_results_widgets()
        if add_results:
            self.add_widgets_for_results()

    def closeEvent(self, event):
        self.has_closed = True
        if FormsWindow.top_level is self:
            FormsWindow.top_level = None
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)
