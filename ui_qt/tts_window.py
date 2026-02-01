"""
Text-to-speech window (PySide6).
Port of ui/tts_window.py; logic preserved, UI uses Qt.
"""

import os

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QComboBox,
    QCheckBox,
    QGroupBox,
    QFileDialog,
    QWidget,
)
from PySide6.QtCore import Qt, Signal

from lib.multi_display_qt import SmartWindow
from muse.voice import Voice
from tts.speakers import speakers
from ui_qt.app_style import AppStyle
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._


class TTSWindow(SmartWindow):
    """Window for text-to-speech conversion."""

    top_level = None
    DEFAULT_TOPIC = _("Text to Speech")

    status_message = Signal(str)

    def __init__(self, master, app_actions, dimensions="800x600"):
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("Text to Speech"),
            geometry=dimensions,
            offset_x=50,
            offset_y=50,
        )
        TTSWindow.top_level = self
        self.setMinimumSize(400, 400)

        self.master = master
        self.app_actions = app_actions
        self.speaker = "Aaron Dreschner" if "Aaron Dreschner" in speakers else (speakers[0] if speakers else "Royston Min")
        self.voice = Voice(coqui_named_voice=self.speaker)

        self.status_message.connect(self._update_status)

        self.setStyleSheet(AppStyle.get_stylesheet())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        text_group = QGroupBox(_("Text Input"), self)
        text_layout = QVBoxLayout(text_group)
        self.text_input = QPlainTextEdit(text_group)
        self.text_input.setMinimumHeight(120)
        text_layout.addWidget(self.text_input)
        layout.addWidget(text_group)

        file_group = QGroupBox(_("File Input"), self)
        file_layout = QHBoxLayout(file_group)
        self.file_edit = QLineEdit(file_group)
        self.file_edit.setReadOnly(True)
        self.file_edit.setPlaceholderText(_("No file selected"))
        file_layout.addWidget(self.file_edit)
        self.browse_btn = QPushButton(_("Browse"), file_group)
        self.browse_btn.clicked.connect(self._browse_file)
        file_layout.addWidget(self.browse_btn)
        layout.addWidget(file_group)

        options_group = QGroupBox(_("Options"), self)
        options_layout = QHBoxLayout(options_group)
        options_layout.addWidget(QLabel(_("Speaker:"), options_group))
        self.speaker_combo = QComboBox(options_group)
        self.speaker_combo.addItems(speakers)
        self.speaker_combo.currentTextChanged.connect(self._on_speaker_change)
        idx = self.speaker_combo.findText(self.speaker)
        if idx >= 0:
            self.speaker_combo.setCurrentIndex(idx)
        options_layout.addWidget(self.speaker_combo)
        self.split_check = QCheckBox(_("Split on lines"), options_group)
        self.split_check.setChecked(False)
        options_layout.addWidget(self.split_check)
        options_layout.addStretch()
        layout.addWidget(options_group)

        btn_layout = QHBoxLayout()
        self.speak_text_btn = QPushButton(_("Speak Text"), self)
        self.speak_text_btn.clicked.connect(self._speak_text)
        btn_layout.addWidget(self.speak_text_btn)
        self.speak_file_btn = QPushButton(_("Speak File"), self)
        self.speak_file_btn.clicked.connect(self._speak_file)
        btn_layout.addWidget(self.speak_file_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        status_group = QGroupBox(_("Status"), self)
        status_layout = QVBoxLayout(status_group)
        self.status_text = QPlainTextEdit(status_group)
        self.status_text.setReadOnly(True)
        self.status_text.setMinimumHeight(100)
        status_layout.addWidget(self.status_text)
        layout.addWidget(status_group)

        self._on_speaker_change(self.speaker)
        self.show()

    def _browse_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            _("Select Text File"),
            "",
            _("Text files") + " (*.txt);;" + _("All files") + " (*.*)",
        )
        if filepath:
            self.file_edit.setText(filepath)

    def _on_speaker_change(self, text):
        if text:
            self.speaker = text
            self.voice = Voice(coqui_named_voice=self.speaker)

    def _update_status(self, message: str):
        self.status_text.moveCursor(self.status_text.textCursor().End)
        self.status_text.insertPlainText(message + "\n")
        self.status_text.moveCursor(self.status_text.textCursor().End)

    def _speak_text(self):
        text = self.text_input.toPlainText().strip()
        if not text:
            self._update_status(_("Error: No text provided"))
            return

        def speak_thread():
            try:
                output_path = self.voice.say(
                    text, topic=TTSWindow.DEFAULT_TOPIC, save_mp3=True
                )
                if output_path:
                    self.status_message.emit(
                        _("Successfully generated speech file: {}").format(output_path)
                    )
                else:
                    self.status_message.emit(_("No output file was generated"))
            except Exception as e:
                self.status_message.emit(
                    _("Error generating speech: {}").format(str(e))
                )

        Utils.start_thread(speak_thread, use_asyncio=False)

    def _speak_file(self):
        filepath = self.file_edit.text().strip()
        if not filepath:
            self._update_status(_("Error: No file selected"))
            return
        if not os.path.exists(filepath):
            self._update_status(_("Error: File does not exist"))
            return
        if not os.path.isfile(filepath):
            self._update_status(_("Error: Path is not a file"))
            return
        if os.path.getsize(filepath) == 0:
            self._update_status(_("Error: File is empty"))
            return

        def speak_thread():
            try:
                topic = os.path.splitext(os.path.basename(filepath))[0]
                if not topic or not topic.strip():
                    topic = TTSWindow.DEFAULT_TOPIC
                output_path = self.voice.speak_file(
                    filepath,
                    topic=topic,
                    save_mp3=True,
                    split_on_each_line=self.split_check.isChecked(),
                )
                if output_path:
                    self.status_message.emit(
                        _("Successfully generated speech file: {}").format(output_path)
                    )
                else:
                    self.status_message.emit(_("No output file was generated"))
            except Exception as e:
                self.status_message.emit(
                    _("Error generating speech: {}").format(str(e))
                )

        Utils.start_thread(speak_thread, use_asyncio=False)

    def closeEvent(self, event):
        if self.voice:
            self.voice.finish_speaking()
        if TTSWindow.top_level is self:
            TTSWindow.top_level = None
        event.accept()
