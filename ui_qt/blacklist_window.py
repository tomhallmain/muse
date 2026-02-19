"""
Blacklist management window (PySide6).
Port of ui/blacklist_window.py; logic preserved, UI uses Qt.
"""
from typing import Callable, Optional

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QCheckBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFileDialog,
    QMessageBox,
    QApplication,
    QWidget,
    QAbstractItemView,
    QComboBox,
    QPlainTextEdit,
)
from PySide6.QtCore import Qt

from lib.multi_display_qt import SmartWindow
from library_data.blacklist import BlacklistItem, Blacklist
from ui_qt.app_style import AppStyle
from ui_qt.auth.password_utils import require_password
from utils.globals import ProtectedActions, BlacklistMode
from utils.app_info_cache import app_info_cache
from utils.translations import I18N

_ = I18N._

COL_0_WIDTH = 600


class BlacklistModifyWindow(SmartWindow):
    """Dialog for adding or editing a single blacklist item."""

    top_level = None

    def __init__(
        self,
        master: QWidget,
        refresh_callback: Callable,
        blacklist_item: Optional[BlacklistItem],
        app_actions,
        dimensions: str = "600x400",
    ):
        is_new_item = blacklist_item is None
        item_for_title = (
            BlacklistItem("", enabled=True, use_regex=False, use_word_boundary=True, use_space_as_optional_nonword=True)
            if is_new_item
            else blacklist_item
        )
        title = (
            _("New Blacklist Item")
            if is_new_item
            else _("Modify Blacklist Item: {0}").format(item_for_title.string)
        )
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=title,
            geometry=dimensions,
            offset_x=50,
            offset_y=50,
        )
        BlacklistModifyWindow.top_level = self
        self.master = master
        self.refresh_callback = refresh_callback
        self.app_actions = app_actions
        self.is_new_item = is_new_item
        self.original_string = "" if is_new_item else blacklist_item.string
        self.blacklist_item: BlacklistItem = item_for_title

        self.original_values = {
            "string": self.original_string,
            "enabled": self.blacklist_item.enabled,
            "use_regex": self.blacklist_item.use_regex,
            "use_word_boundary": self.blacklist_item.use_word_boundary,
            "exception_pattern": self.blacklist_item.exception_pattern,
            "use_space_as_optional_nonword": self.blacklist_item.use_space_as_optional_nonword,
        }

        self.setStyleSheet(AppStyle.get_stylesheet())
        self._build_ui()

    def _build_ui(self):
        layout = QGridLayout(self)

        row = 0
        layout.addWidget(
            QLabel(_("Blacklist String"), self), row, 0, 1, -1, Qt.AlignmentFlag.AlignLeft
        )
        row += 1
        self.new_string_edit = QLineEdit(self)
        self.new_string_edit.setPlaceholderText("")
        self.new_string_edit.setText(self.original_string)
        self.new_string_edit.setMinimumWidth(400)
        layout.addWidget(self.new_string_edit, row, 0, 1, -1)
        row += 1

        self.enabled_checkbox = QCheckBox(_("Enabled"), self)
        self.enabled_checkbox.setChecked(self.blacklist_item.enabled)
        layout.addWidget(self.enabled_checkbox, row, 0)
        row += 1

        self.regex_checkbox = QCheckBox(_("Use glob-based regex"), self)
        self.regex_checkbox.setChecked(self.blacklist_item.use_regex)
        layout.addWidget(self.regex_checkbox, row, 0)
        row += 1

        self.word_boundary_checkbox = QCheckBox(_("Use word boundary matching"), self)
        self.word_boundary_checkbox.setChecked(self.blacklist_item.use_word_boundary)
        layout.addWidget(self.word_boundary_checkbox, row, 0)
        row += 1

        self.space_as_optional_nonword_checkbox = QCheckBox(
            _("Convert spaces to optional non-word characters"), self
        )
        self.space_as_optional_nonword_checkbox.setChecked(
            getattr(self.blacklist_item, "use_space_as_optional_nonword", False)
        )
        layout.addWidget(self.space_as_optional_nonword_checkbox, row, 0)
        row += 1

        layout.addWidget(
            QLabel(
                _("Exception Pattern (optional regex to unfilter tags)"), self
            ),
            row,
            0,
            1,
            -1,
            Qt.AlignmentFlag.AlignLeft,
        )
        row += 1
        self.exception_pattern_edit = QLineEdit(self)
        self.exception_pattern_edit.setText(
            getattr(self.blacklist_item, "exception_pattern", "") or ""
        )
        self.exception_pattern_edit.setMinimumWidth(400)
        layout.addWidget(self.exception_pattern_edit, row, 0, 1, -1)
        row += 1

        self.done_btn = QPushButton(_("Done"), self)
        self.done_btn.clicked.connect(self.finalize_blacklist_item)
        layout.addWidget(self.done_btn, row, 0)

    def _has_changes(self):
        string = self.new_string_edit.text().strip()
        if self.is_new_item:
            return string != ""
        current_values = {
            "string": string,
            "enabled": self.enabled_checkbox.isChecked(),
            "use_regex": self.regex_checkbox.isChecked(),
            "use_word_boundary": self.word_boundary_checkbox.isChecked(),
            "use_space_as_optional_nonword": self.space_as_optional_nonword_checkbox.isChecked(),
            "exception_pattern": self.exception_pattern_edit.text().strip(),
        }
        return current_values != self.original_values

    def _validate_and_get_item(self):
        string = self.new_string_edit.text().strip()
        if not string:
            self.app_actions.alert(
                _("Error"),
                _("Blacklist string cannot be empty."),
                kind="error",
                master=self,
            )
            return None

        exception_pattern = self.exception_pattern_edit.text().strip()
        if not exception_pattern:
            exception_pattern = None

        return BlacklistItem(
            string=string,
            enabled=self.enabled_checkbox.isChecked(),
            use_regex=self.regex_checkbox.isChecked(),
            use_word_boundary=self.word_boundary_checkbox.isChecked(),
            use_space_as_optional_nonword=self.space_as_optional_nonword_checkbox.isChecked(),
            exception_pattern=exception_pattern,
        )

    def finalize_blacklist_item(self):
        if not self._has_changes():
            self.close()
            if self.app_actions:
                self.app_actions.toast(_("No changes were made"))
            return

        blacklist_item = self._validate_and_get_item()
        if blacklist_item is None:
            return

        self._close_override_check = True
        self.close()
        self.refresh_callback(blacklist_item, self.is_new_item, self.original_string)

    def closeEvent(self, event):
        if getattr(self, "_close_override_check", False):
            event.accept()
            return
        if self._has_changes():
            response = self.app_actions.alert(
                _("Unsaved Changes"),
                _("Do you want to save changes before closing?"),
                kind="askyesnocancel",
                master=self,
            )
            if response == QMessageBox.StandardButton.Yes:
                self.finalize_blacklist_item()
                event.accept()
            elif response == QMessageBox.StandardButton.No:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


class BlacklistWindow(SmartWindow):
    """Main blacklist management window."""

    top_level = None
    blacklist_modify_window = None
    recent_items = []
    last_set_item = None
    item_history = []
    MAX_ITEMS = 50
    MAX_HEIGHT = 900
    N_ITEMS_CUTOFF = 30

    BLACKLIST_CACHE_KEY = "tag_blacklist"
    DEFAULT_BLACKLIST_KEY = "blacklist_user_confirmed_non_default"
    BLACKLIST_MODE_KEY = "blacklist_mode"
    BLACKLIST_SILENT_KEY = "blacklist_silent_removal"

    warning_text = _(
        """WARNING: Are you sure you want to reveal the blacklist concepts? These concepts are damaging or offensive and WILL cause you severe psychological harm. Do not, under any circumstances, reveal these concepts to minors.

If you are young, not sure, or even an adult, click the close button on this window now and do something fun instead."""
    )

    @staticmethod
    def set_blacklist():
        user_confirmed_non_default = app_info_cache.get(
            BlacklistWindow.DEFAULT_BLACKLIST_KEY, default_val=False
        )
        mode_str = app_info_cache.get(
            BlacklistWindow.BLACKLIST_MODE_KEY,
            default_val=str(Blacklist.get_blacklist_mode()),
        )
        try:
            mode = BlacklistMode(mode_str)
        except Exception:
            pass
        Blacklist.set_blacklist_mode(mode)
        silent = app_info_cache.get(BlacklistWindow.BLACKLIST_SILENT_KEY, default_val=False)
        Blacklist.set_blacklist_silent_removal(silent)

        if not user_confirmed_non_default:
            try:
                Blacklist.decrypt_blacklist()
                return
            except Exception:
                pass

        raw_blacklist = app_info_cache.get(
            BlacklistWindow.BLACKLIST_CACHE_KEY, default_val=[]
        )
        Blacklist.set_blacklist(raw_blacklist)

    @staticmethod
    def store_blacklist():
        Blacklist.save_cache()
        blacklist_dicts = [item.to_dict() for item in Blacklist.get_items()]
        app_info_cache.set(BlacklistWindow.BLACKLIST_CACHE_KEY, blacklist_dicts)
        app_info_cache.set(
            BlacklistWindow.BLACKLIST_MODE_KEY, str(Blacklist.get_blacklist_mode())
        )
        app_info_cache.set(
            BlacklistWindow.BLACKLIST_SILENT_KEY,
            Blacklist.get_blacklist_silent_removal(),
        )

    @staticmethod
    def mark_user_confirmed_non_default():
        app_info_cache.set(BlacklistWindow.DEFAULT_BLACKLIST_KEY, True)

    @staticmethod
    def is_in_default_state():
        return not app_info_cache.get(
            BlacklistWindow.DEFAULT_BLACKLIST_KEY, default_val=False
        )

    @staticmethod
    def get_history_item(start_index=0):
        item = None
        for i in range(len(BlacklistWindow.item_history)):
            if i < start_index:
                continue
            item = BlacklistWindow.item_history[i]
            break
        return item

    @staticmethod
    def update_history(item):
        if (
            len(BlacklistWindow.item_history) > 0
            and item == BlacklistWindow.item_history[0]
        ):
            return
        BlacklistWindow.item_history.insert(0, item)
        if len(BlacklistWindow.item_history) > BlacklistWindow.MAX_ITEMS:
            del BlacklistWindow.item_history[-1]

    @staticmethod
    def get_geometry(is_gui=True):
        return (1000, 560)

    def __init__(self, master: QWidget, app_actions):
        w, h = BlacklistWindow.get_geometry(is_gui=True)
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("Blacklist"),
            geometry=f"{w}x{h}",
            offset_x=50,
            offset_y=50,
        )
        BlacklistWindow.top_level = self
        self.master = master
        self.app_actions = app_actions
        self.base_item = ""
        self.filter_text = ""
        self.filtered_items = Blacklist.get_items()[:]
        self.concepts_revealed = False

        self.setStyleSheet(AppStyle.get_stylesheet())
        self._build_ui()
        self.show()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Header
        header = QHBoxLayout()
        header.addWidget(QLabel(_("Global Settings:"), self))
        settings_label = header.itemAt(header.count() - 1).widget()
        if settings_label:
            settings_label.setToolTip(
                _("These settings affect how the blacklist is applied globally.")
            )

        self.mode_combo = QComboBox(self)
        self.mode_combo.addItems(BlacklistMode.display_values())
        idx = self.mode_combo.findText(Blacklist.get_blacklist_mode().display())
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)
        self.mode_combo.setToolTip(
            _("Choose how the blacklist is enforced: block, warn, or allow.")
        )
        self.mode_combo.currentTextChanged.connect(self._on_mode_change)
        header.addWidget(self.mode_combo)

        self.silent_checkbox = QCheckBox(_("Silent Removal"), self)
        self.silent_checkbox.setChecked(Blacklist.get_blacklist_silent_removal())
        self.silent_checkbox.setToolTip(
            _("If enabled, blacklisted words are removed silently without notification.")
        )
        self.silent_checkbox.toggled.connect(self._on_silent_change)
        header.addWidget(self.silent_checkbox)

        layout.addLayout(header)

        # Row: Import, Export, Load Default, Preview
        row1 = QHBoxLayout()
        self.import_btn = QPushButton(_("Import"), self)
        self.import_btn.clicked.connect(self.import_blacklist)
        row1.addWidget(self.import_btn)
        self.export_btn = QPushButton(_("Export"), self)
        self.export_btn.clicked.connect(self.export_blacklist)
        row1.addWidget(self.export_btn)
        self.load_default_btn = QPushButton(_("Load Default"), self)
        self.load_default_btn.clicked.connect(self.load_default_blacklist)
        row1.addWidget(self.load_default_btn)
        self.preview_btn = QPushButton(_("Preview"), self)
        self.preview_btn.clicked.connect(self.open_preview_window)
        row1.addWidget(self.preview_btn)
        layout.addLayout(row1)

        # Row: Add, Clear
        row2 = QHBoxLayout()
        self.add_item_btn = QPushButton(_("Add to blacklist"), self)
        self.add_item_btn.clicked.connect(self.add_new_item)
        row2.addWidget(self.add_item_btn)
        self.clear_blacklist_btn = QPushButton(_("Clear items"), self)
        self.clear_blacklist_btn.clicked.connect(self.clear_items)
        row2.addWidget(self.clear_blacklist_btn)
        layout.addLayout(row2)

        # Content (stacked: either reveal button or table)
        self.content_widget = QWidget(self)
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.content_widget, 1)

        self._add_blacklist_widgets()

    def _get_selected_blacklist_item(self):
        if not getattr(self, "table", None):
            return None
        row = self.table.currentRow()
        if row < 0 or row >= len(self.filtered_items):
            return None
        return self.filtered_items[row]

    def _add_blacklist_widgets(self):
        # Clear content
        while self.content_layout.count():
            child = self.content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self.table = None

        if not self.concepts_revealed:
            if Blacklist.is_empty():
                label_text = _(
                    "No blacklist items found. You can add items by clicking the 'Add to blacklist' button below, or load the default blacklist."
                )
            else:
                label_text = _("Click below to reveal blacklist concepts.")
            if BlacklistWindow.is_in_default_state():
                label_text += "\n\n" + _(
                    "Default blacklist is loaded. You can load your own blacklist by editing the existing concepts, clearing the blacklist and adding your own, or importing concepts from a file."
                )
            lbl = QLabel(label_text, self.content_widget)
            lbl.setWordWrap(True)
            self.content_layout.addWidget(lbl)
            if Blacklist.is_empty():
                return

            self.reveal_concepts_btn = QPushButton(_("Reveal Concepts"), self.content_widget)
            self.reveal_concepts_btn.clicked.connect(self.reveal_concepts)
            self.content_layout.addWidget(self.reveal_concepts_btn)
            return

        # Table of items
        self.table = QTableWidget(self.content_widget)
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels([_("Item"), _("Enabled")])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        for i, item in enumerate(self.filtered_items):
            self.table.insertRow(i)
            self.table.setItem(i, 0, QTableWidgetItem(item.display_text()))
            enabled_str = "✓" if item.enabled else _("Disabled")
            self.table.setItem(i, 1, QTableWidgetItem(enabled_str))

        self.table.cellDoubleClicked.connect(self._on_table_double_click)
        self.content_layout.addWidget(self.table)

        actions = QHBoxLayout()
        mod_btn = QPushButton(_("Modify"), self.content_widget)
        mod_btn.clicked.connect(self._modify_selected)
        actions.addWidget(mod_btn)
        rem_btn = QPushButton(_("Remove"), self.content_widget)
        rem_btn.clicked.connect(self._remove_selected)
        actions.addWidget(rem_btn)
        tog_btn = QPushButton(_("Toggle"), self.content_widget)
        tog_btn.clicked.connect(self._toggle_selected)
        actions.addWidget(tog_btn)
        self.content_layout.addLayout(actions)

    def _on_table_double_click(self, row, _col):
        if 0 <= row < len(self.filtered_items):
            self.modify_item(None, self.filtered_items[row])

    def _modify_selected(self):
        item = self._get_selected_blacklist_item()
        if item is None:
            self.app_actions.toast(_("Select an item first"))
            return
        self.modify_item(None, item)

    def _remove_selected(self):
        item = self._get_selected_blacklist_item()
        if item is None:
            self.app_actions.toast(_("Select an item first"))
            return
        self.remove_item(None, item)

    def _toggle_selected(self):
        item = self._get_selected_blacklist_item()
        if item is None:
            self.app_actions.toast(_("Select an item first"))
            return
        self.toggle_item(None, item=item, button=None)

    @require_password(ProtectedActions.EDIT_BLACKLIST)
    def open_blacklist_modify_window(
        self, event=None, blacklist_item: Optional[BlacklistItem] = None
    ):
        if BlacklistWindow.blacklist_modify_window is not None:
            try:
                BlacklistWindow.blacklist_modify_window.close()
            except Exception:
                pass
        BlacklistWindow.blacklist_modify_window = BlacklistModifyWindow(
            self, self.refresh_blacklist_item, blacklist_item, self.app_actions
        )
        BlacklistWindow.blacklist_modify_window.show()

    @require_password(ProtectedActions.EDIT_BLACKLIST)
    def open_preview_window(self, event=None):
        try:
            from ui_qt.blacklist_preview_window import BlacklistPreviewWindow
            BlacklistPreviewWindow(self, self.app_actions)
        except ImportError:
            self.app_actions.toast(_("Preview window not yet available."))

    def refresh_blacklist_item(
        self, blacklist_item: BlacklistItem, is_new_item: bool, original_string: str
    ):
        BlacklistWindow.update_history(blacklist_item)
        BlacklistWindow.mark_user_confirmed_non_default()

        if is_new_item:
            Blacklist.add_item(blacklist_item)
        else:
            original_item = None
            for item in Blacklist.get_items():
                if item.string == original_string:
                    original_item = item
                    break
            if original_item:
                Blacklist.remove_item(original_item, do_save=False)
            Blacklist.add_item(blacklist_item)

        self.set_blacklist_item(blacklist_item=blacklist_item, is_new_item=is_new_item)

    @require_password(ProtectedActions.EDIT_BLACKLIST)
    def add_new_item(self, event=None):
        self.open_blacklist_modify_window(blacklist_item=None)

    @require_password(ProtectedActions.EDIT_BLACKLIST)
    def modify_item(self, event=None, item=None):
        if item is None:
            return
        self.open_blacklist_modify_window(blacklist_item=item)

    def set_blacklist_item(
        self, event=None, blacklist_item=None, is_new_item=False
    ):
        BlacklistWindow.update_history(blacklist_item)
        BlacklistWindow.last_set_item = blacklist_item
        self.refresh()

        if is_new_item:
            self.app_actions.toast(
                _("Added item to blacklist: {0}").format(blacklist_item.string)
            )
        else:
            self.app_actions.toast(
                _("Modified blacklist item: {0}").format(blacklist_item.string)
            )

    def get_item(self, item: Optional[BlacklistItem] = None):
        if item is not None:
            response = self.app_actions.alert(
                _("Remove blacklist item"),
                _("Are you sure you want to remove this blacklist concept?\n\n{0}").format(
                    item.string
                ),
                kind="askyesno",
                master=self,
            )
            if not response:
                return None
            Blacklist.remove_item(item)
            self.refresh()
            BlacklistWindow.mark_user_confirmed_non_default()
            self.app_actions.toast(_("Removed item: {0}").format(item.string))
            return None
        return ""

    def handle_item(self, event=None, item: Optional[BlacklistItem] = None):
        item = self.get_item(item)
        if item is None:
            return
        if isinstance(item, str) and item.strip() == "":
            self.app_actions.alert(
                _("Warning"),
                _("Please enter a string to add to the blacklist."),
                kind="warning",
                master=self,
            )
            return

        Blacklist.add_to_blacklist(item, enabled=True, use_regex=False)
        self.refresh()
        BlacklistWindow.mark_user_confirmed_non_default()
        self.app_actions.toast(_("Added item to blacklist: {0}").format(item))
        return item

    @require_password(ProtectedActions.EDIT_BLACKLIST)
    def remove_item(self, event=None, item: Optional[BlacklistItem] = None):
        result = self.handle_item(item=item)
        if result is None:
            return
        BlacklistWindow.update_history(result)
        BlacklistWindow.last_set_item = result
        self.close()

    def keyPressEvent(self, event):
        # Don't filter when typing in a line edit or text edit
        focus = QApplication.focusWidget()
        if focus and isinstance(focus, (QLineEdit, QPlainTextEdit)):
            super().keyPressEvent(event)
            return

        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            self.add_new_item()
            event.accept()
            return

        mods = event.modifiers()
        if (mods & Qt.KeyboardModifier.ControlModifier) or (
            mods & Qt.KeyboardModifier.AltModifier
        ):
            super().keyPressEvent(event)
            return

        if key == Qt.Key.Key_Backspace:
            if len(self.filter_text) > 0:
                self.filter_text = self.filter_text[:-1]
        elif event.text():
            self.filter_text += event.text()
        else:
            if key == Qt.Key.Key_Down:
                if self.filtered_items:
                    self.filtered_items = self.filtered_items[1:] + [
                        self.filtered_items[0]
                    ]
                self._add_blacklist_widgets()
                event.accept()
                return
            if key == Qt.Key.Key_Up:
                if self.filtered_items:
                    self.filtered_items = [self.filtered_items[-1]] + self.filtered_items[:-1]
                self._add_blacklist_widgets()
                event.accept()
                return
            super().keyPressEvent(event)
            return

        if self.filter_text.strip() == "":
            self.filtered_items = Blacklist.get_items()[:]
        else:
            temp = []
            for item in Blacklist.get_items():
                if item.string == self.filter_text:
                    temp.append(item)
            for item in Blacklist.get_items():
                if item not in temp and item.string.startswith(self.filter_text):
                    temp.append(item)
            for item in Blacklist.get_items():
                if item not in temp and (
                    f" {self.filter_text}" in item.string.lower()
                    or f"_{self.filter_text}" in item.string.lower()
                ):
                    temp.append(item)
            self.filtered_items = temp[:]

        self._add_blacklist_widgets()
        event.accept()

    def do_action(self, event=None):
        self.add_new_item()

    @require_password(ProtectedActions.EDIT_BLACKLIST, ProtectedActions.REVEAL_BLACKLIST_CONCEPTS)
    def clear_items(self, event=None):
        response = self.app_actions.alert(
            _("Confirm Clear Blacklist"),
            _(
                "Are you sure you want to clear all blacklist items?\n\n"
                "⚠️ WARNING: This action cannot be undone!\n"
                "• All blacklist items will be permanently deleted\n"
                "• The blacklist helps improve image output quality\n"
                "• You will need to rebuild your blacklist from scratch\n\n"
                "Do you want to continue?"
            ),
            kind="askyesno",
            master=self,
        )
        if not response:
            return
        Blacklist.clear()
        self.filtered_items.clear()
        self.refresh()
        BlacklistWindow.mark_user_confirmed_non_default()
        self.app_actions.toast(_("Cleared item blacklist"))

    def refresh(self, refresh_list: bool = True):
        if refresh_list:
            self.filtered_items = Blacklist.get_items()[:]
        self._add_blacklist_widgets()

    def closeEvent(self, event):
        if BlacklistWindow.top_level is self:
            BlacklistWindow.top_level = None
        event.accept()

    @require_password(ProtectedActions.EDIT_BLACKLIST)
    def toggle_item(
        self, event=None, item: Optional[BlacklistItem] = None, button=None
    ):
        if item is None:
            return
        for blacklist_item in Blacklist.get_items():
            if blacklist_item == item:
                blacklist_item.enabled = not blacklist_item.enabled
                new_text = "✓" if blacklist_item.enabled else _("Disabled")
                if self.table and item in self.filtered_items:
                    idx = self.filtered_items.index(item)
                    self.table.item(idx, 1).setText(new_text)
                self.store_blacklist()
                self.app_actions.toast(
                    _('Item "{0}" is now {1}').format(
                        blacklist_item.string,
                        _("enabled") if blacklist_item.enabled else _("disabled"),
                    )
                )
                break

    @require_password(
        ProtectedActions.REVEAL_BLACKLIST_CONCEPTS,
        custom_text=warning_text,
        allow_unauthenticated=False,
    )
    def reveal_concepts(self, event=None):
        self.concepts_revealed = True
        self.refresh()
        self.app_actions.toast(_("Concepts revealed"))

    @require_password(ProtectedActions.EDIT_BLACKLIST)
    def load_default_blacklist(self, event=None):
        if not self.is_in_default_state() and len(Blacklist.get_items()) > 0:
            response = self.app_actions.alert(
                _("Confirm Load Default Blacklist"),
                _(
                    "Are you sure you want to load the default blacklist?\n\n"
                    "⚠️ WARNING: This will erase your current blacklist and replace it with the default items.\n"
                    "• All your current blacklist items will be permanently deleted\n"
                    "• You will need to rebuild your blacklist from scratch if you want to restore it later\n\n"
                    "Do you want to continue?"
                ),
                kind="askyesno",
                master=self,
            )
            if not response:
                return
        try:
            Blacklist.decrypt_blacklist()
            self.refresh()
            self.app_actions.toast(_("Loaded default blacklist"))
            app_info_cache.set(BlacklistWindow.DEFAULT_BLACKLIST_KEY, False)
        except Exception as e:
            self.app_actions.alert(
                _("Error loading default blacklist"), str(e), kind="error", master=self
            )

    @require_password(ProtectedActions.EDIT_BLACKLIST)
    def import_blacklist(self, event=None):
        file_path, _selected = QFileDialog.getOpenFileName(
            self,
            _("Import Blacklist"),
            "",
            "All supported (*.csv *.json *.txt);;CSV (*.csv);;JSON (*.json);;Text (*.txt)",
        )
        if not file_path:
            return
        try:
            if file_path.endswith(".csv"):
                Blacklist.import_blacklist_csv(file_path)
            elif file_path.endswith(".json"):
                Blacklist.import_blacklist_json(file_path)
            else:
                Blacklist.import_blacklist_txt(file_path)
            self.refresh()
            BlacklistWindow.mark_user_confirmed_non_default()
            self.app_actions.toast(_("Successfully imported blacklist"))
        except Exception as e:
            self.app_actions.alert(
                _("Import Error"), str(e), kind="error", master=self
            )

    @require_password(ProtectedActions.EDIT_BLACKLIST)
    def export_blacklist(self, event=None):
        file_path, _selected = QFileDialog.getSaveFileName(
            self,
            _("Export Blacklist"),
            "",
            "CSV (*.csv);;JSON (*.json);;Text (*.txt)",
        )
        if not file_path:
            return
        try:
            if file_path.endswith(".json"):
                Blacklist.export_blacklist_json(file_path)
            elif file_path.endswith(".txt"):
                Blacklist.export_blacklist_txt(file_path)
            else:
                Blacklist.export_blacklist_csv(file_path)
            self.app_actions.toast(_("Successfully exported blacklist"))
        except Exception as e:
            self.app_actions.alert(
                _("Export Error"), str(e), kind="error", master=self
            )

    def _on_mode_change(self, text):
        try:
            mode = BlacklistMode.from_display(text)
        except Exception:
            mode = BlacklistMode.REMOVE_WORD_OR_PHRASE
        Blacklist.set_blacklist_mode(mode)
        self.store_blacklist()
        if self.app_actions:
            self.app_actions.toast(_("Blacklist mode set to: {0}").format(mode.display()))

    def _on_silent_change(self):
        Blacklist.set_blacklist_silent_removal(self.silent_checkbox.isChecked())
        self.store_blacklist()
        if self.app_actions:
            self.app_actions.toast(
                _("Silent removal set to: {0}").format(
                    self.silent_checkbox.isChecked()
                )
            )
