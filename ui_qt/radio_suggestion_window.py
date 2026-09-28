"""
Radio suggestion window (PySide6): titles on watched stations judged new to the
listener, each with a button to switch to that station.
"""

from typing import Dict, List

from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

from lib.multi_display_qt import SmartWindow
from muse.radio_novelty import (
    SIGNAL_ARTIST,
    SIGNAL_COMPOSER,
    SIGNAL_STATION,
    SIGNAL_TITLE,
)
from ui_qt.app_style import AppStyle
from utils.logging_setup import get_logger
from utils.translations import I18N

_ = I18N._
logger = get_logger(__name__)


def signal_description(signal: str) -> str:
    return {
        SIGNAL_TITLE: _("new title"),
        SIGNAL_COMPOSER: _("new composer"),
        SIGNAL_ARTIST: _("new artist"),
        SIGNAL_STATION: _("new to this station"),
    }.get(signal, signal)


class _SuggestionRow:
    def __init__(self, suggestion, widgets: List[QWidget], switch_btn: QPushButton):
        self.suggestion = suggestion
        self.widgets = widgets
        self.switch_btn = switch_btn


class RadioSuggestionWindow(SmartWindow):
    """One window holding every current suggestion.

    A suggestion's Switch button is disabled once its station moves on to
    another title, since switching then would land in the next track.
    """

    top_level = None

    @staticmethod
    def show_suggestion(master, app_actions, suggestion) -> None:
        """Add a suggestion to the open window, opening one if needed."""
        window = RadioSuggestionWindow.top_level
        if window is None:
            window = RadioSuggestionWindow(master, app_actions)
        window.add_suggestion(suggestion)
        window.show()
        window.raise_()

    @staticmethod
    def station_title_changed(station_uuid: str) -> None:
        if RadioSuggestionWindow.top_level is not None:
            RadioSuggestionWindow.top_level.mark_station_moved_on(station_uuid)

    def __init__(self, master, app_actions):
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("New on the Radio"),
            geometry="700x300",
            offset_x=80,
            offset_y=80,
        )
        RadioSuggestionWindow.top_level = self
        self.app_actions = app_actions
        self._rows: Dict[int, _SuggestionRow] = {}
        self._next_row = 0

        self.setStyleSheet(AppStyle.get_stylesheet())
        outer = QVBoxLayout(self)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        self._list_widget = QWidget(scroll)
        self._grid = QGridLayout(self._list_widget)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._grid.setColumnStretch(0, 1)
        scroll.setWidget(self._list_widget)
        outer.addWidget(scroll)

    def add_suggestion(self, suggestion) -> None:
        row = self._next_row
        self._next_row += 1

        heading = " - ".join(part for part in (suggestion.artist, suggestion.title) if part)
        text_lbl = QLabel(
            f"<b>{heading}</b><br>"
            + _("On {0}: {1}").format(
                suggestion.station_name,
                ", ".join(signal_description(s) for s in suggestion.signals),
            ),
            self._list_widget,
        )
        text_lbl.setWordWrap(True)
        text_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._grid.addWidget(text_lbl, row, 0)

        switch_btn = QPushButton(_("Switch"), self._list_widget)
        switch_btn.setToolTip(_("Stop what is playing and switch to this station"))
        switch_btn.clicked.connect(lambda _checked=False, r=row: self._switch(r))
        self._grid.addWidget(switch_btn, row, 1)

        dismiss_btn = QPushButton(_("Dismiss"), self._list_widget)
        dismiss_btn.clicked.connect(lambda _checked=False, r=row: self._remove(r))
        self._grid.addWidget(dismiss_btn, row, 2)

        self._rows[row] = _SuggestionRow(suggestion, [text_lbl, switch_btn, dismiss_btn], switch_btn)

    def mark_station_moved_on(self, station_uuid: str) -> None:
        for entry in self._rows.values():
            if entry.suggestion.station_uuid == station_uuid and entry.switch_btn.isEnabled():
                entry.switch_btn.setEnabled(False)
                entry.switch_btn.setToolTip(_("This track has ended on the station"))

    def _switch(self, row: int) -> None:
        entry = self._rows.get(row)
        if entry is None:
            return
        from muse.radio_watchlist import watchlist_service
        watchlist_service.switch_to_suggestion(entry.suggestion)
        self._remove(row)

    def _remove(self, row: int) -> None:
        entry = self._rows.pop(row, None)
        if entry is None:
            return
        for widget in entry.widgets:
            widget.setParent(None)
            widget.deleteLater()
        if not self._rows:
            self.close()

    def closeEvent(self, event):
        if RadioSuggestionWindow.top_level is self:
            RadioSuggestionWindow.top_level = None
        event.accept()
