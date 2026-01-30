"""
Muse application UI using PySide6 (Qt for Python).
Full UI is ported to ui_qt; this is the main window and entry point.
"""
from copy import deepcopy
import os
import signal
import sys
import time
import traceback
from typing import Optional

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QSlider,
    QComboBox,
    QCheckBox,
    QProgressBar,
    QMenu,
    QFrame,
    QMessageBox,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon

from utils.globals import Globals, PlaylistSortType, PlaybackMasterStrategy
from library_data.library_data import LibraryData
from ui_qt.app_actions import AppActions
from ui_qt.app_style import AppStyle
from muse.run import Run
from muse.run_config import RunConfig
from utils.persistent_data_manager import PersistentDataManager
from utils import (
    app_info_cache,
    config,
    FFmpegHandler,
    JobQueue,
    RunnerAppConfig,
    TempDir,
    I18N,
    Utils,
    get_logger,
)

logger = get_logger(__name__)
_ = I18N._


def _qt_alert(parent: Optional[QWidget], title: str, message: str, kind: str = "info"):
    """Show a Qt message box. kind: info, warning, error, askokcancel, askyesno, askyesnocancel."""
    if kind == "askokcancel":
        result = QMessageBox.question(
            parent, title, message,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return result == QMessageBox.StandardButton.Ok
    if kind == "askyesno":
        result = QMessageBox.question(
            parent, title, message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return result == QMessageBox.StandardButton.Yes
    if kind == "askyesnocancel":
        result = QMessageBox.question(
            parent, title, message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return result
    if kind == "error":
        QMessageBox.critical(parent, title, message)
        return None
    if kind == "warning":
        QMessageBox.warning(parent, title, message)
        return None
    QMessageBox.information(parent, title, message)
    return None


class MediaFrameWidget(QFrame):
    """Album art / video area. Provides winId() for VLC embedding."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(f"background-color: {AppStyle.MEDIA_BG};")
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet(f"color: {AppStyle.FG_COLOR};")
        self._label.setText(_("Album art"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)

    def show_image(self, image_filepath: Optional[str]):
        if image_filepath and os.path.isfile(image_filepath):
            from PySide6.QtGui import QPixmap
            pix = QPixmap(image_filepath)
            if not pix.isNull():
                self._label.setPixmap(pix.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                return
        self._label.clear()
        self._label.setText(_("Album art"))

    def set_background_color(self, color: str):
        self.setStyleSheet(f"background-color: {color or AppStyle.MEDIA_BG};")


class MuseAppQt(QMainWindow):
    """PySide6 main window for Muse. Callbacks are passed to internal modules via AppActions."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(_(" Muse "))
        self.progress_bar: Optional[QProgressBar] = None
        self.job_queue = JobQueue("Playlist Runs")
        self.job_queue_preset_schedules = JobQueue("Preset Schedules")
        self.runner_app_config = self._load_info_cache()
        self.config_history_index = 0
        self.fullscreen = False
        self.current_run = Run(RunConfig(placeholder=True))
        self._library_data: Optional[LibraryData] = None

        self.app_actions = AppActions({
            "track_details_callback": self.update_track_text,
            "update_dj_persona_callback": self.update_dj_persona_callback,
            "update_next_up_callback": self.update_next_up_text,
            "update_prior_track_callback": self.update_previous_track_text,
            "update_spot_profile_topics_text": self.update_spot_profile_topics_text,
            "update_upcoming_group_callback": self.update_upcoming_group_text,
            "update_progress_callback": self.update_progress_bar,
            "update_extension_status": self.update_label_extension_status,
            "update_album_artwork": self.update_album_artwork,
            "get_media_frame_handle": self.get_media_frame_handle,
            "start_play_callback": self.start_playback,
            "shutdown_callback": self.on_closing,
            "toast": self.toast,
            "_alert": self.alert,
            "update_playlist_state": self.update_playlist_state,
            "update_favorite_status": self.update_favorite_status,
            "get_current_track": self.get_current_track,
            "add_favorite": self.add_favorite,
            "open_track_details": self.open_track_details_window,
            "find_track": lambda search_query: self._find_track(search_query),
            "search_and_play": self.search_and_play,
            "update_directory_count": self.update_directory_count,
            "open_password_admin_window": self.open_password_admin_window,
        }, self)

        self._build_menus()
        self._build_central()
        self._apply_theme()

        try:
            from ui_qt.blacklist_window import BlacklistWindow
            BlacklistWindow.set_blacklist()
        except ImportError as e:
            logger.debug("Blacklist init: %s", e)

        import platform
        if platform.system() == "Windows":
            try:
                from utils.admin_utils import is_admin
                if not is_admin():
                    logger.debug("Application started without administrator privileges - audio device switching will be limited")
            except ImportError:
                pass

    def _build_menus(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu(_("File"))
        file_menu.addAction(_("Open Library"), self.open_library_window)
        file_menu.addAction(_("Current Track Text"), self.open_text)
        file_menu.addSeparator()
        file_menu.addAction(_("Exit"), self.quit)

        view_menu = menubar.addMenu(_("View"))
        view_menu.addAction(_("Toggle Fullscreen"), self.toggle_fullscreen)
        view_menu.addAction(_("Toggle Theme"), self.toggle_theme)
        view_menu.addSeparator()
        view_menu.addAction(_("Playlists"), self.open_presets_window)
        view_menu.addAction(_("Favorites"), self.open_favorites_window)
        view_menu.addAction(_("History"), self.open_history_window)
        view_menu.addAction(_("Composers"), self.open_composers_window)
        view_menu.addAction(_("Personas"), self.open_personas_window)

        tools_menu = menubar.addMenu(_("Tools"))
        tools_menu.addAction(_("Search"), self.open_search_window)
        tools_menu.addAction(_("Schedules"), self.open_schedules_window)
        tools_menu.addAction(_("Extensions"), self.open_extensions_window)
        tools_menu.addAction(_("Blacklist"), self.open_blacklist_window)
        tools_menu.addAction(_("Weather"), self.open_weather_window)
        tools_menu.addAction(_("Text to Speech"), self.open_tts_window)
        tools_menu.addAction(_("Timer"), self.open_timer_window)
        tools_menu.addAction(_("Audio Devices"), self.open_audio_device_window)
        tools_menu.addSeparator()
        tools_menu.addAction(_("Configuration"), self.open_configuration_window)
        tools_menu.addAction(_("Security Configuration"), self.open_password_admin_window)

    def _build_central(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        sidebar = QWidget()
        sidebar.setMaximumWidth(380)
        sidebar_layout = QGridLayout(sidebar)
        row = 0

        def add_label(text, colspan=3):
            nonlocal row
            lbl = QLabel(text)
            sidebar_layout.addWidget(lbl, row, 0, 1, colspan)
            row += 1
            return lbl

        self.label_directory_count = add_label("")
        self.label_dj_persona = add_label(_("DJ"))
        self.label_title_text = add_label(_("Title"))
        self.label_album_text = add_label(_("Album"))
        self.label_artist_text = add_label(_("Artist"))
        self.label_composer_text = add_label(_("Composer"))
        self.label_year_text = add_label(_("Year"))
        self.label_next_up = add_label(_("Next Up"))
        self.label_previous_title = add_label(_("Prior Track"))
        self.label_upcoming_group = add_label(_("Upcoming Group"))
        self.label_muse = add_label(_("Spot Details"))
        self.label_extension_status = add_label(_("Extension Status"))

        self.label_volume = QLabel(_("Volume"))
        sidebar_layout.addWidget(self.label_volume, row, 0)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(int(Globals.DEFAULT_VOLUME_THRESHOLD))
        self.volume_slider.valueChanged.connect(self.set_volume)
        sidebar_layout.addWidget(self.volume_slider, row, 1, 1, 2)
        row += 1

        self._progress_bar_row = row
        row += 1

        self.run_btn = QPushButton(_("Play"))
        self.run_btn.clicked.connect(lambda: self.run())
        sidebar_layout.addWidget(self.run_btn, row, 0)
        row += 1

        self.playlists_btn = QPushButton(_("Playlists"))
        self.playlists_btn.clicked.connect(self.open_presets_window)
        sidebar_layout.addWidget(self.playlists_btn, row, 1, 1, 2)
        row += 1

        self.next_btn = QPushButton(_("Next"))
        self.next_btn.clicked.connect(lambda: self.next())
        sidebar_layout.addWidget(self.next_btn, row, 0)
        self.next_grouping_btn = QPushButton(_("Next Grouping"))
        self.next_grouping_btn.clicked.connect(lambda: self.next_grouping())
        sidebar_layout.addWidget(self.next_grouping_btn, row, 1, 1, 2)
        row += 1

        self.pause_btn = QPushButton(_("Pause"))
        self.pause_btn.clicked.connect(lambda: self.pause())
        sidebar_layout.addWidget(self.pause_btn, row, 0)
        self.cancel_btn = QPushButton(_("Stop"))
        self.cancel_btn.clicked.connect(lambda: self.cancel())
        sidebar_layout.addWidget(self.cancel_btn, row, 1, 1, 2)
        self.cancel_btn.hide()
        row += 1

        self.label_delay = QLabel(_("Delay Seconds"))
        sidebar_layout.addWidget(self.label_delay, row, 0)
        self.delay_combo = QComboBox()
        self.delay_combo.addItems([str(i) for i in range(101)])
        self.delay_combo.setCurrentText(str(self.runner_app_config.delay_time_seconds))
        self.delay_combo.currentTextChanged.connect(self.set_delay)
        sidebar_layout.addWidget(self.delay_combo, row, 1, 1, 2)
        row += 1

        self.label_playlist_strategy = QLabel(_("Playlist"))
        sidebar_layout.addWidget(self.label_playlist_strategy, row, 0)
        self.playlist_strategy_combo = QComboBox()
        self.playlist_strategy_combo.addItems(list(PlaybackMasterStrategy.__members__.keys()))
        self.playlist_strategy_combo.setCurrentText(str(self.runner_app_config.playback_master_strategy))
        self.playlist_strategy_combo.currentTextChanged.connect(self.set_playback_master_strategy)
        sidebar_layout.addWidget(self.playlist_strategy_combo, row, 1, 1, 2)
        row += 1

        self.label_sort_type = QLabel(_("Playlist Sort"))
        sidebar_layout.addWidget(self.label_sort_type, row, 0)
        self.sort_type_combo = QComboBox()
        current_type = PlaylistSortType[self.runner_app_config.workflow_type].get_translation()
        self.sort_type_combo.addItems(PlaylistSortType.get_translated_names())
        self.sort_type_combo.setCurrentText(current_type)
        self.sort_type_combo.currentTextChanged.connect(self.set_playlist_sort_type)
        sidebar_layout.addWidget(self.sort_type_combo, row, 1, 1, 2)
        row += 1

        self.favorite_check = QCheckBox(_("Favorite"))
        self.favorite_check.stateChanged.connect(self.set_favorite)
        sidebar_layout.addWidget(self.favorite_check, row, 0)
        self.favorites_btn = QPushButton(_("Favorites"))
        self.favorites_btn.clicked.connect(self.open_favorites_window)
        sidebar_layout.addWidget(self.favorites_btn, row, 1, 1, 2)
        row += 1

        self.overwrite_check = QCheckBox(_("Overwrite"))
        self.overwrite_check.setChecked(self.runner_app_config.overwrite)
        sidebar_layout.addWidget(self.overwrite_check, row, 0, 1, 3)
        row += 1

        self.muse_check = QCheckBox(_("Muse"))
        self.muse_check.setChecked(self.runner_app_config.muse)
        self.muse_check.stateChanged.connect(self.set_muse)
        sidebar_layout.addWidget(self.muse_check, row, 0, 1, 3)
        row += 1

        self.extend_check = QCheckBox(_("Extension"))
        self.extend_check.setChecked(self.runner_app_config.extend)
        self.extend_check.stateChanged.connect(self.set_extend)
        sidebar_layout.addWidget(self.extend_check, row, 0, 1, 3)
        row += 1

        self.track_splitting_check = QCheckBox(_("Enable track splitting"))
        self.track_splitting_check.setChecked(self.runner_app_config.enable_long_track_splitting)
        self.track_splitting_check.stateChanged.connect(self.set_track_splitting)
        sidebar_layout.addWidget(self.track_splitting_check, row, 0, 1, 3)
        row += 1

        self.use_system_language_check = QCheckBox(_("Use system language for all topics"))
        self.use_system_language_check.setChecked(self.runner_app_config.use_system_lang_for_all_topics)
        self.use_system_language_check.stateChanged.connect(self.set_use_system_language)
        sidebar_layout.addWidget(self.use_system_language_check, row, 0, 1, 3)
        row += 1

        self.check_entire_playlist_check = QCheckBox(_("Thorough playlist memory check"))
        self.check_entire_playlist_check.setChecked(self.runner_app_config.check_entire_playlist)
        self.check_entire_playlist_check.stateChanged.connect(self.set_check_entire_playlist)
        sidebar_layout.addWidget(self.check_entire_playlist_check, row, 0, 1, 3)
        row += 1

        sidebar_layout.setRowStretch(row, 1)
        main_layout.addWidget(sidebar)
        self._sidebar_layout = sidebar_layout

        self.media_frame = MediaFrameWidget(self)
        main_layout.addWidget(self.media_frame, 1)

    def _apply_theme(self):
        self.setStyleSheet(AppStyle.get_stylesheet())
        self.media_frame.set_background_color(AppStyle.MEDIA_BG)

    def _load_info_cache(self):
        try:
            PersistentDataManager.load()
            self.config_history_index = app_info_cache.get("config_history_index", default_val=0)
            return app_info_cache.get_history_latest()
        except Exception as e:
            logger.error(e)
            return RunnerAppConfig()

    def closeEvent(self, event):
        self.on_closing()
        event.accept()

    def on_closing(self):
        try:
            from ui_qt.blacklist_window import BlacklistWindow
            BlacklistWindow.store_blacklist()
        except ImportError:
            pass
        self.store_info_cache()
        app_info_cache.wipe_instance()
        FFmpegHandler.cleanup_cache()
        TempDir.cleanup()
        QApplication.quit()

    def store_info_cache(self):
        if self.runner_app_config is not None:
            if app_info_cache.set_history(self.runner_app_config):
                if self.config_history_index > 0:
                    self.config_history_index -= 1
        app_info_cache.set("config_history_index", self.config_history_index)
        PersistentDataManager.store()
        app_info_cache.store()

    def quit(self):
        if _qt_alert(self, _("Confirm Quit"), _("Would you like to quit the application?"), "askokcancel"):
            logger.info("Exiting application")
            self.on_closing()

    def alert(self, title: str, message: str, kind: str = "info", severity: str = "normal", master: Optional[object] = None):
        parent = master if master is not None else self
        if isinstance(parent, QWidget):
            return _qt_alert(parent, title, message, kind)
        return _qt_alert(self, title, message, kind)

    def handle_error(self, error_text, title=None, kind="error"):
        traceback.print_exc()
        if title is None:
            title = _("Error")
        self.alert(title, error_text, kind=kind)

    def set_delay(self, _value=None):
        self.runner_app_config.delay_time_seconds = self.delay_combo.currentText()
        Globals.set_delay(int(self.runner_app_config.delay_time_seconds))

    def set_playback_master_strategy(self, _value=None):
        self.runner_app_config.playback_master_strategy = self.playlist_strategy_combo.currentText()

    def set_volume(self, _value=None):
        self.runner_app_config.volume = self.volume_slider.value()
        Globals.set_volume(int(self.runner_app_config.volume))
        if self.current_run is not None and not self.current_run.is_complete and self.current_run.get_playback() is not None:
            self.current_run.get_playback().set_volume()

    def set_playlist_sort_type(self, _value=None):
        sort_text = self.sort_type_combo.currentText()
        self.runner_app_config.workflow_type = PlaylistSortType.get_from_translation(sort_text).value

    def set_favorite(self, _state=None):
        favorited = self.favorite_check.isChecked()
        current_track = self.current_run.get_current_track() if self.current_run else None
        if current_track is not None:
            try:
                from ui_qt.favorites_window import FavoritesWindow
                FavoritesWindow.set_favorite(current_track, favorited)
            except ImportError as e:
                logger.debug("FavoritesWindow: %s", e)

    def set_muse(self, _state=None):
        self.runner_app_config.muse = self.muse_check.isChecked()

    def set_extend(self, _state=None):
        self.runner_app_config.extend = self.extend_check.isChecked()

    def set_track_splitting(self, _state=None):
        self.runner_app_config.enable_long_track_splitting = self.track_splitting_check.isChecked()

    def set_use_system_language(self, _state=None):
        self.runner_app_config.use_system_lang_for_all_topics = self.use_system_language_check.isChecked()

    def set_check_entire_playlist(self, _state=None):
        self.runner_app_config.check_entire_playlist = self.check_entire_playlist_check.isChecked()

    def set_widgets_from_config(self):
        if self.runner_app_config is None:
            return
        self.sort_type_combo.setCurrentText(PlaylistSortType[self.runner_app_config.workflow_type].get_translation())
        self.delay_combo.setCurrentText(str(self.runner_app_config.delay_time_seconds))
        self.overwrite_check.setChecked(self.runner_app_config.overwrite)
        self.muse_check.setChecked(self.runner_app_config.muse)
        self.volume_slider.setValue(int(self.runner_app_config.volume))

    def get_args(self, track=None):
        self.store_info_cache()
        self.set_delay()
        args = RunConfig()
        args.playlist_sort_type = PlaylistSortType.get_from_translation(self.sort_type_combo.currentText())
        args.playback_master_strategy = PlaybackMasterStrategy.get_from_translation(self.playlist_strategy_combo.currentText())
        args.total = -1
        args.is_all_tracks, args.directories = self.get_directories()
        args.overwrite = self.overwrite_check.isChecked()
        args.muse = self.muse_check.isChecked()
        args.extend = self.extend_check.isChecked()
        args.track = track
        args.enable_long_track_splitting = self.track_splitting_check.isChecked()
        args.use_system_language_for_all_topics = self.use_system_language_check.isChecked()
        args.check_entire_playlist = self.check_entire_playlist_check.isChecked()
        args_copy = deepcopy(args)
        return args, args_copy

    def get_directories(self):
        selection = self.playlist_strategy_combo.currentText()
        all_dirs = config.get_subdirectories()
        if selection == "ALL_MUSIC":
            return True, list(all_dirs.keys())
        directories = []
        for full_path, key in all_dirs.items():
            if key == selection:
                directories.append(full_path)
                break
        return False, directories

    def destroy_progress_bar(self):
        if self.progress_bar is not None:
            self.progress_bar.deleteLater()
            self.progress_bar = None

    def run(self, event=None, track=None, override_scheduled=False):
        args, args_copy = self.get_args(track=track)
        self.update_directory_count(args.directories)
        try:
            from utils.audio_device_manager import AudioDeviceManager
            AudioDeviceManager().check_and_apply_settings(app_actions=self.app_actions)
        except (ImportError, Exception) as e:
            if isinstance(e, ImportError):
                logger.debug("Audio device management not available (pycaw not installed)")
            else:
                logger.error("Error checking audio device settings: %s", e)
        try:
            args.validate()
        except Exception as e:
            if not _qt_alert(self, _("Confirm Run"), str(e) + "\n\n" + _("Are you sure you want to proceed?"), "askokcancel"):
                return
        if override_scheduled:
            self.cancel()
            time.sleep(2)

        def run_async(a):
            self.job_queue.job_running = True
            self.destroy_progress_bar()
            self.progress_bar = QProgressBar()
            self.progress_bar.setMaximum(100)
            self.progress_bar.setValue(0)
            if hasattr(self, "_sidebar_layout") and hasattr(self, "_progress_bar_row"):
                self._sidebar_layout.addWidget(self.progress_bar, self._progress_bar_row, 0, 1, 3)
            self.cancel_btn.show()
            self.current_run = Run(a, app_actions=self.app_actions)
            self.current_run.execute()
            self.cancel_btn.hide()
            self.destroy_progress_bar()
            self.job_queue.job_running = False
            next_args = self.job_queue.take()
            if next_args:
                Utils.start_thread(run_async, use_asyncio=False, args=[next_args])

        if not override_scheduled and self.job_queue.has_pending():
            self.job_queue.add(args)
        else:
            self.runner_app_config.set_from_run_config(args_copy)
            Utils.start_thread(run_async, use_asyncio=False, args=[args])

    def start_playback(self, track=None, playlist_sort_type=None, overwrite=None):
        if playlist_sort_type is not None:
            self.sort_type_combo.setCurrentText(playlist_sort_type.get_translation())
        if overwrite is not None:
            self.overwrite_check.setChecked(overwrite)
        override_scheduled = self.current_run is not None and not self.current_run.is_placeholder()
        self.run(track=track, override_scheduled=override_scheduled)

    def update_progress_bar(self, progress, elapsed_time, total_duration):
        if self.progress_bar is not None:
            self.progress_bar.setValue(int(progress))
            QApplication.processEvents()

    def next(self, event=None):
        if not self.current_run.is_started:
            self.run()
        else:
            self.current_run.next()

    def next_grouping(self, event=None):
        if not self.current_run.is_started:
            self.run()
        else:
            self.current_run.next_grouping()

    def pause(self, event=None):
        self.current_run.pause()

    def cancel(self, event=None):
        self.current_run.cancel()

    def update_track_text(self, audio_track):
        if isinstance(audio_track, str):
            title_text, album_text, artist_text, composer_text, year_text = audio_track, "", "", "", ""
        else:
            title_text = _("Track: ") + audio_track.title
            album_text = (_("Album: ") + audio_track.album) if audio_track.album else ""
            artist_text = (_("Artist: ") + audio_track.artist) if audio_track.artist else ""
            composer_text = (_("Composer: ") + audio_track.composer) if audio_track.composer else ""
            year_text = (_("Year: ") + str(audio_track.year)) if audio_track.year else ""
        self.label_title_text.setText(Utils._wrap_text_to_fit_length(title_text, 100))
        self.label_album_text.setText(Utils._wrap_text_to_fit_length(album_text, 100))
        self.label_artist_text.setText(Utils._wrap_text_to_fit_length(artist_text, 100))
        self.label_composer_text.setText(Utils._wrap_text_to_fit_length(composer_text, 100))
        self.label_year_text.setText(Utils._wrap_text_to_fit_length(year_text, 100))
        QApplication.processEvents()

    def update_next_up_text(self, next_up_text, no_title=False):
        if next_up_text is None or (isinstance(next_up_text, str) and next_up_text.strip() == ""):
            next_up_text = ""
        elif not no_title and isinstance(next_up_text, str):
            next_up_text = _("Next Up: ") + next_up_text
        self.label_next_up.setText(Utils._wrap_text_to_fit_length(str(next_up_text)[:500], 90))
        QApplication.processEvents()

    def update_previous_track_text(self, previous_track_text):
        if previous_track_text is None or (isinstance(previous_track_text, str) and previous_track_text.strip() == ""):
            previous_track_text = ""
        else:
            previous_track_text = _("Previous Track: ") + str(previous_track_text)
        self.label_previous_title.setText(Utils._wrap_text_to_fit_length(str(previous_track_text)[:500], 90))
        QApplication.processEvents()

    def update_upcoming_group_text(self, upcoming_group_text, grouping_type=None):
        if upcoming_group_text is None or (isinstance(upcoming_group_text, str) and upcoming_group_text.strip() == ""):
            upcoming_group_text = ""
        else:
            if grouping_type is not None:
                name = grouping_type.get_grouping_readable_name()
                upcoming_group_text = _("Upcoming {0}: {1}").format(name or "Group", upcoming_group_text)
            else:
                upcoming_group_text = _("Upcoming Group: {0}").format(upcoming_group_text)
        self.label_upcoming_group.setText(Utils._wrap_text_to_fit_length(str(upcoming_group_text)[:500], 90))
        QApplication.processEvents()

    def update_spot_profile_topics_text(self, muse_text):
        self.label_muse.setText(Utils._wrap_text_to_fit_length(str(muse_text)[:500], 90))
        QApplication.processEvents()

    def update_label_extension_status(self, extension):
        self.label_extension_status.setText(Utils._wrap_text_to_fit_length(str(extension)[:500], 90))
        QApplication.processEvents()

    def update_directory_count(self, directories):
        count = len(directories) if isinstance(directories, list) else 0
        self.label_directory_count.setText(_("Directories: {0}").format(count))
        QApplication.processEvents()

    def update_dj_persona_callback(self, persona_name):
        if persona_name is None or (isinstance(persona_name, str) and persona_name.strip() == ""):
            persona_name = ""
        else:
            persona_name = _("DJ: ") + str(persona_name)
        self.label_dj_persona.setText(Utils._wrap_text_to_fit_length(str(persona_name)[:100], 90))
        QApplication.processEvents()

    def update_album_artwork(self, image_filepath):
        self.media_frame.show_image(image_filepath)

    def get_media_frame_handle(self):
        return self.media_frame.winId() if hasattr(self.media_frame, "winId") else None

    def update_playlist_state(self, strategy=None, staged_playlist=None):
        if strategy is not None:
            self.playlist_strategy_combo.setCurrentText(strategy.value)
            self.runner_app_config.playback_master_strategy = strategy.value
        if staged_playlist is not None and not self.current_run.is_started:
            self.update_next_up_text(_("Staged Playlist: ") + str(staged_playlist))
        elif staged_playlist is None and not self.current_run.is_started:
            self.update_next_up_text("")

    def update_favorite_status(self, track):
        try:
            from ui_qt.favorites_window import FavoritesWindow
            is_favorited = FavoritesWindow.is_track_favorited(track)
            if self.favorite_check.isChecked() != is_favorited:
                self.favorite_check.setChecked(is_favorited)
        except ImportError:
            pass

    def get_current_track(self):
        if self.current_run and not self.current_run.is_complete:
            return self.current_run.get_current_track()
        return None

    def _find_track(self, search_query):
        try:
            from ui_qt.search_window import SearchWindow
            return SearchWindow.find_track(self.library_data, search_query)
        except ImportError:
            return None

    def search_and_play(self, search_query):
        track = self._find_track(search_query)
        if track:
            playlist_sort_type = getattr(search_query, "get_playlist_sort_type", lambda: None)()
            self.start_playback(track=track, playlist_sort_type=playlist_sort_type)
        else:
            self.alert(_("Error"), _("Track not found in library for query: ") + "\n\n" + str(search_query), kind="error")

    def add_favorite(self, favorite):
        try:
            from ui_qt.favorites_window import FavoritesWindow
            return FavoritesWindow.add_favorite(favorite, is_new=True, app_actions=self.app_actions, from_favorite_window=False)
        except ImportError:
            self.alert(_("Error"), _("Favorites window not available."), kind="error")
            return False
        except Exception as e:
            self.alert(_("Error"), str(e), kind="error")
            return False

    @property
    def library_data(self):
        if self._library_data is None:
            self._library_data = LibraryData()
        return self._library_data

    def open_text(self):
        if self.current_run is None or self.current_run.is_complete or self.current_run.is_cancelled():
            return
        self.current_run.open_text()

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self.showFullScreen()
        else:
            self.showNormal()

    def toggle_theme(self):
        AppStyle.IS_DEFAULT_THEME = not AppStyle.IS_DEFAULT_THEME
        self._apply_theme()
        self.toast(_("Theme switched to {0}.").format(AppStyle.get_theme_name()))

    def toast(self, message):
        logger.info("Toast: %s", message)
        msg = QMessageBox(self)
        msg.setWindowTitle("")
        msg.setText(message)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.setModal(False)
        msg.show()
        QTimer.singleShot(2000, msg.close)

    def construct_preset(self, name):
        args, _ = self.get_args()
        self.runner_app_config.set_from_run_config(args)
        from ui_qt.preset import Preset
        return Preset.from_runner_app_config(name, self.runner_app_config)

    def start_run_from_preset(self, preset, manual=True):
        if getattr(preset, "playlist_sort_types", None) and len(preset.playlist_sort_types) > 0:
            self.sort_type_combo.setCurrentText(preset.playlist_sort_types[0].get_translation())
        elif getattr(preset, "playlist_sort_type", None):
            sort_val = preset.playlist_sort_type
            if hasattr(sort_val, "get_translation"):
                sort_val = sort_val.get_translation()
            self.sort_type_combo.setCurrentText(sort_val)
        QApplication.processEvents()

    # Open-window methods: assume ui_qt modules exist; toast on ImportError until ported
    def open_library_window(self):
        try:
            from ui_qt.library_window import LibraryWindow
            LibraryWindow(self, self.app_actions, self.library_data)
        except ImportError as e:
            logger.debug("LibraryWindow: %s", e)
            self.toast(_("Open Library not yet available."))

    def open_composers_window(self):
        try:
            from ui_qt.composers_window import ComposersWindow
            ComposersWindow(self, self.app_actions)
        except ImportError as e:
            logger.debug("ComposersWindow: %s", e)
            self.toast(_("Composers not yet available."))

    def open_personas_window(self):
        try:
            from ui_qt.personas_window import PersonasWindow
            PersonasWindow(self, self.app_actions)
        except ImportError as e:
            logger.debug("PersonasWindow: %s", e)
            self.toast(_("Personas not yet available."))

    def open_schedules_window(self):
        try:
            from ui_qt.schedules_window import SchedulesWindow
            SchedulesWindow(self, self.app_actions)
        except ImportError as e:
            logger.debug("SchedulesWindow: %s", e)
            self.toast(_("Schedules not yet available."))

    def open_search_window(self):
        try:
            from ui_qt.search_window import SearchWindow
            SearchWindow(self, self.app_actions, self.library_data)
        except ImportError as e:
            logger.debug("SearchWindow: %s", e)
            self.toast(_("Search not yet available."))

    def open_track_details_window(self, track):
        try:
            from ui_qt.track_details_window import TrackDetailsWindow
            TrackDetailsWindow(self, self.app_actions, track)
        except ImportError as e:
            logger.debug("TrackDetailsWindow: %s", e)
            self.toast(_("Track Details not yet available."))
        except Exception as e:
            self.alert(_("Error"), str(e), kind="error")

    def open_extensions_window(self):
        try:
            from ui_qt.extensions_window import ExtensionsWindow
            ExtensionsWindow(self, self.app_actions, self.library_data)
        except ImportError as e:
            logger.debug("ExtensionsWindow: %s", e)
            self.toast(_("Extensions not yet available."))

    def open_blacklist_window(self):
        try:
            from ui_qt.blacklist_window import BlacklistWindow
            BlacklistWindow(self, self.app_actions)
        except ImportError as e:
            logger.debug("BlacklistWindow: %s", e)
            self.toast(_("Blacklist not yet available."))

    def open_presets_window(self):
        try:
            from ui_qt.presets_window import PresetsWindow
            PresetsWindow(self, self.app_actions, self.construct_preset, self.start_run_from_preset)
        except ImportError as e:
            logger.debug("PresetsWindow: %s", e)
            self.toast(_("Playlists not yet available."))

    def open_favorites_window(self):
        try:
            from ui_qt.favorites_window import FavoritesWindow
            FavoritesWindow(self, self.app_actions, self.library_data)
        except ImportError as e:
            logger.debug("FavoritesWindow: %s", e)
            self.toast(_("Favorites not yet available."))

    def open_history_window(self):
        try:
            from ui_qt.history_window import HistoryWindow
            HistoryWindow(self, self.app_actions, self.library_data)
        except ImportError as e:
            logger.debug("HistoryWindow: %s", e)
            self.toast(_("History not yet available."))

    def open_weather_window(self):
        try:
            from ui_qt.weather_window import WeatherWindow
            WeatherWindow(self, self.app_actions)
        except ImportError as e:
            logger.debug("WeatherWindow: %s", e)
            self.toast(_("Weather not yet available."))

    def open_tts_window(self):
        try:
            from ui_qt.tts_window import TTSWindow
            TTSWindow(self, self.app_actions)
        except ImportError as e:
            logger.debug("TTSWindow: %s", e)
            self.toast(_("Text to Speech not yet available."))

    def open_timer_window(self):
        try:
            from ui_qt.timer_window import TimerWindow
            TimerWindow(self, self.app_actions)
        except ImportError as e:
            logger.debug("TimerWindow: %s", e)
            self.toast(_("Timer not yet available."))

    def open_audio_device_window(self):
        try:
            from ui_qt.audio_device_window import AudioDeviceWindow
            AudioDeviceWindow(self, self.app_actions)
        except ImportError as e:
            logger.debug("AudioDeviceWindow: %s", e)
            self.toast(_("Audio Devices not yet available."))
        except Exception as e:
            self.alert(_("Error"), str(e), kind="error")

    def open_configuration_window(self):
        try:
            from ui_qt.configuration_window import ConfigurationWindow
            ConfigurationWindow(self, self.app_actions)
        except ImportError as e:
            logger.debug("ConfigurationWindow: %s", e)
            self.toast(_("Configuration not yet available."))

    def open_password_admin_window(self):
        try:
            from ui_qt.auth.password_admin_window import PasswordAdminWindow
            PasswordAdminWindow(self, self.app_actions)
        except ImportError as e:
            logger.debug("PasswordAdminWindow: %s", e)
            self.toast(_("Security Configuration not yet available."))
        except Exception as e:
            self.handle_error(str(e), title=_("Password Admin Window Error"))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Muse")
    assets = os.path.join(os.path.dirname(os.path.realpath(__file__)), "assets")
    icon_path = os.path.join(assets, "icon.png")
    if os.path.isfile(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    window = MuseAppQt()
    window.resize(1200, 700)
    window.show()

    def graceful_shutdown(*args):
        logger.info("Caught signal, shutting down gracefully...")
        window.on_closing()
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, graceful_shutdown)
        signal.signal(signal.SIGTERM, graceful_shutdown)
    except (ValueError, AttributeError):
        pass

    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
