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
