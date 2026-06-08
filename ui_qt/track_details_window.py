"""
Track details window (PySide6).
Port of ui/track_details_window.py; logic preserved, UI uses Qt.
"""

import os

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QGroupBox,
    QCheckBox,
    QMessageBox,
    QWidget,
)
from PySide6.QtCore import Qt

from lib.multi_display_qt import SmartWindow
from extensions.open_weather import OpenWeatherAPI
from ui_qt.app_style import AppStyle
from utils.track_path_preview import DirAction, TrackActionKey
from utils.translations import I18N

_ = I18N._


class TrackDetailsWindow(SmartWindow):
    """Window to display and edit track metadata."""

    AUDIO_TRACK = None
    COL_0_WIDTH = 150
    top_level = None

    def __init__(self, master, app_actions, audio_track, dimensions="800x900"):
        title = _("Track Details") + " - " + (audio_track.title or _("Track Details"))
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=title,
            geometry=dimensions,
            offset_x=50,
            offset_y=50,
        )
        TrackDetailsWindow.top_level = self
        TrackDetailsWindow.AUDIO_TRACK = audio_track
        self.master = master
        self.app_actions = app_actions
        self.open_weather_api = OpenWeatherAPI()

        self.setStyleSheet(AppStyle.get_stylesheet())
        outer = QVBoxLayout(self)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        form_widget = QWidget(scroll)
        layout = QGridLayout(form_widget)
        scroll.setWidget(form_widget)
        outer.addWidget(scroll)

        row = 0

        # ── Update button ─────────────────────────────────────────────
        self.update_btn = QPushButton(_("Update"), self)
        self.update_btn.clicked.connect(self._open_confirmation)
        layout.addWidget(self.update_btn, row, 0, 1, 2)
        row += 1

        # ── Live filepath preview ─────────────────────────────────────
        layout.addWidget(QLabel(_("Current path:"), form_widget), row, 0)
        self._current_path_label = QLabel(audio_track.filepath, form_widget)
        self._current_path_label.setWordWrap(True)
        self._current_path_label.setStyleSheet("color: grey; font-size: 10px;")
        layout.addWidget(self._current_path_label, row, 1)
        row += 1

        layout.addWidget(QLabel(_("Proposed path:"), form_widget), row, 0)
        self._proposed_path_label = QLabel(audio_track.filepath, form_widget)
        self._proposed_path_label.setWordWrap(True)
        self._proposed_path_label.setStyleSheet("color: grey; font-size: 10px;")
        layout.addWidget(self._proposed_path_label, row, 1)
        row += 1

        # ── Editable metadata fields ──────────────────────────────────
        self._add_label_and_entry(layout, "title", _("Title"), audio_track.title, row)
        self.title_edit.textChanged.connect(self._update_filepath_preview)
        row += 1

        self._add_label_and_entry(layout, "album", _("Album"), audio_track.album, row)
        self.album_edit.textChanged.connect(self._update_filepath_preview)
        row += 1

        self._add_label_and_entry(layout, "artist", _("Artist"), audio_track.artist, row)
        self.artist_edit.textChanged.connect(self._update_filepath_preview)
        row += 1

        self._add_label_and_entry(layout, "albumartist", _("Album Artist"), audio_track.albumartist, row)
        row += 1
        self._add_label_and_entry(layout, "composer", _("Composer"), audio_track.composer, row)
        row += 1
        self._add_label_and_entry(layout, "genre", _("Genre"), audio_track.genre, row)
        row += 1
        self._add_label_and_entry(
            layout, "year", _("Year"),
            str(audio_track.year) if audio_track.year else "",
            row,
        )
        row += 1

        track_row = QHBoxLayout()
        track_row.addWidget(QLabel(_("Track Number"), form_widget))
        self.tracknumber_edit = QLineEdit(form_widget)
        self.tracknumber_edit.setMaximumWidth(60)
        self.tracknumber_edit.setText(str(audio_track.tracknumber) if audio_track.tracknumber > 0 else "")
        track_row.addWidget(self.tracknumber_edit)
        track_row.addWidget(QLabel(_("of"), form_widget))
        self.totaltracks_edit = QLineEdit(form_widget)
        self.totaltracks_edit.setMaximumWidth(60)
        self.totaltracks_edit.setText(str(audio_track.totaltracks) if audio_track.totaltracks > 0 else "")
        track_row.addWidget(self.totaltracks_edit)
        track_row.addStretch()
        layout.addLayout(track_row, row, 0, 1, 2)
        row += 1

        disc_row = QHBoxLayout()
        disc_row.addWidget(QLabel(_("Disc Number"), form_widget))
        self.discnumber_edit = QLineEdit(form_widget)
        self.discnumber_edit.setMaximumWidth(60)
        self.discnumber_edit.setText(str(audio_track.discnumber) if audio_track.discnumber > 0 else "")
        disc_row.addWidget(self.discnumber_edit)
        disc_row.addWidget(QLabel(_("of"), form_widget))
        self.totaldiscs_edit = QLineEdit(form_widget)
        self.totaldiscs_edit.setMaximumWidth(60)
        self.totaldiscs_edit.setText(str(audio_track.totaldiscs) if audio_track.totaldiscs > 0 else "")
        disc_row.addWidget(self.totaldiscs_edit)
        disc_row.addStretch()
        layout.addLayout(disc_row, row, 0, 1, 2)
        row += 1

        self._add_label_and_entry(layout, "form", _("Musical Form"), audio_track.get_form(), row)
        row += 1
        self._add_label_and_entry(layout, "instrument", _("Main Instrument"), audio_track.get_instrument(), row)
        row += 1

        layout.addWidget(QLabel(_("Lyrics"), form_widget), row, 0, Qt.AlignmentFlag.AlignTop)
        self.lyrics_edit = QPlainTextEdit(form_widget)
        self.lyrics_edit.setMinimumHeight(120)
        if hasattr(audio_track, "lyrics"):
            self.lyrics_edit.setPlainText(audio_track.lyrics or "")
        layout.addWidget(self.lyrics_edit, row, 1)
        row += 1

        layout.addWidget(QLabel(_("Comments"), form_widget), row, 0, Qt.AlignmentFlag.AlignTop)
        self.comments_edit = QPlainTextEdit(form_widget)
        self.comments_edit.setMinimumHeight(120)
        if hasattr(audio_track, "comment"):
            self.comments_edit.setPlainText(audio_track.comment or "")
        layout.addWidget(self.comments_edit, row, 1)
        row += 1

        # Duration (read-only)
        duration = audio_track.get_track_length()
        if duration > 0:
            duration_text = f"{int(duration // 60)}:{int(duration % 60):02d}"
            layout.addWidget(QLabel(_("Duration: ") + duration_text, form_widget), row, 0, 1, 2)
            row += 1

        # ── Rename track file ─────────────────────────────────────────
        rename_file_group = QGroupBox(_("Rename Track File"), form_widget)
        rfg_layout = QGridLayout(rename_file_group)

        rfg_layout.addWidget(QLabel(_("New filename:"), rename_file_group), 0, 0)
        stem_row = QHBoxLayout()
        self._rename_stem_edit = QLineEdit(rename_file_group)
        stem, ext = os.path.splitext(audio_track.basename or "")
        self._rename_stem_edit.setText(stem)
        self._rename_stem_edit.setMinimumWidth(280)
        stem_row.addWidget(self._rename_stem_edit)
        self._rename_ext_label = QLabel(ext, rename_file_group)
        self._rename_ext_label.setFixedWidth(60)
        stem_row.addWidget(self._rename_ext_label)
        rfg_layout.addLayout(stem_row, 0, 1)

        self._retain_ids_check = QCheckBox(_("Retain IDs in filename (e.g. [FLAC])"), rename_file_group)
        self._retain_ids_check.setChecked(True)
        self._retain_ids_check.toggled.connect(self._update_filepath_preview)
        rfg_layout.addWidget(self._retain_ids_check, 1, 0, 1, 2)

        btn_row_file = QHBoxLayout()
        suggest_btn = QPushButton(_("Suggest from tags"), rename_file_group)
        suggest_btn.clicked.connect(self._suggest_filename)
        btn_row_file.addWidget(suggest_btn)
        rename_file_btn = QPushButton(_("Rename Track"), rename_file_group)
        rename_file_btn.clicked.connect(self._rename_track)
        btn_row_file.addWidget(rename_file_btn)
        btn_row_file.addStretch()
        rfg_layout.addLayout(btn_row_file, 2, 0, 1, 2)

        self._file_path_label = QLabel(audio_track.filepath, rename_file_group)
        self._file_path_label.setWordWrap(True)
        self._file_path_label.setStyleSheet("color: grey; font-size: 10px;")
        rfg_layout.addWidget(self._file_path_label, 3, 0, 1, 2)

        layout.addWidget(rename_file_group, row, 0, 1, 2)
        row += 1

        # ── Rename album folder ───────────────────────────────────────
        rename_album_group = QGroupBox(_("Rename Album Folder"), form_widget)
        rag_layout = QGridLayout(rename_album_group)

        album_dir = os.path.dirname(audio_track.filepath)
        album_folder_name = os.path.basename(album_dir)
        parent_dir = os.path.dirname(album_dir)

        rag_layout.addWidget(QLabel(_("Folder name:"), rename_album_group), 0, 0)
        self._album_folder_edit = QLineEdit(rename_album_group)
        self._album_folder_edit.setText(album_folder_name)
        self._album_folder_edit.setMinimumWidth(300)
        rag_layout.addWidget(self._album_folder_edit, 0, 1)

        rename_album_btn = QPushButton(_("Rename Album Folder"), rename_album_group)
        rename_album_btn.clicked.connect(self._rename_album_folder)
        rag_layout.addWidget(rename_album_btn, 1, 0, 1, 2, Qt.AlignmentFlag.AlignLeft)

        self._album_parent_label = QLabel(_("In: ") + parent_dir, rename_album_group)
        self._album_parent_label.setWordWrap(True)
        self._album_parent_label.setStyleSheet("color: grey; font-size: 10px;")
        rag_layout.addWidget(self._album_parent_label, 2, 0, 1, 2)

        layout.addWidget(rename_album_group, row, 0, 1, 2)
        row += 1

        # ── Delete track file ─────────────────────────────────────────
        delete_group = QGroupBox(_("Delete Track File"), form_widget)
        dg_layout = QVBoxLayout(delete_group)

        delete_warning = QLabel(
            _("Permanently deletes the file from disk and removes it from all caches. "
              "This cannot be undone."),
            delete_group,
        )
        delete_warning.setWordWrap(True)
        delete_warning.setStyleSheet("color: #cc4444; font-size: 10px;")
        dg_layout.addWidget(delete_warning)

        delete_btn = QPushButton(_("Delete Track"), delete_group)
        delete_btn.setStyleSheet("QPushButton { color: #cc4444; }")
        delete_btn.clicked.connect(self._confirm_delete_track)
        dg_layout.addWidget(delete_btn)

        layout.addWidget(delete_group, row, 0, 1, 2)
        row += 1

        self.show()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _add_label_and_entry(self, layout, attr_name, label_text, initial_value, row):
        layout.addWidget(QLabel(label_text, layout.parentWidget()), row, 0)
        edit = QLineEdit(layout.parentWidget())
        edit.setText(initial_value if initial_value else "")
        layout.addWidget(edit, row, 1)
        setattr(self, attr_name + "_edit", edit)

    def _collect_metadata(self) -> tuple:
        """Return (metadata_dict, validation_errors_list)."""
        metadata = {
            "title":       self.title_edit.text().strip(),
            "album":       self.album_edit.text().strip(),
            "artist":      self.artist_edit.text().strip(),
            "albumartist": self.albumartist_edit.text().strip(),
            "composer":    self.composer_edit.text().strip(),
            "genre":       self.genre_edit.text().strip(),
            "lyrics":      self.lyrics_edit.toPlainText().strip(),
            "comment":     self.comments_edit.toPlainText().strip(),
            "form":        self.form_edit.text().strip(),
            "instrument":  self.instrument_edit.text().strip(),
        }
        numeric_fields = {
            "year":        self.year_edit.text().strip(),
            "tracknumber": self.tracknumber_edit.text().strip(),
            "totaltracks": self.totaltracks_edit.text().strip(),
            "discnumber":  self.discnumber_edit.text().strip(),
            "totaldiscs":  self.totaldiscs_edit.text().strip(),
        }
        errors = []
        for field, value in numeric_fields.items():
            ok, result = self.validate_numeric_field(value, field)
            if not ok:
                errors.append(result)
            else:
                metadata[field] = result
        return metadata, errors

    def validate_numeric_field(self, value, field_name, allow_empty=True):
        if not value and allow_empty:
            return True, None
        try:
            num = int(value)
            if field_name == "year":
                if num < 0 or num > 9999:
                    return False, _("Year must be between 0 and 9999")
            elif "number" in field_name.lower():
                if num < 0:
                    return False, _("{0} cannot be negative").format(field_name)
            return True, num
        except ValueError:
            return False, _("{0} must be a valid number").format(field_name)

    # ------------------------------------------------------------------
    # Live filepath preview
    # ------------------------------------------------------------------

    def _update_filepath_preview(self) -> None:
        """Recompute the proposed path using the same rules as the confirmation dialog.

        Assumes default directory actions (tag-only: paths stay on disk) and file
        rename when the title field differs, matching RenameConfirmationWindow defaults.
        """
        track = TrackDetailsWindow.AUDIO_TRACK
        if not track:
            return

        from library_data.media_track import MediaTrack
        from utils.track_path_preview import compute_proposed_filepath

        metadata, _ = self._collect_metadata()
        current_stem = os.path.splitext(track.basename or "")[0]
        _, id_tags = MediaTrack.extract_ids(current_stem)
        title_changed = str(metadata.get("title", "") or "") != str(track.title or "")

        proposed_path = compute_proposed_filepath(
            track,
            metadata,
            rename_track_file=title_changed,
            retain_ids=self._retain_ids_check.isChecked(),
            id_tags=id_tags,
        )
        self._proposed_path_label.setText(proposed_path)

        if proposed_path != track.filepath:
            self._proposed_path_label.setStyleSheet("color: #4a9eff; font-size: 10px;")
        else:
            self._proposed_path_label.setStyleSheet("color: grey; font-size: 10px;")

    # ------------------------------------------------------------------
    # Update flow — opens confirmation window
    # ------------------------------------------------------------------

    def _open_confirmation(self) -> None:
        metadata, errors = self._collect_metadata()
        if errors:
            self.app_actions.alert(
                _("Validation Error"), "\n".join(str(e) for e in errors),
                kind="error", master=self,
            )
            return

        from ui_qt.rename_confirmation_window import RenameConfirmationWindow
        RenameConfirmationWindow(
            self,
            self.app_actions,
            TrackDetailsWindow.AUDIO_TRACK,
            metadata,
            self._on_rename_confirmed,
        )

    def update_track_data(self):
        """Direct metadata save without opening the confirmation window.

        Called internally (e.g. before a file rename) when the confirmation
        step has already been handled or is not needed.
        """
        track = TrackDetailsWindow.AUDIO_TRACK
        metadata, errors = self._collect_metadata()
        if errors:
            self.app_actions.alert(
                _("Validation Error"), "\n".join(str(e) for e in errors),
                kind="error", master=self,
            )
            return False
        if track.update_metadata(metadata):
            self.setWindowTitle(_("Track Details") + " - " + (track.title or ""))
            return True
        return False

    def _on_rename_confirmed(self, metadata: dict, actions: dict) -> None:
        """Execute all changes chosen in the confirmation window."""
        track = TrackDetailsWindow.AUDIO_TRACK

        has_file_changes = (
            actions.get(TrackActionKey.RENAME_FILE)
            or actions.get(TrackActionKey.ARTIST_ACTION, DirAction.NONE) != DirAction.NONE
            or actions.get(TrackActionKey.ALBUM_ACTION, DirAction.NONE) != DirAction.NONE
        )
        if has_file_changes and not self._warn_if_current_track():
            return

        # 1. Save metadata tags first.
        if not track.update_metadata(metadata):
            self.app_actions.alert(
                _("Error"),
                _("Failed to update track metadata. Check the logs."),
                kind="error", master=self,
            )
            return

        # 2. Artist directory action (before album, since album is beneath artist).
        artist_action = actions.get(TrackActionKey.ARTIST_ACTION, DirAction.NONE)
        if artist_action != DirAction.NONE:
            self._execute_dir_action(
                track,
                level="artist",
                action=artist_action,
                target=actions.get(TrackActionKey.ARTIST_TARGET, ""),
                new_tag_value=metadata.get("artist", "") or track.artist or "",
            )

        # 3. Album directory action (uses track.filepath which may have moved).
        album_action = actions.get(TrackActionKey.ALBUM_ACTION, DirAction.NONE)
        if album_action != DirAction.NONE:
            self._execute_dir_action(
                track,
                level="album",
                action=album_action,
                target=actions.get(TrackActionKey.ALBUM_TARGET, ""),
                new_tag_value=metadata.get("album", "") or track.album or "",
            )

        # 4. Rename the track file to match the new title if requested.
        if actions.get(TrackActionKey.RENAME_FILE):
            from library_data.media_track import MediaTrack
            title = metadata.get("title", "") or track.title or ""
            stem = MediaTrack.sanitize_filename_stem(title)
            if actions.get(TrackActionKey.RETAIN_IDS) and track.basename:
                _, ids = MediaTrack.extract_ids(os.path.splitext(track.basename)[0])
                stem = MediaTrack.reattach_ids(stem, ids)
            if stem:
                ok, result = track.rename_file(stem)
                if not ok:
                    self.app_actions.alert(_("Rename Failed"), result, kind="error", master=self)

        self._refresh_path_ui()
        self.app_actions.toast(_("Track updated successfully"))

    def _execute_dir_action(
        self, track, level: str, action: str, target: str, new_tag_value: str
    ) -> None:
        """Perform a single directory action for the album or artist level."""
        from library_data.media_track import MediaTrack

        if level == "album":
            current_dir = os.path.dirname(track.filepath)
            parent_dir  = os.path.dirname(current_dir)
        else:  # artist
            album_dir   = os.path.dirname(track.filepath)
            current_dir = os.path.dirname(album_dir)
            parent_dir  = os.path.dirname(current_dir)

        if action == DirAction.RENAME:
            new_name = MediaTrack.sanitize_filename_stem(new_tag_value)
            if not new_name:
                return
            if level == "album":
                ok, result = track.rename_album_folder(new_name)
            else:
                ok, result = track.rename_artist_folder(new_name)
            if not ok:
                self.app_actions.alert(
                    _("Rename Failed"), result, kind="error", master=self
                )

        elif action in (DirAction.MOVE_EXIST, DirAction.MOVE_NEW):
            if not target:
                return
            if action == DirAction.MOVE_NEW:
                try:
                    os.makedirs(target, exist_ok=True)
                except OSError as exc:
                    self.app_actions.alert(
                        _("Error"), f"Could not create directory: {exc}",
                        kind="error", master=self,
                    )
                    return

            from utils.path_move import destination_occupied, move_on_disk

            new_path = os.path.join(target, track.basename)
            if destination_occupied(track.filepath, new_path):
                self.app_actions.alert(
                    _("Move Failed"),
                    _("A file named '{}' already exists in the target directory.").format(
                        track.basename
                    ),
                    kind="error", master=self,
                )
                return

            old_path = track.filepath
            try:
                new_path = move_on_disk(old_path, new_path)
            except OSError as exc:
                self.app_actions.alert(
                    _("Move Failed"), str(exc), kind="error", master=self
                )
                return

            track.filepath = new_path
            try:
                from utils.filepath_update import propagate_file_rename
                propagate_file_rename(old_path, new_path)
            except Exception as exc:
                from utils.logging_setup import get_logger
                get_logger(__name__).warning("Cache propagation failed after move: %s", exc)

    def _refresh_path_ui(self) -> None:
        """Sync all path-related labels and fields with the track's current filepath."""
        track = TrackDetailsWindow.AUDIO_TRACK
        if not track:
            return
        self._current_path_label.setText(track.filepath)
        self._proposed_path_label.setText(track.filepath)
        self._proposed_path_label.setStyleSheet("color: grey; font-size: 10px;")
        self._file_path_label.setText(track.filepath)
        stem = os.path.splitext(track.basename or "")[0]
        self._rename_stem_edit.setText(stem)
        self._rename_ext_label.setText(track.ext)
        album_dir = os.path.dirname(track.filepath)
        self._album_folder_edit.setText(os.path.basename(album_dir))
        self._album_parent_label.setText(_("In: ") + os.path.dirname(album_dir))
        self.setWindowTitle(_("Track Details") + " - " + (track.title or ""))

    # ------------------------------------------------------------------
    # Current-track guard
    # ------------------------------------------------------------------

    def _is_current_track(self) -> bool:
        """Return True if the open track is the one currently playing."""
        track = TrackDetailsWindow.AUDIO_TRACK
        if not track:
            return False
        current = None
        try:
            current = self.app_actions.get_current_track()
        except Exception:
            pass
        if current is None:
            return False
        import os
        return os.path.normpath(track.filepath) == os.path.normpath(getattr(current, "filepath", ""))

    def _warn_if_current_track(self) -> bool:
        """Show a confirmation dialog when the track is currently playing.

        Returns True if the caller should proceed, False if the user cancelled.
        """
        if not self._is_current_track():
            return True
        msg = QMessageBox(self)
        msg.setWindowTitle(_("Currently Playing"))
        msg.setText(
            _("This track is currently playing. "
              "Modifying it may interrupt playback. Proceed?")
        )
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        return msg.exec() == QMessageBox.StandardButton.Yes

    # ------------------------------------------------------------------
    # Delete track
    # ------------------------------------------------------------------

    def _confirm_delete_track(self) -> None:
        track = TrackDetailsWindow.AUDIO_TRACK
        if not track:
            return
        msg = QMessageBox(self)
        msg.setWindowTitle(_("Confirm Delete"))
        msg.setText(
            _("Permanently delete this file from disk?\n\n{0}\n\n"
              "This cannot be undone.").format(track.filepath)
        )
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        msg.setIcon(QMessageBox.Icon.Warning)
        if msg.exec() != QMessageBox.StandardButton.Yes:
            return

        ok = self.app_actions.delete_track(track.filepath)
        if ok:
            self.app_actions.toast(_("Track deleted: {}").format(track.filepath))
            self.close()

    # ------------------------------------------------------------------
    # Rename section actions
    # ------------------------------------------------------------------

    def _suggest_filename(self) -> None:
        """Fill the stem field with a name derived from current tag values.

        IDs embedded in the current filename (e.g. [FLAC]) are appended when
        the 'Retain IDs' checkbox is checked (default on).
        """
        from library_data.media_track import MediaTrack
        track = TrackDetailsWindow.AUDIO_TRACK

        title  = self.title_edit.text().strip() or track.title or ""
        artist = self.artist_edit.text().strip() or track.artist or ""
        try:
            num = int(self.tracknumber_edit.text().strip())
        except ValueError:
            num = 0

        if num > 0 and title:
            stem = f"{num:02d}. {title}"
        elif artist and title:
            stem = f"{artist} - {title}"
        elif title:
            stem = title
        else:
            return

        stem = MediaTrack.sanitize_filename_stem(stem)

        if self._retain_ids_check.isChecked() and track.basename:
            current_stem = os.path.splitext(track.basename)[0]
            _, ids = MediaTrack.extract_ids(current_stem)
            if ids:
                stem = MediaTrack.reattach_ids(stem, ids)

        self._rename_stem_edit.setText(stem)

    def _rename_track(self) -> None:
        """Save pending metadata then rename the audio file on disk."""
        track = TrackDetailsWindow.AUDIO_TRACK
        new_stem = self._rename_stem_edit.text().strip()
        if not new_stem:
            self.app_actions.alert(_("Error"), _("Filename cannot be empty."), kind="error", master=self)
            return
        if not self._warn_if_current_track():
            return

        # Flush metadata before renaming so the embedded tags are in sync.
        self.update_track_data()

        ok, result = track.rename_file(new_stem)
        if ok:
            self._refresh_path_ui()
            self.app_actions.toast(_("Track renamed to: {}").format(track.basename))
        else:
            self.app_actions.alert(_("Rename Failed"), result, kind="error", master=self)

    def _rename_album_folder(self) -> None:
        """Rename the album directory to the value in the folder field."""
        track = TrackDetailsWindow.AUDIO_TRACK
        new_name = self._album_folder_edit.text().strip()
        if not new_name:
            self.app_actions.alert(_("Error"), _("Folder name cannot be empty."), kind="error", master=self)
            return
        if not self._warn_if_current_track():
            return

        ok, result = track.rename_album_folder(new_name)
        if ok:
            self._refresh_path_ui()
            self.app_actions.toast(
                _("Album folder renamed to: {}").format(os.path.basename(result))
            )
        else:
            self.app_actions.alert(_("Rename Failed"), result, kind="error", master=self)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if TrackDetailsWindow.top_level is self:
            TrackDetailsWindow.top_level = None
        event.accept()
