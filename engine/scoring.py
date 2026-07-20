"""Priority scoring: one number per open task, from visible ingredients.

score = w_urgency·urgency + w_priority·project_priority + w_critical·criticality
      + w_stale·staleness + w_unblock·unblock_value

Every component is normalized to [0, 1] before weighting so the weights mean
what they say. See PROJECT_PLAN.md §4.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from engine.model import DelayProfile, Project, Status, Task


@dataclass
class Weights:
    urgency: float = 4.0
    priority: float = 2.0
    criticality: float = 1.5
    staleness: float = 0.5
    unblock: float = 1.0


@dataclass
class ScoredTask:
    task: Task
    score: float
    urgency: float
    dead: bool                      # past a cliff deadline
    effective_deadline: dt.date | None
    components: dict = field(default_factory=dict)


def dependents_map(tasks: list[Task]) -> dict[int, list[int]]:
    """task id -> ids of tasks that depend on it (direct)."""
    out: dict[int, list[int]] = {t.id: [] for t in tasks}
    for t in tasks:
        for dep in t.depends_on:
            if dep in out:
                out[dep].append(t.id)
    return out


def transitive_dependents(tasks: list[Task]) -> dict[int, int]:
    """task id -> count of all downstream tasks unblocked by finishing it."""
    direct = dependents_map(tasks)
    counts: dict[int, int] = {}

    def walk(tid: int, seen: set[int]) -> set[int]:
        for d in direct.get(tid, []):
            if d not in seen:
                seen.add(d)
                walk(d, seen)
        return seen

    for t in tasks:
        counts[t.id] = len(walk(t.id, set()))
    return counts


def effective_deadlines(
    tasks: list[Task],
    projects: dict[int, Project],
    uplifts: dict[int, float] | None = None,
) -> dict[int, dt.date | None]:
    """Backward-chain deadlines through the dependency graph.

    A task's effective deadline is the earliest of its own deadline, its
    project's deadline, and — for each task that depends on it — that
    dependent's effective deadline pulled back by the dependent's remaining
    work (in calendar days at one nominal 6h focus day; a deliberate
    simplification for scoring, not scheduling).
    """
    uplifts = uplifts or {}
    by_id = {t.id: t for t in tasks}
    direct = dependents_map(tasks)
    memo: dict[int, dt.date | None] = {}

    def eff(tid: int, stack: set[int]) -> dt.date | None:
        if tid in memo:
            return memo[tid]
        if tid in stack:            # dependency cycle: no chaining, own date only
            t = by_id[tid]
            return t.deadline or _project_deadline(t, projects)
        stack = stack | {tid}
        t = by_id[tid]
        candidates: list[dt.date] = []
        own = t.deadline or _project_deadline(t, projects)
        if own:
            candidates.append(own)
        for d_id in direct.get(tid, []):
            d = by_id[d_id]
            d_eff = eff(d_id, stack)
            if d_eff:
                pullback = max(
                    round(d.remaining_hours(uplifts.get(d.id, 1.0)) / 6.0), 0)
                candidates.append(d_eff - dt.timedelta(days=pullback))
        memo[tid] = min(candidates) if candidates else None
        return memo[tid]

    return {t.id: eff(t.id, set()) for t in tasks}


def _project_deadline(task: Task, projects: dict[int, Project]) -> dt.date | None:
    p = projects.get(task.project_id)
    return p.deadline if p else None


def urgency_component(
    task: Task,
    eff_deadline: dt.date | None,
    today: dt.date,
    uplift: float = 1.0,
) -> tuple[float, bool]:
    """(urgency in [0,1], dead flag). Cost-of-delay ÷ job-size logic:
    pressure compares remaining work-days against calendar days left."""
    if task.delay_profile == DelayProfile.SLOW_BURN or eff_deadline is None:
        return 0.0, False
    days_left = (eff_deadline - today).days
    if days_left < 0:
        if task.delay_profile == DelayProfile.CLIFF:
            return 0.0, True        # dead: the date passed, the value is gone
        return 1.0, False           # overdue linear work: maximum urgency
    if task.has_estimate:
        remaining_days = task.remaining_hours(uplift) / 6.0
    else:
        # Unknown work is not zero work: assume one nominal day so an
        # unestimated task due soon still reads as urgent, not negligible.
        remaining_days = 1.0
    pressure = (remaining_days + 0.05) / max(days_left, 0.25)
    u = min(pressure, 1.0)
    if task.delay_profile == DelayProfile.CLIFF:
        # steepen near the cliff: low pressure stays low, high pressure spikes
        u = u ** 0.5 if u > 0.5 else u * (0.5 ** -0.5) * (u / 0.5) ** 1.5
        u = min(u, 1.0)
    return u, False


def score_tasks(
    tasks: list[Task],
    projects: list[Project],
    today: dt.date,
    weights: Weights | None = None,
    uplifts: dict[int, float] | None = None,
    criticality: dict[int, float] | None = None,
) -> list[ScoredTask]:
    """Score all open tasks, highest first. Done tasks are excluded.

    `criticality` is task id -> [0,1] critical-path membership, as computed
    by engine.schedule.compute_criticality(); passed in rather than computed
    here to avoid a scoring<->schedule import cycle. Callers that don't need
    it (e.g. tests) can omit it and every task scores 0.0 on this component.
    """
    w = weights or Weights()
    uplifts = uplifts or {}
    criticality = criticality or {}
    proj = {p.id: p for p in projects}
    open_tasks = [t for t in tasks if t.status != Status.DONE]
    eff = effective_deadlines(open_tasks, proj, uplifts)
    unblocks = transitive_dependents(open_tasks)
    max_unblock = max(unblocks.values(), default=0) or 1

    out: list[ScoredTask] = []
    for t in open_tasks:
        u, dead = urgency_component(t, eff[t.id], today, uplifts.get(t.id, 1.0))
        pr = (proj[t.project_id].priority_class.value - 1) / 3.0 \
            if t.project_id in proj else 0.33
        stale_days = (today - t.last_touched).days if t.last_touched else 0
        stale = min(stale_days / 30.0, 1.0)
        unblock = unblocks[t.id] / max_unblock
        crit = criticality.get(t.id, 0.0)
        components = {
            "urgency": u, "priority": pr, "criticality": crit,
            "staleness": stale, "unblock": unblock,
        }
        score = (w.urgency * u + w.priority * pr + w.criticality * crit
                 + w.staleness * stale + w.unblock * unblock)
        if dead:
            score = -1.0            # sinks to the bottom; surfaced as "dead"
        out.append(ScoredTask(
            task=t, score=score, urgency=u, dead=dead,
            effective_deadline=eff[t.id], components=components))
    out.sort(key=lambda s: s.score, reverse=True)
    return out
