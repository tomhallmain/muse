"""
Extensions management window (PySide6).
Port of ui/extensions_window.py; logic preserved, UI uses Qt.
"""
from datetime import datetime
import os

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QScrollArea,
    QWidget,
    QFrame,
)
from PySide6.QtCore import Qt

from lib.multi_display_qt import SmartWindow
from extensions.extension_manager import ExtensionManager
from extensions.library_extender import q20, q23
from library_data.library_data import LibraryDataSearch
from ui_qt.app_style import AppStyle
from ui_qt.auth.password_utils import require_password
from utils.globals import ExtensionStrategy, ProtectedActions
from utils.logging_setup import get_logger
from utils.translations import I18N

_ = I18N._
logger = get_logger(__name__)


class ExtensionsWindow(SmartWindow):
    """Window to display and manage extension history."""

    CURRENT_EXTENSION_TEXT = _("Extensions")
    COL_0_WIDTH = 150
    MAX_EXTENSIONS = 100
    top_level = None

    def __init__(self, master, app_actions, library_data):
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("Extensions"),
            geometry="1400x800",
            offset_x=50,
            offset_y=50,
        )
        ExtensionsWindow.top_level = self
        self.master = master
        self.app_actions = app_actions
        self.library_data = library_data
        self.has_closed = False

        self.setStyleSheet(AppStyle.get_stylesheet())
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        self._init_sidebar(layout)
        self._init_extension_list(layout)
        self._refresh_extension_list()
        self.show()

    def _init_sidebar(self, main_layout):
        sidebar = QFrame(self)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        sidebar_layout.addWidget(QLabel(_("Extension Settings"), sidebar))
        sidebar_layout.addWidget(QLabel(_("Thread Status"), sidebar))
        self.status_label = QLabel(
            _("Click Check Status to see thread state"), sidebar
        )
        self.status_label.setWordWrap(True)
        sidebar_layout.addWidget(self.status_label)

        check_status_btn = QPushButton(_("Check Status"), sidebar)
        check_status_btn.clicked.connect(self._check_thread_status)
        sidebar_layout.addWidget(check_status_btn)

        sidebar_layout.addWidget(QLabel(_("Strategy"), sidebar))
        self.strategy_combo = QComboBox(sidebar)
        self.strategy_combo.addItems(ExtensionStrategy.get_translated_names())
        idx = self.strategy_combo.findText(ExtensionManager.strategy.get_translation())
        if idx >= 0:
            self.strategy_combo.blockSignals(True)
            self.strategy_combo.setCurrentIndex(idx)
            self.strategy_combo.blockSignals(False)
        self.strategy_combo.currentTextChanged.connect(self._on_strategy_change)
        sidebar_layout.addWidget(self.strategy_combo)

        clear_btn = QPushButton(_("Clear History"), sidebar)
        clear_btn.clicked.connect(self._clear_history)
        sidebar_layout.addWidget(clear_btn)

        sidebar_layout.addWidget(QLabel(_("Statistics"), sidebar))
        self.total_extensions_label = QLabel(sidebar)
        sidebar_layout.addWidget(self.total_extensions_label)
        self.avg_duration_label = QLabel(sidebar)
        sidebar_layout.addWidget(self.avg_duration_label)

        main_layout.addWidget(sidebar)

    def _init_extension_list(self, main_layout):
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.content_widget = QWidget(self.scroll)
        self.content_layout = QGridLayout(self.content_widget)
        self.content_layout.setContentsMargins(5, 5, 5, 5)
        self.scroll.setWidget(self.content_widget)
        main_layout.addWidget(self.scroll, 1)

        self.date_labels = []
        self.published_labels = []
        self.title_labels = []
        self.duration_labels = []
        self.strategy_labels = []
        self.attribute_labels = []
        self.query_labels = []
        self.status_labels = []
        self.details_buttons = []
        self.delete_buttons = []
        self.play_buttons = []

    def _clear_extension_widgets(self):
        while self.content_layout.count():
            child = self.content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.date_labels.clear()
        self.published_labels.clear()
        self.title_labels.clear()
        self.duration_labels.clear()
        self.strategy_labels.clear()
        self.attribute_labels.clear()
        self.query_labels.clear()
        self.status_labels.clear()
        self.details_buttons.clear()
        self.delete_buttons.clear()
        self.play_buttons.clear()

    def _refresh_extension_list(self):
        self._clear_extension_widgets()

        header_style = "font-weight: bold;"
        self.content_layout.addWidget(
            QLabel(_("Date"), self.content_widget, styleSheet=header_style), 0, 0
        )
        self.content_layout.addWidget(
            QLabel(_("Published"), self.content_widget, styleSheet=header_style), 0, 1
        )
        self.content_layout.addWidget(
            QLabel(_("Title"), self.content_widget, styleSheet=header_style), 0, 2
        )
        self.content_layout.addWidget(
            QLabel(_("Duration"), self.content_widget, styleSheet=header_style), 0, 3
        )
        self.content_layout.addWidget(
            QLabel(_("Strategy"), self.content_widget, styleSheet=header_style), 0, 4
        )
        self.content_layout.addWidget(
            QLabel(_("Attribute"), self.content_widget, styleSheet=header_style), 0, 5
        )
        self.content_layout.addWidget(
            QLabel(_("Search Query"), self.content_widget, styleSheet=header_style), 0, 6
        )
        self.content_layout.addWidget(
            QLabel(_("Status"), self.content_widget, styleSheet=header_style), 0, 7
        )
        self.content_layout.addWidget(
            QLabel(_("Actions"), self.content_widget, styleSheet=header_style), 0, 8, 1, 3
        )

        recent_extensions = sorted(
            ExtensionManager.extensions[-ExtensionsWindow.MAX_EXTENSIONS:],
            key=lambda x: x.get("date", ""),
            reverse=True,
        )

        for i, ext in enumerate(recent_extensions):
            row = i + 1

            duration = ext.get("duration", 0)
            duration_str = (
                f"{int(duration // 60)}:{int(duration % 60):02d}" if duration else _("N/A")
            )

            date_str = ""
            try:
                date_str = ext.get("date", "")
                if date_str:
                    date = datetime.fromisoformat(date_str)
                    date_str = date.strftime("%Y-%m-%d")
            except Exception:
                pass

            published_date_str = ""
            try:
                published_date_str = ext.get("snippet", {}).get("publishTime", "")
                if published_date_str:
                    date = datetime.fromisoformat(published_date_str)
                    published_date_str = date.strftime("%Y-%m-%d")
            except Exception:
                pass

            date_label = QLabel(date_str, self.content_widget)
            self.content_layout.addWidget(date_label, row, 0)
            self.date_labels.append(date_label)

            published_label = QLabel(published_date_str, self.content_widget)
            self.content_layout.addWidget(published_label, row, 1)
            self.published_labels.append(published_label)

            title_label = QLabel(
                ext.get("snippet", {}).get("title", ""), self.content_widget
            )
            title_label.setWordWrap(True)
            self.content_layout.addWidget(title_label, row, 2)
            self.title_labels.append(title_label)

            duration_label = QLabel(duration_str, self.content_widget)
            self.content_layout.addWidget(duration_label, row, 3)
            self.duration_labels.append(duration_label)

            strategy_label = QLabel(ext.get("strategy", ""), self.content_widget)
            self.content_layout.addWidget(strategy_label, row, 4)
            self.strategy_labels.append(strategy_label)

            attribute_label = QLabel(ext.get("track_attr", ""), self.content_widget)
            self.content_layout.addWidget(attribute_label, row, 5)
            self.attribute_labels.append(attribute_label)

            query_label = QLabel(ext.get("search_query", ""), self.content_widget)
            query_label.setWordWrap(True)
            self.content_layout.addWidget(query_label, row, 6)
            self.query_labels.append(query_label)

            status_text = "X" if ext.get("failed", False) else ""
            status_label = QLabel(status_text, self.content_widget)
            self.content_layout.addWidget(status_label, row, 7)
            self.status_labels.append(status_label)

            details_btn = QPushButton(_("Details"), self.content_widget)
            self.content_layout.addWidget(details_btn, row, 8)
            self.details_buttons.append(details_btn)
            details_btn.clicked.connect(
                lambda checked=False, e=ext: self._show_extension_details(e)
            )

            play_btn = QPushButton(_("Play"), self.content_widget)
            self.content_layout.addWidget(play_btn, row, 9)
            self.play_buttons.append(play_btn)
            play_btn.clicked.connect(
                lambda checked=False, e=ext: self._play_extension(e)
            )

            delete_btn = QPushButton(_("Delete"), self.content_widget)
            self.content_layout.addWidget(delete_btn, row, 10)
            self.delete_buttons.append(delete_btn)
            delete_btn.clicked.connect(
                lambda checked=False, e=ext: self._delete_extension(e)
            )

        self._update_statistics()

    def _update_statistics(self):
        total = len(ExtensionManager.extensions)
        self.total_extensions_label.setText(_("Total Extensions: {}").format(total))
        if total > 0:
            avg_duration = (
                sum(ext.get("duration", 0) for ext in ExtensionManager.extensions)
                / total
            )
            avg_duration_str = f"{int(avg_duration // 60)}:{int(avg_duration % 60):02d}"
            self.avg_duration_label.setText(
                _("Average Duration: {}").format(avg_duration_str)
            )
        else:
            self.avg_duration_label.setText(_("Average Duration: N/A"))

    def _on_strategy_change(self, text):
        try:
            new_strategy = ExtensionStrategy.get_from_translation(text)
            ExtensionManager.strategy = new_strategy
            logger.info("Extension strategy changed to: %s", new_strategy.name)
            ExtensionManager.store_extensions()
            self.library_data.extension_manager.reset_extension()
            self._refresh_extension_list()
        except Exception as e:
            logger.warning("Invalid strategy selected: %s - %s", text, e)

    @require_password(ProtectedActions.EDIT_EXTENSIONS)
    def _clear_history(self):
        res = self.app_actions.alert(
            _("Confirm Clear"),
            _("Are you sure you want to clear all extension history?"),
            kind="askokcancel",
            master=self,
        )
        if res:
            ExtensionManager.extensions = []
            ExtensionManager.store_extensions()
            self._refresh_extension_list()

    def closeEvent(self, event):
        self.has_closed = True
        if ExtensionsWindow.top_level is self:
            ExtensionsWindow.top_level = None
        event.accept()

    def update(self):
        self._refresh_extension_list()

    @staticmethod
    def set_title(extra_text):
        if ExtensionsWindow.top_level:
            ExtensionsWindow.top_level.setWindowTitle(
                _("Extensions") + " - " + extra_text
            )

    @require_password(ProtectedActions.EDIT_EXTENSIONS)
    def _show_extension_details(self, extension):
        ExtensionDetailsWindow(self, extension).show()

    @require_password(ProtectedActions.EDIT_EXTENSIONS)
    @require_password(ProtectedActions.DELETE_MEDIA)
    def _delete_extension(self, extension):
        res = self.app_actions.alert(
            _("Confirm Delete"),
            _("Are you sure you want to delete this extension?"),
            kind="askokcancel",
            master=self,
        )
        if res:
            if extension in ExtensionManager.extensions:
                ExtensionManager.extensions.remove(extension)
                ExtensionManager.store_extensions()
                self._refresh_extension_list()

    def _play_extension(self, extension):
        try:
            id_val = extension.get(q20, {}).get(q23, None)
            original_filename = os.path.splitext(
                os.path.basename(extension.get("filename", ""))
            )[0]
            if not id_val or not original_filename:
                raise ValueError(
                    _("No original filename or id found in extension data")
                )
            search = LibraryDataSearch(
                title=original_filename,
                id=id_val,
                max_results=1,
            )
            self.app_actions.search_and_play(search)
        except Exception as e:
            error_msg = str(e)
            if "No matching tracks found" in error_msg:
                error_msg += "\n\n" + _(
                    "Tip: If you've recently added or moved files, try checking 'Overwrite Cache' in the search options."
                )
            logger.error("Error playing extension: %s", error_msg)
            self.app_actions.alert(
                _("Error"), error_msg, kind="error", master=self
            )

    def _check_thread_status(self):
        if ExtensionManager.extension_thread is None:
            status = _("No extension thread running")
        elif not ExtensionManager.extension_thread.is_alive():
            status = _("Extension thread terminated")
        else:
            status = _("Extension thread running")
            if ExtensionManager.EXTENSION_QUEUE.has_pending():
                status += _(" (with pending jobs)")
            if not ExtensionManager.extension_thread_delayed_complete:
                status += _(" (processing delayed operation)")
        self.status_label.setText(status)


class ExtensionDetailsWindow(SmartWindow):
    """Window to display detailed information about an extension."""

    def __init__(self, master, extension):
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("Extension Details"),
            geometry="800x600",
            offset_x=50,
            offset_y=50,
        )
        self.master = master
        self.extension = extension
        self.has_closed = False

        self.setStyleSheet(AppStyle.get_stylesheet())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        title = extension.get("snippet", {}).get("title", "")
        title_label = QLabel(title, self)
        title_label.setStyleSheet("font-size: 12pt; font-weight: bold;")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        details_frame = QFrame(self)
        details_layout = QGridLayout(details_frame)
        row = 0

        details_layout.addWidget(QLabel(_("Published:"), details_frame), row, 0)
        try:
            published_date = datetime.fromisoformat(
                extension.get("snippet", {}).get("publishTime", "")
            )
            published_str = published_date.strftime("%Y-%m-%d")
        except Exception:
            published_str = _("N/A")
        details_layout.addWidget(QLabel(published_str, details_frame), row, 1)
        row += 1

        details_layout.addWidget(QLabel(_("Duration:"), details_frame), row, 0)
        duration = extension.get("duration", 0)
        duration_str = (
            f"{int(duration // 60)}:{int(duration % 60):02d}" if duration else _("N/A")
        )
        details_layout.addWidget(QLabel(duration_str, details_frame), row, 1)
        row += 1

        details_layout.addWidget(QLabel(_("Strategy:"), details_frame), row, 0)
        details_layout.addWidget(
            QLabel(extension.get("strategy", ""), details_frame), row, 1
        )
        row += 1

        details_layout.addWidget(QLabel(_("Attribute:"), details_frame), row, 0)
        details_layout.addWidget(
            QLabel(extension.get("track_attr", ""), details_frame), row, 1
        )
        row += 1

        details_layout.addWidget(QLabel(_("Search Query:"), details_frame), row, 0)
        q_label = QLabel(extension.get("search_query", ""), details_frame)
        q_label.setWordWrap(True)
        details_layout.addWidget(q_label, row, 1)
        row += 1

        details_layout.addWidget(QLabel(_("Status:"), details_frame), row, 0)
        status_text = (
            _("Failed") if extension.get("failed", False) else _("Success")
        )
        details_layout.addWidget(QLabel(status_text, details_frame), row, 1)
        row += 1

        details_layout.addWidget(QLabel(_("Description:"), details_frame), row, 0)
        desc_label = QLabel(
            extension.get("snippet", {}).get("description", ""), details_frame
        )
        desc_label.setWordWrap(True)
        details_layout.addWidget(desc_label, row, 1)
        row += 1

        details_layout.addWidget(QLabel(_("File:"), details_frame), row, 0)
        if extension.get("failed", False) and extension.get("exception"):
            file_text = extension.get("exception", "")
        else:
            file_text = extension.get("filename", "")
        file_label = QLabel(file_text, details_frame)
        file_label.setWordWrap(True)
        details_layout.addWidget(file_label, row, 1)

        layout.addWidget(details_frame)

        close_btn = QPushButton(_("Close"), self)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

    def closeEvent(self, event):
        self.has_closed = True
        event.accept()
