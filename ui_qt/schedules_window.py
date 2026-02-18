"""
Schedules window (PySide6).
Port of ui/schedules_window.py; logic preserved, UI uses Qt.
"""

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QCheckBox,
    QScrollArea,
    QSizePolicy,
    QWidget,
)
from PySide6.QtCore import Qt

from lib.multi_display_qt import SmartWindow
from muse.schedule import Schedule
from muse.schedules_manager import schedules_manager
from tts.speakers import speakers
from ui_qt.app_style import AppStyle
from ui_qt.auth.password_utils import require_password
from utils.globals import ProtectedActions
from utils.translations import I18N

_ = I18N._


class ScheduleModifyWindow(SmartWindow):
    """Dialog to create or edit one schedule."""

    top_level = None
    COL_0_WIDTH = 600

    def __init__(self, master, refresh_callback, schedule=None, dimensions="600x600"):
        sched = schedule if schedule is not None else Schedule()
        title = _("Modify Preset Schedule: {0}").format(sched.name)
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=title,
            geometry=dimensions,
            offset_x=50,
            offset_y=50,
        )
        ScheduleModifyWindow.top_level = self
        self.refresh_callback = refresh_callback
        self.schedule = sched

        self.setStyleSheet(AppStyle.get_stylesheet())
        layout = QGridLayout(self)
        row = 0

        layout.addWidget(
            QLabel(_("Schedule Name"), self), row, 0
        )
        self.new_schedule_name_edit = QLineEdit(self)
        self.new_schedule_name_edit.setMinimumWidth(280)
        self.new_schedule_name_edit.setText(
            _("New Schedule") if schedule is None else schedule.name
        )
        layout.addWidget(self.new_schedule_name_edit, row, 1)
        self.add_schedule_btn = QPushButton(_("Add schedule"), self)
        self.add_schedule_btn.clicked.connect(self.finalize_schedule)
        layout.addWidget(self.add_schedule_btn, row, 2)
        row += 1

        layout.addWidget(QLabel(_("Voice"), self), row, 0)
        self.voice_combo = QComboBox(self)
        self.voice_combo.addItems(speakers)
        idx = self.voice_combo.findText(self.schedule.voice)
        if idx >= 0:
            self.voice_combo.setCurrentIndex(idx)
        else:
            self.voice_combo.setCurrentIndex(0)
        layout.addWidget(self.voice_combo, row, 1)
        row += 1

        self.all_days_check = QCheckBox(_("Every day"), self)
        self.all_days_check.setChecked(False)
        self.all_days_check.stateChanged.connect(self._toggle_all_days)
        layout.addWidget(self.all_days_check, row, 0)
        row += 1

        self.days_of_the_week_checks = []
        for i in range(7):
            day_text = I18N.day_of_the_week(i)
            check = QCheckBox(day_text, self)
            check.setChecked(i in self.schedule.weekday_options)
            layout.addWidget(check, row, 0)
            self.days_of_the_week_checks.append(check)
            row += 1

        layout.addWidget(QLabel(_("Start Time"), self), row, 0)
        self.start_hour_combo = QComboBox(self)
        self.start_hour_combo.addItems([str(i) for i in range(24)])
        self.start_min_combo = QComboBox(self)
        self.start_min_combo.addItems([str(i) for i in range(0, 61, 15)])
        if self.schedule.start_time is not None and self.schedule.start_time >= 0:
            h, m = int(self.schedule.start_time // 60), int(self.schedule.start_time % 60)
            self.start_hour_combo.setCurrentText(str(h))
            self.start_min_combo.setCurrentText(str(m))
        else:
            self.start_hour_combo.setCurrentText("0")
            self.start_min_combo.setCurrentText("0")
        layout.addWidget(self.start_hour_combo, row, 1)
        layout.addWidget(self.start_min_combo, row, 2)
        row += 1

        layout.addWidget(QLabel(_("End Time"), self), row, 0)
        self.end_hour_combo = QComboBox(self)
        self.end_hour_combo.addItems([str(i) for i in range(24)])
        self.end_min_combo = QComboBox(self)
        self.end_min_combo.addItems([str(i) for i in range(0, 61, 15)])
        if self.schedule.end_time is not None and self.schedule.end_time >= 0:
            h, m = int(self.schedule.end_time // 60), int(self.schedule.end_time % 60)
            self.end_hour_combo.setCurrentText(str(h))
            self.end_min_combo.setCurrentText(str(m))
        else:
            self.end_hour_combo.setCurrentText("0")
            self.end_min_combo.setCurrentText("0")
        layout.addWidget(self.end_hour_combo, row, 1)
        layout.addWidget(self.end_min_combo, row, 2)
        row += 1

        layout.addWidget(QLabel(_("Shutdown Time"), self), row, 0)
        self.shutdown_hour_combo = QComboBox(self)
        self.shutdown_hour_combo.addItem("")
        self.shutdown_hour_combo.addItems([str(i) for i in range(24)])
        self.shutdown_min_combo = QComboBox(self)
        self.shutdown_min_combo.addItem("")
        self.shutdown_min_combo.addItems([str(i) for i in range(0, 61, 15)])
        if self.schedule.shutdown_time is not None and self.schedule.shutdown_time >= 0:
            h, m = int(self.schedule.shutdown_time // 60), int(self.schedule.shutdown_time % 60)
            self.shutdown_hour_combo.setCurrentText(str(h))
            self.shutdown_min_combo.setCurrentText(str(m))
        else:
            self.shutdown_hour_combo.setCurrentIndex(0)
            self.shutdown_min_combo.setCurrentIndex(0)
        layout.addWidget(self.shutdown_hour_combo, row, 1)
        layout.addWidget(self.shutdown_min_combo, row, 2)
        row += 1

        self.show()

    def _toggle_all_days(self):
        set_to = self.all_days_check.isChecked()
        for check in self.days_of_the_week_checks:
            check.setChecked(set_to)

    def get_active_weekday_indices(self):
        return [i for i, check in enumerate(self.days_of_the_week_checks) if check.isChecked()]

    @require_password(ProtectedActions.EDIT_SCHEDULES)
    def finalize_schedule(self):
        self.schedule.name = self.new_schedule_name_edit.text().strip()
        self.schedule.voice = self.voice_combo.currentText()
        self.schedule.weekday_options = self.get_active_weekday_indices()
        if len(self.schedule.weekday_options) == 0:
            app_actions = getattr(self, "app_actions", None) or getattr(
                self.parent(), "app_actions", None
            )
            if app_actions:
                app_actions.alert(
                    _("Error"),
                    _("No days selected"),
                    kind="error",
                    master=self,
                )
            return
        start_h = self.start_hour_combo.currentText()
        if start_h != "":
            self.schedule.set_start_time(
                int(start_h), int(self.start_min_combo.currentText())
            )
        end_h = self.end_hour_combo.currentText()
        if end_h != "":
            self.schedule.set_end_time(
                int(end_h), int(self.end_min_combo.currentText())
            )
        shutdown_h = self.shutdown_hour_combo.currentText()
        if shutdown_h != "":
            self.schedule.set_shutdown_time(
                int(shutdown_h), int(self.shutdown_min_combo.currentText())
            )
        self.close()
        self.refresh_callback(self.schedule)

    def closeEvent(self, event):
        if ScheduleModifyWindow.top_level is self:
            ScheduleModifyWindow.top_level = None
        event.accept()


class SchedulesWindow(SmartWindow):
    """Main schedules window: list schedules, add/modify/delete."""

    top_level = None
    schedule_modify_window = None
    MAX_HEIGHT = 900
    N_TAGS_CUTOFF = 30
    COL_0_WIDTH = 400

    @staticmethod
    def get_geometry(is_gui=True):
        return "700x400"

    def __init__(self, master, app_actions, runner_app_config=None):
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("Preset Schedules"),
            geometry=SchedulesWindow.get_geometry(),
            offset_x=50,
            offset_y=50,
        )
        SchedulesWindow.top_level = self
        self.master = master
        self.app_actions = app_actions
        self.filter_text = ""
        self.filtered_schedules = list(schedules_manager.recent_schedules)
        self._preset_rows = []

        self.setStyleSheet(AppStyle.get_stylesheet())
        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel(_("Create and modify schedules"), self))
        self.add_schedule_btn = QPushButton(_("Add schedule"), self)
        self.add_schedule_btn.clicked.connect(lambda: self.open_schedule_modify_window(None))
        top_row.addWidget(self.add_schedule_btn)
        self.clear_recent_btn = QPushButton(_("Clear schedules"), self)
        self.clear_recent_btn.clicked.connect(self.clear_recent_schedules)
        top_row.addWidget(self.clear_recent_btn)
        top_row.addStretch()
        layout.addLayout(top_row)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget(scroll)
        self.scroll_layout = QVBoxLayout(scroll_widget)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        self._add_schedule_widgets()
        self.show()

    def _add_schedule_widgets(self):
        for row_widget, _mod_btn, _del_btn in self._preset_rows:
            row_widget.deleteLater()
        self._preset_rows.clear()
        for schedule in self.filtered_schedules:
            row = QHBoxLayout()
            lbl = QLabel(str(schedule), self)
            lbl.setWordWrap(True)
            lbl.setMinimumWidth(SchedulesWindow.COL_0_WIDTH)
            lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            row.addWidget(lbl, 1)
            modify_btn = QPushButton(_("Modify"), self)
            modify_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            modify_btn.clicked.connect(
                lambda checked=False, s=schedule: self.open_schedule_modify_window(s)
            )
            row.addWidget(modify_btn, 0)
            delete_btn = QPushButton(_("Delete"), self)
            delete_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            delete_btn.clicked.connect(
                lambda checked=False, s=schedule: self.delete_schedule(s)
            )
            row.addWidget(delete_btn, 0)
            row_widget = QWidget(self)
            row_widget.setLayout(row)
            self.scroll_layout.addWidget(row_widget)
            self._preset_rows.append((row_widget, modify_btn, delete_btn))

    @require_password(ProtectedActions.EDIT_SCHEDULES)
    def open_schedule_modify_window(self, schedule=None):
        if SchedulesWindow.schedule_modify_window is not None:
            try:
                SchedulesWindow.schedule_modify_window.close()
            except Exception:
                pass
        win = ScheduleModifyWindow(self, self.refresh_schedules, schedule)
        SchedulesWindow.schedule_modify_window = win
        win.app_actions = self.app_actions

    def refresh_schedules(self, schedule):
        schedules_manager.refresh_schedule(schedule)
        self.filtered_schedules = list(schedules_manager.recent_schedules)
        self.refresh()

    def refresh(self, refresh_list=True):
        self.filtered_schedules = list(schedules_manager.recent_schedules)
        self._add_schedule_widgets()

    @require_password(ProtectedActions.EDIT_SCHEDULES)
    def delete_schedule(self, schedule=None):
        schedules_manager.delete_schedule(schedule)
        self.refresh()

    @require_password(ProtectedActions.EDIT_SCHEDULES)
    def clear_recent_schedules(self):
        schedules_manager.recent_schedules.clear()
        self.filtered_schedules.clear()
        self._add_schedule_widgets()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if SchedulesWindow.top_level is self:
            SchedulesWindow.top_level = None
        event.accept()
