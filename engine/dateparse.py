"""Small, dependency-free natural-language date parsing for quick data entry
(Todoist-style "next friday", "in 3 days"). Deliberately not a library
dependency, to stay consistent with the engine's dependency-light design
(plan §8) — handles the common cases; anything odder returns None and the
caller decides what to do (e.g. try a strict date parser first, or reject).
"""

from __future__ import annotations

import datetime as dt
import re

_WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

_RELATIVE_UNIT_DAYS = {"day": 1, "days": 1, "week": 7, "weeks": 7}


def _next_weekday(today: dt.date, target: int) -> dt.date:
    """The next strictly-future occurrence of `target` weekday."""
    days_ahead = (target - today.weekday()) % 7
    days_ahead = days_ahead + 7 if days_ahead == 0 else days_ahead
    return today + dt.timedelta(days=days_ahead)


def parse_natural_date(text: str, today: dt.date) -> dt.date | None:
    """Parse a small set of natural-language date phrases relative to
    `today`. Returns None if nothing recognized."""
    if not text:
        return None
    s = text.strip().lower()

    if s == "today":
        return today
    if s == "tomorrow":
        return today + dt.timedelta(days=1)
    if s == "yesterday":
        return today - dt.timedelta(days=1)

    m = re.fullmatch(r"in\s+(\d+)\s*(day|days|week|weeks)", s)
    if m:
        n = int(m.group(1))
        return today + dt.timedelta(days=n * _RELATIVE_UNIT_DAYS[m.group(2)])

    m = re.fullmatch(r"(\d+)\s*(day|days|week|weeks)\s+from\s+now", s)
    if m:
        n = int(m.group(1))
        return today + dt.timedelta(days=n * _RELATIVE_UNIT_DAYS[m.group(2)])

    m = re.fullmatch(r"next\s+(\w+)", s)
    if m and m.group(1) in _WEEKDAYS:
        return _next_weekday(today, _WEEKDAYS[m.group(1)])

    m = re.fullmatch(r"this\s+(\w+)", s)
    if m and m.group(1) in _WEEKDAYS:
        target = _WEEKDAYS[m.group(1)]
        return today + dt.timedelta(days=(target - today.weekday()) % 7)

    if s in _WEEKDAYS:
        # a bare weekday name means "the next occurrence", same as "next X"
        return _next_weekday(today, _WEEKDAYS[s])

    return None
