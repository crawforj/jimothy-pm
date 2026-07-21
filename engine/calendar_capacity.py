"""Real calendar-derived daily capacity (plan §7c), pure Python -- no
Django, no network, no OAuth. Whatever fetched the events (Microsoft Graph,
Google Calendar, anything else) lives in core/calendarsync/ instead; this
module only turns a day's busy/free blocks into an hours number."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum


class BusyStatus(str, Enum):
    FREE = "free"
    TENTATIVE = "tentative"
    BUSY = "busy"
    OUT_OF_OFFICE = "oof"


@dataclass
class BusyBlock:
    start: dt.datetime
    end: dt.datetime
    busy_status: BusyStatus
    all_day: bool = False


@dataclass
class DayCapacity:
    available_hours: float
    meeting_hours: float
    has_tentative: bool


_COUNTS_AGAINST_CAPACITY = (BusyStatus.BUSY, BusyStatus.OUT_OF_OFFICE)


def _merge_intervals(intervals: list[tuple[dt.datetime, dt.datetime]]) -> list[tuple[dt.datetime, dt.datetime]]:
    """Union overlapping/adjacent (start, end) pairs so double-booked time
    isn't counted twice."""
    if not intervals:
        return []
    ordered = sorted(intervals)
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def day_capacity(
    day: dt.date,
    nominal_hours_per_day: float,
    busy_blocks: list[BusyBlock],
    workday_start: dt.time = dt.time(8, 0),
    workday_end: dt.time = dt.time(17, 0),
    interruption_haircut: float = 0.85,
) -> DayCapacity:
    """§7c: available hours = nominal - actual meeting hours, with a smaller
    interruption haircut applied to the non-meeting remainder. Only Busy/
    Out-of-Office blocks count against capacity; Free is ignored; Tentative
    never subtracts but is flagged as a soft warning."""
    window_start = dt.datetime.combine(day, workday_start)
    window_end = dt.datetime.combine(day, workday_end)
    nominal_seconds = nominal_hours_per_day * 3600.0

    has_tentative = False
    counted_intervals: list[tuple[dt.datetime, dt.datetime]] = []
    for block in busy_blocks:
        if block.busy_status == BusyStatus.TENTATIVE:
            has_tentative = True
            continue
        if block.busy_status not in _COUNTS_AGAINST_CAPACITY:
            continue
        if block.all_day:
            counted_intervals.append((window_start, window_end))
            continue
        clipped_start = max(block.start, window_start)
        clipped_end = min(block.end, window_end)
        if clipped_end > clipped_start:
            counted_intervals.append((clipped_start, clipped_end))

    meeting_seconds = sum(
        (end - start).total_seconds() for start, end in _merge_intervals(counted_intervals))
    meeting_hours = round(min(meeting_seconds, nominal_seconds) / 3600.0, 2)

    available_hours = round(
        max(nominal_hours_per_day - meeting_hours, 0.0) * interruption_haircut, 2)

    return DayCapacity(available_hours=available_hours, meeting_hours=meeting_hours,
                       has_tentative=has_tentative)
