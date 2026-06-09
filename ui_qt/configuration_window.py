"""
Configuration settings window (PySide6).
Port of ui/configuration_window.py; logic preserved, UI uses Qt.
"""

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QCheckBox,
    QComboBox,
    QPushButton,
    QTabWidget,
    QWidget,
    QFrame,
    QGroupBox,
    QListWidget,
    QScrollArea,
    QFileDialog,
)
from PySide6.QtCore import Qt

from lib.multi_display_qt import SmartWindow
from muse.playlist import TRACK_EXCLUSIONS_KEY, _DEFAULT_TRACK_EXCLUSIONS
from ui_qt.app_style import AppStyle
from ui_qt.auth.password_utils import require_password
from utils.app_info_cache import app_info_cache
from utils.config import config
from utils.globals import ProtectedActions
from utils.translations import I18N

_ = I18N._


class ConfigurationWindow(SmartWindow):
    """Configuration settings dialog with tabbed interface."""

    top_level = None

    def __init__(self, master, app_actions):
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("Configuration Settings"),
            geometry="1000x800",
            offset_x=50,
            offset_y=50,
        )
        ConfigurationWindow.top_level = self
        self.master = master
        self.app_actions = app_actions

        # key -> (widget, "entry" | "checkbox") for save
        self.config_vars = {}

        self.setStyleSheet(AppStyle.get_stylesheet())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self.notebook = QTabWidget(self)
        self.general_tab = QWidget(self)
        self.audio_tab = QWidget(self)
        self.api_tab = QWidget(self)
        self.tts_tab = QWidget(self)
        self.playlist_options_tab = QWidget(self)

        self.notebook.addTab(self.general_tab, _("General"))
        self.notebook.addTab(self.audio_tab, _("Audio"))
        self.notebook.addTab(self.api_tab, _("API Keys"))
        self.notebook.addTab(self.tts_tab, _("TTS Settings"))
        self.notebook.addTab(self.playlist_options_tab, _("Playlist Options"))

        self.create_general_tab()
        self.create_audio_tab()
        self.create_api_tab()
        self.create_tts_tab()
        self.create_playlist_options_tab()

        layout.addWidget(self.notebook)

        self.save_button = QPushButton(_("Save Configuration"), self)
        self.save_button.clicked.connect(self.save_config)
        layout.addWidget(self.save_button)

        self.show()

    def create_general_tab(self):
        frame = QFrame(self.general_tab)
        layout = QGridLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)

        self.add_config_entry(frame, layout, "foreground_color", _("Foreground Color"), 0)
        self.add_config_entry(frame, layout, "background_color", _("Background Color"), 1)
        self.add_config_entry(
            frame, layout, "muse_language_learning_language", _("Language Learning Language"), 2
        )
        self.add_config_entry(
            frame, layout, "muse_language_learning_language_level", _("Language Learning Level"), 3
        )
        self.add_config_checkbox(frame, layout, "enable_dynamic_volume", _("Enable Dynamic Volume"), 4)
        self.add_config_checkbox(frame, layout, "enable_library_extender", _("Enable Library Extender"), 5)
        self.add_config_checkbox(frame, layout, "auto_file_extensions", _("Auto-File Extensions"), 6)
        self.add_config_checkbox(frame, layout, "embed_extension_artwork", _("Embed Artwork for Extensions"), 6)
        self.add_config_checkbox(frame, layout, "enable_long_track_splitting", _("Enable Long Track Splitting"), 6)
        self.add_config_entry(
            frame, layout, "long_track_splitting_time_cutoff_minutes", _("Long Track Cutoff (minutes)"), 7
        )

        tab_layout = QVBoxLayout(self.general_tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(frame)

    def create_audio_tab(self):
        frame = QFrame(self.audio_tab)
        layout = QGridLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)

        self.add_config_checkbox(
            frame, layout, "play_videos_in_separate_window", _("Play Videos in Separate Window"), 0
        )
        self.add_config_entry(
            frame, layout, "playlist_recently_played_check_count", _("Recently Played Check Count"), 1
        )
        self.add_config_entry(frame, layout, "max_search_results", _("Max Search Results"), 2)
        self.add_config_entry(frame, layout, "max_recent_searches", _("Max Recent Searches"), 3)

        tab_layout = QVBoxLayout(self.audio_tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(frame)

    def create_api_tab(self):
        frame = QFrame(self.api_tab)
        layout = QGridLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)

        self.add_config_entry(frame, layout, "open_weather_api_key", _("OpenWeather API Key"), 0)
        self.add_config_entry(frame, layout, "open_weather_city", _("OpenWeather City"), 1)
        self.add_config_entry(frame, layout, "news_api_key", _("News API Key"), 2)

        tab_layout = QVBoxLayout(self.api_tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(frame)

    def create_tts_tab(self):
        scroll = QScrollArea(self.tts_tab)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # ── Common fields ─────────────────────────────────────────────
        common_frame = QFrame(content)
        common_layout = QGridLayout(common_frame)
        common_layout.setContentsMargins(0, 0, 0, 0)

        # Provider combo
        common_layout.addWidget(
            QLabel(_("TTS Provider:"), common_frame), 0, 0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        self._provider_combo = QComboBox(common_frame)
        for value in ("coqui", "kokoro", "f5tts", "maskgct", "piper", "zonos"):
            self._provider_combo.addItem(value)
        current = getattr(config, "tts_provider", "coqui") or "coqui"
        self._provider_combo.setCurrentText(current)
        self._provider_combo.currentTextChanged.connect(self._on_tts_provider_changed)
        common_layout.addWidget(self._provider_combo, 0, 1, Qt.AlignmentFlag.AlignLeft)
        self.config_vars["tts_provider"] = (self._provider_combo, "combo")

        self.add_config_entry(common_frame, common_layout, "llm_model_name", _("LLM Model Name"), 1)
        self.add_config_checkbox(
            common_frame, common_layout,
            "llm_use_streaming", _("Stream LLM responses (Ollama NDJSON)"), 2,
        )
        self.add_config_checkbox(
            common_frame, common_layout,
            "llm_stream_redundancy",
            _("Stop LLM on repetitive output (streaming redundancy)"), 3,
        )
        self.add_config_entry(common_frame, common_layout, "max_chunk_tokens", _("Max Chunk Tokens"), 4)
        main_layout.addWidget(common_frame)

        # ── Coqui section ─────────────────────────────────────────────
        self._coqui_section = QGroupBox(_("Coqui TTS"), content)
        coqui_layout = QGridLayout(self._coqui_section)
        self.add_config_entry(
            self._coqui_section, coqui_layout,
            "coqui_tts_location", _("TTS Library Path"), 0,
        )
        main_layout.addWidget(self._coqui_section)

        # ── Kokoro section ────────────────────────────────────────────
        self._kokoro_section = QGroupBox(_("Kokoro TTS"), content)
        kokoro_layout = QGridLayout(self._kokoro_section)

        kokoro_layout.addWidget(
            QLabel(_("Voice:"), self._kokoro_section), 0, 0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        self._kokoro_voice_combo = QComboBox(self._kokoro_section)
        try:
            from tts.providers.kokoro import KOKORO_VOICES
            self._kokoro_voice_combo.addItems(KOKORO_VOICES)
        except Exception:
            self._kokoro_voice_combo.addItem("af_heart")
        saved_voice = getattr(config, "kokoro_voice", "af_heart") or "af_heart"
        idx = self._kokoro_voice_combo.findText(saved_voice)
        self._kokoro_voice_combo.setCurrentIndex(max(idx, 0))
        kokoro_layout.addWidget(self._kokoro_voice_combo, 0, 1, Qt.AlignmentFlag.AlignLeft)
        self.config_vars["kokoro_voice"] = (self._kokoro_voice_combo, "combo")

        self.add_config_entry(
            self._kokoro_section, kokoro_layout,
            "kokoro_model", _("Model"), 1,
        )
        main_layout.addWidget(self._kokoro_section)

        # ── F5-TTS section ────────────────────────────────────────────
        self._f5tts_section = QGroupBox(_("F5-TTS"), content)
        f5_layout = QGridLayout(self._f5tts_section)
        self.add_config_filepath_entry(
            self._f5tts_section, f5_layout,
            "f5tts_reference_audio", _("Reference Audio (.wav)"), 0,
            _("Audio files") + " (*.wav *.mp3 *.flac)",
        )
        self.add_config_entry(
            self._f5tts_section, f5_layout,
            "f5tts_reference_text", _("Reference Text (optional)"), 1,
        )
        self.add_config_entry(
            self._f5tts_section, f5_layout,
            "f5tts_model", _("Model"), 2,
        )
        main_layout.addWidget(self._f5tts_section)

        # ── MaskGCT section ───────────────────────────────────────────
        self._maskgct_section = QGroupBox(_("MaskGCT / Amphion"), content)
        mgct_layout = QGridLayout(self._maskgct_section)
        self.add_config_filepath_entry(
            self._maskgct_section, mgct_layout,
            "maskgct_reference_audio", _("Reference Audio (.wav)"), 0,
            _("Audio files") + " (*.wav *.mp3 *.flac)",
        )
        self.add_config_entry(
            self._maskgct_section, mgct_layout,
            "maskgct_language", _("Language Code"), 1,
        )
        main_layout.addWidget(self._maskgct_section)

        # ── Zonos section ─────────────────────────────────────────────
        self._zonos_section = QGroupBox(_("Zonos / Zyphra"), content)
        zonos_layout = QGridLayout(self._zonos_section)
        self.add_config_filepath_entry(
            self._zonos_section, zonos_layout,
            "zonos_reference_audio", _("Reference Audio (10–30 s)"), 0,
            _("Audio files") + " (*.wav *.mp3 *.flac)",
        )
        self.add_config_entry(
            self._zonos_section, zonos_layout,
            "zonos_model", _("Model (HuggingFace ID)"), 1,
        )
        self.add_config_entry(
            self._zonos_section, zonos_layout,
            "zonos_language", _("Default Language Code"), 2,
        )
        main_layout.addWidget(self._zonos_section)

        # ── Piper section ─────────────────────────────────────────────
        self._piper_section = QGroupBox(_("Piper TTS"), content)
        piper_layout = QGridLayout(self._piper_section)
        self.add_config_filepath_entry(
            self._piper_section, piper_layout,
            "piper_model_path", _("Model Path (.onnx, optional)"), 0,
            _("ONNX models") + " (*.onnx)",
        )
        self.add_config_dirpath_entry(
            self._piper_section, piper_layout,
            "piper_voices_dir", _("Voices Cache Directory"), 1,
        )

        piper_layout.addWidget(
            QLabel(_("Quality:"), self._piper_section), 2, 0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        self._piper_quality_combo = QComboBox(self._piper_section)
        for q in ("x_low", "low", "medium", "high"):
            self._piper_quality_combo.addItem(q)
        saved_q = getattr(config, "piper_quality", "medium") or "medium"
        self._piper_quality_combo.setCurrentText(saved_q)
        piper_layout.addWidget(self._piper_quality_combo, 2, 1, Qt.AlignmentFlag.AlignLeft)
        self.config_vars["piper_quality"] = (self._piper_quality_combo, "combo")

        self.add_config_checkbox(
            self._piper_section, piper_layout,
            "piper_auto_download", _("Auto-download voice for language"), 3,
        )
        main_layout.addWidget(self._piper_section)

        main_layout.addStretch()
        scroll.setWidget(content)

        tab_layout = QVBoxLayout(self.tts_tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)

        # Apply initial visibility
        self._on_tts_provider_changed(current)

    def create_playlist_options_tab(self):
        layout = QVBoxLayout(self.playlist_options_tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        group = QGroupBox(_("Track Exclusion Filters"), self.playlist_options_tab)
        group_layout = QVBoxLayout(group)
        group_layout.setSpacing(6)

        desc = QLabel(
            _("Tracks whose file path contains any of these strings (case-insensitive) will be excluded from playlists."),
            group,
        )
        desc.setWordWrap(True)
        group_layout.addWidget(desc)

        self._exclusions_list = QListWidget(group)
        for entry in app_info_cache.get(TRACK_EXCLUSIONS_KEY, _DEFAULT_TRACK_EXCLUSIONS):
            self._exclusions_list.addItem(entry)
        group_layout.addWidget(self._exclusions_list)

        add_row = QWidget(group)
        add_layout = QHBoxLayout(add_row)
        add_layout.setContentsMargins(0, 0, 0, 0)
        self._exclusion_entry = QLineEdit(add_row)
        self._exclusion_entry.setPlaceholderText(_("New exclusion string..."))
        self._exclusion_entry.returnPressed.connect(self._add_exclusion)
        add_layout.addWidget(self._exclusion_entry)
        add_btn = QPushButton(_("Add"), add_row)
        add_btn.clicked.connect(self._add_exclusion)
        add_layout.addWidget(add_btn)
        remove_btn = QPushButton(_("Remove Selected"), add_row)
        remove_btn.clicked.connect(self._remove_exclusion)
        add_layout.addWidget(remove_btn)
        group_layout.addWidget(add_row)

        layout.addWidget(group)
        layout.addStretch()

    def _add_exclusion(self):
        text = self._exclusion_entry.text().strip()
        if not text:
            return
        existing = [self._exclusions_list.item(i).text() for i in range(self._exclusions_list.count())]
        if text not in existing:
            self._exclusions_list.addItem(text)
        self._exclusion_entry.clear()

    def _remove_exclusion(self):
        for item in self._exclusions_list.selectedItems():
            self._exclusions_list.takeItem(self._exclusions_list.row(item))

    def _on_tts_provider_changed(self, provider_value: str):
        sections = {
            "coqui":   self._coqui_section,
            "kokoro":  self._kokoro_section,
            "f5tts":   self._f5tts_section,
            "maskgct": self._maskgct_section,
            "zonos":   self._zonos_section,
            "piper":   self._piper_section,
        }
        for key, section in sections.items():
            section.setVisible(key == provider_value)

    def add_config_entry(self, parent, layout, key, label_text, row):
        label = QLabel(label_text, parent)
        layout.addWidget(label, row, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        entry = QLineEdit(parent)
        entry.setMinimumWidth(320)
        val = config.get_config_value(key)
        entry.setText(str(val) if val is not None else "")
        layout.addWidget(entry, row, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.config_vars[key] = (entry, "entry")

    def add_config_filepath_entry(self, parent, layout, key, label_text, row, file_filter=""):
        """A config entry row with an inline Browse button for file paths."""
        label = QLabel(label_text, parent)
        layout.addWidget(label, row, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        row_widget = QWidget(parent)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)

        entry = QLineEdit(row_widget)
        entry.setMinimumWidth(260)
        val = config.get_config_value(key)
        entry.setText(str(val) if val is not None else "")
        row_layout.addWidget(entry)

        browse_btn = QPushButton(_("Browse"), row_widget)
        _filter = file_filter

        def _browse():
            path, _ = QFileDialog.getOpenFileName(self, label_text, "", _filter)
            if path:
                entry.setText(path)

        browse_btn.clicked.connect(_browse)
        row_layout.addWidget(browse_btn)

        layout.addWidget(row_widget, row, 1, Qt.AlignmentFlag.AlignLeft)
        self.config_vars[key] = (entry, "entry")

    def add_config_dirpath_entry(self, parent, layout, key, label_text, row):
        """A config entry row with an inline Browse button for directory paths."""
        label = QLabel(label_text, parent)
        layout.addWidget(label, row, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        row_widget = QWidget(parent)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)

        entry = QLineEdit(row_widget)
        entry.setMinimumWidth(260)
        val = config.get_config_value(key)
        entry.setText(str(val) if val is not None else "")
        row_layout.addWidget(entry)

        browse_btn = QPushButton(_("Browse"), row_widget)

        def _browse():
            path = QFileDialog.getExistingDirectory(self, label_text)
            if path:
                entry.setText(path)

        browse_btn.clicked.connect(_browse)
        row_layout.addWidget(browse_btn)

        layout.addWidget(row_widget, row, 1, Qt.AlignmentFlag.AlignLeft)
        self.config_vars[key] = (entry, "entry")

    def add_config_checkbox(self, parent, layout, key, label_text, row):
        checkbox = QCheckBox(label_text, parent)
        val = config.get_config_value(key)
        checkbox.setChecked(bool(val))
        layout.addWidget(checkbox, row, 0, 1, 2, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.config_vars[key] = (checkbox, "checkbox")

    def confirm_close(self):
        if config.has_changes():
            res = self.app_actions.alert(
                _("Close Configuration"),
                _("Do you want to close the configuration window?\nAny unsaved changes will be lost."),
                kind="askokcancel",
                master=self,
            )
            if res:
                self.on_closing()
        else:
            self.on_closing()

    def closeEvent(self, event):
        if config.has_changes():
            res = self.app_actions.alert(
                _("Close Configuration"),
                _("Do you want to close the configuration window?\nAny unsaved changes will be lost."),
                kind="askokcancel",
                master=self,
            )
            if not res:
                event.ignore()
                return
        self.master = None
        if ConfigurationWindow.top_level is self:
            ConfigurationWindow.top_level = None
        event.accept()

    @require_password(ProtectedActions.EDIT_CONFIGURATION)
    def save_config(self):
        try:
            for key, (widget, kind) in self.config_vars.items():
                if kind == "checkbox":
                    config.set_config_value(key, widget.isChecked())
                elif kind == "combo":
                    config.set_config_value(key, widget.currentText())
                else:
                    config.set_config_value(key, widget.text())

            exclusions = [
                self._exclusions_list.item(i).text()
                for i in range(self._exclusions_list.count())
            ]
            app_info_cache.set(TRACK_EXCLUSIONS_KEY, exclusions)

            if config.save_config():
                self.app_actions.toast(_("Configuration saved successfully"))
            else:
                self.app_actions.alert(
                    _("Error"), _("Failed to save configuration"), kind="error", master=self
                )
        except Exception as e:
            self.app_actions.alert(_("Error"), str(e), kind="error", master=self)

    def on_closing(self):
        self.master = None
        self.close()
