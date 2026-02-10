"""
Playlist management window (PySide6).
Port of ui/playlist_window.py; logic preserved, UI uses Qt.
Feature is in partial development: requires app_actions to provide
get_track, get_all_filepaths (and optionally set_playback_master_strategy) for full functionality.
"""

from types import SimpleNamespace

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QListWidget,
    QWidget,
    QInputDialog,
    QCheckBox,
)
from PySide6.QtCore import Qt

from lib.multi_display_qt import SmartWindow
from muse.playback_config import PlaybackConfig
from muse.playlist import Playlist
from ui_qt.app_style import AppStyle
from utils.app_info_cache_qt import app_info_cache
from utils.config import config
from utils.globals import PlaylistSortType, PlaybackMasterStrategy
from utils.logging_setup import get_logger
from utils.translations import I18N

_ = I18N._
logger = get_logger(__name__)


class PlaybackMaster:
    """Container for a list of PlaybackConfigs (master playlist)."""

    def __init__(self, initial_configs=None):
        self.playback_configs = list(initial_configs or [])


class MasterPlaylistWindow(SmartWindow):
    """Main window for managing playlists using PlaybackMaster.

    TODO: WIP / currently in development. No menu or callback in app_qt opens this
    window yet (View → Playlists opens PresetsWindow). This window will need to be
    hooked up to the main window (e.g. open_playlist_window equivalent) when
    master-playlist management should be available in the Qt UI.
    """

    named_playlist_configs = {}
    top_level = None

    @staticmethod
    def load_named_playlist_configs():
        MasterPlaylistWindow.named_playlist_configs = app_info_cache.get(
            "named_playlist_configs", {}
        )

    @staticmethod
    def store_named_playlist_configs():
        app_info_cache.set(
            "named_playlist_configs", MasterPlaylistWindow.named_playlist_configs
        )

    def __init__(self, master, app_actions, initial_configs=None, is_current_playlist=True):
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("Playlists"),
            geometry="700x500",
            offset_x=50,
            offset_y=50,
        )
        MasterPlaylistWindow.top_level = self
        self.master = master
        self.app_actions = app_actions
        self.is_current_playlist = is_current_playlist

        MasterPlaylistWindow.load_named_playlist_configs()

        self.setStyleSheet(AppStyle.get_stylesheet())
        layout = QGridLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Available playlists
        avail_label = QLabel(_("Available Playlists"), self)
        layout.addWidget(avail_label, 0, 0)
        self.available_playlists = QListWidget(self)
        self.available_playlists.setMinimumWidth(200)
        self.update_available_playlists()
        layout.addWidget(self.available_playlists, 1, 0)

        # Current / master playlist
        master_label = QLabel(_("Current Playlist"), self)
        layout.addWidget(master_label, 0, 1)
        self.master_playlist = QListWidget(self)
        self.master_playlist.setMinimumWidth(200)
        layout.addWidget(self.master_playlist, 1, 1)

        # Settings row: tracks per config
        settings_w = QWidget(self)
        settings_layout = QHBoxLayout(settings_w)
        settings_layout.addWidget(QLabel(_("Tracks per Config"), settings_w))
        self.tracks_per_config_edit = QLineEdit(settings_w)
        self.tracks_per_config_edit.setMaximumWidth(60)
        self.tracks_per_config_edit.setText("2")
        settings_layout.addWidget(self.tracks_per_config_edit)
        settings_layout.addStretch()
        layout.addWidget(settings_w, 2, 0, 1, 2)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton(_("Add to Master"), self)
        self.btn_add.clicked.connect(self.add_to_master)
        btn_layout.addWidget(self.btn_add)
        self.btn_remove = QPushButton(_("Remove from Master"), self)
        self.btn_remove.clicked.connect(self.remove_from_master)
        btn_layout.addWidget(self.btn_remove)
        self.btn_new_playlist = QPushButton(_("New Playlist"), self)
        self.btn_new_playlist.clicked.connect(self.open_new_playlist)
        btn_layout.addWidget(self.btn_new_playlist)
        self.btn_save = QPushButton(_("Save Master Playlist"), self)
        self.btn_save.clicked.connect(self.save_master_playlist)
        btn_layout.addWidget(self.btn_save)
        btn_layout.addStretch()
        layout.addLayout(btn_layout, 3, 0, 1, 2)

        self.playback_master = PlaybackMaster(initial_configs or [])
        self.update_master_playlist_display()
        self.show()

    def update_available_playlists(self):
        self.available_playlists.clear()
        for name in MasterPlaylistWindow.named_playlist_configs.keys():
            self.available_playlists.addItem(name)

    def update_master_playlist_display(self):
        self.master_playlist.clear()
        for cfg in self.playback_master.playback_configs:
            self.master_playlist.addItem(str(cfg))

    def add_to_master(self):
        row = self.available_playlists.currentRow()
        if row < 0:
            return
        playlist_name = self.available_playlists.item(row).text()
        if playlist_name in [str(c) for c in self.playback_master.playback_configs]:
            return
        raw = MasterPlaylistWindow.named_playlist_configs.get(playlist_name)
        if not raw:
            return
        # Support both single-playlist format and master format (configs list)
        configs_to_add = []
        if "configs" in raw:
            for c in raw["configs"]:
                configs_to_add.append(self._playback_config_from_saved(c))
        else:
            configs_to_add.append(self._playback_config_from_saved(raw))
        for pc in configs_to_add:
            if pc:
                self.playback_master.playback_configs.append(pc)
        self.update_master_playlist_display()
        self._set_playback_master_strategy(PlaybackMasterStrategy.PLAYLIST_CONFIG)

    def _playback_config_from_saved(self, c):
        """Build one PlaybackConfig from a saved config dict (tracks, sort_type, etc.)."""
        sort_type = c.get("sort_type")
        if sort_type is not None and not hasattr(sort_type, "value"):
            sort_type = PlaylistSortType(sort_type) if isinstance(sort_type, str) else sort_type
        args = SimpleNamespace(
            playlist_sort_type=sort_type or PlaylistSortType.RANDOM,
            directories=[],
            total=-1,
            overwrite=False,
            enable_dynamic_volume=True,
            enable_long_track_splitting=False,
            long_track_splitting_time_cutoff_minutes=20,
            check_entire_playlist=False,
            track=None,
        )
        try:
            playback_config = PlaybackConfig(args=args, data_callbacks=self.app_actions)
            tracks = c.get("tracks") or []
            playback_config.list = Playlist(
                tracks=tracks,
                _type=playback_config.type,
                data_callbacks=self.app_actions,
            )
            return playback_config
        except Exception as e:
            logger.exception("Error building playback config from saved: %s", e)
            return None

    def remove_from_master(self):
        row = self.master_playlist.currentRow()
        if row < 0:
            return
        del self.playback_master.playback_configs[row]
        self.update_master_playlist_display()
        if not self.playback_master.playback_configs:
            self._set_playback_master_strategy(PlaybackMasterStrategy.ALL_MUSIC)

    def _set_playback_master_strategy(self, strategy):
        setter = getattr(self.app_actions, "set_playback_master_strategy", None)
        if callable(setter):
            try:
                setter(strategy.name if hasattr(strategy, "name") else str(strategy))
            except Exception as e:
                logger.debug("set_playback_master_strategy: %s", e)

    def open_new_playlist(self):
        NewPlaylistWindow(self, self.app_actions, self)

    def set_playlist(self, playback_config):
        self.playback_master.playback_configs = [playback_config]
        self.update_master_playlist_display()
        self._set_playback_master_strategy(PlaybackMasterStrategy.PLAYLIST_CONFIG)

    def add_playlist(self, playback_config):
        self.playback_master.playback_configs.append(playback_config)
        self.update_master_playlist_display()
        self._set_playback_master_strategy(PlaybackMasterStrategy.PLAYLIST_CONFIG)

    def save_master_playlist(self):
        if not self.playback_master.playback_configs:
            return
        name, ok = QInputDialog.getText(
            self,
            _("Save Master Playlist"),
            _("Enter a name for this master playlist:"),
        )
        if not ok or not (name and name.strip()):
            return
        name = name.strip()
        try:
            tracks_per = int(self.tracks_per_config_edit.text() or "2")
        except ValueError:
            tracks_per = 2
        MasterPlaylistWindow.named_playlist_configs[name] = {
            "configs": [
                {
                    "tracks": [t.filepath for t in cfg.list.sorted_tracks],
                    "sort_type": cfg.list.sort_type,
                    "config_type": cfg.type,
                    "tracks_per_play": tracks_per,
                }
                for cfg in self.playback_master.playback_configs
            ]
        }
        MasterPlaylistWindow.store_named_playlist_configs()
        self.app_actions.toast(_("Master playlist created successfully"))

    def closeEvent(self, event):
        MasterPlaylistWindow.store_named_playlist_configs()
        if MasterPlaylistWindow.top_level is self:
            MasterPlaylistWindow.top_level = None
        event.accept()


class NewPlaylistWindow(SmartWindow):
    """Window for creating new playlists and playback configs."""

    def __init__(self, parent, app_actions, current_master_window=None):
        super().__init__(
            persistent_parent=parent,
            position_parent=parent,
            title=_("New Playlist"),
            geometry="500x300",
            offset_x=50,
            offset_y=50,
        )
        self.app_actions = app_actions
        self.current_master_window = current_master_window

        self.setStyleSheet(AppStyle.get_stylesheet())
        layout = QGridLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        row = 0

        layout.addWidget(QLabel(_("Playlist Name"), self), row, 0)
        self.playlist_name_edit = QLineEdit(self)
        self.playlist_name_edit.setMinimumWidth(280)
        layout.addWidget(self.playlist_name_edit, row, 1)
        row += 1

        layout.addWidget(QLabel(_("Sort Type"), self), row, 0)
        self.sort_combo = QComboBox(self)
        self.sort_combo.addItems([t.value for t in PlaylistSortType])
        self.sort_combo.setCurrentText(PlaylistSortType.RANDOM.value)
        layout.addWidget(self.sort_combo, row, 1)
        row += 1

        layout.addWidget(QLabel(_("Directory"), self), row, 0)
        self.dir_combo = QComboBox(self)
        self.dir_combo.addItem("ALL_MUSIC")
        for val in config.get_subdirectories().values():
            self.dir_combo.addItem(val)
        layout.addWidget(self.dir_combo, row, 1)
        row += 1

        layout.addWidget(QLabel(_("Playback Config Settings"), self), row, 0, 1, 2)
        row += 1
        self.enable_dynamic_volume = QCheckBox(_("Enable Dynamic Volume"), self)
        self.enable_dynamic_volume.setChecked(True)
        layout.addWidget(self.enable_dynamic_volume, row, 0, 1, 2)
        row += 1
        self.enable_long_track_splitting = QCheckBox(_("Enable Long Track Splitting"), self)
        self.enable_long_track_splitting.setChecked(False)
        layout.addWidget(self.enable_long_track_splitting, row, 0, 1, 2)
        row += 1
        layout.addWidget(QLabel(_("Track Splitting Cutoff (minutes)"), self), row, 0)
        self.cutoff_edit = QLineEdit(self)
        self.cutoff_edit.setMaximumWidth(80)
        self.cutoff_edit.setText("20")
        layout.addWidget(self.cutoff_edit, row, 1)
        row += 1

        btn_layout = QHBoxLayout()
        btn_start = QPushButton(_("Start Playlist"), self)
        btn_start.clicked.connect(lambda: self.create_playlist("start"))
        btn_layout.addWidget(btn_start)
        btn_add_current = QPushButton(_("Add to Current Playlist"), self)
        btn_add_current.clicked.connect(lambda: self.create_playlist("add_current"))
        btn_layout.addWidget(btn_add_current)
        btn_new_master = QPushButton(_("Add to New Master Playlist"), self)
        btn_new_master.clicked.connect(lambda: self.create_playlist("new_master"))
        btn_layout.addWidget(btn_new_master)
        btn_cancel = QPushButton(_("Cancel"), self)
        btn_cancel.clicked.connect(self.close)
        btn_layout.addWidget(btn_cancel)
        btn_layout.addStretch()
        layout.addLayout(btn_layout, row, 0, 1, 2)
        self.show()

    def create_playlist(self, action):
        name = self.playlist_name_edit.text().strip()
        if not name:
            self.app_actions.alert(
                _("Error"),
                _("Please enter a playlist name"),
                kind="error",
                master=self,
            )
            return
        selection = self.dir_combo.currentText()
        all_dirs = config.get_subdirectories()
        directories = []
        if selection == "ALL_MUSIC":
            directories = list(all_dirs.keys())
        else:
            for full_path, key in all_dirs.items():
                if key == selection:
                    directories.append(full_path)
                    break
        try:
            cutoff = int(self.cutoff_edit.text() or "20")
        except ValueError:
            cutoff = 20
        sort_type = PlaylistSortType(self.sort_combo.currentText())
        args = SimpleNamespace(
            playlist_sort_type=sort_type,
            directories=directories,
            total=-1,
            overwrite=False,
            enable_dynamic_volume=self.enable_dynamic_volume.isChecked(),
            enable_long_track_splitting=self.enable_long_track_splitting.isChecked(),
            long_track_splitting_time_cutoff_minutes=cutoff,
            check_entire_playlist=False,
            track=None,
        )
        data_callbacks = getattr(self.app_actions, "data_callbacks", self.app_actions)
        try:
            playback_config = PlaybackConfig(
                args=args,
                data_callbacks=data_callbacks,
            )
            playback_config.get_list()
        except Exception as e:
            logger.exception("Error creating playlist: %s", e)
            self.app_actions.alert(
                _("Error"),
                _("Failed to build playlist. Ensure library/data callbacks are available."),
                kind="error",
                master=self,
            )
            return
        MasterPlaylistWindow.named_playlist_configs[name] = {
            "tracks": [t.filepath for t in playback_config.list.sorted_tracks],
            "sort_type": playback_config.list.sort_type,
            "config_type": playback_config.type,
        }
        MasterPlaylistWindow.store_named_playlist_configs()
        if action == "start" and self.current_master_window:
            self.current_master_window.set_playlist(playback_config)
        elif action == "add_current" and self.current_master_window:
            self.current_master_window.add_playlist(playback_config)
        elif action == "new_master":
            MasterPlaylistWindow(self.app_actions.get_master(), self.app_actions, [playback_config])
        self.app_actions.toast(_("Playlist created successfully"))
        self.close()
