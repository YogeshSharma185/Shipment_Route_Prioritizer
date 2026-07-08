"""Small helpers for parsing time windows and formatting distance/duration."""
from datetime import datetime, time

TIME_FORMAT = "%H:%M"
METERS_PER_MILE = 1609.344


def parse_time(time_str: str) -> time:
    """Parse an 'HH:MM' string into a datetime.time. Raises ValueError if malformed."""
    return datetime.strptime(time_str, TIME_FORMAT).time()


def seconds_since_midnight(value: time) -> int:
    """Convert a datetime.time into seconds elapsed since 00:00, for easy comparison/sorting."""
    return value.hour * 3600 + value.minute * 60


def meters_to_miles(meters: float) -> float:
    return round(meters / METERS_PER_MILE, 2)


def seconds_to_duration_str(seconds: float) -> str:
    """Format a duration in seconds as e.g. '1h 25m', '2h' or '15m'."""
    total_minutes = round(seconds / 60)
    hours, minutes = divmod(total_minutes, 60)
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"
