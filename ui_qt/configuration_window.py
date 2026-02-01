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
    QPushButton,
    QTabWidget,
    QWidget,
    QFrame,
)
from PySide6.QtCore import Qt

from lib.multi_display_qt import SmartWindow
from ui_qt.app_style import AppStyle
from ui_qt.auth.password_utils import require_password
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

        self.notebook.addTab(self.general_tab, _("General"))
        self.notebook.addTab(self.audio_tab, _("Audio"))
        self.notebook.addTab(self.api_tab, _("API Keys"))
        self.notebook.addTab(self.tts_tab, _("TTS Settings"))

        self.create_general_tab()
        self.create_audio_tab()
        self.create_api_tab()
        self.create_tts_tab()

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
        frame = QFrame(self.tts_tab)
        layout = QGridLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)

        self.add_config_entry(frame, layout, "coqui_tts_location", _("Coqui TTS Location"), 0)
        self.add_config_entry(frame, layout, "llm_model_name", _("LLM Model Name"), 1)
        self.add_config_entry(frame, layout, "max_chunk_tokens", _("Max Chunk Tokens"), 2)

        tab_layout = QVBoxLayout(self.tts_tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(frame)

    def add_config_entry(self, parent, layout, key, label_text, row):
        label = QLabel(label_text, parent)
        layout.addWidget(label, row, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        entry = QLineEdit(parent)
        entry.setMinimumWidth(320)
        val = config.get_config_value(key)
        entry.setText(str(val) if val is not None else "")
        layout.addWidget(entry, row, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
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
                else:
                    config.set_config_value(key, widget.text())

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
