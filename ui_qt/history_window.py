"""
History window (PySide6).
Port of ui/history_window.py; logic preserved, UI uses Qt.
"""

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QScrollArea,
    QWidget,
    QFrame,
    QSizePolicy,
)
from PySide6.QtCore import Qt

from lib.multi_display_qt import SmartWindow
from muse.playlist import Playlist
from ui_qt.app_style import AppStyle
from ui_qt.auth.password_utils import require_password
from utils.globals import HistoryType, ProtectedActions
from utils.logging_setup import get_logger
from utils.translations import I18N

_ = I18N._
logger = get_logger(__name__)


class HistoryDataSearch:
    """Search helper for history (no UI)."""

    def __init__(self, search_term="", max_results=200):
        self.search_term = search_term.lower()
        self.max_results = max_results
        self.results = []

    def is_valid(self):
        return len(self.search_term.strip()) > 0

    def get_readable_results_count(self):
        count = len(self.results)
        results_str = f"{self.max_results}+" if count > self.max_results else str(count)
        return _("({0} results)").format(results_str)

    def get_results(self):
        return self.results

    def _get_match_priority(self, search_text: str) -> int:
        if not self.search_term:
            return 0
        search_text = search_text.lower()
        if search_text.startswith(self.search_term):
            return 3
        for word in search_text.split():
            if word.startswith(self.search_term):
                return 2
        if self.search_term in search_text:
            return 1
        return 0

    def add_result(self, item, search_text: str):
        priority = self._get_match_priority(search_text)
        if priority > 0:
            self.results.append((priority, item))

    def sort_results(self):
        self.results.sort(key=lambda x: (-x[0], x[1]))
        self.results = [item for _, item in self.results[: self.max_results]]


class HistoryWindow(SmartWindow):
    """Window to view playback history data."""

    COL_0_WIDTH = 150
    TRACK_LABEL_MIN_WIDTH = 420
    top_level = None
    MAX_RESULTS = 200

    def __init__(self, master, app_actions, library_data, dimensions="800x600"):
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("History") + " - " + _("History"),
            geometry=dimensions,
            offset_x=50,
            offset_y=50,
        )
        HistoryWindow.top_level = self
        logger.info("Opening HistoryWindow with dimensions %s", dimensions)
        self.master = master
        self.app_actions = app_actions
        self.library_data = library_data
        self.history_data_search = None

        self.setStyleSheet(AppStyle.get_stylesheet())
        layout = QVBoxLayout(self)

        inner = QFrame(self)
        inner_layout = QGridLayout(inner)

        inner_layout.addWidget(QLabel(_("History Type"), self), 0, 0)
        self.history_type_combo = QComboBox(self)
        self.history_type_combo.addItems(HistoryType.get_translated_names())
        idx = self.history_type_combo.findText(HistoryType.TRACKS.get_translation())
        if idx >= 0:
            self.history_type_combo.blockSignals(True)
            self.history_type_combo.setCurrentIndex(idx)
            self.history_type_combo.blockSignals(False)
        self.history_type_combo.currentTextChanged.connect(self.show_history)
        inner_layout.addWidget(self.history_type_combo, 0, 1)

        inner_layout.addWidget(QLabel(_("Search History"), self), 1, 0)
        self.search_entry = QLineEdit(self)
        self.search_entry.returnPressed.connect(self.do_search)
        inner_layout.addWidget(self.search_entry, 1, 1)

        self.search_btn = QPushButton(_("Search"), self)
        self.search_btn.clicked.connect(self.do_search)
        inner_layout.addWidget(self.search_btn, 2, 0, 1, 2)
        layout.addWidget(inner)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.results_widget = QWidget(self.scroll)
        self.results_layout = QVBoxLayout(self.results_widget)
        self.results_layout.setContentsMargins(5, 5, 5, 5)
        self.results_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.results_widget)
        layout.addWidget(self.scroll, 1)

        self.show()
        self.show_history(HistoryType.TRACKS.get_translation())

    @require_password(ProtectedActions.VIEW_HISTORY)
    def do_search(self, event=None):
        search_term = self.search_entry.text().strip()
        self.history_data_search = HistoryDataSearch(
            search_term, HistoryWindow.MAX_RESULTS
        )
        self._do_search()

    @require_password(ProtectedActions.VIEW_HISTORY)
    def _do_search(self, event=None):
        if self.history_data_search is None:
            return
        self._refresh_widgets(add_results=False)
        history_type = HistoryType.get_from_translation(
            self.history_type_combo.currentText()
        )
        history_list = getattr(Playlist, history_type.value)
        for item in history_list:
            if history_type == HistoryType.TRACKS:
                track = self.library_data.get_track(item)
                search_text = f"{track.title} - {track.artist}" if track else item
            else:
                search_text = item
            self.history_data_search.add_result(item, search_text)
        self.history_data_search.sort_results()
        self._refresh_widgets()

    def show_history(self, history_type_translation):
        logger.info("Showing history for type: %s", history_type_translation)
        self._clear_results()
        history_type = HistoryType.get_from_translation(history_type_translation)
        history_list = getattr(Playlist, history_type.value)
        logger.info("Found %s items in history", len(history_list))

        if not history_list:
            logger.info("No history items found")
            lbl = QLabel(_("No history found."), self.results_widget)
            self.results_layout.addWidget(lbl)
            return

        for item in history_list[: HistoryWindow.MAX_RESULTS]:
            if history_type == HistoryType.TRACKS:
                track = self.library_data.get_track(item)
                if track:
                    display_text = f"{track.title} - {track.artist}"
                else:
                    display_text = item
                    logger.info("Could not find track details for: %s", item)
            else:
                display_text = item
                track = None

            item_frame = QFrame(self.results_widget)
            row_layout = QHBoxLayout(item_frame)
            row_layout.setContentsMargins(5, 2, 5, 2)

            label = QLabel(display_text, item_frame)
            label.setWordWrap(True)
            label.setFixedWidth(HistoryWindow.TRACK_LABEL_MIN_WIDTH)
            label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            label.setSizePolicy(
                QSizePolicy.Policy.Fixed,
                QSizePolicy.Policy.MinimumExpanding,
            )
            label.setMinimumHeight(0)
            row_layout.addWidget(label, 1)

            if history_type == HistoryType.TRACKS and track:
                details_btn = QPushButton(_("Details"), item_frame)
                details_btn.clicked.connect(
                    lambda checked=False, t=track: self.app_actions.open_track_details(t)
                )
                row_layout.addWidget(details_btn)

            favorite_btn = QPushButton("★", item_frame)
            favorite_btn.clicked.connect(
                lambda checked=False, v=item, t=history_type: self.add_favorite(v, t)
            )
            row_layout.addWidget(favorite_btn)

            self.results_layout.addWidget(item_frame)

    def _clear_results(self):
        while self.results_layout.count():
            child = self.results_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    @require_password(ProtectedActions.EDIT_FAVORITES)
    def add_favorite(self, value: str, history_type: HistoryType):
        from library_data.favorite import Favorite
        favorite = Favorite.from_attribute(history_type.get_track_attribute(), value)
        self.app_actions.add_favorite(favorite)

    def _refresh_widgets(self, add_results=True):
        self._clear_results()
        if add_results:
            if (
                self.history_data_search is not None
                and self.history_data_search.search_term
            ):
                self.add_widgets_for_results()
            else:
                self.show_history(self.history_type_combo.currentText())

    def add_widgets_for_results(self):
        if self.history_data_search is None:
            return
        results = self.history_data_search.get_results()[: HistoryWindow.MAX_RESULTS]
        history_type = HistoryType.get_from_translation(
            self.history_type_combo.currentText()
        )
        for item in results:
            if history_type == HistoryType.TRACKS:
                track = self.library_data.get_track(item)
                display_text = (
                    f"{track.title} - {track.artist}" if track else item
                )
            else:
                display_text = item
                track = None

            item_frame = QFrame(self.results_widget)
            row_layout = QHBoxLayout(item_frame)
            row_layout.setContentsMargins(5, 2, 5, 2)

            label = QLabel(display_text, item_frame)
            label.setWordWrap(True)
            label.setFixedWidth(HistoryWindow.TRACK_LABEL_MIN_WIDTH)
            label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            label.setSizePolicy(
                QSizePolicy.Policy.Fixed,
                QSizePolicy.Policy.MinimumExpanding,
            )
            label.setMinimumHeight(0)
            row_layout.addWidget(label, 1)

            if history_type == HistoryType.TRACKS and track:
                details_btn = QPushButton(_("Details"), item_frame)
                details_btn.clicked.connect(
                    lambda checked=False, t=track: self.app_actions.open_track_details(t)
                )
                row_layout.addWidget(details_btn)

            favorite_btn = QPushButton("★", item_frame)
            favorite_btn.clicked.connect(
                lambda checked=False, v=item, t=history_type: self.add_favorite(v, t)
            )
            row_layout.addWidget(favorite_btn)

            self.results_layout.addWidget(item_frame)

    def closeEvent(self, event):
        if HistoryWindow.top_level is self:
            HistoryWindow.top_level = None
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    @staticmethod
    def set_title(extra_text):
        if HistoryWindow.top_level:
            HistoryWindow.top_level.setWindowTitle(_("History") + " - " + extra_text)
