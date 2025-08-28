from datetime import datetime
import requests

from utils.config import config
from utils.logging_setup import get_logger

logger = get_logger(__name__)


class OpenWeatherResponse:
    def __init__(self, current_json, forecast_json=None):
        self.datetime = datetime.fromtimestamp(current_json['dt'])
        self.city = current_json["name"] + ", " + current_json["sys"]["country"] if "name" in current_json else None
        self.temperature = int(round(float(current_json['main']['temp']), 0))
        self.feels_like = int(round(float(current_json['main']['feels_like']), 0))
        self.humidity = str(current_json["main"]["humidity"]) + "%"
        self.pressure = str(current_json["main"]["pressure"]) + " hPa"
        self.wind = str(current_json["wind"]["speed"]) + " miles per hour" if "wind" in current_json else None
        if "rain" in current_json:
            rain_obj = current_json["rain"]
            hours = list(rain_obj.keys())[-1]
            inches = rain_obj[hours]
            self.rain = str(inches) + " inches in " + hours
        else:
            self.rain = None
        self.clouds = str(current_json["clouds"]["all"]) + "%" if "clouds" in current_json else None
        self.description = current_json["weather"][0]["main"] + ", " + current_json["weather"][0]["description"]
        self.sunrise = datetime.fromtimestamp(current_json["sys"]["sunrise"]).strftime("%H:%M") if "sunrise" in current_json["sys"] else None
        self.sunset = datetime.fromtimestamp(current_json["sys"]["sunset"]).strftime("%H:%M") if "sunset" in current_json["sys"] else None
        self.hourly_forecast = {}
        if forecast_json is not None:
            for i in range(len(forecast_json["list"])):
                hourly_data = forecast_json["list"][i]
                hour = datetime.fromtimestamp(hourly_data['dt']).strftime("%Y-%m-%d %H:%M")
                self.hourly_forecast[hour] = OpenWeatherResponse(hourly_data)

    def rain_in_next_5_days(self):
        """Returns rainy periods grouped by date, with consecutive periods shown as ranges."""
        hours_with_rain = {}
        for hour, hourly_data in self.hourly_forecast.items():
            if hourly_data.rain is not None:
                date = hourly_data.datetime.strftime("%m/%d (%A)")
                if date not in hours_with_rain:
                    hours_with_rain[date] = []
                hours_with_rain[date].append(hourly_data.datetime)
        
        # Group consecutive periods into ranges
        rainy_periods = {}
        for date, datetimes in hours_with_rain.items():
            if not datetimes:
                continue
                
            # Sort datetimes for the date
            datetimes.sort()
            periods = self._group_consecutive_periods(datetimes)
            rainy_periods[date] = periods
            
        return rainy_periods
    
    def _group_consecutive_periods(self, datetimes):
        """Groups consecutive datetime objects into time ranges."""
        if not datetimes:
            return []
            
        periods = []
        start_time = datetimes[0]
        end_time = datetimes[0]
        
        for i in range(1, len(datetimes)):
            current_time = datetimes[i]
            # Check if this is consecutive (within 3 hours of the previous)
            time_diff = (current_time - end_time).total_seconds() / 3600
            
            if time_diff <= 3:  # Consecutive or same time period
                end_time = current_time
            else:
                # End of consecutive period, add to periods
                periods.append(self._format_time_range(start_time, end_time))
                start_time = current_time
                end_time = current_time
        
        # Add the last period
        periods.append(self._format_time_range(start_time, end_time))
        return periods
    
    def _format_time_range(self, start_time, end_time):
        """Formats a time range in a readable format."""
        if start_time == end_time:
            # Single time point
            return start_time.strftime("%I:%M %p").lstrip("0")
        else:
            # Time range
            start_str = start_time.strftime("%I:%M %p").lstrip("0")
            end_str = end_time.strftime("%I:%M %p").lstrip("0")
            return f"{start_str}-{end_str}"

    def forecast_min_max_temps_by_day(self):
        data = {}
        for hour, hourly_data in self.hourly_forecast.items():
            date = hourly_data.datetime.strftime("%m/%d (%A)")
            if date in data:
                if hourly_data.temperature > data[date]["max_temp"]:
                    data[date]["max_temp"] = hourly_data.temperature
                elif hourly_data.temperature < data[date]["min_temp"]:
                    data[date]["min_temp"] = hourly_data.temperature
                if hourly_data.rain is not None:
                    data[date]["rain"] = True
                data[date]["hour_count"] += 1
            else:
                data[date] = {
                    "max_temp": hourly_data.temperature, 
                    "min_temp": hourly_data.temperature, 
                    "rain": hourly_data.rain is not None,
                    "hour_count": 1
                }
        return data

    def _is_day_complete(self, date, date_data):
        """Check if a day has complete data (8 data points for 24 hours in 3-hour increments)."""
        # OpenWeather API returns data in 3-hour increments
        # A complete day should have 8 data points (24 hours / 3 hours = 8)
        expected_hours = 8
        return date_data.get("hour_count", 0) >= expected_hours

    def _get_complete_days_only(self):
        """Return forecast data excluding incomplete days."""
        all_data = self.forecast_min_max_temps_by_day()
        complete_data = {}
        for date, date_data in all_data.items():
            if self._is_day_complete(date, date_data):
                complete_data[date] = date_data
        return complete_data

    def _get_incomplete_days(self):
        """Return days with incomplete data."""
        all_data = self.forecast_min_max_temps_by_day()
        incomplete_data = {}
        for date, date_data in all_data.items():
            if not self._is_day_complete(date, date_data):
                incomplete_data[date] = date_data
        return incomplete_data

    def has_incomplete_days(self):
        """Check if there are any days with incomplete forecast data."""
        return len(self._get_incomplete_days()) > 0

    def get_complete_forecast_only(self):
        """Return forecast data excluding incomplete days."""
        return self._get_complete_days_only()

    def get_forecast_summary(self, include_incomplete=True):
        """Get a summary of forecast data with option to include incomplete days."""
        if include_incomplete:
            return self.forecast_min_max_temps_by_day()
        else:
            return self.get_complete_forecast_only()

    def get_clean_forecast_string(self, include_incomplete=False):
        """Get a clean forecast string, optionally excluding incomplete days."""
        if not self.hourly_forecast:
            return "No forecast data available"
            
        forecast_data = self.get_forecast_summary(include_incomplete)
        if not forecast_data:
            return "No complete forecast data available"
            
        out = "Forecast:"
        rainy_periods = self.rain_in_next_5_days()
        
        for date, date_data in forecast_data.items():
            out += f"\n{date}: Max {date_data['max_temp']}°F Min {date_data['min_temp']}°F"
            if date_data['rain'] and date in rainy_periods:
                periods_str = ', '.join(rainy_periods[date])
                out += f"  Rain expected: {periods_str}"
                
        return out

    def __str__(self):
        out = f"""Current weather details for {self.datetime.strftime("%A %B %d at %H:%M")}
City: {self.city}
Temperature: {self.temperature}°F
Feels Like: {self.feels_like}°F"""
        if self.rain is not None:
            out += f"\nRain: {self.rain}"
        if self.wind is not None:
            out += f"\nWind Speed: {self.wind}"
        out += f"""
Humidity: {self.humidity}
Pressure: {self.pressure}
Description: {self.description}
Sunrise: {self.sunrise} hours
Sunset: {self.sunset} hours"""
        if self.hourly_forecast is not None:
            out += "\nForecast"
            # Get complete and incomplete days
            complete_days = self._get_complete_days_only()
            incomplete_days = self._get_incomplete_days()
            rainy_periods = self.rain_in_next_5_days()
            # Display complete days
            for date, date_data in complete_days.items():
                out += f"\n{date}: Max {date_data['max_temp']}°F Min {date_data['min_temp']}°F"
                if date_data['rain'] and date in rainy_periods:
                    periods_str = ', '.join(rainy_periods[date])
                    out += f"  Rain expected: {periods_str}"

            # Display incomplete days with warning
            if incomplete_days:
                out += "\n--- Incomplete Data (Partial Day) ---"
                for date, date_data in incomplete_days.items():
                    out += f"\n{date}: Max {date_data['max_temp']}°F Min {date_data['min_temp']}°F (INCOMPLETE - {date_data['hour_count']}/8 hours)"
                    if date_data['rain'] and date in rainy_periods:
                        periods_str = ', '.join(rainy_periods[date])
                        out += f"  Rain expected: {periods_str}"
        return out

class OpenWeatherAPI:
    WEATHER_ENDPOINT = "https://api.openweathermap.org/data/2.5/weather"
    HOURLY_FORECAST_ENDPOINT = "https://api.openweathermap.org/data/2.5/forecast"
    GEO_ENDPOINT = "https://api.openweathermap.org/geo/1.0/direct"
    api_key = config.open_weather_api_key
    
    def __init__(self):
        pass

    def get_coordinates(self, city=config.open_weather_city):
        url = f"{self.GEO_ENDPOINT}?q={city}&limit=3&appid={self.api_key}"
        response = requests.get(url)
        resp_json = response.json()[0]
        return float(resp_json["lat"]), float(resp_json["lon"])

    def get_weather_for_city(self, city):
        lat, lon = self.get_coordinates(city)

        current_weather_url = f"{self.WEATHER_ENDPOINT}?lat={lat}&lon={lon}&appid={self.api_key}&units=imperial"
        current_weather_response = requests.get(current_weather_url)

        hourly_forecast_url = f"{self.HOURLY_FORECAST_ENDPOINT}?lat={lat}&lon={lon}&appid={self.api_key}&units=imperial"
        hourly_forecast_response = requests.get(hourly_forecast_url)

        weather = OpenWeatherResponse(current_weather_response.json(), hourly_forecast_response.json())
        return weather



if __name__ == "__main__":
    api = OpenWeatherAPI()
    weather = api.get_weather_for_city("Washington")
    
    # Test the new incomplete day detection
    print("Testing incomplete day detection:")
    print(f"Has incomplete days: {weather.has_incomplete_days()}")
    
    # Get only complete days
    complete_forecast = weather.get_complete_forecast_only()
    print(f"\nComplete days: {len(complete_forecast)}")
    
    # Get all days including incomplete
    all_forecast = weather.get_forecast_summary(include_incomplete=True)
    print(f"All days: {len(all_forecast)}")
    
    # Get clean forecast string (complete days only)
    clean_forecast = weather.get_clean_forecast_string(include_incomplete=False)
    print(f"\nClean forecast (complete days only):\n{clean_forecast}")
    
    # Print the full string representation
    print(f"\nFull weather report:\n{weather}")
