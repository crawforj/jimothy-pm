"""Shared helpers that bridge Django querysets into engine calls.

Views should not talk to the engine directly for anything reused across more
than one page — that logic lives here instead, so Today/Week/Month/Quarter/
Year/Projects/Reports can't quietly drift out of sync with each other.
"""

from __future__ import annotations

import datetime as dt
import logging

from core.models import CalendarEvent, Project, ScoringSettings, Sprint, Staff, Task
from engine.calendar_capacity import DayCapacity, day_capacity
from engine.estimate import HistoryRecord, calibration_factors, pert_expected, uplift_for
from engine.model import Task as ETask
from engine.schedule import compute_criticality, feasibility
from engine.scoring import ScoredTask, score_tasks
from engine.sprint import roll_forward, week_start

logger = logging.getLogger(__name__)


def calibration_history() -> list[HistoryRecord]:
    """Completed-task estimate-vs-actual history, for reference-class
    calibration (plan §5)."""
    completed = Task.objects.filter(
        status="done", est_likely__isnull=False, actual_hours__gt=0)
    history = []
    for t in completed:
        tags = [tag.strip() for tag in t.tags.split(",") if tag.strip()]
        estimated = pert_expected(
            t.est_optimistic if t.est_optimistic is not None else t.est_likely,
            t.est_likely,
            t.est_pessimistic if t.est_pessimistic is not None else t.est_likely,
        )
        history.append(HistoryRecord(staff_id=t.assignee_id, tags=tags,
                                     estimated_hours=estimated,
                                     actual_hours=t.actual_hours))
    return history


def build_uplifts(e_tasks: list[ETask]) -> dict[int, float]:
    """task id -> calibration uplift, for every task in e_tasks."""
    factors = calibration_factors(calibration_history())
    return {t.id: uplift_for(factors, t.assignee_id, t.tags) for t in e_tasks}


def portfolio_scoring(today_date: dt.date):
    """The shared scoring pass: every open task on every non-done/shelved
    project, scored and ranked. Returns
    (scored, staff, projects_qs, tasks_qs, uplifts) — Django model instances
    alongside the engine's scored output, so callers can join back to
    templates without a second query.
    """
    staff = list(Staff.objects.filter(active=True))
    projects_qs = list(Project.objects.exclude(status__in=("done", "shelved")))
    tasks_qs = list(Task.objects.exclude(status="done")
                    .prefetch_related("depends_on"))
    try:
        e_projects = [p.to_engine() for p in projects_qs]
        e_tasks = [t.to_engine() for t in tasks_qs]
        uplifts = build_uplifts(e_tasks)
        criticality = compute_criticality(e_tasks)
        weights = ScoringSettings.load().to_weights()
        scored = score_tasks(e_tasks, e_projects, today_date, weights=weights,
                             uplifts=uplifts, criticality=criticality)
    except Exception:
        logger.exception("Jimothy portfolio scoring failed")
        uplifts, scored = {}, []
    return scored, staff, projects_qs, tasks_qs, uplifts


def portfolio_feasibility(scored: list[ScoredTask], staff: list[Staff],
                          today_date: dt.date, uplifts: dict[int, float]) -> dict[int, object]:
    """project id -> ProjectForecast, or {} if it can't be computed."""
    if not staff or not scored:
        return {}
    try:
        forecasts = feasibility(scored, [s.to_engine() for s in staff],
                                today_date, uplifts=uplifts)
    except Exception:
        logger.exception("Jimothy feasibility check failed")
        return {}
    return {fc.project_id: fc for fc in forecasts}


def staff_day_capacity(staff: Staff, day: dt.date) -> DayCapacity | None:
    """Real calendar-derived capacity for one staff member on one day
    (plan §7c), or None if nothing is synced for them -- callers then fall
    back to the existing flat focus-factor default, same shape as
    unavailable_on()."""
    events = CalendarEvent.objects.filter(staff=staff, start__date__lte=day, end__date__gte=day)
    if not events.exists():
        return None
    try:
        blocks = [e.to_busy_block() for e in events]
        return day_capacity(day, staff.nominal_hours_per_day, blocks)
    except Exception:
        logger.exception("Jimothy calendar capacity calc failed for staff %s", staff.pk)
        return None


def get_or_create_sprint(today_date: dt.date | None = None) -> Sprint:
    """The current week's Sprint, auto-carrying forward any of the previous
    week's committed-but-unfinished tasks the first time this week's Sprint
    is touched (plan §11 item 2 — Linear's Cycles do this automatically;
    Jimothy previously required a manual re-commit)."""
    today_date = today_date or dt.date.today()
    ws = week_start(today_date)
    sprint, created = Sprint.objects.get_or_create(week_start=ws)
    if created:
        prev = Sprint.objects.filter(week_start=ws - dt.timedelta(days=7)).first()
        if prev:
            prev_committed = list(prev.committed.all())
            incomplete_ids = {t.id for t in roll_forward([t.to_engine() for t in prev_committed])}
            carryover = [t for t in prev_committed if t.pk in incomplete_ids]
            if carryover:
                sprint.committed.add(*carryover)
    return sprint


def project_ev_metrics(project: Project, today_date: dt.date):
    """Earned-value metrics for one project, over *all* its tasks (done
    included — EV needs completed work, unlike the live scoring queue)."""
    from engine.ev import project_ev  # local import: keep the EV module optional-ish

    tasks = list(Task.objects.filter(project=project))
    e_tasks = [t.to_engine() for t in tasks]
    uplifts = build_uplifts(e_tasks)
    try:
        return project_ev(e_tasks, project.to_engine(), today_date, uplifts=uplifts)
    except Exception:
        logger.exception("Jimothy EV calc failed for project %s", project.pk)
        return None


def project_weekly_throughput(project: Project, today_date: dt.date, weeks: int = 12) -> list[float]:
    """Hours of this project's work actually completed, one entry per of
    the last `weeks` full weeks (oldest first, current in-progress week not
    included) — the raw material Monte Carlo forecasting samples from.
    Weeks with no completions are real zeros, not gaps."""
    starts = [week_start(today_date) - dt.timedelta(weeks=i) for i in range(weeks, 0, -1)]
    by_week = dict.fromkeys(starts, 0.0)
    completed = Task.objects.filter(project=project, status="done",
                                    completed__isnull=False, actual_hours__gt=0)
    for t in completed:
        ws = week_start(t.completed)
        if ws in by_week:
            by_week[ws] += t.actual_hours
    return [round(by_week[ws], 2) for ws in starts]


def project_monte_carlo(project: Project, today_date: dt.date):
    """P50/P85 completion-date estimate for a project's remaining open
    work, sampled from its own completed-task throughput history (plan §11
    item 7). Returns None below the function's own ≥4-weeks-of-history
    floor — a real "not enough data yet" rather than a misleading guess."""
    from engine.montecarlo import completion_percentiles

    tasks = list(Task.objects.filter(project=project).exclude(status="done"))
    e_tasks = [t.to_engine() for t in tasks]
    uplifts = build_uplifts(e_tasks)
    remaining_hours = sum(t.remaining_hours(uplifts.get(t.id, 1.0)) for t in e_tasks)
    history = project_weekly_throughput(project, today_date)
    try:
        percentiles = completion_percentiles(remaining_hours, history, today_date,
                                             percentiles=(50, 85))
    except ValueError:
        return None   # <4 weeks of history, or all-zero throughput
    except Exception:
        logger.exception("Jimothy Monte Carlo forecast failed for project %s", project.pk)
        return None
    # named keys, not the engine's raw {50: date, 85: date} — Django templates
    # can't do dict[int] lookup via dotted access
    return {"p50": percentiles[50], "p85": percentiles[85]}


def project_burndown(project: Project, today_date: dt.date, weeks: int = 12):
    """Remaining-work history for the Reports page's burndown chart.
    Reconstructed from today's snapshot plus project_weekly_throughput's
    existing weekly-completed-hours history (engine.ev.burndown_series),
    not by replaying historical task/WorkLog state. None only if the
    project has no tasks at all -- unlike Monte Carlo, no minimum-history
    floor, since even an early project with all-zero throughput still has
    a legitimate (flat) line to show."""
    from engine.ev import burndown_series

    tasks = list(Task.objects.filter(project=project))
    if not tasks:
        return None
    open_tasks = [t.to_engine() for t in tasks if t.status != "done"]
    uplifts = build_uplifts(open_tasks)
    remaining_now_hours = sum(t.remaining_hours(uplifts.get(t.id, 1.0)) for t in open_tasks)
    history = project_weekly_throughput(project, today_date, weeks=weeks)
    week_starts = [week_start(today_date) - dt.timedelta(weeks=i) for i in range(weeks, 0, -1)]
    try:
        return burndown_series(remaining_now_hours, history, week_starts,
                               today_date, project.deadline)
    except Exception:
        logger.exception("Jimothy burndown calc failed for project %s", project.pk)
        return None
