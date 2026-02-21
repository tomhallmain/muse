"""General-purpose formatting helpers for test output."""

import datetime
import time


def format_time(timestamp) -> str:
    """Format a Unix timestamp into ``YYYY-MM-DD HH:MM:SS``, or ``"Never"``."""
    if timestamp is None or timestamp == 0:
        return "Never"
    return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def format_time_diff(seconds) -> str:
    """Format a duration in seconds into a compact human-readable string."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds / 60)}m"
    elif seconds < 86400:
        return f"{int(seconds / 3600)}h"
    else:
        return f"{int(seconds / 86400)}d"


def mktime(dt: datetime.datetime) -> float:
    """Shorthand for ``time.mktime(dt.timetuple())``."""
    return time.mktime(dt.timetuple())
