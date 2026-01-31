"""
Timer window (PySide6).
Port of ui/timer_window.py; logic preserved, UI uses Qt.
"""

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QGroupBox,
    QWidget,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from muse.timer import Timer
from ui_qt.app_style import AppStyle
from utils.logging_setup import get_logger
from utils.translations import I18N

_ = I18N._
logger = get_logger(__name__)


class TimerWindow(QDialog):
    """Timer dialog: set duration, start/pause/stop/reset, display countdown."""

    def __init__(self, master, app_actions):
        super().__init__(master)
        self.setWindowTitle(_("Timer"))
        self.resize(400, 360)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Window)
        self.setMinimumSize(320, 300)

        self.master = master
        self.app_actions = app_actions
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._poll_display)

        try:
            app_instance = master.master if hasattr(master, "master") else master
            if app_instance and hasattr(app_instance, "current_run") and app_instance.current_run:
                playback_instance = app_instance.current_run.get_playback()
                if playback_instance:
                    Timer().set_playback_instance(playback_instance)
        except Exception as e:
            logger.warning("Could not set playback instance for timer: %s", e)

        self.setStyleSheet(AppStyle.get_stylesheet())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self._create_timer_input_section(layout)
        self._create_timer_display_section(layout)
        self._create_control_buttons_section(layout)

        self.sync_ui_with_timer()
        self.show()
        self._start_polling()

    def _create_timer_input_section(self, parent_layout):
        group = QGroupBox(_("Set Timer"), self)
        group_layout = QGridLayout(group)
        row = 0
        group_layout.addWidget(QLabel(_("Hours:"), group), row, 0)
        self.hours_edit = QLineEdit(group)
        self.hours_edit.setMaximumWidth(60)
        self.hours_edit.setText("0")
        group_layout.addWidget(self.hours_edit, row, 1)
        group_layout.addWidget(QLabel(_("Minutes:"), group), row, 2)
        self.minutes_edit = QLineEdit(group)
        self.minutes_edit.setMaximumWidth(60)
        self.minutes_edit.setText("0")
        group_layout.addWidget(self.minutes_edit, row, 3)
        group_layout.addWidget(QLabel(_("Seconds:"), group), row, 4)
        self.seconds_edit = QLineEdit(group)
        self.seconds_edit.setMaximumWidth(60)
        self.seconds_edit.setText("0")
        group_layout.addWidget(self.seconds_edit, row, 5)
        row += 1
        preset_layout = QHBoxLayout()
        presets = [("5m", 300), ("10m", 600), ("15m", 900), ("30m", 1800), ("1h", 3600)]
        for label, seconds in presets:
            btn = QPushButton(label, group)
            btn.clicked.connect(lambda checked=False, s=seconds: self.set_preset_time(s))
            preset_layout.addWidget(btn)
        preset_layout.addStretch()
        group_layout.addLayout(preset_layout, row, 0, 1, 6)
        parent_layout.addWidget(group)

    def _create_timer_display_section(self, parent_layout):
        group = QGroupBox(_("Timer Display"), self)
        group_layout = QVBoxLayout(group)
        self.time_display = QLabel("00:00:00", self)
        font = QFont()
        font.setPointSize(24)
        font.setBold(True)
        self.time_display.setFont(font)
        self.time_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        group_layout.addWidget(self.time_display)
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        group_layout.addWidget(self.progress_bar)
        self.status_label = QLabel(_("Ready"), self)
        self.status_label.setStyleSheet("font-size: 12pt;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        group_layout.addWidget(self.status_label)
        parent_layout.addWidget(group)

    def _create_control_buttons_section(self, parent_layout):
        btn_layout = QHBoxLayout()
        self.start_button = QPushButton(_("Start"), self)
        self.start_button.clicked.connect(self.start_timer)
        btn_layout.addWidget(self.start_button)
        self.pause_button = QPushButton(_("Pause"), self)
        self.pause_button.clicked.connect(self.pause_resume_timer)
        self.pause_button.setEnabled(False)
        btn_layout.addWidget(self.pause_button)
        self.stop_button = QPushButton(_("Stop"), self)
        self.stop_button.clicked.connect(self.stop_timer)
        self.stop_button.setEnabled(False)
        btn_layout.addWidget(self.stop_button)
        self.reset_button = QPushButton(_("Reset"), self)
        self.reset_button.clicked.connect(self.reset_timer)
        btn_layout.addWidget(self.reset_button)
        parent_layout.addLayout(btn_layout)

    def sync_ui_with_timer(self):
        timer = Timer()
        if timer.is_running() or timer.is_completed():
            remaining = timer.get_remaining_time()
            if timer.is_completed():
                remaining = 0
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            seconds = remaining % 60
            self.hours_edit.setText(str(hours))
            self.minutes_edit.setText(str(minutes))
            self.seconds_edit.setText(str(seconds))
        self.update_button_states()
        if timer.is_running():
            self.status_label.setText(_("Running..."))
        elif timer.is_completed():
            self.status_label.setText(_("Timer Complete!"))
        elif timer.is_paused():
            self.status_label.setText(_("Paused"))

    def set_preset_time(self, seconds):
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        self.hours_edit.setText(str(hours))
        self.minutes_edit.setText(str(minutes))
        self.seconds_edit.setText(str(secs))

    def start_timer(self):
        try:
            hours = int(self.hours_edit.text() or "0")
            minutes = int(self.minutes_edit.text() or "0")
            seconds = int(self.seconds_edit.text() or "0")
            total_seconds = hours * 3600 + minutes * 60 + seconds
            if total_seconds <= 0:
                self.app_actions.alert(
                    _("Invalid Time"),
                    _("Please enter a valid time greater than 0."),
                    kind="warning",
                    master=self,
                )
                return
            Timer().start_timer(total_seconds)
            self.update_button_states()
        except ValueError:
            self.app_actions.alert(
                _("Invalid Input"),
                _("Please enter valid numbers for hours, minutes, and seconds."),
                kind="error",
                master=self,
            )

    def pause_resume_timer(self):
        timer = Timer()
        if timer.is_paused():
            timer.resume_timer()
            self.pause_button.setText(_("Pause"))
        else:
            timer.pause_timer()
            self.pause_button.setText(_("Resume"))
        self.update_button_states()

    def stop_timer(self):
        Timer().stop_timer()
        self.update_button_states()

    def reset_timer(self):
        self.hours_edit.setText("0")
        self.minutes_edit.setText("0")
        self.seconds_edit.setText("0")
        self.progress_bar.setValue(0)
        self.status_label.setText(_("Ready"))

    def update_button_states(self):
        timer = Timer()
        is_running = timer.is_running()
        self.start_button.setEnabled(not is_running)
        self.pause_button.setEnabled(is_running)
        self.stop_button.setEnabled(is_running)
        self.reset_button.setEnabled(not is_running)

    def _start_polling(self):
        self._update_timer.start(100)

    def _stop_polling(self):
        self._update_timer.stop()

    def _poll_display(self):
        timer = Timer()
        if timer.is_running() or timer.is_completed():
            remaining = timer.get_remaining_time()
            progress = timer.get_progress()
            status = timer.get_status()
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            seconds = remaining % 60
            time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            self.time_display.setText(time_str)
            self.progress_bar.setValue(int(progress * 100))
            if status == "completed":
                self.status_label.setText(_("Timer Complete!"))
                self.update_button_states()
            elif status == "paused":
                self.status_label.setText(_("Paused"))
            elif status == "running":
                self.status_label.setText(_("Running..."))
        else:
            self.status_label.setText(_("Ready"))

    def closeEvent(self, event):
        self._stop_polling()
        event.accept()
