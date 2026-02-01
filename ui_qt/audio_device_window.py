"""
Audio Device Management window (PySide6).
Port of ui/audio_device_window.py; logic preserved, UI uses Qt.
"""
from datetime import datetime, time as dt_time

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QCheckBox,
    QComboBox,
    QFrame,
)
from PySide6.QtCore import Qt

from lib.multi_display_qt import SmartWindow
from ui_qt.app_style import AppStyle
from utils.translations import I18N
from utils.audio_device_manager import AudioDeviceManager
from utils.logging_setup import get_logger

_ = I18N._
logger = get_logger(__name__)


class AudioDeviceWindow(SmartWindow):
    """Window for managing audio device settings and day/night switching."""

    top_level = None

    def __init__(self, master, app_actions):
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("Audio Device Management"),
            geometry="800x600",
            offset_x=50,
            offset_y=50,
        )
        AudioDeviceWindow.top_level = self
        self.master = master
        self.app_actions = app_actions

        try:
            self.audio_manager = AudioDeviceManager()
            self.audio_available = True
            logger.info("Audio device manager initialized successfully")
        except ImportError as e:
            self.audio_manager = None
            self.audio_available = False
            logger.warning("Audio device manager not available: %s", e)

        self.devices = []
        self.show_all_devices = False
        self.day_device_name = ""
        self.night_device_name = ""
        self.day_start_hour = "07"
        self.day_start_minute = "00"
        self.night_start_hour = "22"
        self.night_start_minute = "00"
        self.monitoring_enabled = False

        self._build_ui()
        self.load_current_settings()
        self.refresh_devices()
        self.show()

    def _build_ui(self):
        self.setStyleSheet(AppStyle.get_stylesheet())
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self._create_device_list_section(layout)
        self._create_day_night_section(layout)
        self._create_controls_section(layout)

    def _create_device_list_section(self, parent_layout):
        title = QLabel(_("Available Audio Devices"))
        title.setStyleSheet("font-weight: bold; font-size: 12pt;")
        parent_layout.addWidget(title)

        self.device_listbox = QListWidget()
        self.device_listbox.setMinimumHeight(180)
        self.device_listbox.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        parent_layout.addWidget(self.device_listbox)

        control_row = QHBoxLayout()
        self.refresh_btn = QPushButton(_("Refresh Devices"))
        self.refresh_btn.clicked.connect(self.refresh_devices)
        control_row.addWidget(self.refresh_btn)

        self.show_all_checkbox = QCheckBox(_("Show all devices (including virtual)"))
        self.show_all_checkbox.stateChanged.connect(self._on_show_all_changed)
        control_row.addWidget(self.show_all_checkbox)
        control_row.addStretch()
        parent_layout.addLayout(control_row)

    def _on_show_all_changed(self, _state):
        self.show_all_devices = self.show_all_checkbox.isChecked()
        self.refresh_devices()

    def _create_day_night_section(self, parent_layout):
        title = QLabel(_("Day/Night Device Switching"))
        title.setStyleSheet("font-weight: bold; font-size: 12pt;")
        parent_layout.addWidget(title)

        device_row = QHBoxLayout()
        device_row.addWidget(QLabel(_("Day Device:")))
        self.day_device_combo = QComboBox()
        self.day_device_combo.setMinimumWidth(280)
        device_row.addWidget(self.day_device_combo)
        parent_layout.addLayout(device_row)

        night_row = QHBoxLayout()
        night_row.addWidget(QLabel(_("Night Device:")))
        self.night_device_combo = QComboBox()
        self.night_device_combo.setMinimumWidth(280)
        night_row.addWidget(self.night_device_combo)
        parent_layout.addLayout(night_row)

        time_row = QHBoxLayout()
        time_row.addWidget(QLabel(_("Day Start:")))
        self.day_hour_combo = QComboBox()
        self.day_hour_combo.addItems([str(i).zfill(2) for i in range(24)])
        self.day_minute_combo = QComboBox()
        self.day_minute_combo.addItems([str(i).zfill(2) for i in range(0, 60, 15)])
        time_row.addWidget(self.day_hour_combo)
        time_row.addWidget(QLabel(":"))
        time_row.addWidget(self.day_minute_combo)
        time_row.addSpacing(20)

        time_row.addWidget(QLabel(_("Night Start:")))
        self.night_hour_combo = QComboBox()
        self.night_hour_combo.addItems([str(i).zfill(2) for i in range(24)])
        self.night_minute_combo = QComboBox()
        self.night_minute_combo.addItems([str(i).zfill(2) for i in range(0, 60, 15)])
        time_row.addWidget(self.night_hour_combo)
        time_row.addWidget(QLabel(":"))
        time_row.addWidget(self.night_minute_combo)
        time_row.addStretch()
        parent_layout.addLayout(time_row)

        self.monitoring_checkbox = QCheckBox(_("Enable automatic day/night switching"))
        self.monitoring_checkbox.stateChanged.connect(self.toggle_monitoring)
        parent_layout.addWidget(self.monitoring_checkbox)

    def _create_controls_section(self, parent_layout):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        parent_layout.addWidget(line)

        buttons_row = QHBoxLayout()
        apply_btn = QPushButton(_("Apply Settings"))
        apply_btn.clicked.connect(self.apply_settings)
        buttons_row.addWidget(apply_btn)

        test_btn = QPushButton(_("Test Day/Night Switch"))
        test_btn.clicked.connect(self.test_day_night)
        buttons_row.addWidget(test_btn)

        buttons_row.addStretch()
        close_btn = QPushButton(_("Close"))
        close_btn.clicked.connect(self.on_closing)
        buttons_row.addWidget(close_btn)
        parent_layout.addLayout(buttons_row)

    def load_current_settings(self):
        """Load current audio device settings into the UI."""
        if not self.audio_available:
            return

        try:
            if AudioDeviceManager._cached_day_device:
                self.day_device_name = AudioDeviceManager._cached_day_device
                idx = self.day_device_combo.findText(self.day_device_name)
                if idx >= 0:
                    self.day_device_combo.setCurrentIndex(idx)

            if AudioDeviceManager._cached_night_device:
                self.night_device_name = AudioDeviceManager._cached_night_device
                idx = self.night_device_combo.findText(self.night_device_name)
                if idx >= 0:
                    self.night_device_combo.setCurrentIndex(idx)

            if AudioDeviceManager._cached_day_start_time:
                t = AudioDeviceManager._cached_day_start_time
                self.day_hour_combo.setCurrentText(str(t.hour).zfill(2))
                self.day_minute_combo.setCurrentText(str(t.minute).zfill(2))

            if AudioDeviceManager._cached_night_start_time:
                t = AudioDeviceManager._cached_night_start_time
                self.night_hour_combo.setCurrentText(str(t.hour).zfill(2))
                self.night_minute_combo.setCurrentText(str(t.minute).zfill(2))

            self.monitoring_enabled = AudioDeviceManager._cached_monitoring_enabled
            self.monitoring_checkbox.blockSignals(True)
            self.monitoring_checkbox.setChecked(self.monitoring_enabled)
            self.monitoring_checkbox.blockSignals(False)

            logger.info("Loaded current audio device settings into UI")

        except Exception as e:
            logger.error("Error loading current settings: %s", e)

    def refresh_devices(self):
        """Refresh the list of available audio devices."""
        self.device_listbox.clear()

        if not self.audio_available:
            self.device_listbox.addItem(_("Audio device management not available"))
            self.device_listbox.addItem(_("Install pycaw and comtypes to enable this feature"))
            return

        try:
            if self.show_all_checkbox.isChecked():
                self.devices = self.audio_manager.list_all_devices(refresh=True)
                logger.info("Refreshed all audio devices, found %d devices", len(self.devices))
            else:
                self.devices = self.audio_manager.list_devices(refresh=True)
                logger.info("Refreshed filtered audio devices, found %d devices", len(self.devices))

            if not self.devices:
                self.device_listbox.addItem(_("No audio devices found"))
                logger.warning("No audio devices found")
                return

            device_names = []
            for i, device in enumerate(self.devices):
                status = " (Default)" if device.get("is_default", False) else ""
                state_info = ""
                state = device.get("state", 0)
                if state == 1:
                    state_info = " [Active]"
                elif state == 2:
                    state_info = " [Disabled]"
                elif state == 4:
                    state_info = " [Not Present]"

                device_text = f"{i + 1}. {device['name']}{status}{state_info}"
                self.device_listbox.addItem(device_text)
                device_names.append(device["name"])

            self._update_device_menus(device_names)

            if self.day_device_name:
                idx = self.day_device_combo.findText(self.day_device_name)
                if idx >= 0:
                    self.day_device_combo.setCurrentIndex(idx)
            if self.night_device_name:
                idx = self.night_device_combo.findText(self.night_device_name)
                if idx >= 0:
                    self.night_device_combo.setCurrentIndex(idx)

            self.device_listbox.addItem("")
            self.device_listbox.addItem("--- Recently Used Devices ---")

            recent_devices = self.audio_manager.get_recently_used_devices(limit=3)
            for device in recent_devices:
                self.device_listbox.addItem(f"★ {device['name']}")

            current_device = self.audio_manager.get_current_device()
            if current_device:
                self.device_listbox.addItem("")
                self.device_listbox.addItem(f"Current Device: {current_device['name']}")
                logger.info("Current device: %s", current_device["name"])

        except Exception as e:
            logger.error("Error refreshing devices: %s", e)
            self.device_listbox.clear()
            self.device_listbox.addItem(f"Error loading devices: {str(e)}")

    def _update_device_menus(self, device_names):
        """Update the device selection combos and auto-select common devices."""
        old_day = self.day_device_combo.currentText()
        old_night = self.night_device_combo.currentText()

        self.day_device_combo.clear()
        self.night_device_combo.clear()
        self.day_device_combo.addItems(device_names)
        self.night_device_combo.addItems(device_names)

        if old_day and old_day in device_names:
            self.day_device_combo.setCurrentText(old_day)
        else:
            for device_name in device_names:
                name_lower = device_name.lower()
                if "speaker" in name_lower or "monitor" in name_lower:
                    self.day_device_combo.setCurrentText(device_name)
                    break

        if old_night and old_night in device_names:
            self.night_device_combo.setCurrentText(old_night)
        else:
            for device_name in device_names:
                name_lower = device_name.lower()
                if "headphone" in name_lower or "headset" in name_lower:
                    self.night_device_combo.setCurrentText(device_name)
                    break

    def toggle_monitoring(self):
        """Toggle automatic monitoring."""
        if not self.audio_available:
            self.app_actions.alert(_("Error"), _("Audio device management not available"), kind="error")
            return

        try:
            if self.monitoring_checkbox.isChecked():
                success = self.audio_manager.start_monitoring()
                if success:
                    self.app_actions.toast(_("Audio device monitoring started"))
                    AudioDeviceManager.store_settings()
                else:
                    self.monitoring_checkbox.setChecked(False)
                    self.app_actions.alert(_("Error"), _("Failed to start monitoring"), kind="error")
            else:
                self.audio_manager.stop_monitoring()
                self.app_actions.toast(_("Audio device monitoring stopped"))
                AudioDeviceManager.store_settings()
        except Exception as e:
            self.monitoring_checkbox.setChecked(False)
            self.app_actions.alert(_("Error"), str(e), kind="error")

    def apply_settings(self):
        """Apply the current settings."""
        if not self.audio_available:
            self.app_actions.alert(_("Error"), _("Audio device management not available"), kind="error")
            return

        try:
            day_device = self.day_device_combo.currentText()
            night_device = self.night_device_combo.currentText()

            if not day_device or not night_device:
                self.app_actions.alert(_("Error"), _("Please select both day and night devices"), kind="error")
                return

            day_hour = int(self.day_hour_combo.currentText())
            day_minute = int(self.day_minute_combo.currentText())
            night_hour = int(self.night_hour_combo.currentText())
            night_minute = int(self.night_minute_combo.currentText())

            day_start_time = dt_time(day_hour, day_minute)
            night_start_time = dt_time(night_hour, night_minute)

            success = self.audio_manager.set_day_night_schedule(
                day_device=day_device,
                night_device=night_device,
                day_start=day_start_time,
                night_start=night_start_time,
            )

            if success:
                self.app_actions.toast(_("Audio device settings applied successfully"))
                if self.monitoring_checkbox.isChecked():
                    self.audio_manager.start_monitoring()
            else:
                self.app_actions.alert(_("Error"), _("Failed to apply audio device settings"), kind="error")

        except Exception as e:
            self.app_actions.alert(_("Error"), str(e), kind="error")

    def test_day_night(self):
        """Test the day/night switching functionality."""
        if not self.audio_available:
            self.app_actions.alert(_("Error"), _("Audio device management not available"), kind="error")
            return

        try:
            current_time = datetime.now().time()
            day_device = self.day_device_combo.currentText()
            night_device = self.night_device_combo.currentText()

            if not day_device or not night_device:
                self.app_actions.alert(_("Error"), _("Please select both day and night devices"), kind="error")
                return

            day_hour = int(self.day_hour_combo.currentText())
            day_minute = int(self.day_minute_combo.currentText())
            night_hour = int(self.night_hour_combo.currentText())
            night_minute = int(self.night_minute_combo.currentText())

            day_start_time = dt_time(day_hour, day_minute)
            night_start_time = dt_time(night_hour, night_minute)

            if self.audio_manager._is_night_time(current_time):
                target_device = night_device
                time_period = "night"
            else:
                target_device = day_device
                time_period = "day"

            success = self.audio_manager.switch_to_device(target_device)

            if success:
                self.app_actions.toast(_("Switched to {} device for {} time").format(target_device, time_period))
            else:
                self.app_actions.alert(_("Error"), _("Failed to switch audio device"), kind="error")

        except Exception as e:
            self.app_actions.alert(_("Error"), str(e), kind="error")

    def on_closing(self):
        """Handle window closing."""
        if self.audio_available and self.audio_manager:
            self.audio_manager.stop_monitoring()

        AudioDeviceWindow.top_level = None
        self.close()

    def closeEvent(self, event):
        self.on_closing()
        event.accept()
