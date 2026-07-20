"""Dependency ordering, daily packing, and the feasibility simulator."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from engine.model import Staff, Status, Task
from engine.scoring import ScoredTask

WIP_LIMIT_STAFF = 2
WIP_LIMIT_MANAGER = 3
SWITCH_PENALTY = 0.10   # ≥10% lost per context switch (plan §4)
# Tolerate up to two switch-penalties' worth of score gap before preferring
# a same-project task over a marginally higher-scored one elsewhere.
BATCH_SCORE_TOLERANCE = 1 - 2 * SWITCH_PENALTY


class CycleError(ValueError):
    pass


def topo_order(tasks: list[Task]) -> list[Task]:
    """Kahn's algorithm; raises CycleError naming the tasks involved."""
    by_id = {t.id: t for t in tasks}
    indeg = {t.id: 0 for t in tasks}
    for t in tasks:
        for dep in t.depends_on:
            if dep in by_id:
                indeg[t.id] += 1
    ready = [tid for tid, d in indeg.items() if d == 0]
    order: list[Task] = []
    while ready:
        tid = ready.pop(0)
        order.append(by_id[tid])
        for t in tasks:
            if tid in t.depends_on:
                indeg[t.id] -= 1
                if indeg[t.id] == 0:
                    ready.append(t.id)
    if len(order) != len(tasks):
        stuck = sorted(set(by_id) - {t.id for t in order})
        raise CycleError("dependency cycle involving task ids %s" % stuck)
    return order


@dataclass
class DayPlan:
    staff_id: int
    entries: list[tuple[int, float]] = field(default_factory=list)  # (task_id, hours)
    hours_free: float = 0.0
    switches: int = 0
    distinct_projects: int = 0
    wip_limit: int = 0

    @property
    def at_wip_cap(self) -> bool:
        """True once the day touches as many distinct projects as this
        person's WIP cap allows — the real WIP signal, not switch count."""
        return self.wip_limit > 0 and self.distinct_projects >= self.wip_limit


def pack_day(
    scored: list[ScoredTask],
    staff: Staff,
    hours_available: float | None = None,
) -> DayPlan:
    """Fill one person's day from the scored queue, WIP-capped and
    batching-aware: after each pick, same-project tasks get first refusal
    before the queue moves on, because a context switch costs ~10%.
    """
    hours = hours_available if hours_available is not None \
        else staff.available_hours_per_day
    wip = WIP_LIMIT_MANAGER if staff.is_manager else WIP_LIMIT_STAFF
    plan = DayPlan(staff_id=staff.id, wip_limit=wip)
    queue = [s for s in scored
             if not s.dead
             and s.task.assignee_id == staff.id
             and s.task.status in (Status.TODO, Status.DOING)
             # substantively finished-but-unmarked work needs no time today
             and not (s.task.has_estimate and s.task.remaining_hours() <= 0)]
    picked_projects: list[int] = []
    used: set[int] = set()

    def take(s: ScoredTask) -> None:
        nonlocal hours
        chunk = min(s.task.remaining_hours() or 0.5, hours)
        if picked_projects and s.task.project_id != picked_projects[-1]:
            plan.switches += 1
            chunk = min(chunk, hours - hours * SWITCH_PENALTY)
        plan.entries.append((s.task.id, round(chunk, 2)))
        picked_projects.append(s.task.project_id)
        used.add(s.task.id)
        hours -= chunk

    while hours > 0.25 and len({p for p in picked_projects}) <= wip:
        # next unpicked task, preferring the current project when close in score
        candidates = [s for s in queue if s.task.id not in used]
        if not candidates:
            break
        best = candidates[0]
        if picked_projects:
            same = [s for s in candidates
                    if s.task.project_id == picked_projects[-1]]
            if same and same[0].score >= best.score * BATCH_SCORE_TOLERANCE:
                best = same[0]      # batching beats a marginal score edge
        if len({*picked_projects, best.task.project_id}) > wip:
            break
        take(best)
    plan.hours_free = round(max(hours, 0.0), 2)
    plan.distinct_projects = len(set(picked_projects))
    return plan


def compute_criticality(tasks: list[Task], slack_scale_hours: float = 24.0) -> dict[int, float]:
    """Zero-slack (critical-path) membership per PROJECT_PLAN.md §4's
    "is the task on a project's critical path?" definition, via forward/
    backward CPM passes over each project's dependency subgraph, in hours.

    Returns task id -> criticality in [0, 1]: 1.0 at zero slack, decaying
    to 0.0 by slack_scale_hours of float. Cross-project dependencies are
    treated as boundary conditions (their own slack isn't computed here).
    """
    open_tasks = [t for t in tasks if t.status != Status.DONE]
    by_id = {t.id: t for t in open_tasks}
    by_project: dict[int, list[Task]] = {}
    for t in open_tasks:
        by_project.setdefault(t.project_id, []).append(t)

    out: dict[int, float] = {}
    for project_tasks in by_project.values():
        ids = {t.id for t in project_tasks}
        try:
            order = topo_order(project_tasks)
        except CycleError:
            for t in project_tasks:
                out[t.id] = 0.0
            continue

        earliest_start: dict[int, float] = {}
        earliest_finish: dict[int, float] = {}
        for t in order:
            deps_in_project = [d for d in t.depends_on if d in ids]
            earliest_start[t.id] = max(
                (earliest_finish[d] for d in deps_in_project), default=0.0)
            earliest_finish[t.id] = earliest_start[t.id] + t.remaining_hours()

        horizon = max(earliest_finish.values(), default=0.0)
        dependents: dict[int, list[int]] = {t.id: [] for t in project_tasks}
        for t in order:
            for d in t.depends_on:
                if d in dependents:
                    dependents[d].append(t.id)

        latest_finish: dict[int, float] = {}
        latest_start: dict[int, float] = {}
        for t in reversed(order):
            successors = dependents[t.id]
            latest_finish[t.id] = min(
                (latest_start[s] for s in successors), default=horizon)
            latest_start[t.id] = latest_finish[t.id] - t.remaining_hours()

        for t in project_tasks:
            slack = max(latest_start[t.id] - earliest_start[t.id], 0.0)
            out[t.id] = max(1.0 - slack / slack_scale_hours, 0.0)
    return out


@dataclass
class WeekLoad:
    """One person's assigned load in one future week, vs. capacity (plan
    §11 item 5 — a forward capacity timeline, Asana-Workload-style)."""
    week_start: dt.date
    load_hours: float
    capacity_hours: float

    @property
    def over_capacity(self) -> bool:
        return self.capacity_hours > 0 and self.load_hours > self.capacity_hours

    @property
    def pct(self) -> int:
        """Bar-fill percentage, capped at 100 — over_capacity carries the
        "how far over" signal instead, so the bar never overflows its track."""
        if self.capacity_hours <= 0:
            return 0
        return min(round(self.load_hours / self.capacity_hours * 100), 100)


def weekly_load(
    scored: list[ScoredTask],
    staff: list[Staff],
    today: dt.date,
    weeks: int = 6,
    uplifts: dict[int, float] | None = None,
) -> dict[int, list[WeekLoad]]:
    """Per person, per week: assigned remaining hours bucketed by the week
    containing each task's effective deadline, against that week's available
    capacity (available_hours_per_day × 5).

    Overdue tasks land in the current week (they're due *now*). Tasks whose
    deadline falls beyond the horizon pile into the last week, still visible
    rather than silently dropped. Tasks with no effective deadline (slow-burn,
    undated work) are excluded — this is a *dated* capacity view; undated
    pressure already shows up via staleness scoring elsewhere.
    """
    from engine.sprint import week_start as _week_start  # local: avoid a module cycle

    uplifts = uplifts or {}
    starts = [_week_start(today) + dt.timedelta(weeks=i) for i in range(weeks)]
    start_set = set(starts)
    by_staff: dict[int, dict[dt.date, float]] = {p.id: {ws: 0.0 for ws in starts} for p in staff}

    for s in scored:
        if s.dead or s.task.assignee_id not in by_staff or s.effective_deadline is None:
            continue
        remaining = s.task.remaining_hours(uplifts.get(s.task.id, 1.0))
        if remaining <= 0:
            continue
        bucket = _week_start(max(s.effective_deadline, today))
        if bucket not in start_set:
            bucket = starts[-1]
        by_staff[s.task.assignee_id][bucket] += remaining

    capacity = {p.id: round(p.available_hours_per_day * 5, 1) for p in staff}
    return {
        p.id: [WeekLoad(week_start=ws, load_hours=round(by_staff[p.id][ws], 1),
                        capacity_hours=capacity[p.id])
              for ws in starts]
        for p in staff
    }


@dataclass
class ProjectForecast:
    project_id: int
    finish_date: dt.date | None
    deadline: dt.date | None
    slip_days: int          # positive = misses deadline by this many days
    remaining_hours: float


def feasibility(
    scored: list[ScoredTask],
    staff: list[Staff],
    today: dt.date,
    horizon_days: int = 400,
    uplifts: dict[int, float] | None = None,
) -> list[ProjectForecast]:
    """Forward-simulate the whole portfolio day by day at real capacity,
    in score order, respecting dependencies and assignments. Answers:
    when does each project actually finish, and by how much does it slip?

    Weekends are skipped (Mon–Fri work). Unassigned tasks draw from a
    shared pool equal to the sum of everyone's spare capacity.
    """
    uplifts = uplifts or {}
    remaining = {
        s.task.id: s.task.remaining_hours(uplifts.get(s.task.id, 1.0))
        for s in scored if not s.dead}
    task_of = {s.task.id: s.task for s in scored}
    order = [s.task.id for s in scored if not s.dead]
    finish: dict[int, dt.date] = {}
    day = today
    for _ in range(horizon_days):
        if all(v <= 0.01 for v in remaining.values()):
            break
        if day.weekday() < 5:
            capacity = {p.id: p.available_hours_per_day for p in staff}
            pool = sum(capacity.values()) * 0.25
            # Finish-to-start at day granularity: work completed today only
            # unlocks its dependents tomorrow, so snapshot now.
            done_at_start = {tid for tid, v in remaining.items() if v <= 0.01}
            for tid in order:
                if remaining.get(tid, 0) <= 0.01:
                    continue
                t = task_of[tid]
                deps_done = all(d in done_at_start
                                for d in t.depends_on if d in remaining)
                if not deps_done:
                    continue
                if t.assignee_id in capacity:
                    give = min(capacity[t.assignee_id], remaining[tid])
                    capacity[t.assignee_id] -= give
                else:
                    give = min(pool, remaining[tid])
                    pool -= give
                remaining[tid] -= give
                if remaining[tid] <= 0.01:
                    finish[tid] = day
        day += dt.timedelta(days=1)

    projects: dict[int, list[int]] = {}
    for s in scored:
        projects.setdefault(s.task.project_id, []).append(s.task.id)
    out = []
    for pid, tids in projects.items():
        open_tids = [t for t in tids if t in remaining]
        if not open_tids:
            continue
        unfinished = [t for t in open_tids if remaining.get(t, 0) > 0.01]
        fdate = None if unfinished else max(
            (finish[t] for t in open_tids if t in finish), default=today)
        project_deadlines = [s.effective_deadline for s in scored
                            if s.task.project_id == pid and s.effective_deadline]
        deadline = min(project_deadlines) if project_deadlines else None
        slip = 0
        if deadline:
            slip = ((fdate or (today + dt.timedelta(days=horizon_days)))
                    - deadline).days
        out.append(ProjectForecast(
            project_id=pid, finish_date=fdate, deadline=deadline,
            slip_days=max(slip, 0) if deadline else 0,
            remaining_hours=round(sum(remaining.get(t, 0) for t in open_tids), 1)))
    out.sort(key=lambda f: f.slip_days, reverse=True)
    return out
