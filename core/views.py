import calendar
import datetime as dt
import logging

from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core import phrases
from core.models import Milestone, Project, RiskItem, ScoringSettings, Staff, Task, WorkLog
from core.services import (build_uplifts, calibration_history, get_or_create_sprint,
                           portfolio_feasibility, portfolio_scoring, project_ev_metrics,
                           project_monte_carlo)
from engine.estimate import calibration_factors
from engine.schedule import compute_criticality, pack_day, weekly_load
from engine.sprint import committed_capacity, compute_velocity, week_start

logger = logging.getLogger(__name__)


def today(request):
    today_date = dt.date.today()
    scored, staff, projects_qs, tasks_qs, uplifts = portfolio_scoring(today_date)

    task_by_id = {t.pk: t for t in tasks_qs}
    project_by_id = {p.pk: p for p in projects_qs}

    people = []
    for s in staff:
        hours_available = 0.0 if s.unavailable_on(today_date) else None
        plan = pack_day(scored, s.to_engine(), hours_available=hours_available)
        entries = []
        for tid, hours in plan.entries:
            t = task_by_id[tid]
            entries.append({
                "task": t, "hours": hours,
                "project": project_by_id.get(t.project_id),
            })
        people.append({
            "staff": s, "entries": entries,
            "hours_free": plan.hours_free,
            "over_wip": plan.at_wip_cap,
        })

    unassigned = [s for s in scored if s.task.assignee_id is None and not s.dead]
    blocked = [t for t in tasks_qs if t.status == "blocked"]
    waiting = [t for t in tasks_qs if t.status == "waiting-external"]
    needs_triage = [t for t in tasks_qs if t.est_likely is None]

    forecasts = portfolio_feasibility(scored, staff, today_date, uplifts)
    warnings = []
    for pid, fc in forecasts.items():
        if fc.slip_days > 0:
            pname = project_by_id.get(pid)
            if pname:
                warnings.append(phrases.feasibility_warning(pname.name, fc.slip_days))

    context = {
        "greeting": phrases.greeting(),
        "today": today_date,
        "people": people,
        "unassigned": unassigned[:10],
        "blocked": blocked,
        "waiting": waiting,
        "needs_triage": needs_triage,
        "triage_note": phrases.TRIAGE_NOTE,
        "warnings": warnings,
        "no_tasks_message": phrases.no_tasks_message(),
        "wip_warning": phrases.wip_warning(),
        "project_count": len(projects_qs),
        "task_count": len(tasks_qs),
    }
    return render(request, "core/today.html", context)


def week(request):
    """The sprint board: this week's commitment against real capacity,
    plus the top-scored candidates for anything not yet committed."""
    today_date = dt.date.today()
    ws = week_start(today_date)
    sprint = get_or_create_sprint(today_date)

    staff = list(Staff.objects.filter(active=True))
    committed_tasks = list(sprint.committed.select_related("project", "assignee")
                           .prefetch_related("depends_on"))
    committed_ids = {t.pk for t in committed_tasks}

    scored, _staff, projects_qs, tasks_qs, uplifts = portfolio_scoring(today_date)
    candidates = [s for s in scored
                  if s.task.id not in committed_ids and not s.dead][:15]

    e_committed = [t.to_engine() for t in committed_tasks]
    committed_uplifts = build_uplifts(e_committed)
    committed_hours = round(sum(t.expected_hours(committed_uplifts.get(t.id, 1.0))
                                for t in e_committed), 1)
    capacity_hours = committed_capacity(
        [s.to_engine().available_hours_per_day for s in staff]) if staff else 0.0

    columns = {status: [] for status in
              ("todo", "doing", "blocked", "waiting-external", "done")}
    for t in committed_tasks:
        columns[t.status].append(t)
    # A list, not a dict, so the template can iterate without needing a
    # custom filter for keys like "waiting-external" that aren't valid
    # Django template dotted-lookup tokens.
    board = [
        {"key": "todo", "label": "To do", "tasks": columns["todo"]},
        {"key": "doing", "label": "Doing", "tasks": columns["doing"]},
        {"key": "blocked", "label": "Blocked", "tasks": columns["blocked"]},
        {"key": "waiting-external", "label": "Waiting on external",
         "tasks": columns["waiting-external"]},
        {"key": "done", "label": "Done", "tasks": columns["done"]},
    ]

    context = {
        "sprint": sprint,
        "week_start": ws,
        "week_end": ws + dt.timedelta(days=6),
        "board": board,
        "candidates": candidates,
        "committed_hours": committed_hours,
        "capacity_hours": capacity_hours,
        "over_committed": capacity_hours > 0 and committed_hours > capacity_hours,
        "retro_prompt_text": phrases.retro_prompt(),
    }
    return render(request, "core/week.html", context)


@require_POST
def week_commit(request, task_id):
    """Toggle a task in/out of the current week's sprint commitment."""
    task = get_object_or_404(Task, pk=task_id)
    sprint = get_or_create_sprint()
    if sprint.committed.filter(pk=task.pk).exists():
        sprint.committed.remove(task)
    else:
        sprint.committed.add(task)
    return redirect("week")


@require_POST
def week_closeout(request):
    """Friday close-out: compute velocity from this sprint's committed
    tasks and save the retro note."""
    sprint = get_or_create_sprint()
    committed_tasks = list(sprint.committed.all())
    e_committed = [t.to_engine() for t in committed_tasks]
    uplifts = build_uplifts(e_committed)
    sprint.velocity_actual = compute_velocity(e_committed, uplifts)
    sprint.retro_note = request.POST.get("retro_note", "").strip()
    sprint.save()
    return redirect("week")


def month(request):
    today_date = dt.date.today()
    horizon = today_date + dt.timedelta(weeks=8)
    milestones = list(Milestone.objects.filter(
        due_date__gte=today_date, due_date__lte=horizon, done=False
    ).select_related("project").order_by("due_date"))

    tasks_qs = list(Task.objects.exclude(status="done").prefetch_related("depends_on"))
    e_tasks = [t.to_engine() for t in tasks_qs]
    try:
        criticality = compute_criticality(e_tasks)
    except Exception:
        logger.exception("Jimothy month-view criticality calc failed")
        criticality = {}

    rows = []
    for m in milestones:
        m_tasks = [t for t in tasks_qs if t.milestone_id == m.pk]
        e_m_tasks = [t.to_engine() for t in m_tasks]
        uplifts = build_uplifts(e_m_tasks)
        remaining = sum(et.remaining_hours(uplifts.get(et.id, 1.0)) for et in e_m_tasks)
        rows.append({
            "milestone": m,
            "days_remaining": (m.due_date - today_date).days,
            "open_tasks": len(m_tasks),
            "remaining_hours": round(remaining, 1),
            "on_critical_path": any(criticality.get(t.pk, 0.0) >= 0.99 for t in m_tasks),
        })

    context = {"today": today_date, "horizon": horizon, "rows": rows}
    return render(request, "core/month.html", context)


def quarter(request):
    today_date = dt.date.today()
    q_start_month = ((today_date.month - 1) // 3) * 3 + 1
    q_start = dt.date(today_date.year, q_start_month, 1)
    q_end_month = q_start_month + 2
    q_end = dt.date(today_date.year, q_end_month,
                    calendar.monthrange(today_date.year, q_end_month)[1])

    scored, staff, projects_qs, tasks_qs, uplifts = portfolio_scoring(today_date)
    forecasts = portfolio_feasibility(scored, staff, today_date, uplifts)

    rows = []
    for p in projects_qs:
        ev = project_ev_metrics(p, today_date)
        risks = list(RiskItem.objects.filter(
            project=p, open=True, trigger_date__gte=q_start, trigger_date__lte=q_end))
        fc = forecasts.get(p.pk)
        rows.append({
            "project": p,
            "ev": ev,
            "ev_summary": phrases.ev_summary(ev.spi, ev.cpi) if ev else None,
            "slip_days": fc.slip_days if fc else 0,
            "risks": risks,
        })
    rows.sort(key=lambda r: (-r["project"].priority_class, -r["slip_days"]))

    context = {"today": today_date, "q_start": q_start, "q_end": q_end, "rows": rows}
    return render(request, "core/quarter.html", context)


def year(request):
    today_date = dt.date.today()
    horizon = today_date + dt.timedelta(days=365)
    projects_qs = list(Project.objects.exclude(status__in=("done", "shelved")))

    dated_projects = sorted(
        (p for p in projects_qs if p.deadline and today_date <= p.deadline <= horizon),
        key=lambda p: p.deadline)
    ongoing_projects = [p for p in projects_qs if not p.deadline]

    total_budget = sum((p.budget_staff_days for p in projects_qs if p.budget_staff_days), 0.0)
    total_consumed = 0.0
    for p in projects_qs:
        ev = project_ev_metrics(p, today_date)
        if ev:
            total_consumed += ev.ac

    milestone_dates = list(Milestone.objects.filter(
        due_date__gte=today_date, due_date__lte=horizon, done=False
    ).values_list("due_date", flat=True))
    all_dates = [p.deadline for p in dated_projects] + list(milestone_dates)

    months = []
    m = dt.date(today_date.year, today_date.month, 1)
    for _ in range(12):
        months.append(m)
        m = (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    counts = {m: sum(1 for d in all_dates if d.year == m.year and d.month == m.month)
              for m in months}
    max_count = max(counts.values(), default=0)

    context = {
        "today": today_date, "horizon": horizon,
        "dated_projects": dated_projects, "ongoing_projects": ongoing_projects,
        "total_budget": round(total_budget, 1) if total_budget else None,
        "total_consumed": round(total_consumed, 1),
        "density": [{"month": m, "count": c,
                    "pct": round(c / max_count * 100) if max_count else 0}
                   for m, c in counts.items()],
    }
    return render(request, "core/year.html", context)


def projects(request):
    today_date = dt.date.today()
    scored, staff, projects_qs, tasks_qs, uplifts = portfolio_scoring(today_date)
    forecasts = portfolio_feasibility(scored, staff, today_date, uplifts)

    all_projects = list(Project.objects.all().order_by("-priority_class", "deadline"))
    rows = []
    for p in all_projects:
        ev = project_ev_metrics(p, today_date)
        fc = forecasts.get(p.pk)
        rows.append({
            "project": p,
            "ev": ev,
            "ev_summary": phrases.ev_summary(ev.spi, ev.cpi) if ev else None,
            "slip_days": fc.slip_days if fc else 0,
            "open_task_count": sum(1 for t in tasks_qs if t.project_id == p.pk),
        })
    return render(request, "core/projects.html", {"rows": rows, "today": today_date})


def staff(request):
    today_date = dt.date.today()
    staff_qs = list(Staff.objects.all().order_by("-is_manager", "name"))
    factors = calibration_factors(calibration_history())

    scored, _staff, _projects_qs, _tasks_qs, uplifts = portfolio_scoring(today_date)
    active_staff = [s for s in staff_qs if s.active]
    load_by_staff = weekly_load(scored, [s.to_engine() for s in active_staff],
                                today_date, weeks=6, uplifts=uplifts)

    rows = []
    for s in staff_qs:
        upcoming = list(s.unavailability.filter(end_date__gte=today_date)
                        .order_by("start_date")[:5])
        tag_factors = {tag: f for (sid, tag), f in factors.items()
                       if sid == s.pk and tag is not None}
        rows.append({
            "staff": s,
            "available_hours_per_day": round(s.nominal_hours_per_day * s.focus_factor, 2),
            "unavailable_today": s.unavailable_on(today_date),
            "upcoming_unavailability": upcoming,
            "overall_factor": factors.get((s.pk, None)),
            "tag_factors": tag_factors,
            "weekly_load": load_by_staff.get(s.pk, []),
        })
    return render(request, "core/staff.html", {"rows": rows, "today": today_date})


def reports_index(request):
    projects_qs = list(Project.objects.exclude(status__in=("done", "shelved"))
                       .order_by("name"))
    return render(request, "core/reports_index.html", {"projects": projects_qs})


def report_detail(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    today_date = dt.date.today()
    ev = project_ev_metrics(project, today_date)
    milestones = list(project.milestones.all().order_by("due_date"))
    risks = list(project.risks.filter(open=True).order_by("trigger_date"))
    tasks = list(Task.objects.filter(project=project).select_related("assignee"))
    blockers = [t for t in tasks if t.status in ("blocked", "waiting-external")]
    recent_done = sorted(
        (t for t in tasks if t.status == "done" and t.completed),
        key=lambda t: t.completed, reverse=True)[:10]
    forecast = project_monte_carlo(project, today_date)

    context = {
        "project": project, "ev": ev,
        "ev_summary": phrases.ev_summary(ev.spi, ev.cpi) if ev else None,
        "milestones": milestones, "risks": risks,
        "blockers": blockers, "recent_done": recent_done,
        "forecast": forecast,
        "today": today_date,
    }
    return render(request, "core/report_detail.html", context)


def _focus_redirect(request):
    staff_id = request.POST.get("staff_id") or request.GET.get("staff")
    url = reverse("focus")
    return url + ("?staff=%s" % staff_id if staff_id else "")


def focus(request):
    """The "what's my ONE thing right now" view (plan §7b): the single
    top-scored task for one person, nothing else. Anti-doomscroll by design
    — the rest of the queue is deliberately not shown here."""
    today_date = dt.date.today()
    scored, _staff, _projects_qs, tasks_qs, _uplifts = portfolio_scoring(today_date)
    task_by_id = {t.pk: t for t in tasks_qs}

    staff_id = request.GET.get("staff")
    person = None
    if staff_id and staff_id.isdigit():
        person = Staff.objects.filter(pk=staff_id, active=True).first()
    if person is None:
        person = (Staff.objects.filter(active=True, is_manager=True).first()
                 or Staff.objects.filter(active=True).first())

    entry = None
    started_at = None
    if person:
        skip_key = "focus_skipped_%s_%s" % (person.pk, today_date.isoformat())
        skipped = set(request.session.get(skip_key, []))
        hours_available = 0.0 if person.unavailable_on(today_date) else None
        plan = pack_day(scored, person.to_engine(), hours_available=hours_available)
        for tid, hours in plan.entries:
            if tid not in skipped:
                entry = {"task": task_by_id[tid], "hours": hours}
                break
        if entry:
            started_at = request.session.get("focus_start_%s" % entry["task"].pk)

    context = {
        "person": person,
        "staff_list": list(Staff.objects.filter(active=True)),
        "entry": entry,
        "started_at": started_at,
        "no_task_message": phrases.no_tasks_message(),
    }
    return render(request, "core/focus.html", context)


@require_POST
def focus_start(request, task_id):
    request.session["focus_start_%s" % task_id] = dt.datetime.now().isoformat()
    return redirect(_focus_redirect(request))


@require_POST
def focus_done(request, task_id):
    """Mark the task done and, if it was timed, log the elapsed hours as a
    WorkLog entry and roll them into actual_hours — feeding straight into
    calibration (§5) and earned value (§6) without a separate data-entry step."""
    task = get_object_or_404(Task, pk=task_id)
    started_iso = request.session.pop("focus_start_%s" % task_id, None)
    elapsed_hours = 0.0
    if started_iso:
        started = dt.datetime.fromisoformat(started_iso)
        elapsed_hours = round((dt.datetime.now() - started).total_seconds() / 3600.0, 2)

    task.status = "done"
    task.completed = dt.date.today()
    task.last_touched = dt.date.today()
    if elapsed_hours > 0:
        task.actual_hours = (task.actual_hours or 0.0) + elapsed_hours
        if task.assignee_id:
            WorkLog.objects.create(task=task, staff_id=task.assignee_id,
                                   date=dt.date.today(), hours=elapsed_hours)
    task.save()
    return redirect(_focus_redirect(request))


@require_POST
def focus_skip(request, task_id):
    """Not a rejection of the task, just "not this one, right now" — skips
    it for the rest of today's Focus Mode session only."""
    person_id = request.POST.get("staff_id")
    if person_id:
        key = "focus_skipped_%s_%s" % (person_id, dt.date.today().isoformat())
        skipped = request.session.get(key, [])
        if task_id not in skipped:
            skipped.append(task_id)
        request.session[key] = skipped
    return redirect(_focus_redirect(request))


def settings_view(request):
    settings_obj = ScoringSettings.load()
    if request.method == "POST":
        if request.POST.get("reset") == "1":
            from engine.scoring import Weights
            defaults = Weights()
            for field in ("urgency", "priority", "criticality", "staleness", "unblock"):
                setattr(settings_obj, field, getattr(defaults, field))
        else:
            for field in ("urgency", "priority", "criticality", "staleness", "unblock"):
                try:
                    setattr(settings_obj, field, float(request.POST.get(field, "")))
                except (TypeError, ValueError):
                    pass
        settings_obj.save()
        return redirect("settings")
    return render(request, "core/settings.html", {"settings": settings_obj})
