"""
Last.fm public library browser window (PySide6).
"""

from __future__ import annotations

import time
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QComboBox,
    QVBoxLayout,
)

from extensions.lastfm_api import LastFmAPIError, LastFmReadAPI
from lib.multi_display_qt import SmartWindow
from ui_qt.app_style import AppStyle
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._


class LastFmLibraryWindow(SmartWindow):
    top_level = None

    _lookup_complete = Signal(object)
    _status = Signal(str)
    _error = Signal(str)
    _set_busy = Signal(bool)
    _download_progress = Signal(int, str)
    _download_complete = Signal(str, int)

    def __init__(self, master, app_actions, dimensions: str = "900x700"):
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("Last.fm Library Browser"),
            geometry=dimensions,
            offset_x=50,
            offset_y=50,
        )
        LastFmLibraryWindow.top_level = self
        self.master = master
        self.app_actions = app_actions
        self.api = LastFmReadAPI()
        self._build_ui()
        self._connect_signals()
        self.setStyleSheet(AppStyle.get_stylesheet())
        self.show()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)

        search_row = QGridLayout()
        search_row.addWidget(QLabel(_("Last.fm Username"), self), 0, 0)
        self.user_entry = QLineEdit(self)
        self.user_entry.setPlaceholderText(_("e.g. RJ"))
        self.user_entry.returnPressed.connect(self.lookup_library)
        search_row.addWidget(self.user_entry, 0, 1)

        search_row.addWidget(QLabel(_("Library View"), self), 0, 2)
        self.scope_combo = QComboBox(self)
        self.scope_combo.addItems([_("Tracks"), _("Albums"), _("Artists")])
        search_row.addWidget(self.scope_combo, 0, 3)

        self.search_btn = QPushButton(_("Load User Library"), self)
        self.search_btn.clicked.connect(self.lookup_library)
        search_row.addWidget(self.search_btn, 0, 4)
        root.addLayout(search_row)

        self.summary_label = QLabel(_("Enter a username and load library data."), self)
        self.summary_label.setWordWrap(True)
        root.addWidget(self.summary_label)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        root.addWidget(self.progress_bar)

        self.status_label = QLabel("", self)
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.results_list = QListWidget(self)
        root.addWidget(self.results_list, 1)

        dl_row = QHBoxLayout()
        dl_row.addWidget(QLabel(_("Download Unique"), self))
        self.unique_combo = QComboBox(self)
        self.unique_combo.addItems(
            [
                _("Main fields from current view"),
                _("Artists"),
                _("Titles"),
                _("Albums"),
            ]
        )
        dl_row.addWidget(self.unique_combo)
        self.download_btn = QPushButton(_("Download Unique Entries"), self)
        self.download_btn.clicked.connect(self.download_unique_entries)
        dl_row.addWidget(self.download_btn)
        dl_row.addStretch()
        root.addLayout(dl_row)

    def _connect_signals(self):
        self._lookup_complete.connect(self._on_lookup_complete)
        self._status.connect(self.status_label.setText)
        self._error.connect(self._on_error)
        self._set_busy.connect(self._on_set_busy)
        self._download_progress.connect(self._on_download_progress)
        self._download_complete.connect(self._on_download_complete)

    def _on_set_busy(self, busy: bool):
        self.search_btn.setEnabled(not busy)
        self.download_btn.setEnabled(not busy)

    def lookup_library(self):
        username = self.user_entry.text().strip()
        if not username:
            self.app_actions.alert(_("Missing username"), _("Please enter a Last.fm username."), kind="warning")
            return
        scope = self.scope_combo.currentText()
        self.progress_bar.setValue(0)
        self.results_list.clear()
        self._set_busy.emit(True)
        self._status.emit(_("Loading Last.fm data..."))
        Utils.start_thread(
            lambda: self._lookup_library_worker(username, scope),
            use_asyncio=False,
        )

    def _lookup_library_worker(self, username: str, scope_text: str):
        try:
            user_info = self.api.get_user_info(username)
            scope = self._normalize_scope(scope_text)
            if scope == "tracks":
                page = self.api.get_library_tracks(username, page=1, limit=100)
                items = [
                    f"{t.playcount:>6}  {t.artist} - {t.name}" for t in page.tracks
                ]
            elif scope == "albums":
                page = self.api.get_library_albums(username, page=1, limit=100)
                items = [
                    f"{a.playcount:>6}  {a.artist} - {a.name}" for a in page.albums
                ]
            else:
                page = self.api.get_library_artists(username, page=1, limit=100)
                items = [f"{a.playcount:>6}  {a.name}" for a in page.artists]
            self._lookup_complete.emit(
                {
                    "username": username,
                    "scope": scope,
                    "user_info": user_info,
                    "pagination": page.pagination,
                    "items": items,
                }
            )
        except Exception as exc:
            self._error.emit(str(exc))
        finally:
            self._set_busy.emit(False)

    def _on_lookup_complete(self, payload: dict[str, Any]):
        info = payload["user_info"]
        pagination = payload["pagination"]
        self.summary_label.setText(
            _(
                "User: {0}\nProfile: {1}\nLibrary counts: artists={2}, albums={3}, tracks={4}\n"
                "Showing page {5}/{6} ({7} total in this view)."
            ).format(
                info.name,
                info.url,
                info.artist_count or 0,
                info.album_count or 0,
                info.track_count or 0,
                pagination.page,
                pagination.total_pages,
                pagination.total,
            )
        )
        self.results_list.clear()
        self.results_list.addItems(payload["items"])
        self.progress_bar.setValue(100)
        self._status.emit(_("Loaded first page."))

    def download_unique_entries(self):
        username = self.user_entry.text().strip()
        if not username:
            self.app_actions.alert(_("Missing username"), _("Please enter a Last.fm username."), kind="warning")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            _("Save Unique Library Entries"),
            f"lastfm_{username}_unique_entries.txt",
            _("Text Files (*.txt);;All Files (*.*)"),
        )
        if not file_path:
            return

        scope = self._normalize_scope(self.scope_combo.currentText())
        unique_mode = self.unique_combo.currentText()
        self.progress_bar.setValue(0)
        self._set_busy.emit(True)
        self._status.emit(_("Downloading unique entries..."))
        Utils.start_thread(
            lambda: self._download_unique_worker(username, scope, unique_mode, file_path),
            use_asyncio=False,
        )

    def _download_unique_worker(self, username: str, scope: str, unique_mode: str, file_path: str):
        try:
            if scope == "tracks":
                sections, total = self._collect_unique_tracks(username, unique_mode)
            elif scope == "albums":
                sections, total = self._collect_unique_albums(username, unique_mode)
            else:
                sections, total = self._collect_unique_artists(username)

            lines = [f"Last.fm unique entries for user: {username}", ""]
            for title, values in sections.items():
                lines.append(f"[{title}]")
                if values:
                    lines.extend(sorted(values))
                else:
                    lines.append("(none)")
                lines.append("")

            with open(file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

            self._download_complete.emit(file_path, total)
        except Exception as exc:
            self._error.emit(str(exc))
            self._set_busy.emit(False)

    def _collect_unique_tracks(self, username: str, unique_mode: str):
        titles = set()
        artists = set()
        albums = set()
        page_num = 1
        first_page = self.api.get_library_tracks(username, page=page_num, limit=200)
        total_pages = max(first_page.pagination.total_pages, 1)

        def collect(page):
            for t in page.tracks:
                if t.name:
                    titles.add(t.name)
                if t.artist:
                    artists.add(t.artist)
                if t.album:
                    albums.add(t.album)

        collect(first_page)
        self._download_progress.emit(int((page_num / total_pages) * 100), _("Fetched page {0}/{1}").format(page_num, total_pages))
        for page_num in range(2, total_pages + 1):
            page = self.api.get_library_tracks(username, page=page_num, limit=200)
            collect(page)
            self._download_progress.emit(int((page_num / total_pages) * 100), _("Fetched page {0}/{1}").format(page_num, total_pages))
            time.sleep(0.2)

        sections = self._select_sections(unique_mode, titles=titles, artists=artists, albums=albums)
        return sections, len(titles) + len(artists) + len(albums)

    def _collect_unique_albums(self, username: str, unique_mode: str):
        albums = set()
        artists = set()
        page_num = 1
        first_page = self.api.get_library_albums(username, page=page_num, limit=200)
        total_pages = max(first_page.pagination.total_pages, 1)

        def collect(page):
            for a in page.albums:
                if a.name:
                    albums.add(a.name)
                if a.artist:
                    artists.add(a.artist)

        collect(first_page)
        self._download_progress.emit(int((page_num / total_pages) * 100), _("Fetched page {0}/{1}").format(page_num, total_pages))
        for page_num in range(2, total_pages + 1):
            page = self.api.get_library_albums(username, page=page_num, limit=200)
            collect(page)
            self._download_progress.emit(int((page_num / total_pages) * 100), _("Fetched page {0}/{1}").format(page_num, total_pages))
            time.sleep(0.2)

        sections = self._select_sections(unique_mode, titles=set(), artists=artists, albums=albums)
        return sections, len(albums) + len(artists)

    def _collect_unique_artists(self, username: str):
        artists = set()
        page_num = 1
        first_page = self.api.get_library_artists(username, page=page_num, limit=200)
        total_pages = max(first_page.pagination.total_pages, 1)
        for a in first_page.artists:
            if a.name:
                artists.add(a.name)
        self._download_progress.emit(int((page_num / total_pages) * 100), _("Fetched page {0}/{1}").format(page_num, total_pages))

        for page_num in range(2, total_pages + 1):
            page = self.api.get_library_artists(username, page=page_num, limit=200)
            for a in page.artists:
                if a.name:
                    artists.add(a.name)
            self._download_progress.emit(int((page_num / total_pages) * 100), _("Fetched page {0}/{1}").format(page_num, total_pages))
            time.sleep(0.2)

        return {"Artists": artists}, len(artists)

    def _select_sections(self, unique_mode: str, titles: set[str], artists: set[str], albums: set[str]):
        if unique_mode == _("Artists"):
            return {"Artists": artists}
        if unique_mode == _("Titles"):
            return {"Titles": titles}
        if unique_mode == _("Albums"):
            return {"Albums": albums}
        return {
            "Artists": artists,
            "Titles": titles,
            "Albums": albums,
        }

    def _on_download_progress(self, value: int, status: str):
        self.progress_bar.setValue(max(0, min(value, 100)))
        self.status_label.setText(status)

    def _on_download_complete(self, file_path: str, unique_count: int):
        self.progress_bar.setValue(100)
        self._set_busy.emit(False)
        self.status_label.setText(_("Download complete."))
        QMessageBox.information(
            self,
            _("Last.fm Download Complete"),
            _("Saved {0} unique entries to:\n{1}").format(unique_count, file_path),
        )

    def _on_error(self, msg: str):
        self.progress_bar.setValue(0)
        self.status_label.setText(_("Error: {0}").format(msg))
        self._set_busy.emit(False)
        self.app_actions.alert(_("Last.fm Error"), msg, kind="error")

    @staticmethod
    def _normalize_scope(scope_text: str) -> str:
        lowered = scope_text.strip().lower()
        if "album" in lowered:
            return "albums"
        if "artist" in lowered:
            return "artists"
        return "tracks"

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if LastFmLibraryWindow.top_level is self:
            LastFmLibraryWindow.top_level = None
        event.accept()
