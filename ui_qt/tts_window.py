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
    QStackedWidget,
    QWidget,
)
from PySide6.QtCore import Qt, Signal

from lib.multi_display_qt import SmartWindow
from muse.voice import Voice
from tts.providers import TTSProviderType
from ui_qt.app_style import AppStyle
from utils.config import config
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._

# Display label → provider enum value
_PROVIDERS = [
    (_("Coqui"),   TTSProviderType.COQUI),
    (_("Kokoro"),  TTSProviderType.KOKORO),
    (_("F5-TTS"),  TTSProviderType.F5TTS),
    (_("MaskGCT"), TTSProviderType.MASKGCT),
    (_("Piper"),   TTSProviderType.PIPER),
]
_LABEL_TO_TYPE = {label: ptype for label, ptype in _PROVIDERS}
_TYPE_TO_LABEL = {ptype: label for label, ptype in _PROVIDERS}

# Stacked-widget page indices
_PAGE_NAMED  = 0   # QComboBox  — Coqui / Kokoro
_PAGE_FILE   = 1   # file-picker — F5-TTS / MaskGCT
_PAGE_PIPER  = 2   # .onnx path or auto — Piper


class TTSWindow(SmartWindow):
    """Window for testing text-to-speech synthesis."""

    top_level = None
    DEFAULT_TOPIC = _("Text to Speech")

    status_message = Signal(str)

    def __init__(self, master, app_actions, dimensions="800x650"):
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("Text to Speech"),
            geometry=dimensions,
            offset_x=50,
            offset_y=50,
        )
        TTSWindow.top_level = self
        self.setMinimumSize(420, 480)

        self.master = master
        self.app_actions = app_actions

        # Resolve the active provider from config
        try:
            self._provider = TTSProviderType(
                (getattr(config, "tts_provider", "coqui") or "coqui").lower()
            )
        except ValueError:
            self._provider = TTSProviderType.COQUI

        self._voice_name = self._default_voice_for(self._provider)
        self.voice = self._make_voice()

        self.status_message.connect(self._update_status)
        self.setStyleSheet(AppStyle.get_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # ── Text input ────────────────────────────────────────────────
        text_group = QGroupBox(_("Text Input"), self)
        text_layout = QVBoxLayout(text_group)
        self.text_input = QPlainTextEdit(text_group)
        self.text_input.setMinimumHeight(120)
        text_layout.addWidget(self.text_input)
        layout.addWidget(text_group)

        # ── File input ────────────────────────────────────────────────
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

        # ── Options ───────────────────────────────────────────────────
        options_group = QGroupBox(_("Options"), self)
        options_layout = QVBoxLayout(options_group)

        # Provider row
        provider_row = QHBoxLayout()
        provider_row.addWidget(QLabel(_("Provider:"), options_group))
        self.provider_combo = QComboBox(options_group)
        for label, _ in _PROVIDERS:
            self.provider_combo.addItem(label)
        current_label = _TYPE_TO_LABEL.get(self._provider, _("Coqui"))
        self.provider_combo.setCurrentText(current_label)
        self.provider_combo.currentTextChanged.connect(self._on_provider_change)
        provider_row.addWidget(self.provider_combo)
        provider_row.addStretch()
        options_layout.addLayout(provider_row)

        # Voice row — label + stacked widget
        voice_row = QHBoxLayout()
        self.voice_label = QLabel(_("Speaker:"), options_group)
        self.voice_label.setMinimumWidth(90)
        voice_row.addWidget(self.voice_label)

        self.voice_stack = QStackedWidget(options_group)

        # Page 0: named voice combo (Coqui / Kokoro)
        self.voice_combo = QComboBox()
        self.voice_stack.addWidget(self.voice_combo)

        # Page 1: file picker (F5-TTS / MaskGCT)
        file_voice_widget = QWidget()
        file_voice_layout = QHBoxLayout(file_voice_widget)
        file_voice_layout.setContentsMargins(0, 0, 0, 0)
        self.voice_file_edit = QLineEdit()
        self.voice_file_edit.setPlaceholderText(_("Path to reference audio (.wav)"))
        self.voice_file_edit.textChanged.connect(self._on_voice_file_changed)
        file_voice_layout.addWidget(self.voice_file_edit)
        browse_voice_btn = QPushButton(_("Browse"))
        browse_voice_btn.clicked.connect(self._browse_voice_file)
        file_voice_layout.addWidget(browse_voice_btn)
        self.voice_stack.addWidget(file_voice_widget)

        # Page 2: Piper path (optional override; empty = auto-download)
        piper_widget = QWidget()
        piper_layout = QHBoxLayout(piper_widget)
        piper_layout.setContentsMargins(0, 0, 0, 0)
        self.piper_path_edit = QLineEdit()
        self.piper_path_edit.setPlaceholderText(
            _("Auto (language: {lang})").format(lang=_("en"))
        )
        self.piper_path_edit.textChanged.connect(self._on_piper_path_changed)
        piper_layout.addWidget(self.piper_path_edit)
        browse_piper_btn = QPushButton(_("Browse .onnx"))
        browse_piper_btn.clicked.connect(self._browse_piper_model)
        piper_layout.addWidget(browse_piper_btn)
        self.voice_stack.addWidget(piper_widget)

        voice_row.addWidget(self.voice_stack)
        options_layout.addLayout(voice_row)

        # Split-on-lines checkbox
        self.split_check = QCheckBox(_("Split on lines"), options_group)
        options_layout.addWidget(self.split_check)

        layout.addWidget(options_group)

        # ── Action buttons ────────────────────────────────────────────
        btn_layout = QHBoxLayout()
        self.speak_text_btn = QPushButton(_("Speak Text"), self)
        self.speak_text_btn.clicked.connect(self._speak_text)
        btn_layout.addWidget(self.speak_text_btn)
        self.speak_file_btn = QPushButton(_("Speak File"), self)
        self.speak_file_btn.clicked.connect(self._speak_file)
        btn_layout.addWidget(self.speak_file_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # ── Status ────────────────────────────────────────────────────
        status_group = QGroupBox(_("Status"), self)
        status_layout = QVBoxLayout(status_group)
        self.status_text = QPlainTextEdit(status_group)
        self.status_text.setReadOnly(True)
        self.status_text.setMinimumHeight(80)
        status_layout.addWidget(self.status_text)
        layout.addWidget(status_group)

        # Populate the voice area for the initial provider
        self._refresh_voice_area()
        self.show()

    # ------------------------------------------------------------------
    # Provider / voice helpers
    # ------------------------------------------------------------------

    def _default_voice_for(self, provider: TTSProviderType) -> str:
        """Return a sensible default voice name for a given provider."""
        if provider == TTSProviderType.COQUI:
            from tts.speakers import speakers as _S
            return getattr(config, "coqui_tts_model", [None, "Royston Min"])[1] or (
                _S[0] if _S else "Royston Min"
            )
        if provider == TTSProviderType.KOKORO:
            return getattr(config, "kokoro_voice", "af_heart") or "af_heart"
        if provider == TTSProviderType.F5TTS:
            return getattr(config, "f5tts_reference_audio", "") or ""
        if provider == TTSProviderType.MASKGCT:
            return getattr(config, "maskgct_reference_audio", "") or ""
        if provider == TTSProviderType.PIPER:
            return getattr(config, "piper_model_path", "") or ""
        return ""

    def _refresh_voice_area(self):
        """Update the voice stack page, label and current selection."""
        p = self._provider

        if p == TTSProviderType.COQUI:
            self.voice_label.setText(_("Speaker:"))
            from tts.speakers import speakers as _S
            self.voice_combo.blockSignals(True)
            self.voice_combo.clear()
            self.voice_combo.addItems(_S)
            idx = self.voice_combo.findText(self._voice_name)
            self.voice_combo.setCurrentIndex(max(idx, 0))
            self.voice_combo.blockSignals(False)
            self.voice_combo.currentTextChanged.connect(self._on_named_voice_change)
            self.voice_stack.setCurrentIndex(_PAGE_NAMED)

        elif p == TTSProviderType.KOKORO:
            self.voice_label.setText(_("Voice:"))
            from tts.providers.kokoro import KOKORO_VOICES
            self.voice_combo.blockSignals(True)
            self.voice_combo.clear()
            self.voice_combo.addItems(KOKORO_VOICES)
            idx = self.voice_combo.findText(self._voice_name)
            self.voice_combo.setCurrentIndex(max(idx, 0))
            self.voice_combo.blockSignals(False)
            self.voice_combo.currentTextChanged.connect(self._on_named_voice_change)
            self.voice_stack.setCurrentIndex(_PAGE_NAMED)

        elif p in (TTSProviderType.F5TTS, TTSProviderType.MASKGCT):
            label = _("Ref. audio (F5-TTS):") if p == TTSProviderType.F5TTS \
                else _("Ref. audio (MaskGCT):")
            self.voice_label.setText(label)
            self.voice_file_edit.setText(self._voice_name or "")
            self.voice_stack.setCurrentIndex(_PAGE_FILE)

        elif p == TTSProviderType.PIPER:
            self.voice_label.setText(_("Model (.onnx):"))
            self.piper_path_edit.setText(self._voice_name or "")
            self.voice_stack.setCurrentIndex(_PAGE_PIPER)

    def _make_voice(self) -> Voice:
        return Voice(voice_name=self._voice_name)

    def _save_provider_and_voice(self):
        """Persist the current provider and voice selection to config.json."""
        config.set_config_value("tts_provider", self._provider.value)

        # Write the voice into whichever config key owns it for the active provider.
        if self._provider == TTSProviderType.COQUI and self._voice_name:
            current = list(
                getattr(config, "coqui_tts_model",
                        ["tts_models/multilingual/multi-dataset/xtts_v2",
                         self._voice_name, "en"])
            )
            if len(current) >= 2:
                current[1] = self._voice_name
            config.set_config_value("coqui_tts_model", current)
        elif self._provider == TTSProviderType.KOKORO:
            config.set_config_value("kokoro_voice", self._voice_name)
        elif self._provider == TTSProviderType.F5TTS:
            config.set_config_value("f5tts_reference_audio", self._voice_name)
        elif self._provider == TTSProviderType.MASKGCT:
            config.set_config_value("maskgct_reference_audio", self._voice_name)
        elif self._provider == TTSProviderType.PIPER:
            config.set_config_value("piper_model_path", self._voice_name)

        if config.save_config():
            self.status_message.emit(
                _("Provider saved: {provider}, voice: {voice}").format(
                    provider=self._provider.value,
                    voice=self._voice_name or _("(auto)"),
                )
            )
        else:
            self.status_message.emit(_("Warning: could not save configuration"))

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_provider_change(self, label: str):
        new_provider = _LABEL_TO_TYPE.get(label, TTSProviderType.COQUI)
        if new_provider == self._provider:
            return
        self._provider = new_provider
        self._voice_name = self._default_voice_for(new_provider)
        self._refresh_voice_area()
        self._rebuild_voice()
        self._save_provider_and_voice()

    def _on_named_voice_change(self, text: str):
        if text and text != self._voice_name:
            self._voice_name = text
            self._rebuild_voice()
            self._save_provider_and_voice()

    def _on_voice_file_changed(self, text: str):
        # Track changes; save only when browse confirms or Speak is pressed.
        self._voice_name = text.strip()

    def _on_piper_path_changed(self, text: str):
        # Track changes; save only when browse confirms or Speak is pressed.
        self._voice_name = text.strip()

    def _rebuild_voice(self):
        if self.voice:
            self.voice.finish_speaking()
        self.voice = self._make_voice()

    # ------------------------------------------------------------------
    # File browsers
    # ------------------------------------------------------------------

    def _browse_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, _("Select Text File"), "",
            _("Text files") + " (*.txt);;" + _("All files") + " (*.*)",
        )
        if filepath:
            self.file_edit.setText(filepath)

    def _browse_voice_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, _("Select Reference Audio"), "",
            _("Audio files") + " (*.wav *.mp3 *.flac);;" + _("All files") + " (*.*)",
        )
        if filepath:
            self.voice_file_edit.setText(filepath)
            self._voice_name = filepath
            self._rebuild_voice()
            self._save_provider_and_voice()

    def _browse_piper_model(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, _("Select Piper Model"), "",
            _("ONNX models") + " (*.onnx);;" + _("All files") + " (*.*)",
        )
        if filepath:
            self.piper_path_edit.setText(filepath)
            self._voice_name = filepath
            self._rebuild_voice()
            self._save_provider_and_voice()

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def _update_status(self, message: str):
        self.status_text.moveCursor(self.status_text.textCursor().End)
        self.status_text.insertPlainText(message + "\n")
        self.status_text.moveCursor(self.status_text.textCursor().End)

    # ------------------------------------------------------------------
    # Speak actions
    # ------------------------------------------------------------------

    def _speak_text(self):
        text = self.text_input.toPlainText().strip()
        if not text:
            self._update_status(_("Error: No text provided"))
            return

        # Finalise and persist voice for file-path providers in case the user
        # typed the path manually without using Browse.
        if self._provider in (TTSProviderType.F5TTS, TTSProviderType.MASKGCT):
            typed = self.voice_file_edit.text().strip()
            if typed != self._voice_name:
                self._voice_name = typed
                self._rebuild_voice()
                self._save_provider_and_voice()
        elif self._provider == TTSProviderType.PIPER:
            typed = self.piper_path_edit.text().strip()
            if typed != self._voice_name:
                self._voice_name = typed
                self._rebuild_voice()
                self._save_provider_and_voice()

        def speak_thread():
            try:
                output_path = self.voice.say(
                    text, topic=TTSWindow.DEFAULT_TOPIC, save_mp3=True
                )
                if output_path:
                    self.status_message.emit(
                        _("Generated: {}").format(output_path)
                    )
                else:
                    self.status_message.emit(_("No output file was generated"))
            except Exception as e:
                self.status_message.emit(_("Error: {}").format(str(e)))

        Utils.start_thread(speak_thread, use_asyncio=False)

    def _speak_file(self):
        filepath = self.file_edit.text().strip()
        if not filepath:
            self._update_status(_("Error: No file selected"))
            return
        if not os.path.isfile(filepath):
            self._update_status(_("Error: File not found"))
            return
        if os.path.getsize(filepath) == 0:
            self._update_status(_("Error: File is empty"))
            return

        if self._provider in (TTSProviderType.F5TTS, TTSProviderType.MASKGCT):
            typed = self.voice_file_edit.text().strip()
            if typed != self._voice_name:
                self._voice_name = typed
                self._rebuild_voice()
                self._save_provider_and_voice()
        elif self._provider == TTSProviderType.PIPER:
            typed = self.piper_path_edit.text().strip()
            if typed != self._voice_name:
                self._voice_name = typed
                self._rebuild_voice()
                self._save_provider_and_voice()

        def speak_thread():
            try:
                topic = os.path.splitext(os.path.basename(filepath))[0] or TTSWindow.DEFAULT_TOPIC
                output_path = self.voice.speak_file(
                    filepath,
                    topic=topic,
                    save_mp3=True,
                    split_on_each_line=self.split_check.isChecked(),
                )
                if output_path:
                    self.status_message.emit(_("Generated: {}").format(output_path))
                else:
                    self.status_message.emit(_("No output file was generated"))
            except Exception as e:
                self.status_message.emit(_("Error: {}").format(str(e)))

        Utils.start_thread(speak_thread, use_asyncio=False)

    def closeEvent(self, event):
        if self.voice:
            self.voice.finish_speaking()
        if TTSWindow.top_level is self:
            TTSWindow.top_level = None
        event.accept()
