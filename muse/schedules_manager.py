
import datetime

from muse.schedule import Schedule
from utils.app_info_cache import app_info_cache
from utils.logging_setup import get_logger
from utils.translations import I18N

logger = get_logger(__name__)
_ = I18N._

class ScheduledShutdownException(Exception):
    """Exception raised when a scheduled shutdown is requested."""
    pass


class SchedulesManager:
    default_schedule = Schedule(name="Default", enabled=True, voice="Royston Min", weekday_options=[0,1,2,3,4,5,6])
    recent_schedules = []
    last_set_schedule = None
    MAX_PRESETS = 50
    MAX_RECENT_SCHEDULES = 200  # Maximum number of schedules to persist
    schedule_history = []

    def __init__(self):
        pass

    @staticmethod
    def get_tomorrow(now):
       try:
           return datetime.datetime(now.year, now.month, (now.day if now.hour < 5 else now.day + 1), hour=7, tzinfo=now.tzinfo)
       except Exception as e:
           try:
               return datetime.datetime(now.year, now.month + 1, 1, hour=7, tzinfo=now.tzinfo)
           except Exception as e:
               return datetime.datetime(now.year + 1, 1, 1, hour=7, tzinfo=now.tzinfo)

    @staticmethod
    def set_schedules():
        # Clear existing schedules to prevent duplicates if called multiple times
        SchedulesManager.recent_schedules.clear()
        
        # Load schedules from cache and deduplicate by name
        seen_names = set()
        for schedule_dict in list(app_info_cache.get("recent_schedules", default_val=[])):
            schedule = Schedule.from_dict(schedule_dict)
            # Only add if we haven't seen this schedule name before
            if schedule.name not in seen_names:
                SchedulesManager.recent_schedules.append(schedule)
                seen_names.add(schedule.name)
        
        # Limit to MAX_RECENT_SCHEDULES to prevent excessive growth
        if len(SchedulesManager.recent_schedules) > SchedulesManager.MAX_RECENT_SCHEDULES:
            logger.warning(f"Limiting schedules from {len(SchedulesManager.recent_schedules)} to {SchedulesManager.MAX_RECENT_SCHEDULES}")
            SchedulesManager.recent_schedules = SchedulesManager.recent_schedules[:SchedulesManager.MAX_RECENT_SCHEDULES]

    @staticmethod
    def store_schedules():
        # Deduplicate schedules by name before storing
        seen_names = set()
        unique_schedules = []
        for schedule in SchedulesManager.recent_schedules:
            if schedule.name not in seen_names:
                unique_schedules.append(schedule)
                seen_names.add(schedule.name)
        
        # Limit to MAX_RECENT_SCHEDULES
        if len(unique_schedules) > SchedulesManager.MAX_RECENT_SCHEDULES:
            logger.warning(f"Limiting stored schedules from {len(unique_schedules)} to {SchedulesManager.MAX_RECENT_SCHEDULES}")
            unique_schedules = unique_schedules[:SchedulesManager.MAX_RECENT_SCHEDULES]
        
        schedule_dicts = [schedule.to_dict() for schedule in unique_schedules]
        app_info_cache.set("recent_schedules", schedule_dicts)

    @staticmethod
    def get_schedule_by_name(name):
        for schedule in SchedulesManager.recent_schedules:
            if name == schedule.name:
                return schedule
        raise Exception(f"No schedule found with name: {name}. Set it on the Schedules Window.")

    @staticmethod
    def get_history_schedule(start_index=0):
        # Get a previous schedule.
        schedule = None
        for i in range(len(SchedulesManager.schedule_history)):
            if i < start_index:
                continue
            schedule = SchedulesManager.schedule_history[i]
            break
        return schedule

    @staticmethod
    def update_history(schedule):
        if len(SchedulesManager.schedule_history) > 0 and \
                schedule == SchedulesManager.schedule_history[0]:
            return
        SchedulesManager.schedule_history.insert(0, schedule)
        if len(SchedulesManager.schedule_history) > SchedulesManager.MAX_PRESETS:
            del SchedulesManager.schedule_history[-1]

    @staticmethod
    def next_schedule(alert_callback):
        if len(SchedulesManager.recent_schedules) == 0:
            alert_callback(_("Not enough schedules found."))
        next_schedule = SchedulesManager.recent_schedules[-1]
        SchedulesManager.recent_schedules.remove(next_schedule)
        SchedulesManager.recent_schedules.insert(0, next_schedule)
        return next_schedule

    @staticmethod
    def refresh_schedule(schedule):
        SchedulesManager.update_history(schedule)
        # Remove all instances of schedules with the same name (handles duplicates)
        SchedulesManager.recent_schedules = [s for s in SchedulesManager.recent_schedules if s.name != schedule.name]
        SchedulesManager.recent_schedules.insert(0, schedule)

    @staticmethod
    def delete_schedule(schedule):
        # Remove all instances of schedules with the same name (handles duplicates)
        if schedule is not None:
            SchedulesManager.recent_schedules = [s for s in SchedulesManager.recent_schedules if s.name != schedule.name]

    @staticmethod
    def get_active_schedule(datetime):
        assert datetime is not None
        day_index = datetime.weekday()
        current_time = Schedule.get_time(datetime.hour, datetime.minute)
        partially_applicable = []
        no_specific_times = []
        for schedule in SchedulesManager.recent_schedules:
            skip = False
            if not schedule.enabled:
                skip = True
            if schedule.shutdown_time is not None and schedule.voice == SchedulesManager.default_schedule.voice:
                logger.debug(f"Skipping schedule {schedule} - a shutdown time is set on this schedule and it is assumed to be for shutdown purposes only.")
                skip = True
            if day_index not in schedule.weekday_options:
                logger.debug(f"Skipping schedule {schedule} - today is index {day_index} - schedule weekday options {schedule.weekday_options}")
                skip = True
            if skip:
                continue
            if schedule.start_time is not None and schedule.start_time < current_time:
                if schedule.end_time is not None and schedule.end_time > current_time:
                    logger.info(f"Schedule {schedule} is applicable")
                    return schedule
                else:
                    partially_applicable.append(schedule)
            elif schedule.end_time is not None and schedule.end_time > current_time:
                partially_applicable.append(schedule)
            elif (schedule.start_time is None and schedule.end_time is None) or \
                    (schedule.start_time == 0 and schedule.end_time == 0):
                no_specific_times.append(schedule)
        if len(partially_applicable) >= 1:
            partially_applicable.sort(key=lambda schedule: schedule.calculate_generality())
            schedules_text = "\n".join([str(schedule) for schedule in partially_applicable])
            logger.info(f"Schedules are partially applicable:\n{schedules_text}")
            return partially_applicable[0]
        elif len(no_specific_times) >= 1:
            no_specific_times.sort(key=lambda schedule: schedule.calculate_generality())
            schedules_text = "\n".join([str(schedule) for schedule in no_specific_times])
            logger.info(f"Schedules are applicable to today but have no specific times:\n{schedules_text}")
            return no_specific_times[0]
        else:
            return SchedulesManager.default_schedule

    @staticmethod
    def get_next_weekday_index_for_voice(voice, datetime):
        assert voice is not None
        voice_schedules = []
        for schedule in SchedulesManager.recent_schedules:
            if schedule.enabled and schedule.voice == voice:
                voice_schedules.append(schedule)
        if len(voice_schedules) == 0:
            return None
        voice_schedules.sort(key=lambda schedule: schedule.start_time * (1+SchedulesManager.get_closest_weekday_index_to_datetime(schedule, datetime, total_days=True)))
        return SchedulesManager.get_closest_weekday_index_to_datetime(voice_schedules[0], datetime)

    @staticmethod
    def get_closest_weekday_index_to_datetime(schedule, datetime, total_days=False):
        assert isinstance(schedule, Schedule) and datetime is not None
        datetime_index = datetime.weekday()
        for i in schedule.weekday_options:
            if i >= datetime_index:
                return i
        for i in schedule.weekday_options:
            return i + 7 if total_days else i
        raise Exception("Invalid schedule, no weekday options found")

    @staticmethod
    def check_for_shutdown_request(datetime):
        schedule_requesting_shutdown = SchedulesManager._check_for_shutdown_request(datetime)
        if schedule_requesting_shutdown is not None:
            raise ScheduledShutdownException(f"Shutdown scheduled: {schedule_requesting_shutdown}")

    @staticmethod
    def _check_for_shutdown_request(datetime):
        assert datetime is not None
        day_index = datetime.weekday()
        current_time = Schedule.get_time(datetime.hour, datetime.minute)
        for schedule in SchedulesManager.recent_schedules:
            if not schedule.enabled or schedule.shutdown_time is None or day_index not in schedule.weekday_options:
                continue
            if schedule.shutdown_time < current_time:
                return schedule
        return None

    @staticmethod
    def get_hour():
        return datetime.datetime.now().hour


schedules_manager = SchedulesManager()

