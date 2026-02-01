"""
DJ Personas management window (PySide6).
Port of ui/personas_window.py; logic preserved, UI uses Qt.
Styles inherit from the global stylesheet (no per-widget color/background overrides).
"""

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPlainTextEdit,
    QTabWidget,
    QWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QAbstractItemView,
)
from PySide6.QtCore import Qt

from lib.multi_display_qt import SmartWindow
from ui_qt.app_style import AppStyle
from ui_qt.auth.password_utils import require_password
from muse.dj_persona import DJPersona, DJPersonaManager
from tts.speakers import speakers
from utils.globals import ProtectedActions, PersonaSex
from utils.logging_setup import get_logger
from utils.translations import I18N, SUPPORTED_LANGUAGE_CODES
from utils.utils import Utils

_ = I18N._
logger = get_logger(__name__)


class PersonasWindow(SmartWindow):
    """Window for managing DJ personas - creating, editing, and deleting personas."""

    top_level = None

    def __init__(self, master, app_actions):
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("DJ Personas"),
            geometry="1200x800",
            offset_x=50,
            offset_y=50,
        )
        PersonasWindow.top_level = self
        self.master = master
        self.app_actions = app_actions

        from muse.muse_memory import muse_memory
        self.persona_manager = muse_memory.get_persona_manager()
        if not self.persona_manager:
            self.persona_manager = DJPersonaManager()

        self.selected_persona = None

        self.setStyleSheet(AppStyle.get_stylesheet())
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        self._create_sidebar(layout)
        self._create_content_area(layout)

        self.refresh_persona_list()
        self.set_default_persona_values()
        self.show()

    def _create_sidebar(self, main_layout):
        sidebar = QWidget(self)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title_label = QLabel(_("DJ Personas"), sidebar)
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        sidebar_layout.addWidget(title_label)

        self.persona_table = QTableWidget(sidebar)
        self.persona_table.setColumnCount(2)
        self.persona_table.setHorizontalHeaderLabels([_("Name"), _("Voice")])
        self.persona_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.persona_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.persona_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.persona_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.persona_table.selectionModel().selectionChanged.connect(
            self._on_persona_select
        )
        sidebar_layout.addWidget(self.persona_table, 1)

        button_layout = QHBoxLayout()
        self.add_btn = QPushButton(_("Add New"), sidebar)
        self.add_btn.clicked.connect(self.add_persona)
        button_layout.addWidget(self.add_btn)
        self.edit_btn = QPushButton(_("Edit"), sidebar)
        self.edit_btn.clicked.connect(self.edit_persona)
        button_layout.addWidget(self.edit_btn)
        self.delete_btn = QPushButton(_("Delete"), sidebar)
        self.delete_btn.clicked.connect(self.delete_persona)
        button_layout.addWidget(self.delete_btn)
        sidebar_layout.addLayout(button_layout)

        main_layout.addWidget(sidebar)

    def _create_content_area(self, main_layout):
        content = QWidget(self)
        content_layout = QVBoxLayout(content)

        self.notebook = QTabWidget(content)
        self.basic_tab = QWidget(self.notebook)
        self.characteristics_tab = QWidget(self.notebook)
        self.prompt_tab = QWidget(self.notebook)
        self.notebook.addTab(self.basic_tab, _("Basic Info"))
        self.notebook.addTab(self.characteristics_tab, _("Characteristics"))
        self.notebook.addTab(self.prompt_tab, _("System Prompt"))

        self._create_basic_tab()
        self._create_characteristics_tab()
        self._create_prompt_tab()
        content_layout.addWidget(self.notebook)

        action_layout = QHBoxLayout()
        self.save_btn = QPushButton(_("Save Changes"), content)
        self.save_btn.clicked.connect(self.save_persona)
        action_layout.addWidget(self.save_btn)
        self.cancel_btn = QPushButton(_("Cancel"), content)
        self.cancel_btn.clicked.connect(self.cancel_edit)
        action_layout.addWidget(self.cancel_btn)
        self.reload_btn = QPushButton(_("Reload from Config"), content)
        self.reload_btn.clicked.connect(self.reload_personas)
        action_layout.addWidget(self.reload_btn)
        content_layout.addLayout(action_layout)

        main_layout.addWidget(content, 2)

    def _create_basic_tab(self):
        layout = QGridLayout(self.basic_tab)
        row = 0
        layout.addWidget(QLabel(_("Display Name:"), self.basic_tab), row, 0)
        self.name_edit = QLineEdit(self.basic_tab)
        self.name_edit.setMinimumWidth(320)
        layout.addWidget(self.name_edit, row, 1)
        row += 1

        layout.addWidget(QLabel(_("Voice Name:"), self.basic_tab), row, 0)
        self.voice_combo = QComboBox(self.basic_tab)
        self.voice_combo.addItems(speakers)
        self.voice_combo.setMinimumWidth(320)
        layout.addWidget(self.voice_combo, row, 1)
        row += 1

        layout.addWidget(QLabel(_("Sex:"), self.basic_tab), row, 0)
        self.sex_combo = QComboBox(self.basic_tab)
        self.sex_combo.addItems(PersonaSex.get_translated_names())
        layout.addWidget(self.sex_combo, row, 1)
        row += 1

        layout.addWidget(QLabel(_("Tone:"), self.basic_tab), row, 0)
        self.tone_edit = QLineEdit(self.basic_tab)
        self.tone_edit.setMinimumWidth(320)
        layout.addWidget(self.tone_edit, row, 1)
        row += 1

        layout.addWidget(QLabel(_("Language:"), self.basic_tab), row, 0)
        self.language_edit = QLineEdit(self.basic_tab)
        self.language_edit.setMinimumWidth(320)
        layout.addWidget(self.language_edit, row, 1)
        row += 1

        layout.addWidget(QLabel(_("Language Code:"), self.basic_tab), row, 0)
        self.language_code_combo = QComboBox(self.basic_tab)
        self.language_code_combo.addItems(SUPPORTED_LANGUAGE_CODES)
        self.language_code_combo.currentTextChanged.connect(self._on_language_code_change)
        layout.addWidget(self.language_code_combo, row, 1)

    def _create_characteristics_tab(self):
        layout = QVBoxLayout(self.characteristics_tab)
        layout.addWidget(QLabel(_("Characteristics:"), self.characteristics_tab))
        self.characteristics_text = QPlainTextEdit(self.characteristics_tab)
        self.characteristics_text.setMinimumHeight(200)
        layout.addWidget(self.characteristics_text)
        instructions = QLabel(
            _("Enter one characteristic per line. These describe the persona's personality and expertise."),
            self.characteristics_tab,
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

    def _create_prompt_tab(self):
        layout = QVBoxLayout(self.prompt_tab)
        layout.addWidget(QLabel(_("System Prompt:"), self.prompt_tab))
        self.prompt_text = QPlainTextEdit(self.prompt_tab)
        self.prompt_text.setMinimumHeight(200)
        layout.addWidget(self.prompt_text)
        instructions = QLabel(
            _("Enter the system prompt that defines how this persona should behave and speak."),
            self.prompt_tab,
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

    def refresh_persona_list(self):
        self.persona_table.setRowCount(0)
        for voice_name, persona in self.persona_manager.personas.items():
            row = self.persona_table.rowCount()
            self.persona_table.insertRow(row)
            self.persona_table.setItem(row, 0, QTableWidgetItem(persona.name))
            self.persona_table.setItem(row, 1, QTableWidgetItem(voice_name))

    def _on_persona_select(self):
        row = self.persona_table.currentRow()
        if row >= 0:
            voice_item = self.persona_table.item(row, 1)
            if voice_item:
                self.load_persona(voice_item.text())

    def _on_language_code_change(self, text):
        try:
            if text:
                language_name = Utils.get_english_language_name(text)
                self.language_edit.setText(language_name)
        except Exception as e:
            logger.error("Error updating language name from code: %s", e)

    def set_default_persona_values(self):
        self.name_edit.setText(_("New Persona"))
        self.tone_edit.setText(_("friendly and engaging"))
        self.language_edit.setText(_("English"))
        idx = self.language_code_combo.findText("en")
        if idx >= 0:
            self.language_code_combo.setCurrentIndex(idx)
        idx = self.sex_combo.findText(PersonaSex.MALE.get_translation())
        if idx >= 0:
            self.sex_combo.setCurrentIndex(idx)
        default_characteristics = [
            _("music enthusiast"),
            _("knowledgeable about various genres"),
            _("engaging storyteller"),
            _("passionate about sharing music"),
        ]
        self.characteristics_text.setPlainText("\n".join(default_characteristics))
        default_prompt = _(
            """You are a knowledgeable and engaging DJ with a passion for music. Your speaking style is friendly and engaging, with a talent for connecting with your audience. You love sharing interesting facts about music, artists, and genres, and you have a gift for making every song feel special and meaningful. When discussing tracks, you often provide context about the artist, the genre, or the cultural significance of the music. Your enthusiasm is infectious, and you have a way of making listeners feel like they're discovering something wonderful together with you."""
        )
        self.prompt_text.setPlainText(default_prompt)

    def load_persona(self, voice_name):
        persona = self.persona_manager.get_persona(voice_name)
        if persona:
            self.selected_persona = persona
            self.name_edit.setText(persona.name)
            idx = self.voice_combo.findText(persona.voice_name)
            if idx >= 0:
                self.voice_combo.setCurrentIndex(idx)
            idx = self.sex_combo.findText(PersonaSex.to_translated_display(persona.s))
            if idx >= 0:
                self.sex_combo.setCurrentIndex(idx)
            self.tone_edit.setText(persona.tone)
            self.language_edit.setText(persona.language)
            idx = self.language_code_combo.findText(persona.language_code)
            if idx >= 0:
                self.language_code_combo.setCurrentIndex(idx)
            self.characteristics_text.setPlainText(
                "\n".join(persona.characteristics) if persona.characteristics else ""
            )
            self.prompt_text.setPlainText(persona.system_prompt or "")

    @require_password(ProtectedActions.EDIT_PERSONAS)
    def add_persona(self):
        self.clear_form()
        self.selected_persona = None

    @require_password(ProtectedActions.EDIT_PERSONAS)
    def edit_persona(self):
        if not self.selected_persona:
            self.app_actions.alert(
                _("No Selection"),
                _("Please select a persona to edit."),
                kind="warning",
                master=self,
            )
            return

    @require_password(ProtectedActions.EDIT_PERSONAS)
    def delete_persona(self):
        if not self.selected_persona:
            self.app_actions.alert(
                _("No Selection"),
                _("Please select a persona to delete."),
                kind="warning",
                master=self,
            )
            return
        res = self.app_actions.alert(
            _("Confirm Delete"),
            _("Are you sure you want to delete the persona '{}'?").format(
                self.selected_persona.name
            ),
            kind="askyesno",
            master=self,
        )
        if not res:
            return
        success = self.persona_manager.remove_persona(self.selected_persona.voice_name)
        if success:
            self.save_personas_to_config()
            self.clear_form()
            self.refresh_persona_list()
            self.app_actions.toast(_("Persona deleted successfully."))
        else:
            self.app_actions.alert(
                _("Error"),
                _("Failed to remove persona from manager."),
                kind="error",
                master=self,
            )

    @require_password(ProtectedActions.EDIT_PERSONAS)
    def save_persona(self):
        try:
            name = self.name_edit.text().strip()
            if not name:
                self.app_actions.alert(
                    _("Validation Error"),
                    _("Display name is required."),
                    kind="error",
                    master=self,
                )
                return
            voice_name = self.voice_combo.currentText().strip()
            if not voice_name:
                self.app_actions.alert(
                    _("Validation Error"),
                    _("Voice name is required."),
                    kind="error",
                    master=self,
                )
                return
            tone = self.tone_edit.text().strip()
            if not tone:
                self.app_actions.alert(
                    _("Validation Error"),
                    _("Tone is required."),
                    kind="error",
                    master=self,
                )
                return
            prompt_plain = self.prompt_text.toPlainText().strip()
            if not prompt_plain:
                self.app_actions.alert(
                    _("Validation Error"),
                    _("System prompt is required."),
                    kind="error",
                    master=self,
                )
                return

            characteristics_plain = self.characteristics_text.toPlainText().strip()
            characteristics = [
                line.strip()
                for line in characteristics_plain.split("\n")
                if line.strip()
            ]
            try:
                sex_enum = PersonaSex.get_from_translation(self.sex_combo.currentText())
                sex_value = sex_enum.get_legacy_value()
            except Exception:
                sex_value = "M"
            persona_data = {
                "name": name,
                "voice_name": voice_name,
                "s": sex_value,
                "tone": tone,
                "characteristics": characteristics,
                "system_prompt": prompt_plain,
                "language": self.language_edit.text().strip(),
                "language_code": self.language_code_combo.currentText(),
            }
            try:
                persona = DJPersona.from_dict(persona_data)
            except ValueError as e:
                self.app_actions.alert(
                    _("Validation Error"),
                    _("Invalid persona data: {}").format(str(e)),
                    kind="error",
                    master=self,
                )
                return
            if (
                self.selected_persona
                and self.selected_persona.voice_name == persona.voice_name
            ):
                self.persona_manager.update_persona(persona.voice_name, persona)
            else:
                self.persona_manager.add_persona(persona)
            self.save_personas_to_config()
            self.refresh_persona_list()
            self.selected_persona = persona
            self.app_actions.toast(_("Persona saved successfully."))
        except Exception as e:
            logger.error("Error saving persona: %s", e)
            self.app_actions.alert(
                _("Error"),
                _("Failed to save persona: {}").format(str(e)),
                kind="error",
                master=self,
            )

    @require_password(ProtectedActions.EDIT_PERSONAS)
    def save_personas_to_config(self):
        try:
            success = self.persona_manager.save_personas_to_config()
            if success:
                self.persona_manager.reload_personas()
            else:
                self.app_actions.alert(
                    _("Error"),
                    _("Failed to save personas to configuration."),
                    kind="error",
                    master=self,
                )
        except Exception as e:
            logger.error("Error saving personas to config: %s", e)
            self.app_actions.alert(
                _("Error"),
                _("Failed to save personas to configuration: {}").format(str(e)),
                kind="error",
                master=self,
            )

    def cancel_edit(self):
        if self.selected_persona:
            self.load_persona(self.selected_persona.voice_name)
        else:
            self.clear_form()

    def clear_form(self):
        self.name_edit.clear()
        self.tone_edit.clear()
        self.language_edit.clear()
        self.characteristics_text.clear()
        self.prompt_text.clear()
        self.selected_persona = None
        self.set_default_persona_values()

    def reload_personas(self):
        try:
            self.persona_manager.reload_personas()
            self.refresh_persona_list()
            self.clear_form()
            self.app_actions.toast(_("Personas reloaded from configuration."))
        except Exception as e:
            logger.error("Error reloading personas: %s", e)
            self.app_actions.alert(
                _("Error"),
                _("Failed to reload personas: {}").format(str(e)),
                kind="error",
                master=self,
            )

    def closeEvent(self, event):
        if PersonasWindow.top_level is self:
            PersonasWindow.top_level = None
        event.accept()
