import datetime
import requests
import time

from utils.config import config


class EventGroup:
    def __init__(self, date=datetime.datetime.now(), events=[]):
        self.date = date
        self.events = events
    
    def add_event(self, event):
        self.events.append(event)

    def __eq__(self, other: object):
        return isinstance(other, EventGroup) and self.date == other.date

    def __hash__(self) -> int:
        return hash(self.date)

class Event:
    def __init__(self, name="", date=datetime.datetime.now(), source=None,
                 fixed=False, country=None, other_name=None, notes=None):
        self.name = name
        self.date = date
        self.sources = []
        self.fixed = fixed
        self.countries = []
        self.other_names = []
        self.notes = []
        if source is not None:
            if not source in self.sources:
                self.sources.append(source)
        if country is not None:
            if isinstance(country, list):
                self.countries.extend(country)
            else:
                self.countries.append(country)
        if notes is not None:
            if isinstance(notes, list):
                self.notes.extend(notes)
            else:
                self.notes.append(notes)
        if other_name is not None:
            if not other_name in self.other_names:
                self.other_names.append(other_name)

    def merge(self, other):
        if self.fixed is None and other.fixed is not None:
            self.fixed = other.fixed
        for country in other.countries:
            if not country in self.countries:
                self.countries.append(country)
        for note in other.notes:
            if not note in self.notes:
                self.notes.append(note)
        for other_name in other.other_names:
            if not other_name in self.other_names:
                self.other_names.append(other_name)

    @staticmethod
    def from_holiday_api(event):
        notes = []
        if "public" in event:
            notes.append({"public": event["public"]})
        new_event = Event(name=event["name"],
            date=datetime.datetime.strptime(event["date"], "%Y-%m-%d"),
            source="Holiday API",
            fixed=None,
            country=event["country"],
            other_name=None,
            notes=notes)
        return new_event

    @staticmethod
    def from_nager_public_holidays_api(event):
        notes = []
        if "launchYear" in event:
            notes.append({"launchYear": event["launchYear"]})
        new_event = Event(name=event["name"],
            date=datetime.datetime.fromisoformat(event["date"]),
            source="Nager Public Holidays API",
            fixed=event["fixed"],
            country=event["countryCode"],
            other_name=event["localName"],
            notes=notes)
        return new_event

    @staticmethod
    def from_inadiutorium(event):
        notes = []
        new_event = Event(name=event["name"],
            date=datetime.datetime.strptime(event["date"], "%Y-%m-%d"),
            source="Inadiutorium",
            fixed=None,
            country=None,
            other_name=None,
            notes=notes)
        return new_event

    @staticmethod
    def from_hijri_calendar(event):
        notes = []
        new_event = Event(name=event["name"],
            date=datetime.datetime.strptime(event["date"], "%Y-%m-%d"),
            source="Hijri Calendar",
            fixed=None,
            country="IR",
            other_name=None,
            notes=notes)
        return new_event

    @staticmethod
    def contains_ordinal_str(event_name):
        for s in ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th"]:
            if s in event_name:
                return True
        return False

    @staticmethod
    def get_inadiutorium_event_name(celebrations_list):
        if len(celebrations_list) == 0:
            raise Exception("Could not find name for event - celebrations list: empty celebrations list")

        event_name = celebrations_list[0]["title"]

        if len(celebrations_list) > 1:
            other_name = event_name
            found_other_name = False
            i = 1
            while i < len(celebrations_list):
                other_name = celebrations_list[i]["title"]
                if Event.contains_ordinal_str(other_name):
                    found_other_name = True
                    break
                i += 1
            if found_other_name:
                event_name = other_name

        if event_name is None:
            raise Exception("Could not find name for event - celebrations list: " + str(celebrations_list))

        return event_name

    @staticmethod
    def from_inadiutorium_api(event):
        notes = []
        if "season" in event:
            notes.append({"season": event["season"]})
        if "season_week" in event:
            notes.append({"season_week": event["season_week"]})
        if "celebrations" in event:
            notes.append({"celebrations": event["celebrations"]})
        event_name = Event.get_inadiutorium_event_name(event["celebrations"])
        new_event = Event(name=event_name,
            date=datetime.datetime.fromisoformat(event["date"]),
            source="Inadiutorium API",
            fixed=None,
            country=None,
            other_name=None,
            notes=notes)
        return new_event

    @staticmethod
    def from_hijri_api(event):
        notes = []
        new_event = Event(name=event["title"],
            date=datetime.datetime(year=event["year"], month=event["month"], day=event["day"]),
            source="Hijri API",
            fixed=None,
            country=None,
            other_name=None,
            notes=notes)
        return new_event



class HolidayAPI:
    BASE_URL = "https://holidayapi.com/v1/holidays"

    def __init__(self, api_key=None):
        self.api_key = api_key

    def __build_url(self, country, year):
        return f"{self.BASE_URL}?key={self.api_key}&country={country}&year={year}"

    def get_events(self, country="US", year=-1):
        events = []
        try:
            events_json = requests.get(self.__build_url(country, year)).json()
            for event in events_json:
                events.append(Event.from_holiday_api(event))
        except Exception as e:
            print("Error getting events from Holiday API: " + str(e))
        return events


class NagerPublicHolidaysAPI:
    BASE_URL = "https://date.nager.at/api/v3/publicholidays/"

    def __init__(self, api_key=None):
        self.api_key = api_key
    
    def __build_url(self, country_code="US", year=-1):
        return self.BASE_URL + str(year) + "/" + country_code

    def get_events(self, country_code="US", year=-1):
        events = []
        try:
            events_json = requests.get(self.__build_url(country_code, year)).json()
            for event in events_json:
                events.append(Event.from_nager_public_holidays_api(event))
        except Exception as e:
            print("Error getting events from Nager Public Holidays API: " + str(e))
        return events

    def get_events_for_countries(self, country_codes=["US"], year=-1):
        events = []
        for country in country_codes:
            self.merge_events(events, self.get_events(country, year))
        return events

    def merge_events(self, events=[], events_to_merge=[]):
        for event_to_merge in events_to_merge:
            for event in events:
                if event_to_merge.name == event.name and event_to_merge.date == event.date:
                    event.merge(event_to_merge)


class InadiutoriumAPI:
    BASE_URL = "http://calapi.inadiutorium.cz/api/v0/en/calendars/default/"

    def __init__(self):
        pass

    def __build_url(self, year=-1, month=-1):
        return self.BASE_URL + str(year) + "/" + str(month)
    
    def get_events(self, year=-1):
        events = []
        for i in range(0, 12):
            try:
                events_json = requests.get(self.__build_url(year, i + 1)).json()
                for event in events_json["data"]:
                    events.append(Event.from_inadiutorium(event))
                time.sleep(0.5)
            except Exception as e:
                print("Error getting events from Inadiutorium API: " + str(e))
        
        return events



class HijriCalendarAPI:
    # Maybe pip install hijri-converter
    BASE_URL = "http://api.aladhan.com/v1/"
    G_TO_H_CALENDAR = "gToHCalendar/"

    def __init__(self) -> None:
        pass

    def __build_url(self, month=-1, year=-1):
        return self.BASE_URL + str(month) + '/' + str(year)

    def get_events(self, month=-1, year=-1):
        events = []
        try:
            events_json  = requests.get(self.__build_url(month, year)).json()["data"]["items"]
            for event in events_json:
                events.append(Event.from_hijri_api(event))
        except Exception as e:
           print("Error getting events from Hijri Calendar API: " + str(e))
        return events


class CalendarAggregator:
    def __init__(self):
        self.holiday_api = HolidayAPI(config.holiday_api_key)
        self.public_holidays_api = NagerPublicHolidaysAPI()
        self.inadiutorium_api = InadiutoriumAPI()
        self.hijri_calendar_api = HijriCalendarAPI()

    def get_events(self):
        now = datetime.datetime.now()
        holidays = self.holiday_api.get_events()
        public_holidays = self.public_holidays_api.get_events_for_countries(["US", "DE", "GB", "CA", "RU"], now.year)
        inadiutorium = self.inadiutorium_api.get_events(now.year)
        hijri = self.hijri_calendar_api.get_events(now.year)
        all_events = holidays
        self.merge_events(all_events, public_holidays)
        self.merge_events(all_events, inadiutorium)
        self.merge_events(all_events, hijri)
        return all_events

    def merge_events(self, events=[], events_to_merge=[]):
        for event_to_merge in events_to_merge:
            for event in events:
                if event_to_merge.name == event.name and event_to_merge.date == event.date:
                    event.merge(event_to_merge)
