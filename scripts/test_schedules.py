import os

# Change to the root directory
script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(script_dir)
os.chdir(root_dir)


from datetime import datetime

from muse.schedules_manager import SchedulesManager

if __name__ == "__main__":
    now = datetime.now()
    tomorrow = datetime(now.year, now.month, now.day + 1, hour=7, tzinfo=now.tzinfo)
    print(tomorrow.weekday())
    SchedulesManager.set_schedules()
    active_schedule = SchedulesManager.get_active_schedule(now)
    print(active_schedule)
    print(SchedulesManager.get_next_weekday_index_for_voice(active_schedule.voice, tomorrow))

