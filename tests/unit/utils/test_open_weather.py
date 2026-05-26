import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add the project root directory to the Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from extensions.open_weather import OpenWeatherResponse


class TestOpenWeatherResponse:
    """Test class for OpenWeatherResponse functionality."""
    
    def setup_method(self):
        """Set up test fixtures before each test method."""
        # Mock current weather data
        self.mock_current_weather = {
            'dt': int(datetime.now().timestamp()),
            'name': 'Test City',
            'sys': {
                'country': 'US',
                'sunrise': int((datetime.now() - timedelta(hours=6)).timestamp()),
                'sunset': int((datetime.now() + timedelta(hours=6)).timestamp())
            },
            'main': {
                'temp': 72.5,
                'feels_like': 74.2,
                'humidity': 65,
                'pressure': 1013
            },
            'wind': {
                'speed': 8.5
            },
            'weather': [
                {
                    'main': 'Clear',
                    'description': 'clear sky'
                }
            ],
            'clouds': {
                'all': 20
            }
        }
        
        # Mock forecast data with complete and incomplete days
        self.mock_forecast_data = {
            'list': []
        }
        
        # Generate 5 days of forecast data (3-hour increments)
        base_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Day 1: Complete (8 data points)
        for hour in [0, 3, 6, 9, 12, 15, 18, 21]:
            forecast_time = base_time + timedelta(hours=hour)
            self.mock_forecast_data['list'].append({
                'dt': int(forecast_time.timestamp()),
                'name': 'Test City',
                'sys': {
                    'country': 'US',
                    'sunrise': int((forecast_time - timedelta(hours=6)).timestamp()),
                    'sunset': int((forecast_time + timedelta(hours=6)).timestamp())
                },
                'main': {
                    'temp': 65 + hour,  # Temperature varies by hour
                    'feels_like': 67 + hour,
                    'humidity': 60,
                    'pressure': 1013
                },
                'weather': [{'main': 'Clear', 'description': 'clear sky'}],
                'clouds': {'all': 20},
                'wind': {'speed': 8.5}
            })
        
        # Day 2: Complete (8 data points)
        for hour in [0, 3, 6, 9, 12, 15, 18, 21]:
            forecast_time = base_time + timedelta(days=1, hours=hour)
            self.mock_forecast_data['list'].append({
                'dt': int(forecast_time.timestamp()),
                'name': 'Test City',
                'sys': {
                    'country': 'US',
                    'sunrise': int((forecast_time - timedelta(hours=6)).timestamp()),
                    'sunset': int((forecast_time + timedelta(hours=6)).timestamp())
                },
                'main': {
                    'temp': 70 + hour,
                    'feels_like': 72 + hour,
                    'humidity': 65,
                    'pressure': 1012
                },
                'weather': [{'main': 'Clouds', 'description': 'scattered clouds'}],
                'clouds': {'all': 40},
                'wind': {'speed': 10.0}
            })
        
        # Day 3: Complete (8 data points)
        for hour in [0, 3, 6, 9, 12, 15, 18, 21]:
            forecast_time = base_time + timedelta(days=2, hours=hour)
            self.mock_forecast_data['list'].append({
                'dt': int(forecast_time.timestamp()),
                'name': 'Test City',
                'sys': {
                    'country': 'US',
                    'sunrise': int((forecast_time - timedelta(hours=6)).timestamp()),
                    'sunset': int((forecast_time + timedelta(hours=6)).timestamp())
                },
                'main': {
                    'temp': 68 + hour,
                    'feels_like': 70 + hour,
                    'humidity': 70,
                    'pressure': 1011
                },
                'weather': [{'main': 'Rain', 'description': 'light rain'}],
                'clouds': {'all': 80},
                'wind': {'speed': 12.0},
                'rain': {'3h': 0.5}  # Add rain data
            })
        
        # Day 4: Complete (8 data points)
        for hour in [0, 3, 6, 9, 12, 15, 18, 21]:
            forecast_time = base_time + timedelta(days=3, hours=hour)
            self.mock_forecast_data['list'].append({
                'dt': int(forecast_time.timestamp()),
                'name': 'Test City',
                'sys': {
                    'country': 'US',
                    'sunrise': int((forecast_time - timedelta(hours=6)).timestamp()),
                    'sunset': int((forecast_time + timedelta(hours=6)).timestamp())
                },
                'main': {
                    'temp': 72 + hour,
                    'feels_like': 74 + hour,
                    'humidity': 55,
                    'pressure': 1014
                },
                'weather': [{'main': 'Clear', 'description': 'clear sky'}],
                'clouds': {'all': 10},
                'wind': {'speed': 6.0}
            })
        
        # Day 5: Incomplete (only 5 data points - missing some hours)
        incomplete_hours = [0, 3, 6, 9, 12]  # Missing 15, 18, 21
        for hour in incomplete_hours:
            forecast_time = base_time + timedelta(days=4, hours=hour)
            self.mock_forecast_data['list'].append({
                'dt': int(forecast_time.timestamp()),
                'name': 'Test City',
                'sys': {
                    'country': 'US',
                    'sunrise': int((forecast_time - timedelta(hours=6)).timestamp()),
                    'sunset': int((forecast_time + timedelta(hours=6)).timestamp())
                },
                'main': {
                    'temp': 60 + hour,  # Lower temperatures (night data)
                    'feels_like': 62 + hour,
                    'humidity': 75,
                    'pressure': 1010
                },
                'weather': [{'main': 'Clear', 'description': 'clear sky'}],
                'clouds': {'all': 15},
                'wind': {'speed': 5.0}
            })
    
    def test_initialization(self):
        """Test OpenWeatherResponse initialization with current weather only."""
        response = OpenWeatherResponse(self.mock_current_weather)
        
        assert response.city == "Test City, US"
        assert response.temperature == 72  # Rounded from 72.5 (Python rounds 0.5 to even)
        assert response.feels_like == 74   # Rounded from 74.2 (Python rounds 0.2 down)
        assert response.humidity == "65%"
        assert response.pressure == "1013 hPa"
        assert response.wind == "8.5 miles per hour"
        assert response.description == "Clear, clear sky"
        assert response.hourly_forecast == {}
    
    def test_initialization_with_forecast(self):
        """Test OpenWeatherResponse initialization with both current weather and forecast."""
        response = OpenWeatherResponse(self.mock_current_weather, self.mock_forecast_data)
        
        assert response.city == "Test City, US"
        assert len(response.hourly_forecast) == 37  # 5 days * 8 hours + 1 incomplete day * 5 hours
    
    def test_forecast_min_max_temps_by_day(self):
        """Test the forecast_min_max_temps_by_day method."""
        response = OpenWeatherResponse(self.mock_current_weather, self.mock_forecast_data)
        forecast_data = response.forecast_min_max_temps_by_day()
        
        # Should have 5 days
        assert len(forecast_data) == 5
        
        # Check first day (complete)
        first_date = list(forecast_data.keys())[0]
        first_day = forecast_data[first_date]
        assert first_day['hour_count'] == 8
        assert first_day['max_temp'] == 86  # 65 + 21
        assert first_day['min_temp'] == 65  # 65 + 0
        assert first_day['rain'] == False
        
        # Check last day (incomplete)
        last_date = list(forecast_data.keys())[-1]
        last_day = forecast_data[last_date]
        assert last_day['hour_count'] == 5  # Only 5 hours of data
        assert last_day['max_temp'] == 72   # 60 + 12
        assert last_day['min_temp'] == 60   # 60 + 0
        assert last_day['rain'] == False
    
    def test_is_day_complete(self):
        """Test the _is_day_complete method."""
        response = OpenWeatherResponse(self.mock_current_weather, self.mock_forecast_data)
        forecast_data = response.forecast_min_max_temps_by_day()
        
        # Test complete day
        first_date = list(forecast_data.keys())[0]
        first_day = forecast_data[first_date]
        assert response._is_day_complete(first_date, first_day) == True
        
        # Test incomplete day
        last_date = list(forecast_data.keys())[-1]
        last_day = forecast_data[last_date]
        assert response._is_day_complete(last_date, last_day) == False
    
    def test_get_complete_days_only(self):
        """Test the _get_complete_days_only method."""
        response = OpenWeatherResponse(self.mock_current_weather, self.mock_forecast_data)
        complete_days = response._get_complete_days_only()
        
        # Should have 4 complete days
        assert len(complete_days) == 4
        
        # All days should have 8 hours
        for date, day_data in complete_days.items():
            assert day_data['hour_count'] == 8
    
    def test_get_incomplete_days(self):
        """Test the _get_incomplete_days method."""
        response = OpenWeatherResponse(self.mock_current_weather, self.mock_forecast_data)
        incomplete_days = response._get_incomplete_days()
        
        # Should have 1 incomplete day
        assert len(incomplete_days) == 1
        
        # The incomplete day should have 5 hours
        for date, day_data in incomplete_days.items():
            assert day_data['hour_count'] == 5
    
    def test_has_incomplete_days(self):
        """Test the has_incomplete_days method."""
        response = OpenWeatherResponse(self.mock_current_weather, self.mock_forecast_data)
        
        # Should have incomplete days
        assert response.has_incomplete_days() == True
        
        # Create response with only complete data
        complete_forecast = {'list': self.mock_forecast_data['list'][:32]}  # Only first 4 days
        response_complete = OpenWeatherResponse(self.mock_current_weather, complete_forecast)
        assert response_complete.has_incomplete_days() == False
    
    def test_get_complete_forecast_only(self):
        """Test the get_complete_forecast_only method."""
        response = OpenWeatherResponse(self.mock_current_weather, self.mock_forecast_data)
        complete_forecast = response.get_complete_forecast_only()
        
        # Should have 4 complete days
        assert len(complete_forecast) == 4
        
        # All days should have 8 hours
        for date, day_data in complete_forecast.items():
            assert day_data['hour_count'] == 8
    
    def test_get_forecast_summary(self):
        """Test the get_forecast_summary method."""
        response = OpenWeatherResponse(self.mock_current_weather, self.mock_forecast_data)
        
        # With incomplete days included
        all_forecast = response.get_forecast_summary(include_incomplete=True)
        assert len(all_forecast) == 5
        
        # Without incomplete days
        complete_forecast = response.get_forecast_summary(include_incomplete=False)
        assert len(complete_forecast) == 4
    
    def test_get_clean_forecast_string(self):
        """Test the get_clean_forecast_string method."""
        response = OpenWeatherResponse(self.mock_current_weather, self.mock_forecast_data)
        
        # With incomplete days excluded
        clean_forecast = response.get_clean_forecast_string(include_incomplete=False)
        assert "Forecast:" in clean_forecast
        assert "INCOMPLETE" not in clean_forecast
        
        # With incomplete days included
        all_forecast = response.get_clean_forecast_string(include_incomplete=True)
        assert "Forecast:" in all_forecast
    
    def test_string_representation_with_incomplete_days(self):
        """Test the __str__ method shows incomplete days properly."""
        response = OpenWeatherResponse(self.mock_current_weather, self.mock_forecast_data)
        weather_string = str(response)
        
        # Should show complete days normally
        assert "Max" in weather_string
        assert "Min" in weather_string
        
        # Should show incomplete days with warning
        assert "--- Incomplete Data (Partial Day) ---" in weather_string
        assert "INCOMPLETE - 5/8 hours" in weather_string
    
    def test_rain_detection_in_forecast(self):
        """Test that rain is properly detected in forecast data."""
        response = OpenWeatherResponse(self.mock_current_weather, self.mock_forecast_data)
        forecast_data = response.forecast_min_max_temps_by_day()
        
        # Find the day with rain (day 3)
        rainy_day = None
        for date, day_data in forecast_data.items():
            if day_data['rain']:
                rainy_day = day_data
                break
        
        assert rainy_day is not None
        assert rainy_day['rain'] == True
    
    def test_edge_case_no_forecast_data(self):
        """Test behavior when no forecast data is provided."""
        response = OpenWeatherResponse(self.mock_current_weather)
        
        assert response.has_incomplete_days() == False
        assert len(response.get_complete_forecast_only()) == 0
        assert len(response._get_incomplete_days()) == 0
        assert response.get_clean_forecast_string() == "No forecast data available"
    
    def test_edge_case_empty_forecast_list(self):
        """Test behavior with empty forecast list."""
        empty_forecast = {'list': []}
        response = OpenWeatherResponse(self.mock_current_weather, empty_forecast)
        
        assert response.has_incomplete_days() == False
        assert len(response.get_complete_forecast_only()) == 0
        assert len(response._get_incomplete_days()) == 0


if __name__ == "__main__":
    pytest.main([__file__])
