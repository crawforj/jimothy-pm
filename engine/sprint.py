"""Sprint (weekly) commit/close-out math per PROJECT_PLAN.md §2 and §8.

The week is the sprint. Committing is just recording which tasks a person
took on for the week; close-out reads back how much of that actually landed.
"""

from __future__ import annotations

import datetime as dt

from engine.model import Status, Task


def week_start(day: dt.date) -> dt.date:
    """Monday of the week containing `day`."""
    return day - dt.timedelta(days=day.weekday())


def compute_velocity(committed_tasks: list[Task],
                      uplifts: dict[int, float] | None = None) -> float:
    """Hours of committed work actually completed this sprint."""
    uplifts = uplifts or {}
    return round(sum(t.expected_hours(uplifts.get(t.id, 1.0))
                     for t in committed_tasks if t.status == Status.DONE), 2)


def committed_capacity(hours_per_person_per_day: list[float],
                        working_days: int = 5) -> float:
    """Total staff-hours available this sprint, for the commitment meter."""
    return round(sum(hours_per_person_per_day) * working_days, 2)


def roll_forward(committed_tasks: list[Task]) -> list[Task]:
    """Committed tasks that didn't finish — these simply aren't re-committed;
    the scoring queue naturally re-offers them next sprint since they're
    still open."""
    return [t for t in committed_tasks if t.status != Status.DONE]
