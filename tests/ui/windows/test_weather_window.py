"""Tests for ui_qt/weather_window.py.

Isolation:
- `Utils.start_thread` is patched to a no-op for every test so the background
  weather-fetch thread is never started and no real network calls are made.
- `OpenWeatherAPI` is replaced per-test where the API response matters.
- `WeatherWindow.top_level` and `WeatherWindow.CITY` are reset by the autouse
  `reset_ui_window_state` fixture in tests/ui/conftest.py.
- All other singleton isolation is provided by the root conftest autouse
  fixtures (app_info_cache, config, metadata JSON, etc.).
"""

import pytest

from tests.utils.qt_test_helpers import process_events_for


@pytest.fixture(autouse=True)
def suppress_weather_thread(monkeypatch):
    """Prevent the background weather-fetch thread from starting in any test."""
    monkeypatch.setattr("ui_qt.weather_window.Utils.start_thread", lambda *a, **k: None)


@pytest.fixture
def win(qapp, qt_master, mock_app_actions):
    from ui_qt.weather_window import WeatherWindow
    w = WeatherWindow(qt_master, mock_app_actions)
    process_events_for(0.2)
    yield w
    w.close()
    qapp.processEvents()


@pytest.mark.ui
class TestWeatherWindow:
    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def test_opens_and_is_visible(self, win):
        assert win.isVisible()

    def test_registered_as_top_level(self, win):
        from ui_qt.weather_window import WeatherWindow
        assert WeatherWindow.top_level is win

    def test_city_edit_prepopulated_from_config(self, win):
        # city_edit should contain whatever CITY was resolved to at open time
        assert win.city_edit.text() != ""

    # ------------------------------------------------------------------
    # _on_weather_result: signal handler
    # ------------------------------------------------------------------

    def test_weather_result_updates_label(self, win):
        win._on_weather_result("Sunny, 22°C", "London")
        assert "Sunny" in win.weather_label.text()
        assert "22" in win.weather_label.text()

    def test_weather_result_updates_window_title(self, win):
        win._on_weather_result("Cloudy", "Paris")
        assert "Paris" in win.windowTitle()

    # ------------------------------------------------------------------
    # get_weather_data: success and error paths
    # ------------------------------------------------------------------

    def test_get_weather_data_emits_result_on_success(self, win, monkeypatch):
        from unittest.mock import MagicMock
        mock_weather = MagicMock()
        mock_weather.__str__ = lambda self: "Partly cloudy"
        win.open_weather_api = MagicMock()
        win.open_weather_api.get_weather_for_city.return_value = mock_weather

        win.city_edit.setText("Berlin")
        win.get_weather_data()
        process_events_for(0.2)

        assert "Partly cloudy" in win.weather_label.text()

    def test_get_weather_data_shows_error_on_api_failure(self, win):
        from unittest.mock import MagicMock
        win.open_weather_api = MagicMock()
        win.open_weather_api.get_weather_for_city.side_effect = RuntimeError("timeout")

        win.city_edit.setText("Nowhere")
        win.get_weather_data()
        process_events_for(0.2)

        # The exception message is not translated, so "timeout" is locale-safe.
        assert "timeout" in win.weather_label.text()

    def test_get_weather_data_falls_back_to_class_city_when_edit_empty(self, win):
        from unittest.mock import MagicMock
        from ui_qt.weather_window import WeatherWindow

        WeatherWindow.CITY = "Tokyo"
        win.city_edit.setText("")
        win.open_weather_api = MagicMock()
        win.open_weather_api.get_weather_for_city.return_value = MagicMock(__str__=lambda s: "Rainy")

        win.get_weather_data()

        win.open_weather_api.get_weather_for_city.assert_called_once_with("Tokyo")

    # ------------------------------------------------------------------
    # Close behaviour
    # ------------------------------------------------------------------

    def test_close_clears_top_level(self, qapp, qt_master, mock_app_actions):
        from ui_qt.weather_window import WeatherWindow
        w = WeatherWindow(qt_master, mock_app_actions)
        process_events_for(0.1)
        w.close()
        qapp.processEvents()
        assert WeatherWindow.top_level is None
