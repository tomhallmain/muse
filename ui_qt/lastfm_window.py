"""
Last.fm public library browser window (PySide6).
"""

from __future__ import annotations

import time
from typing import Any, Optional

import csv
import os

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

from extensions.lastfm_api import LastFmAPIError, LastFmReadAPI, get_lastfm_cache
from extensions.musicbrainz_api import MusicBrainzReadAPI, get_mb_cache
from lib.multi_display_qt import SmartWindow
from ui_qt.app_style import AppStyle
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._


class LastFmLibraryWindow(SmartWindow):
    top_level = None

    _MAX_RETRIES = 3

    _lookup_complete = Signal(object)
    _status = Signal(str)
    _error = Signal(str)
    _set_busy = Signal(bool)
    _download_progress = Signal(int, str)
    _download_complete = Signal(str, str, int)  # (lfm_file, mb_file_or_empty, count)
    _enrich_complete = Signal(int)  # total MB cache entries after manual enrichment

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
        self._mb_api: Optional[MusicBrainzReadAPI] = None  # created on first enrichment
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

        mb_row = QHBoxLayout()
        self.enrich_mb_btn = QPushButton(_("Enrich with MusicBrainz"), self)
        self.enrich_mb_btn.clicked.connect(self.enrich_musicbrainz)
        mb_row.addWidget(self.enrich_mb_btn)
        self.mb_status_label = QLabel("", self)
        mb_row.addWidget(self.mb_status_label)
        mb_row.addStretch()
        root.addLayout(mb_row)

    def _connect_signals(self):
        self._lookup_complete.connect(self._on_lookup_complete)
        self._status.connect(self.status_label.setText)
        self._error.connect(self._on_error)
        self._set_busy.connect(self._on_set_busy)
        self._download_progress.connect(self._on_download_progress)
        self._download_complete.connect(self._on_download_complete)
        self._enrich_complete.connect(self._on_enrich_complete)

    def _on_set_busy(self, busy: bool):
        self.search_btn.setEnabled(not busy)
        self.download_btn.setEnabled(not busy)
        self.enrich_mb_btn.setEnabled(not busy)

    def _call_with_retry(self, fn):
        delay = 1.0
        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                return fn()
            except Exception as exc:
                if attempt >= self._MAX_RETRIES:
                    raise
                self._status.emit(
                    _("Attempt {0}/{1} failed: {2}. Retrying…").format(attempt, self._MAX_RETRIES, exc)
                )
                time.sleep(delay)
                delay *= 2

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
            user_info = self._call_with_retry(lambda: self.api.get_user_info(username))
            scope = self._normalize_scope(scope_text)
            if scope == "tracks":
                page = self._call_with_retry(lambda: self.api.get_library_tracks(username, page=1, limit=100))
                items = [
                    f"{t.playcount:>6}  {t.artist} - {t.name}" for t in page.tracks
                ]
            elif scope == "albums":
                page = self._call_with_retry(lambda: self.api.get_library_albums(username, page=1, limit=100))
                items = [
                    f"{a.playcount:>6}  {a.artist} - {a.name}" for a in page.albums
                ]
            else:
                page = self._call_with_retry(lambda: self.api.get_library_artists(username, page=1, limit=100))
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

        default_name = f"lastfm_{username}_unique_entries.tsv"
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            _("Save Unique Library Entries"),
            default_name,
            _("TSV Files (*.tsv);;CSV Files (*.csv);;All Files (*.*)"),
        )
        if not file_path:
            return

        export_kind = "tsv" if selected_filter.startswith("TSV") else "csv" if selected_filter.startswith("CSV") else self._infer_export_kind(file_path)
        if export_kind == "tsv" and not file_path.lower().endswith(".tsv"):
            file_path += ".tsv"
        if export_kind == "csv" and not file_path.lower().endswith(".csv"):
            file_path += ".csv"

        scope = self._normalize_scope(self.scope_combo.currentText())
        unique_mode = self.unique_combo.currentText()
        self.progress_bar.setValue(0)
        self._set_busy.emit(True)
        self._status.emit(_("Downloading unique entries..."))
        Utils.start_thread(
            lambda: self._download_unique_worker(username, scope, unique_mode, file_path, export_kind),
            use_asyncio=False,
        )

    def _download_unique_worker(self, username: str, scope: str, unique_mode: str, file_path: str, export_kind: str):
        try:
            if scope == "tracks":
                headers, rows, total = self._collect_unique_tracks(username, unique_mode)
            elif scope == "albums":
                headers, rows, total = self._collect_unique_albums(username, unique_mode)
            else:
                headers, rows, total = self._collect_unique_artists(username)

            delimiter = "\t" if export_kind == "tsv" else ","
            self._write_rows(file_path, headers, rows, delimiter)

            # Auto-enrich with MusicBrainz for "Main fields" tracks only.
            # Restart the progress bar so the two phases are visually distinct.
            mb_file_path = ""
            if scope == "tracks" and unique_mode not in (_("Artists"), _("Titles"), _("Albums")):
                mb_file_path = self._derive_mb_path(file_path)
                self._download_progress.emit(0, _("Starting MusicBrainz enrichment…"))
                self._run_mb_enrichment_and_write(username, mb_file_path, delimiter)

            self._download_complete.emit(file_path, mb_file_path, total)
        except Exception as exc:
            self._error.emit(str(exc))
            self._set_busy.emit(False)

    def _collect_unique_tracks(self, username: str, unique_mode: str):
        track_rows: dict[tuple, dict] = {}
        artists: set[str] = set()
        titles: set[str] = set()
        albums: set[str] = set()

        def collect(page):
            for t in page.tracks:
                key = (t.artist.lower(), t.name.lower())
                if key not in track_rows:
                    track_rows[key] = {
                        "rank": t.rank if t.rank is not None else "",
                        "playcount": t.playcount,
                        "artist": t.artist,
                        "title": t.name,
                        "_mbid": t.mbid or "",
                    }
                if t.artist:
                    artists.add(t.artist)
                if t.name:
                    titles.add(t.name)
                if t.album:
                    albums.add(t.album)

        page_num = 1
        first_page = self._call_with_retry(lambda: self.api.get_library_tracks(username, page=1, limit=200))
        total_pages = max(first_page.pagination.total_pages, 1)
        collect(first_page)
        self._download_progress.emit(int((page_num / total_pages) * 100), _("Fetched page {0}/{1}").format(page_num, total_pages))
        for page_num in range(2, total_pages + 1):
            page = self._call_with_retry(lambda p=page_num: self.api.get_library_tracks(username, page=p, limit=200))
            collect(page)
            self._download_progress.emit(int((page_num / total_pages) * 100), _("Fetched page {0}/{1}").format(page_num, total_pages))
            time.sleep(0.2)

        # Persist to Last.fm cache so MB enrichment can run as a separate step
        lfm_cache = get_lastfm_cache()
        lfm_cache.set_scope(username, "tracks", [
            {
                "name": r["title"],
                "artist": r["artist"],
                "playcount": r["playcount"],
                "rank": r["rank"] if isinstance(r["rank"], int) else None,
                "mbid": r["_mbid"],
                "album": None,
            }
            for r in track_rows.values()
        ])
        lfm_cache.save()

        if unique_mode == _("Artists"):
            headers = ["artist"]
            rows = [{"artist": a} for a in sorted(artists)]
            return headers, rows, len(rows)

        if unique_mode == _("Titles"):
            headers = ["title"]
            rows = [{"title": t} for t in sorted(titles)]
            return headers, rows, len(rows)

        if unique_mode == _("Albums"):
            headers = ["album"]
            rows = [{"album": a} for a in sorted(albums)]
            return headers, rows, len(rows)

        # Main fields: pure Last.fm data only. MusicBrainz enrichment runs
        # automatically afterwards as a separate pass and writes its own file.
        headers = ["rank", "playcount", "artist", "title"]
        rows = [
            {"rank": r["rank"], "playcount": r["playcount"], "artist": r["artist"], "title": r["title"]}
            for r in sorted(
                track_rows.values(),
                key=lambda r: (r["rank"] if isinstance(r["rank"], int) else 999999, -r["playcount"]),
            )
        ]
        return headers, rows, len(rows)

    def _collect_unique_albums(self, username: str, unique_mode: str):
        album_rows: dict[tuple, dict] = {}
        artists: set[str] = set()
        album_names: set[str] = set()

        def collect(page):
            for a in page.albums:
                key = (a.artist.lower(), a.name.lower())
                if key not in album_rows:
                    album_rows[key] = {
                        "playcount": a.playcount,
                        "artist": a.artist,
                        "album": a.name,
                        "mbid": a.mbid or "",
                    }
                if a.artist:
                    artists.add(a.artist)
                if a.name:
                    album_names.add(a.name)

        page_num = 1
        first_page = self._call_with_retry(lambda: self.api.get_library_albums(username, page=1, limit=200))
        total_pages = max(first_page.pagination.total_pages, 1)
        collect(first_page)
        self._download_progress.emit(int((page_num / total_pages) * 100), _("Fetched page {0}/{1}").format(page_num, total_pages))
        for page_num in range(2, total_pages + 1):
            page = self._call_with_retry(lambda p=page_num: self.api.get_library_albums(username, page=p, limit=200))
            collect(page)
            self._download_progress.emit(int((page_num / total_pages) * 100), _("Fetched page {0}/{1}").format(page_num, total_pages))
            time.sleep(0.2)

        # Persist to Last.fm cache
        lfm_cache = get_lastfm_cache()
        lfm_cache.set_scope(username, "albums", list(album_rows.values()))
        lfm_cache.save()

        if unique_mode == _("Artists"):
            headers = ["artist"]
            rows = [{"artist": a} for a in sorted(artists)]
        elif unique_mode == _("Albums"):
            headers = ["album"]
            rows = [{"album": a} for a in sorted(album_names)]
        else:
            headers = ["playcount", "artist", "album", "mbid"]
            rows = sorted(album_rows.values(), key=lambda r: -r["playcount"])
        return headers, rows, len(rows)

    def _collect_unique_artists(self, username: str):
        artist_rows: dict[str, dict] = {}

        def collect(page):
            for a in page.artists:
                if a.name and a.name.lower() not in artist_rows:
                    artist_rows[a.name.lower()] = {
                        "rank": a.rank if a.rank is not None else "",
                        "playcount": a.playcount,
                        "artist": a.name,
                        "mbid": a.mbid or "",
                    }

        page_num = 1
        first_page = self._call_with_retry(lambda: self.api.get_library_artists(username, page=1, limit=200))
        total_pages = max(first_page.pagination.total_pages, 1)
        collect(first_page)
        self._download_progress.emit(int((page_num / total_pages) * 100), _("Fetched page {0}/{1}").format(page_num, total_pages))
        for page_num in range(2, total_pages + 1):
            page = self._call_with_retry(lambda p=page_num: self.api.get_library_artists(username, page=p, limit=200))
            collect(page)
            self._download_progress.emit(int((page_num / total_pages) * 100), _("Fetched page {0}/{1}").format(page_num, total_pages))
            time.sleep(0.2)

        # Persist to Last.fm cache
        lfm_cache = get_lastfm_cache()
        lfm_cache.set_scope(username, "artists", list(artist_rows.values()))
        lfm_cache.save()

        headers = ["rank", "playcount", "artist", "mbid"]
        rows = sorted(
            artist_rows.values(),
            key=lambda r: (r["rank"] if isinstance(r["rank"], int) else 999999, -r["playcount"]),
        )
        return headers, rows, len(rows)

    def _on_download_progress(self, value: int, status: str):
        self.progress_bar.setValue(max(0, min(value, 100)))
        self.status_label.setText(status)

    def _on_download_complete(self, file_path: str, mb_file_path: str, unique_count: int):
        self.progress_bar.setValue(100)
        self._set_busy.emit(False)
        self.status_label.setText(_("Download complete."))
        if mb_file_path:
            body = _("Saved {0} entries.\n\nLast.fm data:\n{1}\n\nMusicBrainz enrichment:\n{2}").format(
                unique_count, file_path, mb_file_path
            )
        else:
            body = _("Saved {0} unique entries to:\n{1}").format(unique_count, file_path)
        QMessageBox.information(self, _("Last.fm Download Complete"), body)

    @staticmethod
    def _derive_mb_path(file_path: str) -> str:
        """Insert '_mb' before the extension, e.g. 'tracks.tsv' → 'tracks_mb.tsv'."""
        base, ext = os.path.splitext(file_path)
        return f"{base}_mb{ext}"

    @staticmethod
    def _write_rows(file_path: str, headers: list, rows: list, delimiter: str) -> None:
        with open(file_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers, delimiter=delimiter, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def _run_mb_enrichment_and_write(self, username: str, mb_file_path: str, delimiter: str) -> None:
        """Fetch MB credits for all cached track MBIDs, then write the enriched file."""
        if self._mb_api is None:
            self._mb_api = MusicBrainzReadAPI()

        cached = get_lastfm_cache().get_scope(username, "tracks") or []
        mbids = list({t["mbid"] for t in cached if t.get("mbid")})
        mb_cache = get_mb_cache()

        def mb_progress(completed: int, total: int) -> None:
            pct = int((completed / total) * 100) if total > 0 else 100
            self._download_progress.emit(pct, _("MusicBrainz: {0}/{1} recordings").format(completed, total))

        self._mb_api.enrich_recordings(mbids, mb_cache, mb_progress)

        headers = ["lfm_rank", "lfm_playcount", "lfm_artist", "lfm_title", "mb_title", "mb_artist", "mb_genres", "mb_composer", "mb_lyricist", "mb_arranger"]
        rows = []
        for t in sorted(cached, key=lambda t: (t.get("rank") or 999999, -t.get("playcount", 0))):
            mb = mb_cache.get(t.get("mbid", "")) if t.get("mbid") else None
            rows.append({
                "lfm_rank": t.get("rank") or "",
                "lfm_playcount": t.get("playcount", 0),
                "lfm_artist": t.get("artist", ""),
                "lfm_title": t.get("name", ""),
                "mb_title": mb.get("mb_title", "") if mb else "",
                "mb_artist": mb.get("mb_artist", "") if mb else "",
                "mb_genres": "; ".join(mb.get("mb_genres", [])) if mb else "",
                "mb_composer": "; ".join(mb.get("composer", [])) if mb else "",
                "mb_lyricist": "; ".join(mb.get("lyricist", [])) if mb else "",
                "mb_arranger": "; ".join(mb.get("arranger", [])) if mb else "",
            })
        self._write_rows(mb_file_path, headers, rows, delimiter)

    def enrich_musicbrainz(self):
        username = self.user_entry.text().strip()
        if not username:
            self.app_actions.alert(_("Missing username"), _("Please enter a Last.fm username."), kind="warning")
            return
        cached_tracks = get_lastfm_cache().get_scope(username, "tracks")
        if not cached_tracks:
            self.app_actions.alert(
                _("No cached data"),
                _("Export the library first so the tracks are cached, then run enrichment."),
                kind="warning",
            )
            return
        self.progress_bar.setValue(0)
        self._set_busy.emit(True)
        self._status.emit(_("Enriching from MusicBrainz…"))
        Utils.start_thread(
            lambda: self._enrich_mb_worker(cached_tracks),
            use_asyncio=False,
        )

    def _enrich_mb_worker(self, cached_tracks: list):
        try:
            if self._mb_api is None:
                self._mb_api = MusicBrainzReadAPI()
            mbids = list({t["mbid"] for t in cached_tracks if t.get("mbid")})
            mb_cache = get_mb_cache()

            def mb_progress(completed: int, total: int) -> None:
                pct = int((completed / total) * 100) if total > 0 else 100
                self._download_progress.emit(
                    pct,
                    _("MusicBrainz: {0}/{1} recordings").format(completed, total),
                )

            self._mb_api.enrich_recordings(mbids, mb_cache, mb_progress)
            self._enrich_complete.emit(mb_cache.size)
        except Exception as exc:
            self._error.emit(str(exc))
            self._set_busy.emit(False)

    def _on_enrich_complete(self, total_cached: int):
        self.progress_bar.setValue(100)
        self._set_busy.emit(False)
        self.mb_status_label.setText(_("MB cache: {0} recordings").format(total_cached))
        self.status_label.setText(_("MusicBrainz enrichment complete."))

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

    @staticmethod
    def _infer_export_kind(file_path: str) -> str:
        ext = os.path.splitext(file_path.lower())[1]
        if ext == ".csv":
            return "csv"
        return "tsv"

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if LastFmLibraryWindow.top_level is self:
            LastFmLibraryWindow.top_level = None
        event.accept()
