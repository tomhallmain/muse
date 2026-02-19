"""
Favorites management window (PySide6).
Port of ui/favorites_window.py; logic preserved, UI uses Qt.
Includes subsidiary FavoriteWindow for view/edit of a single favorite.
"""
import random
from datetime import datetime

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QScrollArea,
    QSizePolicy,
    QWidget,
    QFrame,
)
from PySide6.QtCore import Qt, QTimer

from lib.multi_display_qt import SmartWindow
from library_data.favorite import Favorite
from ui_qt.app_style import AppStyle
from ui_qt.auth.password_utils import require_password
from utils.app_info_cache import app_info_cache
from utils.logging_setup import get_logger
from utils.translations import I18N
from utils.globals import ProtectedActions, TrackAttribute

_ = I18N._
logger = get_logger(__name__)


class FavoritesDataSearch:
    """Search helper for favorites (no UI)."""

    def __init__(self, favorite="", max_results=200):
        self.favorite = favorite.lower()
        self.max_results = max_results
        self.results = []

    def is_valid(self):
        return len(self.favorite.strip()) > 0

    def get_readable_results_count(self):
        count = len(self.results)
        results_str = f"{self.max_results}+" if count > self.max_results else str(count)
        return _("({0} results)").format(results_str)

    def get_results(self):
        return self.results

    def _get_match_priority(self, search_text: str) -> int:
        if not self.favorite:
            return 0
        search_text = search_text.lower()
        if search_text.startswith(self.favorite):
            return 3
        for word in search_text.split():
            if word.startswith(self.favorite):
                return 2
        if self.favorite in search_text:
            return 1
        return 0

    def add_result(self, favorite, search_text: str):
        priority = self._get_match_priority(search_text)
        if priority > 0:
            self.results.append((priority, favorite))

    def sort_results(self):
        self.results.sort(key=lambda x: (-x[0], x[1].value))
        self.results = [fav for _, fav in self.results[: self.max_results]]


class FavoritesWindow(SmartWindow):
    """Window to search and manage favorites."""

    COL_0_WIDTH = 150
    top_level = None
    MAX_RESULTS = 200
    details_window = None
    recent_favorites = []

    @staticmethod
    def load_favorites():
        json_favorites = app_info_cache.get("favorites", [])
        if not isinstance(json_favorites, list):
            return
        FavoritesWindow.recent_favorites = []
        for fav_dict in json_favorites:
            FavoritesWindow.recent_favorites.append(Favorite.from_dict(fav_dict))
        FavoritesWindow.recent_favorites.sort(key=lambda x: x.timestamp, reverse=True)

    @staticmethod
    def store_favorites():
        json_favorites = [f.to_dict() for f in FavoritesWindow.recent_favorites]
        app_info_cache.set("favorites", json_favorites)

    @staticmethod
    def set_favorite(track, is_favorited=False):
        if is_favorited:
            for existing_fav in FavoritesWindow.recent_favorites[:]:
                if (
                    existing_fav.attribute == TrackAttribute.TITLE
                    and existing_fav.value == track.title
                ):
                    FavoritesWindow.recent_favorites.remove(existing_fav)
                    break
            FavoritesWindow.recent_favorites.insert(0, Favorite.from_track(track))
        else:
            for existing_fav in FavoritesWindow.recent_favorites[:]:
                if (
                    existing_fav.attribute == TrackAttribute.TITLE
                    and existing_fav.value == track.title
                ):
                    FavoritesWindow.recent_favorites.remove(existing_fav)
                    break
        FavoritesWindow.store_favorites()

    @staticmethod
    def set_attribute_favorite(attribute: TrackAttribute, value: str, is_favorited: bool):
        if is_favorited:
            for existing_fav in FavoritesWindow.recent_favorites[:]:
                if existing_fav.attribute == attribute and existing_fav.value == value:
                    FavoritesWindow.recent_favorites.remove(existing_fav)
                    break
            FavoritesWindow.recent_favorites.insert(
                0, Favorite.from_attribute(attribute, value)
            )
        else:
            for existing_fav in FavoritesWindow.recent_favorites[:]:
                if existing_fav.attribute == attribute and existing_fav.value == value:
                    FavoritesWindow.recent_favorites.remove(existing_fav)
                    break
        FavoritesWindow.store_favorites()

    @staticmethod
    def remove_favorite(favorite):
        if favorite in FavoritesWindow.recent_favorites:
            FavoritesWindow.recent_favorites.remove(favorite)
            FavoritesWindow.store_favorites()
            return True
        return False

    @staticmethod
    def is_track_favorited(track):
        if not track:
            return False
        for favorite in FavoritesWindow.recent_favorites:
            if favorite.attribute == TrackAttribute.TITLE:
                if (
                    track.searchable_title
                    and favorite.value_lower in track.searchable_title
                ):
                    return True
            elif favorite.attribute == TrackAttribute.ARTIST:
                if (
                    track.searchable_artist
                    and favorite.value_lower in track.searchable_artist
                ):
                    return True
            elif favorite.attribute == TrackAttribute.ALBUM:
                if (
                    track.searchable_album
                    and favorite.value_lower in track.searchable_album
                ):
                    return True
            elif favorite.attribute == TrackAttribute.COMPOSER:
                if (
                    track.searchable_composer
                    and favorite.value_lower in track.searchable_composer
                ):
                    return True
            elif favorite.attribute == TrackAttribute.INSTRUMENT:
                if (
                    track.get_instrument()
                    and favorite.value_lower in track.get_instrument().lower()
                ):
                    return True
            elif favorite.attribute == TrackAttribute.FORM:
                if (
                    track.get_form()
                    and favorite.value_lower in track.get_form().lower()
                ):
                    return True
        return False

    @staticmethod
    def add_favorite(favorite, is_new=False, app_actions=None, from_favorite_window=True):
        assert app_actions is not None
        if is_new:
            for existing_fav in FavoritesWindow.recent_favorites:
                if (
                    existing_fav.attribute == favorite.attribute
                    and existing_fav.value == favorite.value
                ):
                    app_actions.alert(
                        _("Favorite Exists"), _("This favorite already exists."), master=None
                    )
                    return False
        else:
            for existing_fav in FavoritesWindow.recent_favorites:
                if (
                    existing_fav.attribute == favorite.attribute
                    and existing_fav.value == favorite.value
                ):
                    if id(existing_fav) != id(favorite):
                        app_actions.alert(
                            _("Favorite Exists"), _("This favorite already exists."), master=None
                        )
                        return False
                    if not from_favorite_window:
                        app_actions.alert(
                            _("Favorite Exists"), _("This favorite already exists."), master=None
                        )
                    return True
            try:
                FavoritesWindow.recent_favorites.remove(favorite)
            except ValueError:
                pass
        FavoritesWindow.recent_favorites.insert(0, favorite)
        FavoritesWindow.store_favorites()
        app_actions.toast(_("Favorite updated successfully."))
        return True

    def __init__(self, master, app_actions, library_data, dimensions="600x600"):
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("Favorites") + " - " + _("Favorites"),
            geometry=dimensions,
            offset_x=50,
            offset_y=50,
        )
        FavoritesWindow.top_level = self
        self.master = master
        self.app_actions = app_actions
        self.library_data = library_data
        self.favorite_data_search = None
        self.has_closed = False

        self.setStyleSheet(AppStyle.get_stylesheet())
        layout = QVBoxLayout(self)

        inner = QFrame(self)
        inner_layout = QGridLayout(inner)

        inner_layout.addWidget(
            QLabel(_("Create Favorite From Current Track"), self),
            0, 0,
        )
        self.attribute_combo = QComboBox(self)
        self.attribute_combo.addItems([attr.value for attr in TrackAttribute])
        idx = self.attribute_combo.findText(TrackAttribute.TITLE.value)
        if idx >= 0:
            self.attribute_combo.setCurrentIndex(idx)
        inner_layout.addWidget(self.attribute_combo, 0, 1)
        self.create_favorite_btn = QPushButton(_("Create Favorite"), self)
        self.create_favorite_btn.clicked.connect(self.create_favorite_from_current)
        inner_layout.addWidget(self.create_favorite_btn, 0, 2)
        layout.addWidget(inner)

        inner_layout.addWidget(
            QLabel(_("Search Favorites"), self),
            1, 0,
        )
        self.favorite_entry = QLineEdit(self)
        self.favorite_entry.returnPressed.connect(self.do_search)
        inner_layout.addWidget(self.favorite_entry, 1, 1)
        self.search_btn = QPushButton(_("Search"), self)
        self.search_btn.clicked.connect(self.do_search)
        inner_layout.addWidget(self.search_btn, 2, 0)
        self.play_random_btn = QPushButton(_("Play Random Favorite"), self)
        self.play_random_btn.clicked.connect(self.play_random_favorite)
        inner_layout.addWidget(self.play_random_btn, 2, 1)
        layout.addWidget(inner)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.results_widget = QWidget(self.scroll)
        self.results_layout = QGridLayout(self.results_widget)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll.setWidget(self.results_widget)
        layout.addWidget(self.scroll, 1)

        self.favorite_list = []
        self.open_details_btn_list = []
        self.search_btn_list = []
        self.play_btn_list = []

        self.show()
        QTimer.singleShot(0, self.show_recent_favorites)

    @require_password(ProtectedActions.EDIT_FAVORITES)
    def create_favorite_from_current(self):
        current_track = self.app_actions.get_current_track()
        if not current_track:
            return
        selected_attribute = TrackAttribute(self.attribute_combo.currentText())
        value = None
        if selected_attribute == TrackAttribute.TITLE:
            value = current_track.title or current_track.filepath
        elif selected_attribute == TrackAttribute.ARTIST:
            value = current_track.artist
        elif selected_attribute == TrackAttribute.ALBUM:
            value = current_track.album
        elif selected_attribute == TrackAttribute.COMPOSER:
            value = current_track.composer
        elif selected_attribute == TrackAttribute.GENRE:
            value = current_track.genre
        elif selected_attribute == TrackAttribute.INSTRUMENT:
            value = current_track.get_instrument()
        elif selected_attribute == TrackAttribute.FORM:
            value = current_track.get_form()

        if FavoritesWindow.details_window is not None:
            try:
                FavoritesWindow.details_window.close()
            except Exception:
                pass
        FavoritesWindow.details_window = FavoriteWindow(
            self,
            self,
            Favorite.from_attribute(selected_attribute, value),
            self.library_data,
            is_new=True,
        )
        FavoritesWindow.details_window.show()

    @require_password(ProtectedActions.EDIT_FAVORITES)
    def create_favorite(self, favorite, is_new=False):
        if FavoritesWindow.add_favorite(favorite, is_new, self.app_actions):
            self._refresh_widgets()
            return True
        return False

    def _clear_results_widgets(self):
        while self.results_layout.count():
            child = self.results_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.favorite_list.clear()
        self.open_details_btn_list.clear()
        self.search_btn_list.clear()
        self.play_btn_list.clear()

    def show_recent_favorites(self):
        self._clear_results_widgets()
        if len(FavoritesWindow.recent_favorites) == 0:
            lbl = QLabel(_("No favorites found."), self.results_widget)
            self.results_layout.addWidget(lbl, 0, 0)
            self.favorite_list.append(lbl)
            return
        for i, favorite in enumerate(FavoritesWindow.recent_favorites):
            if favorite is None:
                continue
            row = i + 1
            if favorite.attribute == TrackAttribute.TITLE:
                track = self._get_track_for_favorite(favorite)
                if not track:
                    display_text = f"{favorite.value} ({_('File not found')})"
                else:
                    title = track.title.strip() if track.title else ""
                    filepath = track.filepath.strip() if track.filepath else ""
                    display_text = title or filepath or _("No title or filepath available")
            else:
                display_text = f"{favorite.attribute.value}: {favorite.value}"

            title_label = QLabel(display_text, self.results_widget)
            title_label.setWordWrap(True)
            title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self.results_layout.addWidget(title_label, row, 0)
            self.favorite_list.append(title_label)

            play_btn = QPushButton(_("Play"), self.results_widget)
            play_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.results_layout.addWidget(play_btn, row, 1)
            self.play_btn_list.append(play_btn)
            play_btn.clicked.connect(lambda checked=False, f=favorite: self._play_favorite(f))

            details_btn = QPushButton(_("Details"), self.results_widget)
            details_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.results_layout.addWidget(details_btn, row, 2)
            self.open_details_btn_list.append(details_btn)
            details_btn.clicked.connect(lambda checked=False, f=favorite: self.open_details(f))

            remove_btn = QPushButton(_("Remove"), self.results_widget)
            remove_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.results_layout.addWidget(remove_btn, row, 3)
            self.open_details_btn_list.append(remove_btn)
            remove_btn.clicked.connect(
                lambda checked=False, f=favorite: self._on_remove_favorite(f)
            )

    def _on_remove_favorite(self, favorite):
        if FavoritesWindow.remove_favorite(favorite):
            self._refresh_widgets()

    def _find_track_by_metadata(self, favorite: Favorite):
        if favorite.attribute != TrackAttribute.TITLE:
            return None
        tracks = self.library_data.get_all_tracks()
        for track in tracks:
            if (
                favorite.value == (track.title or track.filepath)
                and (not favorite.artist or favorite.artist == track.artist)
                and (not favorite.album or favorite.album == track.album)
                and (not favorite.composer or favorite.composer == track.composer)
            ):
                return track
        return None

    def _get_track_for_favorite(self, favorite: Favorite):
        if not favorite.filepath:
            track = self._find_track_by_metadata(favorite)
            if track:
                if favorite.update_from_track(track):
                    FavoritesWindow.store_favorites()
                    logger.info(
                        "Updated favorite for track %s with new filepath %s",
                        favorite.value,
                        track.filepath,
                    )
            return track
        track = self.library_data.get_track(favorite.filepath)
        if track and (track.title or track.filepath):
            return track
        track = self._find_track_by_metadata(favorite)
        if track:
            if favorite.update_from_track(track):
                FavoritesWindow.store_favorites()
                logger.info(
                    "Updated favorite for track %s with new filepath %s",
                    favorite.value,
                    track.filepath,
                )
        return track

    def do_search(self, event=None):
        favorite = self.favorite_entry.text().strip()
        self.favorite_data_search = FavoritesDataSearch(
            favorite, FavoritesWindow.MAX_RESULTS
        )
        self._do_search()

    def _do_search(self, event=None):
        if self.favorite_data_search is None:
            return
        self._refresh_widgets(add_results=False)
        for favorite in FavoritesWindow.recent_favorites:
            if favorite.attribute == TrackAttribute.TITLE:
                track = self._get_track_for_favorite(favorite)
                if not track:
                    logger.error("Track not found for favorite %s", favorite.value)
                    continue
                search_text = favorite.value
            else:
                search_text = favorite.value
            self.favorite_data_search.add_result(favorite, search_text)
        self.favorite_data_search.sort_results()
        self._refresh_widgets()

    def add_widgets_for_results(self):
        if self.favorite_data_search is None:
            return
        results = self.favorite_data_search.get_results()
        logger.info("Found %s results", len(results))
        for i, favorite in enumerate(results):
            row = i + 1
            if favorite.attribute == TrackAttribute.TITLE:
                track = self._get_track_for_favorite(favorite)
                if not track:
                    display_text = f"{favorite.value} ({_('File not found')})"
                else:
                    title = track.title.strip() if track.title else ""
                    filepath = track.filepath.strip() if track.filepath else ""
                    display_text = title or filepath or _("No title or filepath available")
            else:
                display_text = f"{favorite.attribute.value}: {favorite.value}"

            title_label = QLabel(display_text, self.results_widget)
            title_label.setWordWrap(True)
            title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self.results_layout.addWidget(title_label, row, 0)
            self.favorite_list.append(title_label)

            play_btn = QPushButton(_("Play"), self.results_widget)
            play_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.results_layout.addWidget(play_btn, row, 1)
            self.play_btn_list.append(play_btn)
            play_btn.clicked.connect(lambda checked=False, f=favorite: self._play_favorite(f))

            details_btn = QPushButton(_("Details"), self.results_widget)
            details_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.results_layout.addWidget(details_btn, row, 2)
            self.open_details_btn_list.append(details_btn)
            details_btn.clicked.connect(lambda checked=False, f=favorite: self.open_details(f))

            remove_btn = QPushButton(_("Remove"), self.results_widget)
            remove_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.results_layout.addWidget(remove_btn, row, 3)
            self.open_details_btn_list.append(remove_btn)
            remove_btn.clicked.connect(
                lambda checked=False, f=favorite: self._on_remove_favorite(f)
            )

    @require_password(ProtectedActions.EDIT_FAVORITES)
    def open_details(self, favorite):
        if FavoritesWindow.details_window is not None:
            try:
                FavoritesWindow.details_window.close()
            except Exception:
                pass
        FavoritesWindow.details_window = FavoriteWindow(
            self, self, favorite, self.library_data
        )
        FavoritesWindow.details_window.show()

    def refresh(self):
        self._refresh_widgets()

    def _refresh_widgets(self, add_results=True):
        self._clear_results_widgets()
        if add_results:
            if (
                self.favorite_data_search is not None
                and self.favorite_data_search.favorite
            ):
                self.add_widgets_for_results()
            else:
                self.show_recent_favorites()

    @staticmethod
    def set_title(extra_text):
        if FavoritesWindow.top_level:
            FavoritesWindow.top_level.setWindowTitle(_("Favorites") + " - " + extra_text)

    def closeEvent(self, event):
        self.has_closed = True
        if FavoritesWindow.top_level is self:
            FavoritesWindow.top_level = None
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    def _play_favorite(self, favorite: Favorite):
        try:
            query = favorite.get_play_query(self.library_data)
            if not query:
                raise ValueError(
                    _("No valid play query could be generated for this favorite")
                )
            if isinstance(query, str):
                track = self.library_data.get_track(query)
                self.app_actions.start_play_callback(track=track)
            else:
                self.app_actions.search_and_play(query)
        except Exception as e:
            error_msg = str(e)
            if "No matching tracks found" in error_msg:
                error_msg += "\n\n" + _(
                    "Tip: If you've recently added or moved files, try checking 'Overwrite Cache' in the search options."
                )
            logger.error("Error playing favorite: %s", error_msg)
            self.app_actions.alert(
                _("Error"), error_msg, kind="error", master=self
            )

    def play_random_favorite(self):
        if not FavoritesWindow.recent_favorites:
            self.app_actions.alert(
                _("No Favorites"), _("No favorites available to play."), master=self
            )
            return
        random_favorite = random.choice(FavoritesWindow.recent_favorites)
        self._play_favorite(random_favorite)


class FavoriteWindow(SmartWindow):
    """Subsidiary window to view and edit a specific favorite."""

    def __init__(self, master, favorites_window, favorite, library_data, is_new=False):
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("Favorite Details"),
            geometry="400x300",
            offset_x=50,
            offset_y=50,
        )
        self.master = master
        self.favorites_window = favorites_window
        self.favorite = favorite
        self.library_data = library_data
        self.is_new = is_new

        self.setStyleSheet(AppStyle.get_stylesheet())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self._create_details_frame(layout)
        self._create_buttons_frame(layout)

    def _create_details_frame(self, parent_layout):
        details_frame = QFrame(self)
        details_layout = QVBoxLayout(details_frame)

        track = None
        if self.favorite.attribute == TrackAttribute.TITLE:
            for t in self.library_data.get_all_tracks():
                if (
                    self.favorite.value == (t.title or t.filepath)
                    and (not self.favorite.artist or self.favorite.artist == t.artist)
                    and (not self.favorite.album or self.favorite.album == t.album)
                    and (not self.favorite.composer or self.favorite.composer == t.composer)
                ):
                    track = t
                    break

        if track:
            details_layout.addWidget(QLabel(_("Type: Track"), self))
            details_layout.addWidget(
                QLabel(f"{_('Title')}: {track.title or track.filepath}", self)
            )
            details_layout.addWidget(QLabel(f"{_('File')}: {track.filepath}", self))
        else:
            details_layout.addWidget(
                QLabel(f"{_('Type')}: {self.favorite.attribute.value}", self)
            )
            details_layout.addWidget(
                QLabel(f"{_('Value')}: {self.favorite.value}", self)
            )

        timestamp = datetime.fromtimestamp(self.favorite.timestamp)
        details_layout.addWidget(
            QLabel(
                f"{_('Added')}: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
                self,
            )
        )
        parent_layout.addWidget(details_frame)

    def _create_buttons_frame(self, parent_layout):
        buttons_layout = QHBoxLayout()
        confirm_btn = QPushButton(
            _("Create Favorite") if self.is_new else _("Update Favorite"), self
        )
        confirm_btn.clicked.connect(self._confirm_favorite)
        buttons_layout.addWidget(confirm_btn)

        if not self.is_new:
            remove_btn = QPushButton(_("Remove Favorite"), self)
            remove_btn.clicked.connect(self._remove_favorite)
            buttons_layout.addWidget(remove_btn)

        close_btn = QPushButton(_("Close"), self)
        close_btn.clicked.connect(self.close)
        buttons_layout.addWidget(close_btn)
        parent_layout.addLayout(buttons_layout)

    def _confirm_favorite(self):
        if self.favorites_window.create_favorite(self.favorite, is_new=self.is_new):
            self.close()

    def _remove_favorite(self):
        if FavoritesWindow.remove_favorite(self.favorite):
            self.favorites_window.refresh()
        self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)
