"""
Search library window (PySide6).
Port of ui/search_window.py; static methods and __init__ only for now.
"""

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QCheckBox,
    QScrollArea,
    QSizePolicy,
    QWidget,
    QFrame,
    QInputDialog,
)
from PySide6.QtCore import Qt, QTimer, Signal

from lib.multi_display_qt import SmartWindow
from library_data.library_data import LibraryDataSearch
from ui_qt.app_style import AppStyle
from ui_qt.auth.password_utils import require_password
from utils.app_info_cache import app_info_cache
from utils.config import config
from utils.globals import PlaylistSortType, ProtectedActions
from utils.translations import I18N
from utils.logging_setup import get_logger
from utils.utils import Utils

_ = I18N._
logger = get_logger(__name__)


class SearchWindow(SmartWindow):
    """Window to search media library."""

    # Emit from worker thread; slots run on main thread
    _search_complete = Signal()
    _search_status = Signal(str)
    _search_error = Signal(str)

    COL_0_WIDTH = 300
    top_level = None
    INITIAL_MAX_RESULTS = getattr(config, "max_search_results", 100)
    MAX_RECENT_SEARCHES = 200
    recent_searches: list[LibraryDataSearch] = []

    @staticmethod
    def load_recent_searches():
        SearchWindow.recent_searches.clear()
        recent_searches = app_info_cache.get("recent_searches", [])
        assert recent_searches is not None
        seen_searches = set()
        skip_count = 0
        for search_json in recent_searches:
            library_data_search = LibraryDataSearch.from_json(search_json)
            if library_data_search.is_valid() and library_data_search.stored_results_count > 0:
                if library_data_search not in seen_searches:
                    SearchWindow.recent_searches.append(library_data_search)
                    seen_searches.add(library_data_search)
                else:
                    skip_count += 1
            else:
                logger.warning("Invalid search removed: %s", search_json)
        if skip_count > 0:
            logger.warning("Skipped %s duplicate searches", skip_count)
        if len(SearchWindow.recent_searches) > SearchWindow.MAX_RECENT_SEARCHES:
            logger.warning(
                "Limiting searches from %s to %s",
                len(SearchWindow.recent_searches),
                SearchWindow.MAX_RECENT_SEARCHES,
            )
            SearchWindow.recent_searches = SearchWindow.recent_searches[
                : SearchWindow.MAX_RECENT_SEARCHES
            ]

    @staticmethod
    def store_recent_searches():
        seen_searches = set()
        unique_searches = []
        for library_data_search in SearchWindow.recent_searches:
            if library_data_search.is_valid() and library_data_search.stored_results_count > 0:
                if library_data_search not in seen_searches:
                    unique_searches.append(library_data_search)
                    seen_searches.add(library_data_search)
        if len(unique_searches) > SearchWindow.MAX_RECENT_SEARCHES:
            logger.warning(
                "Limiting stored searches from %s to %s",
                len(unique_searches),
                SearchWindow.MAX_RECENT_SEARCHES,
            )
            unique_searches = unique_searches[: SearchWindow.MAX_RECENT_SEARCHES]
        json_searches = [s.to_json() for s in unique_searches]
        app_info_cache.set("recent_searches", json_searches)

    @staticmethod
    def find_track(library_data, library_data_search, save_to_recent=False, overwrite=False):
        """Search for a track and play it if found."""
        try:
            if library_data_search.id:
                track = library_data.find_track_by_id(
                    library_data_search.id, overwrite=overwrite
                )
                if track:
                    return track
                logger.info("No track found by ID, falling back to search")
            library_data.do_search(library_data_search, overwrite=False)
            results = library_data_search.get_results()
            if results:
                if save_to_recent:
                    library_data_search.set_selected_track_path(results[0])
                    SearchWindow.update_recent_searches(library_data_search)
            elif library_data_search.title:
                matches = library_data.find_track_by_fuzzy_title(
                    library_data_search.title, overwrite=False, max_results=1
                )
                if matches:
                    results = matches
            if not results:
                raise ValueError(_("No matching tracks found"))
            return results[0]
        except Exception as e:
            logger.error("Error in find_track: %s", str(e))
            raise

    @staticmethod
    def update_recent_searches(library_data_search, remove_searches_with_no_selected_filepath=False):
        assert library_data_search is not None
        SearchWindow.recent_searches = [
            s for s in SearchWindow.recent_searches if s != library_data_search
        ]
        if remove_searches_with_no_selected_filepath:
            SearchWindow.recent_searches = [
                s
                for s in SearchWindow.recent_searches
                if not (
                    (s.selected_track_path is None or s.selected_track_path.strip() == "")
                    and s.matches_no_selected_track_path(library_data_search)
                )
            ]
        SearchWindow.recent_searches.insert(0, library_data_search)
        if len(SearchWindow.recent_searches) > SearchWindow.MAX_RECENT_SEARCHES:
            del SearchWindow.recent_searches[-1]

    def __init__(self, master, app_actions, library_data, dimensions="1100x820"):
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("Search Library"),
            geometry=dimensions,
            offset_x=50,
            offset_y=50,
        )
        SearchWindow.top_level = self
        self.setMinimumSize(400, 400)

        self.app_actions = app_actions
        self.library_data = library_data
        self.library_data_search = None

        self.title_list = []
        self.album_list = []
        self.artist_list = []
        self.composer_list = []
        self.open_details_btn_list = []
        self.play_btn_list = []
        self.add_to_playlist_btn_list = []
        self.remove_btn_list = []
        self.current_offset = 0
        self.pagination_warning_label = None
        self.pagination_next_btn = None
        self.has_closed = False

        self.setStyleSheet(AppStyle.get_stylesheet())
        outer = QVBoxLayout(self)
        outer.setContentsMargins(5, 5, 5, 5)

        self.results_scroll = QScrollArea(self)
        self.results_scroll.setWidgetResizable(True)
        self.results_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.results_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.results_widget = QWidget(self.results_scroll)
        self.results_layout = QGridLayout(self.results_widget)
        self.results_scroll.setWidget(self.results_widget)
        outer.addWidget(self.results_scroll, 7)

        self.pagination_frame = QFrame(self)
        self.pagination_layout = QHBoxLayout(self.pagination_frame)
        self.pagination_layout.addStretch()
        outer.addWidget(self.pagination_frame)

        inner = QFrame(self)
        inner_layout = QGridLayout(inner)
        row = 0

        self.search_btn = QPushButton(_("Search"), self)
        self.search_btn.clicked.connect(self.do_search)
        inner_layout.addWidget(self.search_btn, row, 0, 1, 3)
        row += 1

        inner_layout.addWidget(QLabel(_("Search all fields"), inner), row, 0)
        self.all_entry = QLineEdit(inner)
        self.all_entry.setMinimumWidth(200)
        self.all_entry.returnPressed.connect(self.do_search)
        inner_layout.addWidget(self.all_entry, row, 1)
        row += 1

        inner_layout.addWidget(QLabel(_("Search Title"), inner), row, 0)
        self.title_entry = QLineEdit(inner)
        self.title_entry.setMinimumWidth(200)
        self.title_entry.returnPressed.connect(self.do_search)
        inner_layout.addWidget(self.title_entry, row, 1)
        self.sort_by_title_btn = QPushButton(_("Sort by"), inner)
        self.sort_by_title_btn.clicked.connect(lambda: self.sort_by("title"))
        inner_layout.addWidget(self.sort_by_title_btn, row, 2)
        row += 1

        inner_layout.addWidget(QLabel(_("Search Album"), inner), row, 0)
        self.album_entry = QLineEdit(inner)
        self.album_entry.setMinimumWidth(200)
        self.album_entry.returnPressed.connect(self.do_search)
        inner_layout.addWidget(self.album_entry, row, 1)
        self.sort_by_album_btn = QPushButton(_("Sort by"), inner)
        self.sort_by_album_btn.clicked.connect(lambda: self.sort_by("album"))
        inner_layout.addWidget(self.sort_by_album_btn, row, 2)
        row += 1

        inner_layout.addWidget(QLabel(_("Search Artist"), inner), row, 0)
        self.artist_entry = QLineEdit(inner)
        self.artist_entry.setMinimumWidth(200)
        self.artist_entry.returnPressed.connect(self.do_search)
        inner_layout.addWidget(self.artist_entry, row, 1)
        self.sort_by_artist_btn = QPushButton(_("Sort by"), inner)
        self.sort_by_artist_btn.clicked.connect(lambda: self.sort_by("artist"))
        inner_layout.addWidget(self.sort_by_artist_btn, row, 2)
        row += 1

        inner_layout.addWidget(QLabel(_("Search Composer"), inner), row, 0)
        self.composer_entry = QLineEdit(inner)
        self.composer_entry.setMinimumWidth(200)
        self.composer_entry.returnPressed.connect(self.do_search)
        inner_layout.addWidget(self.composer_entry, row, 1)
        self.sort_by_composer_btn = QPushButton(_("Sort by"), inner)
        self.sort_by_composer_btn.clicked.connect(lambda: self.sort_by("composer"))
        inner_layout.addWidget(self.sort_by_composer_btn, row, 2)
        row += 1

        inner_layout.addWidget(QLabel(_("Search Genre"), inner), row, 0)
        self.genre_entry = QLineEdit(inner)
        self.genre_entry.setMinimumWidth(200)
        self.genre_entry.returnPressed.connect(self.do_search)
        inner_layout.addWidget(self.genre_entry, row, 1)
        self.sort_by_genre_btn = QPushButton(_("Sort by"), inner)
        self.sort_by_genre_btn.clicked.connect(lambda: self.sort_by("genre"))
        inner_layout.addWidget(self.sort_by_genre_btn, row, 2)
        row += 1

        inner_layout.addWidget(QLabel(_("Search Instrument"), inner), row, 0)
        self.instrument_entry = QLineEdit(inner)
        self.instrument_entry.setMinimumWidth(200)
        self.instrument_entry.returnPressed.connect(self.do_search)
        inner_layout.addWidget(self.instrument_entry, row, 1)
        self.sort_by_instrument_btn = QPushButton(_("Sort by"), inner)
        self.sort_by_instrument_btn.clicked.connect(lambda: self.sort_by("instrument"))
        inner_layout.addWidget(self.sort_by_instrument_btn, row, 2)
        row += 1

        inner_layout.addWidget(QLabel(_("Search Form"), inner), row, 0)
        self.form_entry = QLineEdit(inner)
        self.form_entry.setMinimumWidth(200)
        self.form_entry.returnPressed.connect(self.do_search)
        inner_layout.addWidget(self.form_entry, row, 1)
        self.sort_by_form_btn = QPushButton(_("Sort by"), inner)
        self.sort_by_form_btn.clicked.connect(lambda: self.sort_by("form"))
        inner_layout.addWidget(self.sort_by_form_btn, row, 2)
        row += 1

        self.overwrite_cache_check = QCheckBox(_("Overwrite Cache"), inner)
        self.overwrite_cache_check.setChecked(False)
        inner_layout.addWidget(self.overwrite_cache_check, row, 0)
        inner_layout.addWidget(QLabel(_("Playlist Sort"), inner), row, 1)
        self.playlist_sort_combo = QComboBox(inner)
        self.playlist_sort_combo.addItems(PlaylistSortType.get_translated_names())
        self.playlist_sort_combo.setCurrentText(PlaylistSortType.RANDOM.get_translation())
        inner_layout.addWidget(self.playlist_sort_combo, row, 2)
        row += 1

        self._save_as_playlist_btn = QPushButton(_("Save as Playlist"), inner)
        self._save_as_playlist_btn.clicked.connect(self._save_search_as_playlist)
        inner_layout.addWidget(self._save_as_playlist_btn, row, 0)
        row += 1

        inner_layout.addWidget(QLabel(_("Filter Results"), inner), row, 0)
        self.filter_entry = QLineEdit(inner)
        self.filter_entry.setMinimumWidth(200)
        self.filter_entry.textChanged.connect(self.apply_filter)
        inner_layout.addWidget(self.filter_entry, row, 1)
        self.filter_entry.hide()
        row += 1

        outer.addWidget(inner)

        self._search_complete.connect(self._update_ui_after_search)
        self._search_status.connect(self._update_search_status)
        self._search_error.connect(self._show_search_error)

        self._update_playlist_sort_dropdown()
        self.show()
        QTimer.singleShot(0, self.show_recent_searches)

    def show_recent_searches(self):
        if len(SearchWindow.recent_searches) == 0:
            self.clear_widget_lists()
            self.searching_label = QLabel(_("No recent searches found."), self.results_widget)
            self.searching_label.setWordWrap(True)
            self.results_layout.addWidget(self.searching_label, 1, 1)
            self.title_list.append(self.searching_label)
            return
        self.clear_widget_lists()
        for i in range(len(SearchWindow.recent_searches)):
            row = i + 1
            search = SearchWindow.recent_searches[i]
            track = self.library_data.get_track(search.selected_track_path)
            if track is not None:
                title = track.title or ""
                album = track.album or ""
            else:
                title = _("(No track selected)")
                album = "--"

            title_label = QLabel(title, self.results_widget)
            title_label.setWordWrap(True)
            title_label.setMinimumWidth(200)
            title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self.results_layout.addWidget(title_label, row, 1)
            self.title_list.append(title_label)

            album_label = QLabel(album, self.results_widget)
            album_label.setWordWrap(True)
            album_label.setMinimumWidth(200)
            album_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self.results_layout.addWidget(album_label, row, 2)
            self.album_list.append(album_label)

            search_label = QLabel(str(search), self.results_widget)
            search_label.setWordWrap(True)
            search_label.setMinimumWidth(200)
            search_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self.results_layout.addWidget(search_label, row, 3)
            self.artist_list.append(search_label)

            results_count_label = QLabel(
                search.get_readable_stored_results_count(), self.results_widget
            )
            self.results_layout.addWidget(results_count_label, row, 4)
            self.composer_list.append(results_count_label)

            search_btn = QPushButton(_("Search"), self.results_widget)
            search_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.open_details_btn_list.append(search_btn)
            self.results_layout.addWidget(search_btn, row, 5)

            def make_search_handler(lib_search):
                def handler():
                    self.load_stored_search(library_data_search=lib_search)
                    self._do_search(overwrite=self.overwrite_cache_check.isChecked())
                return handler

            search_btn.clicked.connect(make_search_handler(search))

            play_btn = QPushButton(_("Play"), self.results_widget)
            play_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.play_btn_list.append(play_btn)
            self.results_layout.addWidget(play_btn, row, 6)

            def make_play_handler(lib_search, tr):
                def handler():
                    self.load_stored_search(library_data_search=lib_search)
                    self._do_search(overwrite=False)
                    t = tr
                    if t is None:
                        logger.info(
                            "No specific track defined on search, using first available track."
                        )
                        t = lib_search.get_first_available_track()
                        if t is None:
                            raise Exception("No tracks available on search.")
                    elif t.is_invalid():
                        raise Exception("Invalid track: {}".format(t))
                    self.run_play_callback(t)
                return handler

            play_btn.clicked.connect(make_play_handler(search, track))

            remove_btn = QPushButton(_("Remove"), self.results_widget)
            remove_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.remove_btn_list.append(remove_btn)
            self.results_layout.addWidget(remove_btn, row, 7)

            def make_remove_handler(lib_search):
                def handler():
                    self.remove_search(lib_search)
                return handler

            remove_btn.clicked.connect(make_remove_handler(search))

    @require_password(ProtectedActions.RUN_SEARCH)
    def do_search(self):
        all_val = self.all_entry.text().strip()
        title = self.title_entry.text().strip()
        album = self.album_entry.text().strip()
        artist = self.artist_entry.text().strip()
        composer = self.composer_entry.text().strip()
        genre = self.genre_entry.text().strip()
        instrument = self.instrument_entry.text().strip()
        form = self.form_entry.text().strip()
        overwrite = self.overwrite_cache_check.isChecked()
        self.current_offset = 0
        self.filter_entry.clear()
        self._update_playlist_sort_dropdown()
        self.library_data_search = LibraryDataSearch(
            all_val,
            title=title,
            album=album,
            artist=artist,
            composer=composer,
            genre=genre,
            instrument=instrument,
            form=form,
            max_results=SearchWindow.INITIAL_MAX_RESULTS,
            offset=0,
        )
        self._do_search(overwrite=overwrite)

    def load_stored_search(self, library_data_search):
        assert library_data_search is not None
        self.all_entry.setText(library_data_search.all or "")
        self.title_entry.setText(library_data_search.title or "")
        self.album_entry.setText(library_data_search.album or "")
        self.artist_entry.setText(library_data_search.artist or "")
        self.composer_entry.setText(library_data_search.composer or "")
        self.genre_entry.setText(library_data_search.genre or "")
        self.instrument_entry.setText(library_data_search.instrument or "")
        self.form_entry.setText(library_data_search.form or "")
        self.library_data_search = library_data_search
        self._update_playlist_sort_dropdown()

    @require_password(ProtectedActions.RUN_SEARCH)
    def _do_search(self, overwrite=False):
        assert self.library_data_search is not None
        self.library_data_search.offset = self.current_offset

        existing_results = []
        if self.current_offset > 0 and not overwrite:
            existing_results = self.library_data_search.results.copy()

        self.library_data_search.total_matches_count = 0
        self.library_data_search.results = []

        self._refresh_widgets(add_results=False)
        self.searching_label = QLabel(
            _("Please wait, overwriting cache and searching...")
            if overwrite
            else _("Searching..."),
            self.results_widget,
        )
        self.results_layout.addWidget(self.searching_label, 1, 1)
        self.title_list.append(self.searching_label)

        def search_complete(_search_results):
            self._search_complete.emit()

        def update_status(status_text):
            self._search_status.emit(status_text)

        def search_thread():
            try:
                self.library_data.do_search(
                    self.library_data_search,
                    overwrite=overwrite,
                    completion_callback=search_complete,
                    search_status_callback=update_status,
                )
                if existing_results:
                    self.library_data_search.results = (
                        existing_results + self.library_data_search.results
                    )
                    self.library_data_search.set_stored_results_count()
            except Exception as e:
                logger.error("Error in search thread: %s", e)
                self._search_error.emit(str(e))

        Utils.start_thread(search_thread, use_asyncio=False)

    def _update_ui_after_search(self):
        SearchWindow.update_recent_searches(self.library_data_search)
        self.filter_entry.show()
        # Uncheck "Overwrite cache" after search completes so that playing a result
        # does not unintentionally overwrite the cache again.
        if self.overwrite_cache_check.isChecked():
            self.overwrite_cache_check.setChecked(False)
        self._refresh_widgets()

    def _show_search_error(self, error_msg):
        self._refresh_widgets(add_results=False)
        error_label = QLabel(error_msg, self.results_widget)
        error_label.setWordWrap(True)
        self.results_layout.addWidget(error_label, 1, 1)
        self.title_list.append(error_label)

    def _update_search_status(self, status_text):
        """Update the search status label with progress information."""
        if hasattr(self, "searching_label") and self.searching_label.isVisible():
            self.searching_label.setText(status_text)

    def clear_widget_lists(self):
        for w in self.title_list:
            w.setParent(None)
            w.deleteLater()
        for w in self.artist_list:
            w.setParent(None)
            w.deleteLater()
        for w in self.album_list:
            w.setParent(None)
            w.deleteLater()
        for w in self.composer_list:
            w.setParent(None)
            w.deleteLater()
        for w in self.open_details_btn_list:
            w.setParent(None)
            w.deleteLater()
        for w in self.play_btn_list:
            w.setParent(None)
            w.deleteLater()
        for w in self.add_to_playlist_btn_list:
            w.setParent(None)
            w.deleteLater()
        for w in self.remove_btn_list:
            w.setParent(None)
            w.deleteLater()
        # Note: Pagination widgets are in pagination_frame (not scrollable), so they persist
        # They are managed in add_widgets_for_results() with setVisible
        self.title_list = []
        self.artist_list = []
        self.album_list = []
        self.composer_list = []
        self.open_details_btn_list = []
        self.play_btn_list = []
        self.add_to_playlist_btn_list = []
        self.remove_btn_list = []

    def _refresh_widgets(self, add_results=True):
        self.clear_widget_lists()
        if add_results:
            self.add_widgets_for_results()
        # Qt: no master.update() equivalent; layout handles refresh

    def add_widgets_for_results(self):
        assert self.library_data_search is not None
        if len(self.library_data_search.results) == 0:
            self.searching_label = QLabel(_("No results found."), self.results_widget)
            self.searching_label.setWordWrap(True)
            self.results_layout.addWidget(self.searching_label, 1, 1)
            self.title_list.append(self.searching_label)
            # Add cache reminder
            cache_reminder = QLabel(
                _(
                    "Tip: If you've recently added or moved files, try checking 'Overwrite Cache' in the search options below."
                ),
                self.results_widget,
            )
            cache_reminder.setWordWrap(True)
            self.results_layout.addWidget(cache_reminder, 2, 1)
            self.title_list.append(cache_reminder)
            return
        self.library_data_search.sort_results_by()
        results = self.library_data_search.get_results()
        total_results = len(results)
        stored_count = self.library_data_search.stored_results_count
        # Apply filter if filter text is provided
        filter_text = self.filter_entry.text().strip().lower()
        if filter_text:
            # Filter results based on filter text matching any displayed field
            filtered = [
                t
                for t in results
                if filter_text in (t.title or "").lower()
                or filter_text in (t.artist or "").lower()
                or filter_text in (t.album or "").lower()
                or filter_text in (t.composer or "").lower()
            ]
            display_results = filtered
        else:
            # No filter, show all results
            display_results = results
        display_count = len(display_results)
        # Show message if filter returns no results
        if filter_text and display_count == 0:
            self.searching_label = QLabel(
                _("No results match the filter '{0}'.").format(self.filter_entry.text()),
                self.results_widget,
            )
            self.searching_label.setWordWrap(True)
            self.results_layout.addWidget(self.searching_label, 1, 1)
            self.title_list.append(self.searching_label)
            return
        # Check if there are more results available.
        # The current page loaded (total_results - current_offset) new items;
        # if that exceeds the page size it means more exist beyond this page.
        page_result_count = total_results - self.current_offset
        has_more_detected = page_result_count > SearchWindow.INITIAL_MAX_RESULTS
        # Calculate display range - results accumulate in LibraryDataSearch object
        total_displayed = total_results
        # Determine if we should show load more controls
        # Show warning if:
        # - We detected more results (have max_results + 1)
        # - We know there are more total results than displayed
        # - We've loaded more results (current_offset > 0)
        has_more_total = stored_count > (self.current_offset + display_count)
        has_loaded_more = self.current_offset > 0
        # Add warning and load more controls in the fixed frame (not scrollable)
        if has_more_detected or has_more_total or has_loaded_more:
            # Create warning label if it doesn't exist
            if self.pagination_warning_label is None:
                self.pagination_warning_label = QLabel(self.pagination_frame)
                self.pagination_warning_label.setWordWrap(True)
                self.pagination_warning_label.setMaximumWidth(800)
                # Use light yellow/orange color for warning text
                self.pagination_warning_label.setStyleSheet("color: #FFB84D;")
                self.pagination_layout.insertWidget(0, self.pagination_warning_label)
            # Update warning text
            # Note: Results accumulate (showing all results loaded so far, not just current batch)
            # Show both values only if they are different
            filter_text = self.filter_entry.text().strip().lower()
            if filter_text:
                # Show filtered count vs total count when filtering is active
                if stored_count != display_count:
                    warning_text = _(
                        "Found {0} total results. Showing {1} filtered results."
                    ).format(stored_count, display_count)
                else:
                    warning_text = _("Showing {0} filtered results.").format(
                        display_count
                    )
            elif stored_count != total_displayed:
                warning_text = _(
                    "Found {0} total results. Showing all results up to {1}."
                ).format(stored_count, total_displayed)
            else:
                warning_text = _("Showing all results up to {0}.").format(
                    total_displayed
                )
            self.pagination_warning_label.setText(warning_text)
            self.pagination_warning_label.setVisible(True)
            # Find More button - show if we detected more results or know there are more
            if has_more_detected or has_more_total:
                if self.pagination_next_btn is None:
                    self.pagination_next_btn = QPushButton(_("Find More"), self.pagination_frame)
                    self.pagination_next_btn.clicked.connect(self.load_more_results)
                    self.pagination_layout.insertWidget(1, self.pagination_next_btn)
                self.pagination_next_btn.setVisible(True)
            elif self.pagination_next_btn is not None:
                self.pagination_next_btn.setVisible(False)
        else:
            # Hide warning and load more widgets if not needed
            if self.pagination_warning_label is not None:
                self.pagination_warning_label.setVisible(False)
            if self.pagination_next_btn is not None:
                self.pagination_next_btn.setVisible(False)
        # Display results (only show first max_results, not the extra one used for detection)
        # Results start at row 1 (row 0 is for any header if needed)
        results_start_row = 1
        for i, track in enumerate(display_results):
            row = results_start_row + i
            title_label = QLabel(track.title or "", self.results_widget)
            title_label.setWordWrap(True)
            title_label.setMinimumWidth(200)
            title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self.results_layout.addWidget(title_label, row, 1)
            self.title_list.append(title_label)
            artist_label = QLabel(track.artist or "", self.results_widget)
            artist_label.setWordWrap(True)
            artist_label.setMinimumWidth(200)
            artist_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self.results_layout.addWidget(artist_label, row, 2)
            self.artist_list.append(artist_label)
            album_label = QLabel(track.album or "", self.results_widget)
            album_label.setWordWrap(True)
            album_label.setMinimumWidth(200)
            album_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self.results_layout.addWidget(album_label, row, 3)
            self.album_list.append(album_label)
            composer_label = QLabel(track.composer or "", self.results_widget)
            composer_label.setWordWrap(True)
            composer_label.setMinimumWidth(200)
            composer_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self.results_layout.addWidget(composer_label, row, 4)
            self.composer_list.append(composer_label)
            details_btn = QPushButton(_("Details"), self.results_widget)
            details_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.open_details_btn_list.append(details_btn)
            self.results_layout.addWidget(details_btn, row, 5)

            def make_details_handler(tr):
                def handler():
                    self.open_details(tr)
                return handler

            details_btn.clicked.connect(make_details_handler(track))
            play_btn = QPushButton(_("Play"), self.results_widget)
            play_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.play_btn_list.append(play_btn)
            self.results_layout.addWidget(play_btn, row, 6)

            def make_play_handler(tr):
                def handler():
                    logger.info("User selected audio track: %s", tr)
                    self.run_play_callback(tr)
                return handler

            play_btn.clicked.connect(make_play_handler(track))

            add_pl_btn = QPushButton(_("+ Playlist"), self.results_widget)
            add_pl_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.add_to_playlist_btn_list.append(add_pl_btn)
            self.results_layout.addWidget(add_pl_btn, row, 7)

            def make_add_to_playlist_handler(tr):
                def handler():
                    self._add_track_to_playlist(tr)
                return handler

            add_pl_btn.clicked.connect(make_add_to_playlist_handler(track))

    def open_details(self, track):
        pass

    def run_play_callback(self, track, library_data_search=None):
        if track is None or track.is_invalid():
            raise Exception("Invalid track: {}".format(track))
        if library_data_search is None:
            library_data_search = self.library_data_search
        assert library_data_search is not None
        library_data_search.set_selected_track_path(track)
        # the below argument ensures that stored recent searches will have a selected
        # filepath if the user selected to play from them.
        SearchWindow.update_recent_searches(
            library_data_search, remove_searches_with_no_selected_filepath=True
        )
        playlist_sort_type = self.get_playlist_sort_type()
        self.app_actions.start_play_callback(
            track=track,
            playlist_sort_type=playlist_sort_type,
            overwrite=self.overwrite_cache_check.isChecked(),
            use_all_music=True,
        )

    def _update_playlist_sort_dropdown(self):
        """Update the playlist sort dropdown to reflect the largest scope in the search fields."""
        search = LibraryDataSearch(
            composer=self.composer_entry.text(),
            artist=self.artist_entry.text(),
            genre=self.genre_entry.text(),
            instrument=self.instrument_entry.text(),
            form=self.form_entry.text(),
            album=self.album_entry.text(),
        )
        self.playlist_sort_combo.setCurrentText(
            search.get_inferred_sort_type().get_translation()
        )

    def get_playlist_sort_type(self):
        # TODO: In the future, send all scopes from the search to the playlist for multi-level sorting
        # Currently, only the selected sort type is used
        selected_translation = self.playlist_sort_combo.currentText()
        return PlaylistSortType.get_from_translation(selected_translation)

    def _save_search_as_playlist(self):
        """Save the current search fields as a search-based PlaylistDescriptor."""
        from datetime import datetime
        from muse.playlist_descriptor import PlaylistDescriptor, PlaylistDescriptorStore
        from utils.app_info_cache import app_info_cache

        query = {}
        for field, entry in [
            ("all", self.all_entry), ("title", self.title_entry),
            ("album", self.album_entry), ("artist", self.artist_entry),
            ("composer", self.composer_entry), ("genre", self.genre_entry),
            ("instrument", self.instrument_entry), ("form", self.form_entry),
        ]:
            val = entry.text().strip()
            if val:
                query[field] = val

        if not query:
            self.app_actions.alert(
                _("No Search"),
                _("Please fill in at least one search field first."),
                kind="warning",
            )
            return

        name, ok = QInputDialog.getText(
            self, _("Save as Playlist"), _("Enter a name for this playlist:"),
        )
        if not ok or not (name and name.strip()):
            return
        name = name.strip()

        sort_type = self.get_playlist_sort_type()
        pd = PlaylistDescriptor(
            name=name,
            search_query=query,
            sort_type=sort_type,
            created_at=datetime.now().isoformat(),
        )
        PlaylistDescriptorStore.save(pd, cache=app_info_cache)
        self.app_actions.toast(_("Playlist \"{0}\" saved").format(name))

    def _add_track_to_playlist(self, track):
        """Add a single track to an existing track-based PlaylistDescriptor."""
        from muse.playlist_descriptor import PlaylistDescriptor, PlaylistDescriptorStore
        from utils.app_info_cache import app_info_cache

        all_playlists = PlaylistDescriptorStore.load_all(cache=app_info_cache)
        candidates = {
            name: pd for name, pd in all_playlists.items()
            if pd.is_track_based() or (
                not pd.is_search_based() and not pd.is_directory_based()
            )
        }

        if not candidates:
            name, ok = QInputDialog.getText(
                self, _("New Playlist"),
                _("No track-based playlists exist. Enter a name for a new one:"),
            )
            if not ok or not (name and name.strip()):
                return
            name = name.strip()
            pd = PlaylistDescriptor(
                name=name,
                track_filepaths=[track.filepath],
                sort_type=PlaylistSortType.SEQUENCE,
            )
            PlaylistDescriptorStore.save(pd, cache=app_info_cache)
            self.app_actions.toast(
                _("Created playlist \"{0}\" with track").format(name)
            )
            return

        names = list(candidates.keys())
        name, ok = QInputDialog.getItem(
            self, _("Add to Playlist"),
            _("Select a playlist:"), names, 0, False,
        )
        if not ok or name not in candidates:
            return
        pd = candidates[name]
        if pd.track_filepaths is None:
            pd.track_filepaths = []
        pd.track_filepaths.append(track.filepath)
        PlaylistDescriptorStore.save(pd, cache=app_info_cache)
        self.app_actions.toast(_("Added to \"{0}\"").format(name))

    def remove_search(self, search):
        assert search is not None
        # Remove all instances of this search (handles duplicates)
        SearchWindow.recent_searches = [
            s for s in SearchWindow.recent_searches if s != search
        ]
        SearchWindow.store_recent_searches()
        self.clear_widget_lists()
        self.show_recent_searches()

    @staticmethod
    def set_title(extra_text):
        SearchWindow.top_level.setWindowTitle(_("Search") + " - " + extra_text)

    def load_more_results(self):
        """Load more results by re-running the search with an increased offset."""
        if self.library_data_search is None:
            return
        page_size = SearchWindow.INITIAL_MAX_RESULTS
        current_results = len(self.library_data_search.results)
        page_result_count = current_results - self.current_offset
        if page_result_count > page_size:
            self.current_offset += page_size
            self._do_search(overwrite=False)
        else:
            logger.info("Reached end of results")

    def sort_by(self, attr):
        assert self.library_data_search is not None
        self.library_data_search.sort_results_by(attr)
        self._refresh_widgets()

    def apply_filter(self, text=""):
        """Apply filter to search results."""
        self._refresh_widgets()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self.has_closed = True
        if SearchWindow.top_level is self:
            SearchWindow.top_level = None
        event.accept()
