"""
Presets window (PySide6).
Port of ui/presets_window.py; logic preserved, UI uses Qt.
Uses ui_qt.preset.Preset.
"""

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QWidget,
)
from PySide6.QtCore import Qt

from lib.multi_display_qt import SmartWindow
from ui_qt.app_style import AppStyle
from ui_qt.preset import Preset
from utils.app_info_cache import app_info_cache
from utils.translations import I18N

_ = I18N._


class PresetsWindow(SmartWindow):
    """Presets window: list presets, set/delete/add, filter by key."""

    top_level = None
    recent_presets = []
    last_set_preset = None
    preset_history = []
    MAX_PRESETS = 50
    MAX_HEIGHT = 900
    N_TAGS_CUTOFF = 30
    COL_0_WIDTH = 600

    @staticmethod
    def set_recent_presets():
        PresetsWindow.recent_presets.clear()
        for preset_dict in list(app_info_cache.get("recent_presets", default_val=[])):
            PresetsWindow.recent_presets.append(Preset.from_dict(preset_dict))

    @staticmethod
    def store_recent_presets():
        preset_dicts = [p.to_dict() for p in PresetsWindow.recent_presets]
        app_info_cache.set("recent_presets", preset_dicts)

    @staticmethod
    def get_preset_by_name(name):
        for preset in PresetsWindow.recent_presets:
            if name == preset.name:
                return preset
        raise Exception(f"No preset found with name: {name}. Set it on the Presets Window.")

    @staticmethod
    def get_preset_names():
        return sorted([p.name for p in PresetsWindow.recent_presets])

    @staticmethod
    def get_most_recent_preset_name():
        return (
            PresetsWindow.recent_presets[0].name
            if len(PresetsWindow.recent_presets) > 0
            else _("New Preset (ERROR no presets found)")
        )

    @staticmethod
    def get_history_preset(start_index=0):
        preset = None
        for i in range(len(PresetsWindow.preset_history)):
            if i < start_index:
                continue
            preset = PresetsWindow.preset_history[i]
            break
        return preset

    @staticmethod
    def update_history(preset):
        if (
            len(PresetsWindow.preset_history) > 0
            and preset == PresetsWindow.preset_history[0]
        ):
            return
        PresetsWindow.preset_history.insert(0, preset)
        if len(PresetsWindow.preset_history) > PresetsWindow.MAX_PRESETS:
            del PresetsWindow.preset_history[-1]

    @staticmethod
    def get_geometry(is_gui=True):
        return "700x400"

    @staticmethod
    def next_preset(alert_callback):
        if len(PresetsWindow.recent_presets) == 0:
            alert_callback(_("Not enough presets found."))
            return None
        next_preset = PresetsWindow.recent_presets[-1]
        PresetsWindow.recent_presets.remove(next_preset)
        PresetsWindow.recent_presets.insert(0, next_preset)
        return next_preset

    def __init__(
        self,
        master,
        app_actions,
        construct_preset_callback,
        set_widgets_from_preset_callback,
        dimensions=None,
    ):
        geom = dimensions if dimensions else PresetsWindow.get_geometry()
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("Presets Window"),
            geometry=geom,
            offset_x=50,
            offset_y=50,
        )
        PresetsWindow.top_level = self
        self.master = master
        self.app_actions = app_actions
        self.construct_preset_callback = construct_preset_callback
        self.set_widgets_from_preset_callback = set_widgets_from_preset_callback
        self.filter_text = ""
        self.filtered_presets = list(PresetsWindow.recent_presets)
        self._preset_rows = []

        self.setStyleSheet(AppStyle.get_stylesheet())
        layout = QVBoxLayout(self)

        # Top row: "Set a new preset", name entry, Add preset, Clear presets
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel(_("Set a new preset"), self))
        self.new_preset_name_edit = QLineEdit(self)
        self.new_preset_name_edit.setMinimumWidth(280)
        self.new_preset_name_edit.setText(_("New Preset"))
        top_row.addWidget(self.new_preset_name_edit)
        self.add_preset_btn = QPushButton(_("Add preset"), self)
        self.add_preset_btn.clicked.connect(self._on_handle_preset)
        top_row.addWidget(self.add_preset_btn)
        self.clear_recent_btn = QPushButton(_("Clear presets"), self)
        self.clear_recent_btn.clicked.connect(self.clear_recent_presets)
        top_row.addWidget(self.clear_recent_btn)
        layout.addLayout(top_row)

        # Scroll area with preset rows (label, Set, Delete)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget(scroll)
        self.scroll_layout = QVBoxLayout(scroll_widget)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        self._add_preset_widgets()
        self.show()

    def _add_preset_widgets(self):
        for row_widget, set_btn, del_btn in self._preset_rows:
            row_widget.deleteLater()
        self._preset_rows.clear()
        for preset in self.filtered_presets:
            row = QHBoxLayout()
            lbl = QLabel(str(preset), self)
            lbl.setWordWrap(True)
            lbl.setMaximumWidth(PresetsWindow.COL_0_WIDTH)
            row.addWidget(lbl)
            set_btn = QPushButton(_("Set"), self)
            set_btn.clicked.connect(lambda checked=False, p=preset: self._on_set_preset(p))
            row.addWidget(set_btn)
            del_btn = QPushButton(_("Delete"), self)
            del_btn.clicked.connect(lambda checked=False, p=preset: self._on_delete_preset(p))
            row.addWidget(del_btn)
            row_widget = QWidget(self)
            row_widget.setLayout(row)
            self.scroll_layout.addWidget(row_widget)
            self._preset_rows.append((row_widget, set_btn, del_btn))

    def get_preset(self, preset):
        if preset and preset.is_valid():
            return preset, True
        if preset and preset in PresetsWindow.recent_presets:
            PresetsWindow.recent_presets.remove(preset)
        if preset:
            self.app_actions.toast(_("Invalid preset: {0}").format(preset))
        return self.construct_preset_callback(self.new_preset_name_edit.text()), False

    def _on_handle_preset(self):
        self.handle_preset(preset=None)

    def handle_preset(self, preset=None):
        preset, was_valid = self.get_preset(preset)
        if was_valid and preset is not None:
            if preset in PresetsWindow.recent_presets:
                PresetsWindow.recent_presets.remove(preset)
            PresetsWindow.recent_presets.insert(0, preset)
            return preset
        if preset in PresetsWindow.recent_presets:
            PresetsWindow.recent_presets.remove(preset)
        PresetsWindow.recent_presets.insert(0, preset)
        self.set_preset(preset=preset)
        return None

    def _on_set_preset(self, preset):
        self.set_preset(preset=preset)

    def set_preset(self, preset=None):
        preset = self.handle_preset(preset=preset)
        if preset is None:
            return
        PresetsWindow.update_history(preset)
        PresetsWindow.last_set_preset = preset
        self.set_widgets_from_preset_callback(preset)
        self.refresh()

    def _on_delete_preset(self, preset):
        self.delete_preset(preset=preset)

    def delete_preset(self, preset=None):
        if preset is not None and preset in PresetsWindow.recent_presets:
            PresetsWindow.recent_presets.remove(preset)
        self.refresh()

    def filter_presets(self, key_text=None, is_backspace=False, is_up=False, is_down=False):
        if is_up:
            if self.filtered_presets:
                self.filtered_presets = [
                    self.filtered_presets[-1]
                ] + self.filtered_presets[:-1]
            self._add_preset_widgets()
            return
        if is_down:
            if self.filtered_presets:
                self.filtered_presets = (
                    self.filtered_presets[1:] + [self.filtered_presets[0]]
                )
            self._add_preset_widgets()
            return
        if is_backspace:
            if self.filter_text:
                self.filter_text = self.filter_text[:-1]
        elif key_text:
            self.filter_text += key_text
        else:
            return
        if self.filter_text.strip() == "":
            self.filtered_presets = list(PresetsWindow.recent_presets)
        else:
            self.filtered_presets = list(PresetsWindow.recent_presets)
            # TODO: filter by self.filter_text (Tk has return # TODO here)
        self._add_preset_widgets()

    def do_action(self, control_key=False, alt_key=False):
        if alt_key:
            penultimate = PresetsWindow.get_history_preset(start_index=1)
            if penultimate is not None:
                self.set_preset(preset=penultimate)
            return
        if len(self.filtered_presets) == 0 or control_key:
            self.handle_preset()
            return
        if len(self.filtered_presets) == 1 or self.filter_text.strip() != "":
            preset = self.filtered_presets[0]
        else:
            preset = PresetsWindow.last_set_preset
        self.set_preset(preset=preset)

    def clear_recent_presets(self):
        PresetsWindow.recent_presets.clear()
        self.filtered_presets.clear()
        self._add_preset_widgets()

    def refresh(self, refresh_list=True):
        self.filtered_presets = list(PresetsWindow.recent_presets)
        self._add_preset_widgets()

    def keyPressEvent(self, event):
        mods = event.modifiers()
        control_key = mods & Qt.KeyboardModifier.ControlModifier
        alt_key = mods & Qt.KeyboardModifier.AltModifier
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.close()
            return
        if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            self.do_action(control_key=bool(control_key), alt_key=bool(alt_key))
            return
        if key == Qt.Key.Key_Up:
            self.filter_presets(is_up=True)
            return
        if key == Qt.Key.Key_Down:
            self.filter_presets(is_down=True)
            return
        if key == Qt.Key.Key_Backspace:
            self.filter_presets(is_backspace=True)
            return
        if not control_key and not alt_key and event.text():
            self.filter_presets(key_text=event.text())
            return

    def closeEvent(self, event):
        if PresetsWindow.top_level is self:
            PresetsWindow.top_level = None
        event.accept()
