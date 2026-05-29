"""
Confirmation dialog for track metadata updates.

Opens whenever the user clicks "Update" in TrackDetailsWindow.  Shows every
field that will change, a live filepath preview, optional directory-action
controls (album / artist), an ID-retention toggle, and an optional file-rename
checkbox — so the user can review, correct, or cancel before anything is written.
"""

from __future__ import annotations

import os
from typing import Callable, Dict, Any, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox,
    QRadioButton, QButtonGroup, QGroupBox,
    QScrollArea, QWidget, QFileDialog, QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette

from ui_qt.app_style import AppStyle
from utils.translations import I18N

_ = I18N._

from utils.track_path_preview import (
    DIR_ACTION_NONE as _DIR_NONE,
    DIR_ACTION_RENAME as _DIR_RENAME,
    DIR_ACTION_MOVE_EXIST as _DIR_MOVE_EXIST,
    DIR_ACTION_MOVE_NEW as _DIR_MOVE_NEW,
    compute_proposed_filepath,
)


class RenameConfirmationWindow(QDialog):
    """Modal dialog shown before every metadata update.

    Parameters
    ----------
    parent      : parent widget (TrackDetailsWindow)
    app_actions : app-level action dispatcher
    track       : the MediaTrack being edited
    metadata    : proposed metadata dict (as built by TrackDetailsWindow)
    on_confirm  : callable(metadata, actions_dict) called when Apply is clicked
    """

    def __init__(
        self,
        parent,
        app_actions,
        track,
        metadata: Dict[str, Any],
        on_confirm: Callable,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Confirm Changes"))
        self.setMinimumWidth(640)
        self.setModal(True)

        self._app_actions = app_actions
        self._track       = track
        self._metadata    = metadata
        self._on_confirm  = on_confirm

        # Extract IDs embedded in the current filename stem
        from library_data.media_track import MediaTrack
        current_stem = os.path.splitext(track.basename or "")[0]
        _, self._current_ids = MediaTrack.extract_ids(current_stem)

        self._changed = self._diff_fields()

        self.setStyleSheet(AppStyle.get_stylesheet())
        self._build_ui()

    # ------------------------------------------------------------------
    # Field diff
    # ------------------------------------------------------------------

    def _diff_fields(self) -> Dict[str, tuple]:
        """Return {field: (old_value, new_value)} for every field that changed."""
        t = self._track
        m = self._metadata
        display_map = {
            "title":       (_("Title"),        str(t.title or "")),
            "album":       (_("Album"),         str(t.album or "")),
            "artist":      (_("Artist"),        str(t.artist or "")),
            "albumartist": (_("Album Artist"),  str(t.albumartist or "")),
            "composer":    (_("Composer"),      str(t.composer or "")),
            "genre":       (_("Genre"),         str(t.genre or "")),
            "year":        (_("Year"),          str(t.year) if t.year else ""),
            "tracknumber": (_("Track #"),       str(t.tracknumber) if t.tracknumber > 0 else ""),
            "totaltracks": (_("Total Tracks"),  str(t.totaltracks) if t.totaltracks > 0 else ""),
            "discnumber":  (_("Disc #"),        str(t.discnumber) if t.discnumber > 0 else ""),
            "totaldiscs":  (_("Total Discs"),   str(t.totaldiscs) if t.totaldiscs > 0 else ""),
            "form":        (_("Musical Form"),  str(t.get_form() or "")),
            "instrument":  (_("Instrument"),    str(t.get_instrument() or "")),
            "lyrics":      (_("Lyrics"),        str(t.lyrics or "") if hasattr(t, "lyrics") else ""),
            "comment":     (_("Comment"),       str(t.comment or "") if hasattr(t, "comment") else ""),
        }
        changed = {}
        for key, (label, old_val) in display_map.items():
            new_val = str(m.get(key, "")) if m.get(key) is not None else ""
            # Numeric sentinels (-1, None) normalised to ""
            if new_val in ("-1", "None"):
                new_val = ""
            if new_val != old_val:
                changed[key] = (label, old_val, new_val)
        return changed

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        vbox = QVBoxLayout(content)
        vbox.setSpacing(10)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        # ── Changes table ─────────────────────────────────────────────
        if self._changed:
            changes_group = QGroupBox(_("Pending changes"), content)
            cg_layout = QGridLayout(changes_group)
            cg_layout.addWidget(QLabel(f"<b>{_('Field')}</b>"),    0, 0)
            cg_layout.addWidget(QLabel(f"<b>{_('Current')}</b>"),  0, 1)
            cg_layout.addWidget(QLabel(f"<b>{_('New')}</b>"),      0, 2)
            for i, (key, (label, old, new)) in enumerate(self._changed.items(), 1):
                cg_layout.addWidget(QLabel(label), i, 0)
                cg_layout.addWidget(QLabel(old or _("(empty)")), i, 1)
                new_lbl = QLabel(new or _("(empty)"))
                new_lbl.setStyleSheet("color: #4a9eff;")
                cg_layout.addWidget(new_lbl, i, 2)
            vbox.addWidget(changes_group)
        else:
            vbox.addWidget(QLabel(_("No metadata fields have changed.")))

        # ── Filepath preview ──────────────────────────────────────────
        fp_group = QGroupBox(_("Filepath preview"), content)
        fp_layout = QGridLayout(fp_group)
        fp_layout.addWidget(QLabel(_("Current:")), 0, 0)
        fp_layout.addWidget(QLabel(self._track.filepath), 0, 1)
        fp_layout.addWidget(QLabel(_("Proposed:")), 1, 0)
        self._preview_label = QLabel(self._track.filepath)
        self._preview_label.setWordWrap(True)
        fp_layout.addWidget(self._preview_label, 1, 1)
        vbox.addWidget(fp_group)

        # ── Rename track file option ──────────────────────────────────
        title_changed = "title" in self._changed
        self._rename_file_check = QCheckBox(
            _("Rename track file to match new title"), content
        )
        self._rename_file_check.setChecked(title_changed)
        self._rename_file_check.setVisible(title_changed)
        self._rename_file_check.toggled.connect(self._update_preview)

        self._retain_ids_check = QCheckBox(
            _("Retain IDs in filename (e.g. [FLAC], [2024])"), content
        )
        self._retain_ids_check.setChecked(True)
        self._retain_ids_check.setVisible(bool(self._current_ids))
        self._retain_ids_check.toggled.connect(self._update_preview)

        if title_changed:
            vbox.addWidget(self._rename_file_check)
        if self._current_ids:
            vbox.addWidget(self._retain_ids_check)

        # ── Album directory action ─────────────────────────────────────
        album_changed = "album" in self._changed
        self._album_group, self._album_btns, self._album_target_edit = \
            self._build_dir_action_group(
                content,
                _("Album directory"),
                self._metadata.get("album", "") or "",
                is_album=True,
                warn_all=False,
            )
        self._album_group.setVisible(album_changed)
        if album_changed:
            vbox.addWidget(self._album_group)

        # ── Artist directory action ────────────────────────────────────
        artist_changed = "artist" in self._changed
        self._artist_group, self._artist_btns, self._artist_target_edit = \
            self._build_dir_action_group(
                content,
                _("Artist directory"),
                self._metadata.get("artist", "") or "",
                is_album=False,
                warn_all=True,
            )
        self._artist_group.setVisible(artist_changed)
        if artist_changed:
            vbox.addWidget(self._artist_group)

        vbox.addStretch()

        # ── Buttons ───────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        apply_btn = QPushButton(_("Apply Changes"))
        apply_btn.setDefault(True)
        apply_btn.clicked.connect(self._on_apply)
        cancel_btn = QPushButton(_("Cancel"))
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(cancel_btn)
        outer.addLayout(btn_row)

        self._update_preview()

    def _build_dir_action_group(
        self,
        parent,
        title: str,
        new_tag_value: str,
        is_album: bool,
        warn_all: bool,
    ) -> tuple:
        """Build a QGroupBox with four radio options for a directory action.

        Returns (group, button_group, target_line_edit).
        """
        group = QGroupBox(title, parent)
        layout = QVBoxLayout(group)

        if warn_all:
            warn = QLabel(
                _("⚠  Renaming this directory affects every track by this artist.")
            )
            warn.setStyleSheet("color: orange;")
            layout.addWidget(warn)

        btn_group = QButtonGroup(group)

        r_none   = QRadioButton(_("Keep current directory (tag change only)"), group)
        r_rename = QRadioButton(
            _('Rename directory to match new value: "{v}"').format(v=new_tag_value), group
        )
        r_exist  = QRadioButton(_("Move this track to an existing directory"), group)
        r_new    = QRadioButton(_("Move this track to a new directory"), group)

        r_none.setChecked(True)
        for i, rb in enumerate([r_none, r_rename, r_exist, r_new]):
            btn_group.addButton(rb, i)
            layout.addWidget(rb)

        # Target path row (shown for move options)
        target_row = QHBoxLayout()
        target_edit = QLineEdit(group)
        target_edit.setPlaceholderText(_("Target directory path"))
        target_edit.textChanged.connect(self._update_preview)
        target_row.addWidget(target_edit)
        browse_btn = QPushButton(_("Browse…"), group)

        def _browse():
            d = QFileDialog.getExistingDirectory(self, title)
            if d:
                target_edit.setText(d)

        browse_btn.clicked.connect(_browse)
        target_row.addWidget(browse_btn)
        target_widget = QWidget(group)
        target_widget.setLayout(target_row)
        target_widget.setVisible(False)
        layout.addWidget(target_widget)

        # Pre-fill target with the inferred new path
        if is_album:
            album_dir    = os.path.dirname(self._track.filepath)
            artist_dir   = os.path.dirname(album_dir)
            inferred = os.path.join(artist_dir, new_tag_value)
        else:
            album_dir    = os.path.dirname(self._track.filepath)
            artist_dir   = os.path.dirname(album_dir)
            music_root   = os.path.dirname(artist_dir)
            inferred = os.path.join(music_root, new_tag_value)
        target_edit.setText(inferred)

        def _on_toggled():
            action = self._action_from_group(btn_group)
            target_widget.setVisible(action in (_DIR_MOVE_EXIST, _DIR_MOVE_NEW))
            self._update_preview()

        btn_group.buttonToggled.connect(lambda *_: _on_toggled())

        return group, btn_group, target_edit

    # ------------------------------------------------------------------
    # Live preview
    # ------------------------------------------------------------------

    @staticmethod
    def _action_from_group(btn_group: QButtonGroup) -> str:
        idx = btn_group.checkedId()
        return [_DIR_NONE, _DIR_RENAME, _DIR_MOVE_EXIST, _DIR_MOVE_NEW][idx]

    def _compute_proposed_path(self) -> str:
        artist_action = (
            self._action_from_group(self._artist_btns)
            if self._artist_group.isVisible()
            else _DIR_NONE
        )
        album_action = (
            self._action_from_group(self._album_btns)
            if self._album_group.isVisible()
            else _DIR_NONE
        )
        return compute_proposed_filepath(
            self._track,
            self._metadata,
            rename_track_file=(
                self._rename_file_check.isVisible()
                and self._rename_file_check.isChecked()
            ),
            retain_ids=(
                self._retain_ids_check.isVisible()
                and self._retain_ids_check.isChecked()
            ),
            id_tags=self._current_ids,
            artist_action=artist_action,
            album_action=album_action,
            artist_target=self._artist_target_edit.text().strip(),
            album_target=self._album_target_edit.text().strip(),
        )

    def _update_preview(self) -> None:
        proposed = self._compute_proposed_path()
        self._preview_label.setText(proposed)
        if proposed != self._track.filepath:
            self._preview_label.setStyleSheet("color: #4a9eff; font-weight: bold;")
        else:
            self._preview_label.setStyleSheet("color: grey;")

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def _on_apply(self) -> None:
        actions = {
            "rename_track_file": (
                self._rename_file_check.isVisible()
                and self._rename_file_check.isChecked()
            ),
            "retain_ids": (
                self._retain_ids_check.isVisible()
                and self._retain_ids_check.isChecked()
            ),
            "album_action":  self._action_from_group(self._album_btns)
                             if self._album_group.isVisible() else _DIR_NONE,
            "album_target":  self._album_target_edit.text().strip(),
            "artist_action": self._action_from_group(self._artist_btns)
                             if self._artist_group.isVisible() else _DIR_NONE,
            "artist_target": self._artist_target_edit.text().strip(),
        }
        self.accept()
        self._on_confirm(self._metadata, actions)
