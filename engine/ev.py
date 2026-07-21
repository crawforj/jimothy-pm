"""Simple earned value (PV/EV/AC, SPI/CPI) per PROJECT_PLAN.md §6.

Deliberately simple, not a full EVM implementation: PV is what should have
been done by today going purely off deadlines, EV is what's actually done
(at its estimated size, not its actual size), AC is what was actually spent.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from engine.model import Project, Status, Task

HOURS_PER_STAFF_DAY = 8.0


@dataclass
class EVMetrics:
    pv: float   # planned value, staff-days
    ev: float   # earned value, staff-days
    ac: float   # actual cost, staff-days
    spi: float | None   # EV / PV; None if PV is 0 (nothing was due yet)
    cpi: float | None   # EV / AC; None if AC is 0 (nothing logged yet)


def project_ev(tasks: list[Task], project: Project, today: dt.date,
                uplifts: dict[int, float] | None = None) -> EVMetrics:
    """EV metrics for one project's tasks (already filtered to project_id).

    A task counts toward PV once its own deadline (falling back to the
    project deadline) has passed; toward EV once it's done, at its PERT
    expected size; AC is always its logged actual hours.
    """
    uplifts = uplifts or {}
    pv_hours = ev_hours = ac_hours = 0.0
    for t in tasks:
        deadline = t.deadline or project.deadline
        expected = t.expected_hours(uplifts.get(t.id, 1.0))
        if deadline and deadline <= today:
            pv_hours += expected
        if t.status == Status.DONE:
            ev_hours += expected
        ac_hours += t.actual_hours

    pv = round(pv_hours / HOURS_PER_STAFF_DAY, 2)
    ev = round(ev_hours / HOURS_PER_STAFF_DAY, 2)
    ac = round(ac_hours / HOURS_PER_STAFF_DAY, 2)
    spi = round(ev / pv, 2) if pv > 0 else None
    cpi = round(ev / ac, 2) if ac > 0 else None
    return EVMetrics(pv=pv, ev=ev, ac=ac, spi=spi, cpi=cpi)


@dataclass
class BurndownPoint:
    date: dt.date           # a week's start, except the final point (today)
    remaining: float        # staff-days remaining as of this date
    ideal: float | None     # straight-line reference to 0 at the deadline


def burndown_series(
    remaining_now_hours: float,
    weekly_throughput_hours: list[float],
    week_starts: list[dt.date],
    today: dt.date,
    deadline: dt.date | None,
) -> list[BurndownPoint]:
    """Reconstructs a remaining-work history from today's snapshot plus
    weekly completed-hours history (core.services.project_weekly_throughput
    -- the same input Monte Carlo forecasting already uses), rather than
    replaying historical task/WorkLog state by date.

    Remaining work only decreases via completions here (no scope-growth
    modeling -- the same simplifying assumption project_monte_carlo already
    makes): the amount remaining at the start of week i is today's
    remaining amount plus everything completed from the start of week i
    through today. week_starts must be oldest-first and cover only *full*
    weeks (project_weekly_throughput's own convention -- the current,
    in-progress week isn't one of them); this function appends one final
    point for `today` itself so the line actually ends at today's real
    remaining value, not last full week's.

    `ideal` is a simple two-point reference line (the oldest reconstructed
    remaining value, straight down to 0 at the deadline) -- not a stored
    scope baseline, just the standard simplified-burndown "ideal pace"
    convention. None throughout if there's no deadline.
    """
    n = len(week_starts)
    remaining_hours = [0.0] * n
    running = remaining_now_hours
    for i in range(n - 1, -1, -1):
        running += weekly_throughput_hours[i]
        remaining_hours[i] = running

    all_dates = week_starts + [today]
    all_remaining_hours = remaining_hours + [remaining_now_hours]

    if deadline is None or not all_dates:
        ideal_hours = [None] * len(all_dates)
    else:
        start_value = all_remaining_hours[0]
        span_days = (deadline - all_dates[0]).days
        if span_days <= 0:
            ideal_hours = [0.0] * len(all_dates)
        else:
            ideal_hours = [
                max(start_value * (1 - (d - all_dates[0]).days / span_days), 0.0)
                for d in all_dates
            ]

    return [
        BurndownPoint(
            date=d,
            remaining=round(all_remaining_hours[i] / HOURS_PER_STAFF_DAY, 2),
            ideal=round(ideal_hours[i] / HOURS_PER_STAFF_DAY, 2) if ideal_hours[i] is not None else None,
        )
        for i, d in enumerate(all_dates)
    ]
