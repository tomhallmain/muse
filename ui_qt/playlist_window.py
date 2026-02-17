"""
Playlist management window (PySide6).
Port of ui/playlist_window.py; uses NamedPlaylist / NamedPlaylistStore for
persistence and PlaybackConfigMaster for interleaved playback.
"""

import os
from datetime import datetime

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
    QFrame,
    QCheckBox,
    QSpinBox,
    QRadioButton,
    QButtonGroup,
    QMessageBox,
    QInputDialog,
)
from PySide6.QtCore import Qt

from lib.multi_display_qt import SmartWindow
from muse.named_playlist import NamedPlaylist, NamedPlaylistStore
from muse.playback_config import PlaybackConfig
from muse.playback_config_master import PlaybackConfigMaster
from muse.playback_state import PlaybackStateManager
from ui_qt.app_style import AppStyle
from utils.app_info_cache_qt import app_info_cache
from utils.config import config
from utils.globals import PlaylistSortType, PlaybackMasterStrategy
from utils.logging_setup import get_logger
from utils.translations import I18N

_ = I18N._
logger = get_logger(__name__)


class MasterPlaylistWindow(SmartWindow):
    """Window for assembling a master playlist from named playlists.

    Left panel shows available NamedPlaylists (from NamedPlaylistStore).
    Right panel shows the current master playlist with per-entry weight /
    loop controls and reordering.
    Bottom shows an interspersed preview.
    """

    top_level = None

    def __init__(self, master, app_actions, library_data=None, dimensions="860x660"):
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("Playlists"),
            geometry=dimensions,
            offset_x=50,
            offset_y=50,
        )
        MasterPlaylistWindow.top_level = self
        self.master = master
        self.app_actions = app_actions
        self.library_data = library_data

        self._named_playlists = {}
        self._master_entries = []  # list of dicts: {name, named_playlist, playback_config, weight, loop}

        self.setStyleSheet(AppStyle.get_stylesheet())
        self._build_ui()
        self._load_available()
        self._load_existing_master()
        self._refresh_master_list()
        self.show()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)

        panels = QHBoxLayout()

        # --- Left panel: available playlists ---
        left = QVBoxLayout()
        left.addWidget(QLabel(_("Available Playlists"), self))
        self._avail_list = QListWidget(self)
        self._avail_list.setMinimumWidth(250)
        left.addWidget(self._avail_list, 1)

        avail_btns = QHBoxLayout()
        new_pl_btn = QPushButton(_("New Playlist"), self)
        new_pl_btn.clicked.connect(self._open_new_playlist)
        avail_btns.addWidget(new_pl_btn)
        del_btn = QPushButton(_("Delete"), self)
        del_btn.clicked.connect(self._delete_available)
        avail_btns.addWidget(del_btn)
        avail_btns.addStretch()
        left.addLayout(avail_btns)
        panels.addLayout(left, 1)

        # --- Centre: add/remove arrows ---
        centre = QVBoxLayout()
        centre.addStretch()
        add_btn = QPushButton(">>>", self)
        add_btn.clicked.connect(self._add_to_master)
        centre.addWidget(add_btn)
        rem_btn = QPushButton("<<<", self)
        rem_btn.clicked.connect(self._remove_from_master)
        centre.addWidget(rem_btn)
        centre.addStretch()
        panels.addLayout(centre)

        # --- Right panel: master playlist ---
        right = QVBoxLayout()
        right.addWidget(QLabel(_("Master Playlist"), self))
        self._master_list = QListWidget(self)
        self._master_list.setMinimumWidth(280)
        self._master_list.currentRowChanged.connect(self._on_master_select)
        right.addWidget(self._master_list, 1)

        # Per-entry controls
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel(_("Weight:"), self))
        self._weight_spin = QSpinBox(self)
        self._weight_spin.setRange(1, 99)
        self._weight_spin.setValue(1)
        self._weight_spin.valueChanged.connect(self._on_weight_change)
        ctrl.addWidget(self._weight_spin)
        self._loop_check = QCheckBox(_("Loop"), self)
        self._loop_check.stateChanged.connect(self._on_loop_change)
        ctrl.addWidget(self._loop_check)
        up_btn = QPushButton(_("Up"), self)
        up_btn.clicked.connect(self._move_up)
        ctrl.addWidget(up_btn)
        down_btn = QPushButton(_("Down"), self)
        down_btn.clicked.connect(self._move_down)
        ctrl.addWidget(down_btn)
        ctrl.addStretch()
        right.addLayout(ctrl)
        panels.addLayout(right, 1)

        outer.addLayout(panels, 1)

        # --- Bottom: preview ---
        preview_frame = QFrame(self)
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(0, 5, 0, 0)
        preview_layout.addWidget(QLabel(_("Interspersed Preview"), self))
        self._preview_list = QListWidget(self)
        self._preview_list.setMaximumHeight(120)
        preview_layout.addWidget(self._preview_list)
        outer.addWidget(preview_frame)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_available(self):
        self._named_playlists = NamedPlaylistStore.load_all(cache=app_info_cache)
        self._refresh_available_list()

    def _load_existing_master(self):
        """Populate master entries from existing PlaybackStateManager config."""
        master = PlaybackStateManager.get_master_config()
        if master and master.playback_configs:
            for i, pc in enumerate(master.playback_configs):
                weight = master.weights[i] if i < len(master.weights) else 1
                self._master_entries.append({
                    "name": str(pc),
                    "named_playlist": None,
                    "playback_config": pc,
                    "weight": weight,
                    "loop": pc.loop,
                })

    # ------------------------------------------------------------------
    # List refresh helpers
    # ------------------------------------------------------------------

    def _refresh_available_list(self):
        self._avail_list.clear()
        for name, np in self._named_playlists.items():
            self._avail_list.addItem(f"{name}  ({np.get_source_description()})")

    def _refresh_master_list(self):
        self._master_list.blockSignals(True)
        self._master_list.clear()
        for entry in self._master_entries:
            loop_label = _("yes") if entry["loop"] else _("no")
            self._master_list.addItem(
                f"{entry['name']}  [w:{entry['weight']}  loop:{loop_label}]"
            )
        self._master_list.blockSignals(False)
        self._update_preview()

    # ------------------------------------------------------------------
    # Available panel actions
    # ------------------------------------------------------------------

    def _open_new_playlist(self):
        NewPlaylistWindow(self, self.app_actions, self.library_data,
                          on_save=self._on_new_playlist_saved)

    def _on_new_playlist_saved(self):
        """Callback from NewPlaylistWindow after a playlist is saved."""
        self._load_available()

    def _delete_available(self):
        row = self._avail_list.currentRow()
        if row < 0:
            return
        name = list(self._named_playlists.keys())[row]
        reply = QMessageBox.question(
            self, _("Delete"),
            _("Delete playlist \"{0}\"?").format(name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            NamedPlaylistStore.delete(name, cache=app_info_cache)
            self._load_available()

    # ------------------------------------------------------------------
    # Master panel actions
    # ------------------------------------------------------------------

    def _add_to_master(self):
        row = self._avail_list.currentRow()
        if row < 0:
            return
        name = list(self._named_playlists.keys())[row]
        np = self._named_playlists[name]

        try:
            pc = PlaybackConfig.from_named_playlist(
                np,
                data_callbacks=self.library_data.data_callbacks if self.library_data else None,
                library_data=self.library_data,
            )
        except Exception as e:
            logger.error(f"Failed to create PlaybackConfig from '{name}': {e}")
            QMessageBox.critical(self, _("Error"), str(e))
            return

        self._master_entries.append({
            "name": name,
            "named_playlist": np,
            "playback_config": pc,
            "weight": 1,
            "loop": np.loop,
        })
        self._apply_master_change()

    def _remove_from_master(self):
        row = self._master_list.currentRow()
        if row < 0:
            return
        del self._master_entries[row]
        self._apply_master_change()

    def _on_master_select(self, row):
        if row < 0 or row >= len(self._master_entries):
            return
        entry = self._master_entries[row]
        self._weight_spin.blockSignals(True)
        self._weight_spin.setValue(entry["weight"])
        self._weight_spin.blockSignals(False)
        self._loop_check.blockSignals(True)
        self._loop_check.setChecked(entry["loop"])
        self._loop_check.blockSignals(False)

    def _on_weight_change(self, value):
        row = self._master_list.currentRow()
        if row < 0 or row >= len(self._master_entries):
            return
        self._master_entries[row]["weight"] = max(1, value)
        self._apply_master_change()

    def _on_loop_change(self, _state):
        row = self._master_list.currentRow()
        if row < 0 or row >= len(self._master_entries):
            return
        loop_val = self._loop_check.isChecked()
        self._master_entries[row]["loop"] = loop_val
        pc = self._master_entries[row].get("playback_config")
        if pc:
            pc.loop = loop_val
        self._apply_master_change()

    def _move_up(self):
        row = self._master_list.currentRow()
        if row <= 0:
            return
        self._master_entries[row], self._master_entries[row - 1] = \
            self._master_entries[row - 1], self._master_entries[row]
        self._apply_master_change()
        self._master_list.setCurrentRow(row - 1)

    def _move_down(self):
        row = self._master_list.currentRow()
        if row < 0 or row >= len(self._master_entries) - 1:
            return
        self._master_entries[row], self._master_entries[row + 1] = \
            self._master_entries[row + 1], self._master_entries[row]
        self._apply_master_change()
        self._master_list.setCurrentRow(row + 1)

    # ------------------------------------------------------------------
    # Master config rebuild + strategy activation
    # ------------------------------------------------------------------

    def _apply_master_change(self):
        """Rebuild PlaybackConfigMaster from entries, update state, refresh UI."""
        self._refresh_master_list()

        if self._master_entries:
            configs = [e["playback_config"] for e in self._master_entries]
            weights = [e["weight"] for e in self._master_entries]
            master = PlaybackConfigMaster(configs, weights)
            PlaybackStateManager.set_master_config(master)
            try:
                self.app_actions.set_playback_master_strategy(
                    PlaybackMasterStrategy.PLAYLIST_CONFIG
                )
            except (AttributeError, TypeError):
                pass
        else:
            PlaybackStateManager.clear_master_config()
            try:
                self.app_actions.set_playback_master_strategy(
                    PlaybackMasterStrategy.ALL_MUSIC
                )
            except (AttributeError, TypeError):
                pass

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def _update_preview(self, max_tracks: int = 15):
        """Show the first N track slots in weighted round-robin order."""
        self._preview_list.clear()
        if not self._master_entries:
            return

        names = [e["name"] for e in self._master_entries]
        weights = [e["weight"] for e in self._master_entries]

        preview_names = []
        cursor = 0
        counter = 0
        for _ in range(max_tracks):
            for _attempt in range(len(names)):
                if counter >= weights[cursor]:
                    cursor = (cursor + 1) % len(names)
                    counter = 0
                break
            preview_names.append(names[cursor])
            counter += 1
            if counter >= weights[cursor]:
                cursor = (cursor + 1) % len(names)
                counter = 0

        for i, n in enumerate(preview_names):
            self._preview_list.addItem(f"  {i + 1}. {n}")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        if MasterPlaylistWindow.top_level is self:
            MasterPlaylistWindow.top_level = None
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)


class NewPlaylistWindow(SmartWindow):
    """Window for creating / editing a NamedPlaylist.

    Supports three source modes:
    - Directory: pick from configured library directories.
    - Search Query: enter search fields (re-resolved at play time).
    - Explicit Tracks: add individual tracks via search, reorder manually.
    """

    def __init__(self, parent, app_actions, library_data=None, on_save=None,
                 dimensions="600x560"):
        super().__init__(
            persistent_parent=parent,
            position_parent=parent,
            title=_("New Playlist"),
            geometry=dimensions,
            offset_x=50,
            offset_y=50,
        )
        self.app_actions = app_actions
        self.library_data = library_data
        self._on_save = on_save

        self._track_filepaths = []
        self._search_entries = {}
        self._dir_combo = None
        self._dir_map = {}

        self.setStyleSheet(AppStyle.get_stylesheet())
        self._build_ui()
        self.show()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)

        form = QGridLayout()
        row = 0

        # Name
        form.addWidget(QLabel(_("Playlist Name"), self), row, 0)
        self._name_edit = QLineEdit(self)
        self._name_edit.setMinimumWidth(280)
        form.addWidget(self._name_edit, row, 1)
        row += 1

        # Source mode
        form.addWidget(QLabel(_("Source Mode"), self), row, 0)
        row += 1
        mode_frame = QWidget(self)
        mode_layout = QHBoxLayout(mode_frame)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        self._mode_group = QButtonGroup(self)
        self._rb_directory = QRadioButton(_("Directory"), self)
        self._rb_search = QRadioButton(_("Search Query"), self)
        self._rb_tracks = QRadioButton(_("Explicit Tracks"), self)
        self._rb_directory.setChecked(True)
        self._mode_group.addButton(self._rb_directory, 0)
        self._mode_group.addButton(self._rb_search, 1)
        self._mode_group.addButton(self._rb_tracks, 2)
        mode_layout.addWidget(self._rb_directory)
        mode_layout.addWidget(self._rb_search)
        mode_layout.addWidget(self._rb_tracks)
        mode_layout.addStretch()
        form.addWidget(mode_frame, row, 0, 1, 2)
        row += 1

        # Source-specific frame (swapped based on mode)
        self._source_frame = QFrame(self)
        self._source_layout = QVBoxLayout(self._source_frame)
        self._source_layout.setContentsMargins(0, 0, 0, 0)
        form.addWidget(self._source_frame, row, 0, 1, 2)
        form.setRowStretch(row, 1)
        row += 1

        # Sort type
        form.addWidget(QLabel(_("Sort Type"), self), row, 0)
        self._sort_combo = QComboBox(self)
        self._sort_combo.addItems([t.value for t in PlaylistSortType])
        self._sort_combo.setCurrentText(PlaylistSortType.SEQUENCE.value)
        form.addWidget(self._sort_combo, row, 1)
        row += 1

        # Loop
        self._loop_check = QCheckBox(_("Loop"), self)
        form.addWidget(self._loop_check, row, 0)
        row += 1

        # Description
        form.addWidget(QLabel(_("Description (optional)"), self), row, 0)
        self._desc_edit = QLineEdit(self)
        form.addWidget(self._desc_edit, row, 1)
        row += 1

        # Save button
        save_btn = QPushButton(_("Save"), self)
        save_btn.clicked.connect(self._save)
        form.addWidget(save_btn, row, 0)
        row += 1

        outer.addLayout(form)

        self._mode_group.idClicked.connect(self._on_mode_change)
        self._on_mode_change(0)

    # ------------------------------------------------------------------
    # Source-mode panels
    # ------------------------------------------------------------------

    def _clear_source_frame(self):
        while self._source_layout.count():
            item = self._source_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
            elif item.layout():
                # Recursively clear sub-layouts
                sub = item.layout()
                while sub.count():
                    sub_item = sub.takeAt(0)
                    sub_w = sub_item.widget()
                    if sub_w:
                        sub_w.setParent(None)
                        sub_w.deleteLater()

    def _on_mode_change(self, mode_id):
        self._clear_source_frame()
        if mode_id == 0:
            self._build_directory_panel()
        elif mode_id == 1:
            self._build_search_panel()
        elif mode_id == 2:
            self._build_tracks_panel()

    def _build_directory_panel(self):
        container = QWidget(self)
        layout = QGridLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(_("Directory"), self), 0, 0)
        self._dir_combo = QComboBox(self)
        all_dirs = config.get_subdirectories()
        self._dir_map = {v: k for k, v in all_dirs.items()}
        options = list(all_dirs.values()) if all_dirs else [_("(no directories)")]
        self._dir_combo.addItems(options)
        layout.addWidget(self._dir_combo, 1, 0)
        self._source_layout.addWidget(container)
        self._source_layout.addStretch()

    def _build_search_panel(self):
        container = QWidget(self)
        layout = QGridLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        self._search_entries = {}
        fields = ["all", "title", "album", "artist", "composer",
                  "genre", "instrument", "form"]
        for i, field in enumerate(fields):
            layout.addWidget(QLabel(_(field.capitalize()), self), i, 0)
            entry = QLineEdit(self)
            entry.setMinimumWidth(200)
            layout.addWidget(entry, i, 1)
            self._search_entries[field] = entry
        self._source_layout.addWidget(container)
        self._source_layout.addStretch()

    def _build_tracks_panel(self):
        self._tracks_list = QListWidget(self)
        self._tracks_list.setMinimumHeight(120)
        self._refresh_tracks_list()
        self._source_layout.addWidget(self._tracks_list, 1)

        btns = QHBoxLayout()
        add_btn = QPushButton(_("Add Track via Search"), self)
        add_btn.clicked.connect(self._add_track)
        btns.addWidget(add_btn)
        rem_btn = QPushButton(_("Remove"), self)
        rem_btn.clicked.connect(self._remove_track)
        btns.addWidget(rem_btn)
        up_btn = QPushButton(_("Up"), self)
        up_btn.clicked.connect(self._track_up)
        btns.addWidget(up_btn)
        down_btn = QPushButton(_("Down"), self)
        down_btn.clicked.connect(self._track_down)
        btns.addWidget(down_btn)
        btns.addStretch()
        self._source_layout.addLayout(btns)

    def _refresh_tracks_list(self):
        if not hasattr(self, "_tracks_list"):
            return
        self._tracks_list.clear()
        for fp in self._track_filepaths:
            self._tracks_list.addItem(os.path.basename(fp))

    def _add_track(self):
        if self.library_data is None:
            QMessageBox.critical(self, _("Error"), _("Library data not available"))
            return
        from ui_qt.search_window import SearchWindow
        from library_data.library_data import LibraryDataSearch
        search = LibraryDataSearch()
        track = SearchWindow.find_track(self.library_data, search, save_to_recent=False)
        if track and hasattr(track, "filepath"):
            self._track_filepaths.append(track.filepath)
            self._refresh_tracks_list()

    def _remove_track(self):
        row = self._tracks_list.currentRow()
        if row < 0:
            return
        del self._track_filepaths[row]
        self._refresh_tracks_list()

    def _track_up(self):
        row = self._tracks_list.currentRow()
        if row <= 0:
            return
        self._track_filepaths[row], self._track_filepaths[row - 1] = \
            self._track_filepaths[row - 1], self._track_filepaths[row]
        self._refresh_tracks_list()
        self._tracks_list.setCurrentRow(row - 1)

    def _track_down(self):
        row = self._tracks_list.currentRow()
        if row < 0 or row >= len(self._track_filepaths) - 1:
            return
        self._track_filepaths[row], self._track_filepaths[row + 1] = \
            self._track_filepaths[row + 1], self._track_filepaths[row]
        self._refresh_tracks_list()
        self._tracks_list.setCurrentRow(row + 1)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _save(self):
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.critical(self, _("Error"), _("Please enter a playlist name."))
            return

        if NamedPlaylistStore.exists(name, cache=app_info_cache):
            reply = QMessageBox.question(
                self, _("Overwrite"),
                _("A playlist named \"{0}\" already exists. Overwrite?").format(name),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        mode_id = self._mode_group.checkedId()
        search_query = None
        source_directories = None
        track_filepaths = None

        if mode_id == 0:  # directory
            if self._dir_combo is None:
                return
            label = self._dir_combo.currentText()
            full_path = self._dir_map.get(label)
            if not full_path:
                QMessageBox.critical(self, _("Error"), _("Please select a directory."))
                return
            source_directories = [full_path]
        elif mode_id == 1:  # search
            query = {}
            for field, entry in self._search_entries.items():
                val = entry.text().strip()
                if val:
                    query[field] = val
            if not query:
                QMessageBox.critical(
                    self, _("Error"),
                    _("Please fill in at least one search field.")
                )
                return
            search_query = query
        elif mode_id == 2:  # explicit tracks
            if not self._track_filepaths:
                QMessageBox.critical(
                    self, _("Error"),
                    _("Please add at least one track.")
                )
                return
            track_filepaths = list(self._track_filepaths)

        sort_type_str = self._sort_combo.currentText()
        sort_type = PlaylistSortType.get(sort_type_str)

        np = NamedPlaylist(
            name=name,
            search_query=search_query,
            source_directories=source_directories,
            track_filepaths=track_filepaths,
            sort_type=sort_type,
            loop=self._loop_check.isChecked(),
            created_at=datetime.now().isoformat(),
            description=self._desc_edit.text().strip() or None,
        )
        NamedPlaylistStore.save(np, cache=app_info_cache)
        logger.info(f"Saved named playlist: {np}")

        if self._on_save:
            self._on_save()

        self.app_actions.toast(_("Playlist created successfully"))
        self.close()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)
