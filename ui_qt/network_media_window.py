"""Internet Radio / Network Media window (PySide6).

Provides Radio Browser station search and a saved-stations tab.
Uses extensions.radio_browser for API calls and library_data.network_media_track
for stream-compatible track objects that VLC can play natively via HTTP URLs.
"""

import threading

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
    QTabWidget,
    QCheckBox,
)
from PySide6.QtCore import Qt, QTimer, Signal

from lib.multi_display_qt import SmartWindow
from ui_qt.app_style import AppStyle
from muse.radio_watchlist import WatchEntry, load_entries, save_entries, watchlist_service
from utils.app_info_cache import app_info_cache
from utils.translations import I18N
from utils.logging_setup import get_logger
from utils.utils import Utils

_ = I18N._
logger = get_logger(__name__)

_FAVOURITES_CACHE_KEY = "radio_favourites"


def _station_info_label(station: dict) -> str:
    """Compact info string: 'MP3 128 · FR'."""
    parts = []
    codec = (station.get("codec") or "").upper()
    bitrate = station.get("bitrate") or 0
    if codec:
        parts.append(f"{codec} {bitrate}" if bitrate else codec)
    country = (station.get("countrycode") or station.get("country") or "").upper()
    if country:
        parts.append(country)
    return " · ".join(parts)


class NetworkMediaWindow(SmartWindow):
    """Internet radio browser backed by radio-browser.info."""

    top_level = None
    _sig_invoke = Signal(object)  # carries a zero-arg callable; delivers it on the main thread

    def __init__(self, master, app_actions, dimensions="1200x640"):
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("Internet Radio"),
            geometry=dimensions,
            offset_x=50,
            offset_y=50,
        )
        NetworkMediaWindow.top_level = self
        self.setMinimumSize(600, 400)
        self.app_actions = app_actions
        self._search_thread: threading.Thread | None = None

        self._sig_invoke.connect(lambda fn: fn())
        self.setStyleSheet(AppStyle.get_stylesheet())
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(4)

        self._tabs = QTabWidget(self)
        outer.addWidget(self._tabs, 1)

        # ── Search tab ────────────────────────────────────────────────────────
        search_widget = QWidget()
        search_layout = QVBoxLayout(search_widget)
        search_layout.setContentsMargins(4, 4, 4, 4)
        search_layout.setSpacing(4)

        filters = QFrame()
        filters_layout = QHBoxLayout(filters)
        filters_layout.setContentsMargins(0, 0, 0, 0)
        filters_layout.setSpacing(6)

        filters_layout.addWidget(QLabel(_("Station:")))
        self._name_entry = QLineEdit()
        self._name_entry.setPlaceholderText(_("Name or keyword"))
        self._name_entry.returnPressed.connect(self._do_search)
        filters_layout.addWidget(self._name_entry, 2)

        filters_layout.addWidget(QLabel(_("Tags:")))
        self._tags_entry = QLineEdit()
        self._tags_entry.setPlaceholderText(_("e.g. jazz"))
        self._tags_entry.returnPressed.connect(self._do_search)
        filters_layout.addWidget(self._tags_entry, 1)

        filters_layout.addWidget(QLabel(_("Country:")))
        self._country_entry = QLineEdit()
        self._country_entry.setPlaceholderText(_("e.g. DE"))
        self._country_entry.setMaximumWidth(60)
        self._country_entry.returnPressed.connect(self._do_search)
        filters_layout.addWidget(self._country_entry)

        self._search_btn = QPushButton(_("Search"))
        self._search_btn.clicked.connect(self._do_search)
        filters_layout.addWidget(self._search_btn)

        search_layout.addWidget(filters)

        self._search_scroll = QScrollArea()
        self._search_scroll.setWidgetResizable(True)
        self._search_results_widget = QWidget()
        self._search_results_layout = QGridLayout(self._search_results_widget)
        self._search_results_layout.setColumnStretch(0, 3)
        self._search_results_layout.setColumnStretch(1, 1)
        self._search_results_layout.setColumnStretch(2, 2)
        self._search_results_layout.setColumnStretch(3, 1)
        self._search_scroll.setWidget(self._search_results_widget)
        search_layout.addWidget(self._search_scroll, 1)

        self._search_row_widgets: list[QWidget] = []
        self._tabs.addTab(search_widget, _("Search"))

        # ── Saved Stations tab ────────────────────────────────────────────────

        saved_widget = QWidget()
        saved_layout = QVBoxLayout(saved_widget)
        saved_layout.setContentsMargins(4, 4, 4, 4)

        self._saved_scroll = QScrollArea()
        self._saved_scroll.setWidgetResizable(True)
        self._saved_results_widget = QWidget()
        self._saved_results_layout = QGridLayout(self._saved_results_widget)
        self._saved_results_layout.setColumnStretch(0, 3)
        self._saved_results_layout.setColumnStretch(1, 1)
        self._saved_results_layout.setColumnStretch(2, 2)
        self._saved_scroll.setWidget(self._saved_results_widget)
        saved_layout.addWidget(self._saved_scroll, 1)

        self._saved_row_widgets: list[QWidget] = []
        self._tabs.addTab(saved_widget, _("Saved Stations"))

        # ── Watch-list tab ────────────────────────────────────────────────────
        watch_widget = QWidget()
        watch_layout = QVBoxLayout(watch_widget)
        watch_layout.setContentsMargins(4, 4, 4, 4)
        watch_layout.setSpacing(6)

        # "Add entry" form
        add_frame = QFrame()
        add_layout = QVBoxLayout(add_frame)
        add_layout.setContentsMargins(0, 0, 0, 4)
        add_layout.setSpacing(4)

        add_header = QLabel(_("Add Watch Entry"))
        add_header.setStyleSheet("font-weight: bold;")
        add_layout.addWidget(add_header)

        self._watch_selected_label = QLabel(_("No station selected — use Search tab or enter UUID below."))
        self._watch_selected_label.setWordWrap(True)
        add_layout.addWidget(self._watch_selected_label)

        # UUID field (editable as fallback)
        uuid_row = QHBoxLayout()
        uuid_row.addWidget(QLabel(_("Station UUID:")))
        self._watch_uuid_entry = QLineEdit()
        self._watch_uuid_entry.setPlaceholderText(_("Paste UUID from Radio Browser"))
        self._watch_uuid_entry.textChanged.connect(self._on_watch_uuid_changed)
        uuid_row.addWidget(self._watch_uuid_entry, 1)
        add_layout.addLayout(uuid_row)

        # Label
        label_row = QHBoxLayout()
        label_row.addWidget(QLabel(_("Label:")))
        self._watch_label_entry = QLineEdit()
        self._watch_label_entry.setPlaceholderText(_("e.g. Bach on Radio Swiss Classic"))
        label_row.addWidget(self._watch_label_entry, 1)
        add_layout.addLayout(label_row)

        # Match fields
        for attr, placeholder in [
            ("_watch_artist_entry", _("ICY artist contains (e.g. Bach)")),
            ("_watch_title_entry", _("ICY title contains (e.g. Suite)")),
            ("_watch_any_entry", _("Matches full StreamTitle (e.g. classical)")),
        ]:
            row = QHBoxLayout()
            if attr == "_watch_artist_entry":
                row.addWidget(QLabel(_("Match artist:")))
            elif attr == "_watch_title_entry":
                row.addWidget(QLabel(_("Match title:")))
            else:
                row.addWidget(QLabel(_("Match any:")))
            entry = QLineEdit()
            entry.setPlaceholderText(placeholder)
            setattr(self, attr, entry)
            row.addWidget(entry, 1)
            add_layout.addLayout(row)

        btn_row = QHBoxLayout()
        add_btn = QPushButton(_("Add Entry"))
        add_btn.clicked.connect(self._add_watch_entry)
        clear_btn = QPushButton(_("Clear"))
        clear_btn.clicked.connect(self._clear_watch_form)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        add_layout.addLayout(btn_row)

        watch_layout.addWidget(add_frame)

        # Entries table
        self._watch_scroll = QScrollArea()
        self._watch_scroll.setWidgetResizable(True)
        self._watch_results_widget = QWidget()
        self._watch_results_layout = QGridLayout(self._watch_results_widget)
        self._watch_results_layout.setColumnStretch(0, 2)  # label
        self._watch_results_layout.setColumnStretch(1, 2)  # station
        self._watch_results_layout.setColumnStretch(2, 3)  # match criteria
        self._watch_scroll.setWidget(self._watch_results_widget)
        watch_layout.addWidget(self._watch_scroll, 1)

        self._watch_row_widgets: list[QWidget] = []

        # Service reload button
        svc_row = QHBoxLayout()
        reload_btn = QPushButton(_("Reload Watch Service"))
        reload_btn.setToolTip(_("Restart background polling threads after editing the list"))
        reload_btn.clicked.connect(self._reload_watch_service)
        svc_row.addWidget(reload_btn)
        svc_row.addStretch()
        watch_layout.addLayout(svc_row)

        # Watch form state
        self._watch_station_uuid: str = ""
        self._watch_station_name: str = ""

        self._tabs.addTab(watch_widget, _("Watch-list"))

        # ── Manual URL entry (bottom, always visible) ─────────────────────────
        url_frame = QFrame()
        url_layout = QHBoxLayout(url_frame)
        url_layout.setContentsMargins(0, 0, 0, 0)
        url_layout.setSpacing(6)

        url_layout.addWidget(QLabel(_("URL:")))
        self._url_entry = QLineEdit()
        self._url_entry.setPlaceholderText(_("Direct stream URL (http://...)"))
        self._url_entry.returnPressed.connect(self._play_manual_url)
        url_layout.addWidget(self._url_entry, 1)

        play_url_btn = QPushButton(_("Play URL"))
        play_url_btn.clicked.connect(self._play_manual_url)
        url_layout.addWidget(play_url_btn)

        outer.addWidget(url_frame)

        self.show()
        QTimer.singleShot(0, self._populate_saved)
        QTimer.singleShot(0, self._populate_watchlist)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _clear_grid(self, layout: QGridLayout, widget_list: list) -> None:
        for w in widget_list:
            w.setParent(None)
            w.deleteLater()
        widget_list.clear()

    def _set_search_status(self, text: str) -> None:
        self._clear_grid(self._search_results_layout, self._search_row_widgets)
        lbl = QLabel(text, self._search_results_widget)
        lbl.setWordWrap(True)
        self._search_results_layout.addWidget(lbl, 0, 0, 1, 5)
        self._search_row_widgets.append(lbl)

    def _add_station_row(
        self,
        layout: QGridLayout,
        widget_list: list,
        row: int,
        station: dict,
        show_save: bool = True,
        show_remove: bool = False,
        show_watch: bool = False,
    ) -> None:
        """Append one station row to *layout*."""
        name = station.get("name") or ""
        info = _station_info_label(station)
        tags = (station.get("tags") or "")[:40]
        votes = str(station.get("votes") or "")
        url = station.get("url_resolved") or station.get("url") or ""

        name_lbl = QLabel(name, self._search_results_widget if not show_remove else self._saved_results_widget)
        name_lbl.setWordWrap(True)
        layout.addWidget(name_lbl, row, 0)
        widget_list.append(name_lbl)

        info_lbl = QLabel(info)
        layout.addWidget(info_lbl, row, 1)
        widget_list.append(info_lbl)

        tags_lbl = QLabel(tags)
        tags_lbl.setWordWrap(True)
        layout.addWidget(tags_lbl, row, 2)
        widget_list.append(tags_lbl)

        votes_lbl = QLabel(votes)
        layout.addWidget(votes_lbl, row, 3)
        widget_list.append(votes_lbl)

        if show_save:
            save_btn = QPushButton("★")
            save_btn.setFixedWidth(32)
            save_btn.setToolTip(_("Save to Saved Stations"))
            save_btn.clicked.connect(lambda _, s=station: self._save_station(s))
            layout.addWidget(save_btn, row, 4)
            widget_list.append(save_btn)

        if show_remove:
            remove_btn = QPushButton("✕")
            remove_btn.setFixedWidth(32)
            remove_btn.setToolTip(_("Remove from Saved Stations"))
            remove_btn.clicked.connect(lambda _, s=station: self._remove_station(s))
            layout.addWidget(remove_btn, row, 4)
            widget_list.append(remove_btn)

        play_btn = QPushButton(_("Play"))
        play_btn.clicked.connect(lambda _, u=url, n=name, s=station: self._play_station(u, n, s))
        layout.addWidget(play_btn, row, 5)
        widget_list.append(play_btn)

        if show_watch:
            watch_btn = QPushButton(_("Watch"))
            watch_btn.setToolTip(_("Add to watch-list"))
            watch_btn.clicked.connect(lambda _, s=station: self._prefill_watch_form(s))
            layout.addWidget(watch_btn, row, 6)
            widget_list.append(watch_btn)

    # ── Search ────────────────────────────────────────────────────────────────

    def _do_search(self) -> None:
        query = self._name_entry.text().strip()
        tags = self._tags_entry.text().strip()
        country = self._country_entry.text().strip()
        if not query and not tags and not country:
            self._set_search_status(_("Enter a station name, tag, or country code to search."))
            return
        self._set_search_status(_("Searching…"))
        self._search_btn.setEnabled(False)

        def worker():
            try:
                from extensions.radio_browser import search_stations
                logger.debug("Radio search starting: query=%r tags=%r country=%r", query, tags, country)
                results = search_stations(query=query, tags=tags, country=country, limit=80)
                logger.debug("Radio search returned %d result(s)", len(results))
                self._sig_invoke.emit(lambda: self._show_search_results(results))
            except Exception as exc:
                logger.error("Radio Browser search failed: %s", exc, exc_info=True)
                self._sig_invoke.emit(lambda: self._set_search_status(
                    _("Search failed: ") + str(exc)
                ))
            finally:
                self._sig_invoke.emit(lambda: self._search_btn.setEnabled(True))

        Utils.start_thread(worker, use_asyncio=False)

    def _show_search_results(self, results: list) -> None:
        try:
            self._clear_grid(self._search_results_layout, self._search_row_widgets)
            if not results:
                self._set_search_status(_("No stations found."))
                return
            for i, station in enumerate(results):
                self._add_station_row(
                    self._search_results_layout,
                    self._search_row_widgets,
                    i,
                    station,
                    show_save=True,
                    show_remove=False,
                    show_watch=True,
                )
        except Exception:
            logger.exception("Error rendering search results")

    # ── Saved Stations ────────────────────────────────────────────────────────

    def _load_saved(self) -> list:
        return list(app_info_cache.get(_FAVOURITES_CACHE_KEY, []))

    def _persist_saved(self, stations: list) -> None:
        app_info_cache.set(_FAVOURITES_CACHE_KEY, stations)

    def _populate_saved(self) -> None:
        self._clear_grid(self._saved_results_layout, self._saved_row_widgets)
        stations = self._load_saved()
        if not stations:
            lbl = QLabel(_("No saved stations yet. Click ★ on a search result to save one."))
            lbl.setWordWrap(True)
            self._saved_results_layout.addWidget(lbl, 0, 0, 1, 5)
            self._saved_row_widgets.append(lbl)
            return
        for i, station in enumerate(stations):
            self._add_station_row(
                self._saved_results_layout,
                self._saved_row_widgets,
                i,
                station,
                show_save=False,
                show_remove=True,
            )

    def _save_station(self, station: dict) -> None:
        stations = self._load_saved()
        uuid = station.get("stationuuid") or station.get("url_resolved") or ""
        if not any((s.get("stationuuid") or s.get("url_resolved")) == uuid for s in stations):
            stations.append(station)
            self._persist_saved(stations)
        self._populate_saved()
        self._tabs.setCurrentIndex(1)

    def _remove_station(self, station: dict) -> None:
        uuid = station.get("stationuuid") or station.get("url_resolved") or ""
        stations = [
            s for s in self._load_saved()
            if (s.get("stationuuid") or s.get("url_resolved")) != uuid
        ]
        self._persist_saved(stations)
        self._populate_saved()

    # ── Playback ──────────────────────────────────────────────────────────────

    def _play_station(self, url: str, name: str, station: dict) -> None:
        if not url:
            return

        def resolve_and_play():
            from extensions.radio_browser import resolve_stream_url
            from library_data.network_media_track import NetworkMediaTrack
            resolved = resolve_stream_url(url)
            track = NetworkMediaTrack(
                url=resolved,
                name=name,
                station_uuid=station.get("stationuuid") or "",
                codec=station.get("codec") or "",
                bitrate=int(station.get("bitrate") or 0),
                tags=station.get("tags") or "",
                country=station.get("countrycode") or station.get("country") or "",
            )
            self._sig_invoke.emit(lambda: self.app_actions.start_play_callback(track=track))

        Utils.start_thread(resolve_and_play, use_asyncio=False)

    def _play_manual_url(self) -> None:
        url = self._url_entry.text().strip()
        if not url or not url.startswith("http"):
            return
        from library_data.network_media_track import NetworkMediaTrack
        track = NetworkMediaTrack(url=url, name=url)
        self.app_actions.start_play_callback(track=track)

    # ── Watch-list ────────────────────────────────────────────────────────────

    def _prefill_watch_form(self, station: dict) -> None:
        """Pre-fill the Watch-list 'Add Entry' form from a search result."""
        self._watch_station_uuid = station.get("stationuuid") or ""
        self._watch_station_name = station.get("name") or ""
        self._watch_uuid_entry.setText(self._watch_station_uuid)
        self._watch_selected_label.setText(
            _("Selected: ") + self._watch_station_name
        )
        if not self._watch_label_entry.text():
            self._watch_label_entry.setText(self._watch_station_name)
        self._tabs.setCurrentIndex(2)  # switch to Watch-list tab

    def _on_watch_uuid_changed(self, text: str) -> None:
        """Update the internal UUID when the user edits the UUID field directly."""
        self._watch_station_uuid = text.strip()
        if not self._watch_station_name or self._watch_station_name == self._watch_uuid_entry.text():
            self._watch_station_name = text.strip()

    def _add_watch_entry(self) -> None:
        uuid = self._watch_station_uuid.strip() or self._watch_uuid_entry.text().strip()
        label = self._watch_label_entry.text().strip()
        if not uuid or not label:
            return
        entry = WatchEntry(
            label=label,
            station_uuid=uuid,
            station_name=self._watch_station_name or uuid,
            match_artist=self._watch_artist_entry.text().strip(),
            match_title=self._watch_title_entry.text().strip(),
            match_any=self._watch_any_entry.text().strip(),
            enabled=True,
        )
        entries = load_entries()
        entries.append(entry)
        save_entries(entries)
        self._clear_watch_form()
        self._populate_watchlist()

    def _clear_watch_form(self) -> None:
        self._watch_station_uuid = ""
        self._watch_station_name = ""
        self._watch_uuid_entry.clear()
        self._watch_label_entry.clear()
        self._watch_artist_entry.clear()
        self._watch_title_entry.clear()
        self._watch_any_entry.clear()
        self._watch_selected_label.setText(
            _("No station selected — use Search tab or enter UUID below.")
        )

    def _populate_watchlist(self) -> None:
        self._clear_grid(self._watch_results_layout, self._watch_row_widgets)
        entries = load_entries()
        if not entries:
            lbl = QLabel(
                _("No watch entries yet. Search for a station and click Watch, or enter a UUID above.")
            )
            lbl.setWordWrap(True)
            self._watch_results_layout.addWidget(lbl, 0, 0, 1, 5)
            self._watch_row_widgets.append(lbl)
            return

        # Header row
        for col, text in enumerate([_("Label"), _("Station"), _("Match criteria"), _("On"), ""]):
            h = QLabel(f"<b>{text}</b>")
            self._watch_results_layout.addWidget(h, 0, col)
            self._watch_row_widgets.append(h)

        for i, entry in enumerate(entries, start=1):
            label_lbl = QLabel(entry.label)
            label_lbl.setWordWrap(True)
            self._watch_results_layout.addWidget(label_lbl, i, 0)
            self._watch_row_widgets.append(label_lbl)

            station_lbl = QLabel(entry.station_name or entry.station_uuid[:12])
            station_lbl.setWordWrap(True)
            self._watch_results_layout.addWidget(station_lbl, i, 1)
            self._watch_row_widgets.append(station_lbl)

            criteria_parts = []
            if entry.match_any:
                criteria_parts.append(f"any: {entry.match_any}")
            if entry.match_artist:
                criteria_parts.append(f"artist: {entry.match_artist}")
            if entry.match_title:
                criteria_parts.append(f"title: {entry.match_title}")
            criteria_lbl = QLabel(" | ".join(criteria_parts) or _("(no criteria)"))
            criteria_lbl.setWordWrap(True)
            self._watch_results_layout.addWidget(criteria_lbl, i, 2)
            self._watch_row_widgets.append(criteria_lbl)

            toggle = QCheckBox()
            toggle.setChecked(entry.enabled)
            toggle.setToolTip(_("Enable / disable this watch entry"))
            toggle.toggled.connect(
                lambda checked, e=entry: self._toggle_watch_entry(e, checked)
            )
            self._watch_results_layout.addWidget(toggle, i, 3)
            self._watch_row_widgets.append(toggle)

            del_btn = QPushButton("✕")
            del_btn.setFixedWidth(32)
            del_btn.setToolTip(_("Delete this watch entry"))
            del_btn.clicked.connect(lambda _, e=entry: self._delete_watch_entry(e))
            self._watch_results_layout.addWidget(del_btn, i, 4)
            self._watch_row_widgets.append(del_btn)

    def _toggle_watch_entry(self, entry: WatchEntry, enabled: bool) -> None:
        entries = load_entries()
        for e in entries:
            if e.label == entry.label and e.station_uuid == entry.station_uuid:
                e.enabled = enabled
        save_entries(entries)

    def _delete_watch_entry(self, entry: WatchEntry) -> None:
        entries = [
            e for e in load_entries()
            if not (e.label == entry.label and e.station_uuid == entry.station_uuid)
        ]
        save_entries(entries)
        self._populate_watchlist()

    def _reload_watch_service(self) -> None:
        watchlist_service.reload()

    # ── Window lifecycle ──────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if NetworkMediaWindow.top_level is self:
            NetworkMediaWindow.top_level = None
        super().closeEvent(event)
