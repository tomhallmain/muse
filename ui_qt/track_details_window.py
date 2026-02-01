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
    QWidget,
)
from PySide6.QtCore import Qt

from lib.multi_display_qt import SmartWindow
from extensions.open_weather import OpenWeatherAPI
from ui_qt.app_style import AppStyle
from utils.translations import I18N

_ = I18N._


class TrackDetailsWindow(SmartWindow):
    """Window to display and edit track metadata."""

    AUDIO_TRACK = None
    COL_0_WIDTH = 150
    top_level = None

    def __init__(self, master, app_actions, audio_track, dimensions="800x800"):
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
        self.update_btn = QPushButton(_("Update"), self)
        self.update_btn.clicked.connect(self.update_track_data)
        layout.addWidget(self.update_btn, row, 0, 1, 2)
        row += 1

        self._add_label_and_entry(layout, "title", _("Title"), audio_track.title, row)
        row += 1
        self._add_label_and_entry(layout, "album", _("Album"), audio_track.album, row)
        row += 1
        self._add_label_and_entry(layout, "artist", _("Artist"), audio_track.artist, row)
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

        info_row = QHBoxLayout()
        duration = audio_track.get_track_length()
        if duration > 0:
            duration_text = f"{int(duration // 60)}:{int(duration % 60):02d}"
            info_row.addWidget(QLabel(_("Duration: ") + duration_text, form_widget))
        info_row.addWidget(QLabel(_("File: ") + os.path.basename(audio_track.filepath), form_widget))
        info_row.addStretch()
        layout.addLayout(info_row, row, 0, 1, 2)
        row += 1

        self.show()

    def _add_label_and_entry(self, layout, attr_name, label_text, initial_value, row):
        layout.addWidget(QLabel(label_text, layout.parentWidget()), row, 0)
        edit = QLineEdit(layout.parentWidget())
        edit.setText(initial_value if initial_value else "")
        layout.addWidget(edit, row, 1)
        setattr(self, attr_name + "_edit", edit)

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

    def update_track_data(self):
        track = TrackDetailsWindow.AUDIO_TRACK
        metadata = {
            "title": self.title_edit.text().strip(),
            "album": self.album_edit.text().strip(),
            "artist": self.artist_edit.text().strip(),
            "albumartist": self.albumartist_edit.text().strip(),
            "composer": self.composer_edit.text().strip(),
            "genre": self.genre_edit.text().strip(),
            "lyrics": self.lyrics_edit.toPlainText().strip(),
            "comment": self.comments_edit.toPlainText().strip(),
            "form": self.form_edit.text().strip(),
            "instrument": self.instrument_edit.text().strip(),
        }
        numeric_fields = {
            "year": self.year_edit.text().strip(),
            "tracknumber": self.tracknumber_edit.text().strip(),
            "totaltracks": self.totaltracks_edit.text().strip(),
            "discnumber": self.discnumber_edit.text().strip(),
            "totaldiscs": self.totaldiscs_edit.text().strip(),
        }
        validation_errors = []
        for field, value in numeric_fields.items():
            is_valid, result = self.validate_numeric_field(value, field)
            if not is_valid:
                validation_errors.append(result)
            else:
                metadata[field] = result
        if validation_errors:
            self.app_actions.alert(
                _("Validation Error"),
                "\n".join(validation_errors),
                kind="error",
                master=self,
            )
            return
        if track.update_metadata(metadata):
            self.app_actions.toast(_("Track details updated successfully"))
            self.setWindowTitle(_("Track Details") + " - " + (track.title or ""))
        else:
            self.app_actions.alert(
                _("Error"),
                _("Failed to update track details. Check the logs for more information."),
                kind="error",
                master=self,
            )

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if TrackDetailsWindow.top_level is self:
            TrackDetailsWindow.top_level = None
        event.accept()
