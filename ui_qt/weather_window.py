"""
Weather window (PySide6).
Port of ui/weather_window.py; logic preserved, UI uses Qt.
"""

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QWidget,
)
from PySide6.QtCore import Qt, Signal

from extensions.open_weather import OpenWeatherAPI
from ui_qt.app_style import AppStyle
from utils.config import config
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._


class WeatherWindow(QDialog):
    """Window to show weather data."""

    CITY = None
    COL_0_WIDTH = 150
    top_level = None

    weather_result = Signal(str, str)

    def __init__(self, master, app_actions, dimensions="600x600"):
        super().__init__(master)
        if WeatherWindow.CITY is None:
            WeatherWindow.CITY = getattr(config, "open_weather_city", "Washington")
        WeatherWindow.top_level = self
        self.setWindowTitle(_("Weather") + " - " + WeatherWindow.CITY)
        try:
            w, h = dimensions.split("x")
            self.resize(int(w), int(h))
        except Exception:
            self.resize(600, 600)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Window)

        self.master = master
        self.app_actions = app_actions
        self.open_weather_api = OpenWeatherAPI()

        self.weather_result.connect(self._on_weather_result)

        self.setStyleSheet(AppStyle.get_stylesheet())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel(_("Weather"), self))
        self.update_btn = QPushButton(_("Update"), self)
        self.update_btn.clicked.connect(self._on_update_clicked)
        top_row.addWidget(self.update_btn)
        top_row.addStretch()
        layout.addLayout(top_row)

        layout.addWidget(QLabel(_("City"), self))
        self.city_edit = QLineEdit(self)
        self.city_edit.setText(WeatherWindow.CITY)
        self.city_edit.setMinimumWidth(200)
        layout.addWidget(self.city_edit)

        self.weather_label = QLabel(_("Gathering weather data..."), self)
        self.weather_label.setWordWrap(True)
        self.weather_label.setMinimumWidth(WeatherWindow.COL_0_WIDTH)
        layout.addWidget(self.weather_label, 1)

        self.show()
        Utils.start_thread(self.get_weather_data, use_asyncio=False)

    def _on_update_clicked(self):
        Utils.start_thread(self.get_weather_data, use_asyncio=False)

    def get_weather_data(self):
        city = self.city_edit.text().strip()
        if not city:
            city = WeatherWindow.CITY
        WeatherWindow.CITY = city
        try:
            weather = self.open_weather_api.get_weather_for_city(city)
            weather_str = str(weather)
        except Exception as e:
            weather_str = _("Error: {}").format(str(e))
        self.weather_result.emit(weather_str, city)

    def _on_weather_result(self, weather_str: str, city: str):
        self.weather_label.setText(weather_str)
        self.setWindowTitle(_("Weather") + " - " + city)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if WeatherWindow.top_level is self:
            WeatherWindow.top_level = None
        event.accept()
