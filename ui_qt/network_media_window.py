"""
Network media / URL window (PySide6).
Port of ui/network_media_window.py.
"""

from PySide6.QtWidgets import (
    QDialog,
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

from library_data.library_data import LibraryData, LibraryDataSearch
from ui_qt.app_style import AppStyle
from utils.app_info_cache import app_info_cache
from utils.config import config
from utils.globals import PlaylistSortType
from utils.translations import I18N
from utils.logging_setup import get_logger
from utils.utils import Utils

_ = I18N._
logger = get_logger(__name__)


class NetworkMediaURL:
    """A URL with media on it."""

    def __init__(self, url="", title=None):
        self.url = url
        self.title = title
        self.selected_track_path = ""
        self.stored_results_count = 0

    def is_valid(self):
        return (
            self.url is not None
            and self.url.strip() != ""
            and self.url.startswith("http")
        )

    def get_json(self):
        return {"url": self.url, "title": self.title}

    def to_json(self):
        return self.get_json()

    @staticmethod
    def from_json(json):
        return NetworkMediaURL(**json)

    def __str__(self):
        return self.url

    def __eq__(self, value):
        if not isinstance(value, NetworkMediaURL):
            return False
        return self.__dict__ == value.__dict__

    def __hash__(self):
        return hash((self.url, self.title))

    def get_first_available_track(self):
        return None

    def get_readable_stored_results_count(self):
        return str(self.stored_results_count)

    def matches_no_selected_track_path(self, other):
        return False


class NetworkMediaWindow(QDialog):
    """Window to start playlists from a URL.

    TODO: WIP / currently in development. No menu or other entry point in app_qt
    opens this window yet; it will need to be hooked up to the main window
    (e.g. File or View menu) when URL/network media playback is desired in the Qt UI.
    """

    COL_0_WIDTH = 300
    top_level = None
    MAX_RESULTS = getattr(config, "max_search_results", 100)
    MAX_RECENT_SEARCHES = 200
    recent_media_urls = []

    @staticmethod
    def load_recent_media_urls():
        NetworkMediaWindow.recent_media_urls.clear()
        recent_media_urls = app_info_cache.get("recent_media_urls", [])
        assert recent_media_urls is not None
        for json_item in recent_media_urls:
            media_url = NetworkMediaURL(**json_item)
            NetworkMediaWindow.recent_media_urls.append(media_url)

    @staticmethod
    def store_recent_media_urls():
        json_urls = []
        for media_url in NetworkMediaWindow.recent_media_urls:
            if media_url.is_valid() and media_url.stored_results_count > 0:
                json_urls.append(media_url.to_json())
        app_info_cache.set("recent_media_urls", json_urls)

    def __init__(self, master, app_actions, dimensions="1550x700"):
        super().__init__(master)
        NetworkMediaWindow.top_level = self
        NetworkMediaWindow.set_title(_("Search Library"))
        try:
            width, height = map(int, dimensions.split("x"))
            self.resize(width, height)
        except Exception:
            self.resize(1550, 700)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Window)
        self.setMinimumSize(400, 400)

        if hasattr(master, "geometry"):
            geo = master.geometry()
            self.move(geo.x() + 50, geo.y() + 30)

        self.app_actions = app_actions
        self.library_data = LibraryData()
        self.library_data_search = None
        self.has_closed = False

        self.link_list = []
        self.page_title_list = []
        self.check_btn_list = []
        self.play_btn_list = []
        self.artist_list = []
        self.composer_list = []

        self.setStyleSheet(AppStyle.get_stylesheet())
        outer = QVBoxLayout(self)
        outer.setContentsMargins(5, 5, 5, 5)

        self.results_scroll = QScrollArea(self)
        self.results_scroll.setWidgetResizable(True)
        self.results_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.results_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.results_widget = QWidget(self.results_scroll)
        self.results_layout = QGridLayout(self.results_widget)
        self.results_scroll.setWidget(self.results_widget)
        outer.addWidget(self.results_scroll, 7)

        inner = QFrame(self)
        inner_layout = QGridLayout(inner)
        row = 0

        self.search_btn = QPushButton(_("Search"), self)
        self.search_btn.clicked.connect(self.do_search)
        inner_layout.addWidget(self.search_btn, row, 0, 1, 3)
        row += 1

        inner_layout.addWidget(QLabel(_("URL"), inner), row, 0)
        self.link_entry = QLineEdit(inner)
        self.link_entry.setMinimumWidth(200)
        self.link_entry.returnPressed.connect(self.do_search)
        inner_layout.addWidget(self.link_entry, row, 1)
        self.link_button = QPushButton(_("Sort by"), inner)
        self.link_button.clicked.connect(lambda: self.sort_by("title"))
        inner_layout.addWidget(self.link_button, row, 2)
        row += 1

        outer.addWidget(inner)

        self.show()
        QTimer.singleShot(0, self.show_recent_media_urls)

    def show_recent_media_urls(self):
        if len(NetworkMediaWindow.recent_media_urls) == 0:
            self.clear_widget_lists()
            self.searching_label = QLabel(
                _("No recent urls found."), self.results_widget
            )
            self.searching_label.setWordWrap(True)
            self.results_layout.addWidget(self.searching_label, 1, 1)
            self.link_list.append(self.searching_label)
            return
        self.clear_widget_lists()
        for i in range(len(NetworkMediaWindow.recent_media_urls)):
            row = i + 1
            search = NetworkMediaWindow.recent_media_urls[i]
            track = self.library_data.get_track(search.selected_track_path)
            if track is not None:
                title = track.title or ""
                album = track.album or ""
            else:
                title = _("(No track selected)")
                album = "--"

            title_label = QLabel(title, self.results_widget)
            title_label.setWordWrap(True)
            title_label.setMaximumWidth(200)
            self.results_layout.addWidget(title_label, row, 1)
            self.link_list.append(title_label)

            album_label = QLabel(album, self.results_widget)
            album_label.setWordWrap(True)
            album_label.setMaximumWidth(200)
            self.results_layout.addWidget(album_label, row, 2)
            self.page_title_list.append(album_label)

            search_label = QLabel(str(search), self.results_widget)
            search_label.setWordWrap(True)
            search_label.setMaximumWidth(200)
            self.results_layout.addWidget(search_label, row, 3)
            self.artist_list.append(search_label)

            results_count_label = QLabel(
                search.get_readable_stored_results_count(), self.results_widget
            )
            results_count_label.setMaximumWidth(200)
            self.results_layout.addWidget(results_count_label, row, 4)
            self.composer_list.append(results_count_label)

            search_btn = QPushButton(_("Search"), self.results_widget)
            self.check_btn_list.append(search_btn)
            self.results_layout.addWidget(search_btn, row, 5)

            def make_search_handler(lib_search):
                def handler():
                    self.load_stored_search(library_data_search=lib_search)
                    self._do_search(overwrite=False)

                return handler

            search_btn.clicked.connect(make_search_handler(search))

            play_btn = QPushButton(_("Play"), self.results_widget)
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

    def do_search(self, event=None):
        title = self.link_entry.text().strip()
        self.library_data_search = LibraryDataSearch(
            title,
            title=title,
            album="",
            artist="",
            composer="",
            genre="",
            instrument="",
            form="",
            max_results=NetworkMediaWindow.MAX_RESULTS,
        )
        self._do_search(overwrite=False)

    def load_stored_search(self, library_data_search):
        assert library_data_search is not None
        if hasattr(library_data_search, "title"):
            self.link_entry.setText(library_data_search.title or "")
        elif hasattr(library_data_search, "url"):
            self.link_entry.setText(library_data_search.url or "")
        else:
            self.link_entry.setText("")
        self.library_data_search = library_data_search

    def _do_search(self, event=None, overwrite=False):
        assert self.library_data_search is not None
        self._refresh_widgets(add_results=False)
        self.searching_label = QLabel(
            _("Please wait, overwriting cache and searching...")
            if overwrite
            else _("Searching..."),
            self.results_widget,
        )
        self.results_layout.addWidget(self.searching_label, 1, 1)
        self.link_list.append(self.searching_label)

        def search_done():
            self.update_recent_media_urls()
            self._refresh_widgets()

        def search_thread():
            try:
                self.library_data.do_search(
                    self.library_data_search, overwrite=overwrite
                )
                QTimer.singleShot(0, search_done)
            except Exception as e:
                logger.error("Error in search thread: %s", e)
                QTimer.singleShot(
                    0,
                    lambda: self._show_search_error(str(e)),
                )

        Utils.start_thread(search_thread, use_asyncio=False)

    def _show_search_error(self, error_msg):
        self._refresh_widgets(add_results=False)
        error_label = QLabel(error_msg, self.results_widget)
        error_label.setWordWrap(True)
        self.results_layout.addWidget(error_label, 1, 1)
        self.link_list.append(error_label)

    def update_recent_media_urls(self, remove_urls_with_no_selected_filepath=False):
        assert self.library_data_search is not None
        if self.library_data_search in NetworkMediaWindow.recent_media_urls:
            NetworkMediaWindow.recent_media_urls.remove(self.library_data_search)
        if remove_urls_with_no_selected_filepath:
            urls_to_remove = []
            for search in NetworkMediaWindow.recent_media_urls:
                if (
                    search.selected_track_path is None
                    or search.selected_track_path.strip() == ""
                ) and search.matches_no_selected_track_path(self.library_data_search):
                    urls_to_remove.append(search)
            for search in urls_to_remove:
                NetworkMediaWindow.recent_media_urls.remove(search)
        NetworkMediaWindow.recent_media_urls.insert(0, self.library_data_search)
        if len(NetworkMediaWindow.recent_media_urls) > NetworkMediaWindow.MAX_RECENT_SEARCHES:
            del NetworkMediaWindow.recent_media_urls[-1]

    def sort_by(self, attr):
        assert self.library_data_search is not None
        self.library_data_search.sort_results_by(attr)
        self._refresh_widgets()

    def add_widgets_for_results(self):
        assert self.library_data_search is not None
        if len(self.library_data_search.results) == 0:
            self.searching_label = QLabel(
                _("No recent urls found."), self.results_widget
            )
            self.searching_label.setWordWrap(True)
            self.results_layout.addWidget(self.searching_label, 1, 1)
            self.link_list.append(self.searching_label)
            return
        self.library_data_search.sort_results_by()
        results = self.library_data_search.get_results()
        for i in range(len(results)):
            row = i + 1
            track = results[i]

            title_label = QLabel(track.title or "", self.results_widget)
            title_label.setWordWrap(True)
            title_label.setMaximumWidth(200)
            self.results_layout.addWidget(title_label, row, 1)
            self.link_list.append(title_label)

            artist_label = QLabel(track.artist or "", self.results_widget)
            artist_label.setWordWrap(True)
            artist_label.setMaximumWidth(200)
            self.results_layout.addWidget(artist_label, row, 2)
            self.artist_list.append(artist_label)

            album_label = QLabel(track.album or "", self.results_widget)
            album_label.setWordWrap(True)
            album_label.setMaximumWidth(200)
            self.results_layout.addWidget(album_label, row, 3)
            self.page_title_list.append(album_label)

            composer_label = QLabel(track.composer or "", self.results_widget)
            composer_label.setWordWrap(True)
            composer_label.setMaximumWidth(200)
            self.results_layout.addWidget(composer_label, row, 4)
            self.composer_list.append(composer_label)

            open_details_btn = QPushButton(_("Details"), self.results_widget)
            self.check_btn_list.append(open_details_btn)
            self.results_layout.addWidget(open_details_btn, row, 5)

            def make_details_handler(tr):
                def handler():
                    self.open_details(tr)

                return handler

            open_details_btn.clicked.connect(make_details_handler(track))

            play_btn = QPushButton(_("Play"), self.results_widget)
            self.play_btn_list.append(play_btn)
            self.results_layout.addWidget(play_btn, row, 6)

            def make_play_handler(tr):
                def handler():
                    logger.info("User selected audio track: %s", tr)
                    self.run_play_callback(tr)

                return handler

            play_btn.clicked.connect(make_play_handler(track))
            # TODO add to playlist buttons

    def open_details(self, track):
        pass

    def run_play_callback(self, track, library_data_search=None):
        if track is None or track.is_invalid():
            raise Exception("Invalid track: {}".format(track))

        if library_data_search is None:
            library_data_search = self.library_data_search
        assert library_data_search is not None
        library_data_search.set_selected_track_path(track)
        # the below argument ensures that stored recent urls will have a selected
        # filepath if the user selected to play from them.
        self.update_recent_media_urls(remove_urls_with_no_selected_filepath=True)
        playlist_sort_type = self.get_playlist_sort_type()
        overwrite = False
        if getattr(self, "overwrite_cache_check", None) is not None:
            overwrite = self.overwrite_cache_check.isChecked()
        self.app_actions.start_play_callback(
            track=track,
            playlist_sort_type=playlist_sort_type,
            overwrite=overwrite,
        )

    def get_playlist_sort_type(self):
        composer = getattr(self, "composer_entry", None)
        if composer is not None and len(composer.text()) > 0:
            return PlaylistSortType.COMPOSER_SHUFFLE
        artist = getattr(self, "artist_entry", None)
        if artist is not None and len(artist.text()) > 0:
            return PlaylistSortType.ARTIST_SHUFFLE
        genre = getattr(self, "genre_entry", None)
        if genre is not None and len(genre.text()) > 0:
            return PlaylistSortType.GENRE_SHUFFLE
        instrument = getattr(self, "instrument_entry", None)
        if instrument is not None and len(instrument.text()) > 0:
            return PlaylistSortType.INSTRUMENT_SHUFFLE
        form = getattr(self, "form_entry", None)
        if form is not None and len(form.text()) > 0:
            return PlaylistSortType.FORM_SHUFFLE
        album = getattr(self, "album_entry", None)
        if album is not None and len(album.text()) > 0:
            return PlaylistSortType.ALBUM_SHUFFLE
        return PlaylistSortType.RANDOM

    def _refresh_widgets(self, add_results=True):
        self.clear_widget_lists()
        if add_results:
            self.add_widgets_for_results()

    def clear_widget_lists(self):
        for w in self.link_list:
            w.setParent(None)
            w.deleteLater()
        for w in self.artist_list:
            w.setParent(None)
            w.deleteLater()
        for w in self.page_title_list:
            w.setParent(None)
            w.deleteLater()
        for w in self.composer_list:
            w.setParent(None)
            w.deleteLater()
        for w in self.check_btn_list:
            w.setParent(None)
            w.deleteLater()
        for w in self.play_btn_list:
            w.setParent(None)
            w.deleteLater()
        self.link_list = []
        self.artist_list = []
        self.page_title_list = []
        self.composer_list = []
        self.check_btn_list = []
        self.play_btn_list = []

    @staticmethod
    def set_title(extra_text):
        if NetworkMediaWindow.top_level is not None:
            NetworkMediaWindow.top_level.setWindowTitle(
                _("Search") + " - " + extra_text
            )

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self.has_closed = True
        if NetworkMediaWindow.top_level is self:
            NetworkMediaWindow.top_level = None
        event.accept()
