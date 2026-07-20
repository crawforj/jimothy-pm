"""Engine-side data model: plain dataclasses, no framework."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    TODO = "todo"
    DOING = "doing"
    BLOCKED = "blocked"
    WAITING_EXTERNAL = "waiting-external"
    DONE = "done"


class PriorityClass(int, Enum):
    CRITICAL = 4
    HIGH = 3
    NORMAL = 2
    BACKBURNER = 1


class DelayProfile(str, Enum):
    CLIFF = "cliff"          # worthless after the date (grant deadline)
    LINEAR = "linear"        # value erodes steadily
    SLOW_BURN = "slow_burn"  # no real date; staleness is the only pressure


@dataclass
class Staff:
    id: int
    name: str
    nominal_hours_per_day: float = 8.0
    focus_factor: float = 0.75  # manager default is 0.60 (plan §6b)
    is_manager: bool = False

    @property
    def available_hours_per_day(self) -> float:
        return self.nominal_hours_per_day * self.focus_factor


@dataclass
class Project:
    id: int
    name: str
    priority_class: PriorityClass = PriorityClass.NORMAL
    deadline: dt.date | None = None
    budget_staff_days: float | None = None


@dataclass
class Task:
    id: int
    project_id: int
    title: str
    status: Status = Status.TODO
    assignee_id: int | None = None
    est_optimistic: float | None = None   # hours
    est_likely: float | None = None
    est_pessimistic: float | None = None
    actual_hours: float = 0.0
    deadline: dt.date | None = None       # explicit override; else project deadline
    depends_on: list[int] = field(default_factory=list)
    delay_profile: DelayProfile = DelayProfile.LINEAR
    tags: list[str] = field(default_factory=list)
    last_touched: dt.date | None = None

    @property
    def has_estimate(self) -> bool:
        return self.est_likely is not None

    def expected_hours(self, uplift: float = 1.0) -> float:
        """PERT expected hours with a reference-class uplift applied."""
        if not self.has_estimate:
            return 0.0
        o = self.est_optimistic if self.est_optimistic is not None else self.est_likely
        p = self.est_pessimistic if self.est_pessimistic is not None else self.est_likely
        return (o + 4 * self.est_likely + p) / 6.0 * uplift

    def remaining_hours(self, uplift: float = 1.0) -> float:
        if self.status == Status.DONE:
            return 0.0
        return max(self.expected_hours(uplift) - self.actual_hours, 0.0)
