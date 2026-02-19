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
from library_data.library_data import LibraryDataSearch
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

    def __init__(self, master, app_actions, library_data=None, dimensions="860x780"):
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
        edit_pl_btn = QPushButton(_("Edit"), self)
        edit_pl_btn.clicked.connect(self._edit_playlist)
        avail_btns.addWidget(edit_pl_btn)
        freeze_btn = QPushButton(_("Freeze to Tracks"), self)
        freeze_btn.clicked.connect(self._freeze_to_tracks)
        avail_btns.addWidget(freeze_btn)
        del_btn = QPushButton(_("Delete"), self)
        del_btn.clicked.connect(self._delete_available)
        avail_btns.addWidget(del_btn)
        avail_btns.addStretch()
        left.addLayout(avail_btns)
        panels.addLayout(left, 1)

        # --- Centre: add/remove arrows ---
        centre = QVBoxLayout()
        centre.addSpacing(30)
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
        self._preview_list.setMaximumHeight(220)
        preview_layout.addWidget(self._preview_list)
        outer.addWidget(preview_frame)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_available(self):
        self._named_playlists = NamedPlaylistStore.load_all(cache=app_info_cache)
        self._refresh_available_list()

    def _load_existing_master(self):
        """Populate master entries from existing PlaybackStateManager config.

        Falls back to the active (currently playing) config so that the
        user can see the current playlist even in ALL_MUSIC mode.
        """
        master = PlaybackStateManager.get_master_config()
        if not master or not master.playback_configs:
            master = PlaybackStateManager.get_active_config()
        if master and hasattr(master, 'playback_configs') and master.playback_configs:
            for i, pc in enumerate(master.playback_configs):
                weight = master.weights[i] if i < len(master.weights) else 1
                self._master_entries.append({
                    "name": str(pc),
                    "named_playlist": None,
                    "playback_config": pc,
                    "weight": weight,
                    "loop": getattr(pc, 'loop', False),
                })

    # ------------------------------------------------------------------
    # List refresh helpers
    # ------------------------------------------------------------------

    def _refresh_available_list(self):
        self._avail_list.clear()
        for name, np in self._named_playlists.items():
            sort_label = np.sort_type.get_translation()
            self._avail_list.addItem(
                f"{name}  ({np.get_source_description()})  [{sort_label}]"
            )

    def _refresh_master_list(self):
        self._master_list.blockSignals(True)
        self._master_list.clear()
        for entry in self._master_entries:
            loop_label = _("yes") if entry["loop"] else _("no")
            pc = entry.get("playback_config")
            sort_label = ""
            count_label = ""
            if pc:
                sort_label = pc.type.get_translation()
                try:
                    count_label = str(pc.get_list().size())
                except Exception:
                    count_label = "?"
            meta = f"{sort_label}, {count_label} tracks" if sort_label else ""
            self._master_list.addItem(
                f"{entry['name']}  [w:{entry['weight']}  loop:{loop_label}]"
                + (f"  ({meta})" if meta else "")
            )
        self._master_list.blockSignals(False)
        self._update_preview()

    # ------------------------------------------------------------------
    # Available panel actions
    # ------------------------------------------------------------------

    def _open_new_playlist(self):
        PlaylistModifyWindow(self, self.app_actions, self.library_data,
                             on_save=self._on_playlist_saved)

    def _edit_playlist(self):
        row = self._avail_list.currentRow()
        if row < 0:
            return
        name = list(self._named_playlists.keys())[row]
        np = self._named_playlists[name]
        PlaylistModifyWindow(self, self.app_actions, self.library_data,
                             on_save=self._on_playlist_saved, editing=np)

    def _on_playlist_saved(self):
        """Callback from PlaylistModifyWindow after a playlist is saved."""
        self._load_available()

    def _freeze_to_tracks(self):
        """Convert a search/directory playlist to an explicit track list."""
        row = self._avail_list.currentRow()
        if row < 0:
            return
        name = list(self._named_playlists.keys())[row]
        np = self._named_playlists[name]
        if not np.can_freeze():
            QMessageBox.information(
                self, _("Freeze to Tracks"),
                _("This playlist is already track-based.")
            )
            return
        if self.library_data is None:
            QMessageBox.critical(self, _("Error"), _("Library data not available."))
            return
        reply = QMessageBox.question(
            self, _("Freeze to Tracks"),
            _("Convert \"{0}\" to an explicit track list?\n\n"
              "This will resolve the current {1} source and replace it "
              "with a fixed list of tracks. This cannot be undone.").format(
                name, "search" if np.is_search_based() else "directory"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            count = np.freeze_to_tracks(self.library_data)
            NamedPlaylistStore.save(np, cache=app_info_cache)
            self._load_available()
            QMessageBox.information(
                self, _("Freeze to Tracks"),
                _("Playlist \"{0}\" frozen to {1} tracks.").format(name, count)
            )
        except Exception as e:
            logger.error(f"Failed to freeze playlist '{name}': {e}")
            QMessageBox.critical(self, _("Error"), str(e))

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

    def _get_entry_tracks(self, entry):
        """Return a list of track display strings from a master entry's playlist."""
        pc = entry.get("playback_config")
        if pc is None:
            return []
        try:
            playlist = pc.get_list()
        except Exception:
            return []
        tracks = getattr(playlist, 'sorted_tracks', None)
        if not tracks:
            return []
        result = []
        for t in tracks:
            title = getattr(t, 'title', None)
            artist = getattr(t, 'artist', None)
            if not title:
                fp = getattr(t, 'filepath', '')
                title = os.path.basename(fp) if fp else '?'
            result.append(f"{title} - {artist}" if artist else title)
        return result

    def _update_preview(self, max_tracks: int = 15):
        """Show the first N tracks in weighted round-robin order.

        When the underlying playlists have resolved track lists, actual
        track titles are shown.  Otherwise, falls back to playlist names.
        """
        self._preview_list.clear()
        if not self._master_entries:
            return

        names = [e["name"] for e in self._master_entries]
        weights = [e["weight"] for e in self._master_entries]
        entry_tracks = [self._get_entry_tracks(e) for e in self._master_entries]
        has_tracks = any(len(t) > 0 for t in entry_tracks)

        preview_items = []
        track_cursors = [0] * len(names)
        rr_cursor = 0
        rr_counter = 0

        for _ in range(max_tracks):
            for _attempt in range(len(names)):
                if rr_counter >= weights[rr_cursor]:
                    rr_cursor = (rr_cursor + 1) % len(names)
                    rr_counter = 0
                break

            if has_tracks:
                tracks = entry_tracks[rr_cursor]
                idx = track_cursors[rr_cursor]
                if tracks and idx < len(tracks):
                    label = names[rr_cursor] if len(names) > 1 else ""
                    prefix = f"[{label}] " if label else ""
                    preview_items.append(f"{prefix}{tracks[idx]}")
                    track_cursors[rr_cursor] += 1
                else:
                    preview_items.append(f"[{names[rr_cursor]}] —")
            else:
                preview_items.append(names[rr_cursor])

            rr_counter += 1
            if rr_counter >= weights[rr_cursor]:
                rr_cursor = (rr_cursor + 1) % len(names)
                rr_counter = 0

        for i, item in enumerate(preview_items):
            self._preview_list.addItem(f"  {i + 1}. {item}")

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


class PlaylistModifyWindow(SmartWindow):
    """Window for creating or editing a NamedPlaylist.

    Supports three source modes:
    - Search Query: enter search fields (re-resolved at play time).
    - Directory: pick from configured library directories.
    - Explicit Tracks: add individual tracks via search, reorder manually.

    Pass *editing* (a ``NamedPlaylist`` instance) to open in edit mode,
    pre-populating all fields from the existing playlist.
    """

    def __init__(self, parent, app_actions, library_data=None, on_save=None,
                 dimensions="600x560", editing=None):
        self._editing = editing
        title = _("Edit Playlist") if editing else _("New Playlist")
        super().__init__(
            persistent_parent=parent,
            position_parent=parent,
            title=title,
            geometry=dimensions,
            offset_x=50,
            offset_y=50,
        )
        self.app_actions = app_actions
        self.library_data = library_data
        self._on_save = on_save

        self._track_filepaths = list(editing.track_filepaths) if editing and editing.track_filepaths else []
        self._search_entries = {}
        self._dir_combo = None
        self._dir_map = {}

        self.setStyleSheet(AppStyle.get_stylesheet())
        self._build_ui()
        if editing:
            self._populate_from(editing)
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
        self._rb_search = QRadioButton(_("Search Query"), self)
        self._rb_directory = QRadioButton(_("Directory"), self)
        self._rb_tracks = QRadioButton(_("Explicit Tracks"), self)
        self._rb_search.setChecked(True)
        self._mode_group.addButton(self._rb_search, 0)
        self._mode_group.addButton(self._rb_directory, 1)
        self._mode_group.addButton(self._rb_tracks, 2)
        mode_layout.addWidget(self._rb_search)
        mode_layout.addWidget(self._rb_directory)
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
        self._sort_combo.addItems(PlaylistSortType.get_translated_names())
        self._sort_combo.setCurrentText(PlaylistSortType.SEQUENCE.get_translation())
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

    def _populate_from(self, np: 'NamedPlaylist'):
        """Pre-populate all fields from an existing NamedPlaylist for editing."""
        self._name_edit.setText(np.name)
        self._sort_combo.setCurrentText(np.sort_type.get_translation())
        self._loop_check.setChecked(np.loop)
        self._desc_edit.setText(np.description or "")

        if np.is_search_based():
            self._rb_search.setChecked(True)
            self._on_mode_change(0)
            for field, entry in self._search_entries.items():
                val = np.search_query.get(field, "")
                entry.setText(val if val else "")
        elif np.is_directory_based():
            self._rb_directory.setChecked(True)
            self._on_mode_change(1)
            if self._dir_combo and np.source_directories:
                for label, path in self._dir_map.items():
                    if path == np.source_directories[0]:
                        self._dir_combo.setCurrentText(label)
                        break
        elif np.is_track_based():
            self._rb_tracks.setChecked(True)
            self._on_mode_change(2)
            self._refresh_tracks_list()

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
            self._build_search_panel()
        elif mode_id == 1:
            self._build_directory_panel()
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
        row = 0

        # Stored searches dropdown
        layout.addWidget(QLabel(_("Load Stored Search"), self), row, 0)
        self._stored_search_combo = QComboBox(self)
        self._stored_search_combo.addItem("")
        self._stored_searches = self._get_stored_searches()
        for label, _search in self._stored_searches:
            self._stored_search_combo.addItem(label)
        self._stored_search_combo.currentIndexChanged.connect(
            self._on_stored_search_selected
        )
        layout.addWidget(self._stored_search_combo, row, 1)
        row += 1

        self._search_entries = {}
        fields = ["all", "title", "album", "artist", "composer",
                  "genre", "instrument", "form"]
        for field in fields:
            layout.addWidget(QLabel(_(field.capitalize()), self), row, 0)
            entry = QLineEdit(self)
            entry.setMinimumWidth(200)
            layout.addWidget(entry, row, 1)
            self._search_entries[field] = entry
            row += 1
        self._source_layout.addWidget(container)
        self._source_layout.addStretch()

    def _get_stored_searches(self) -> list[tuple[str, LibraryDataSearch]]:
        """Return list of (display_label, LibraryDataSearch) from recent searches."""
        from ui_qt.search_window import SearchWindow
        results = []
        for search in SearchWindow.recent_searches:
            label = str(search)
            count = search.get_readable_stored_results_count()
            if count:
                label = f"{label}  ({count})"
            results.append((label, search))
        return results

    def _on_stored_search_selected(self, index):
        """Populate search fields and sort type from a selected stored search."""
        if index <= 0:
            return
        _label, search = self._stored_searches[index - 1]
        assert isinstance(search, LibraryDataSearch)
        for field, entry in self._search_entries.items():
            val = getattr(search, field, "")
            entry.setText(val if val else "")
        self._sort_combo.setCurrentText(
            search.get_inferred_sort_type().get_translation()
        )

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

        editing_same_name = self._editing and self._editing.name == name
        if not editing_same_name and NamedPlaylistStore.exists(name, cache=app_info_cache):
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

        if mode_id == 0:  # search
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
        elif mode_id == 1:  # directory
            if self._dir_combo is None:
                return
            label = self._dir_combo.currentText()
            full_path = self._dir_map.get(label)
            if not full_path:
                QMessageBox.critical(self, _("Error"), _("Please select a directory."))
                return
            source_directories = [full_path]
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

        created_at = self._editing.created_at if self._editing else datetime.now().isoformat()

        if self._editing and self._editing.name != name:
            NamedPlaylistStore.delete(self._editing.name, cache=app_info_cache)

        np = NamedPlaylist(
            name=name,
            search_query=search_query,
            source_directories=source_directories,
            track_filepaths=track_filepaths,
            sort_type=sort_type,
            loop=self._loop_check.isChecked(),
            created_at=created_at,
            description=self._desc_edit.text().strip() or None,
        )
        NamedPlaylistStore.save(np, cache=app_info_cache)
        logger.info(f"Saved named playlist: {np}")

        if self._on_save:
            self._on_save()

        toast_msg = _("Playlist updated successfully") if self._editing else _("Playlist created successfully")
        self.app_actions.toast(toast_msg)
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
