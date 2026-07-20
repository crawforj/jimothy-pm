"""Seed Jimothy with a representative example portfolio.

Not exhaustive, not authoritative on dates — just varied enough (every task
status, every delay profile, every project priority class, and enough
completed-task history to activate calibration, the recurring-task learned
estimate, and the Monte Carlo forecast) that a fresh clone shows every
feature working on first run instead of a wall of empty states.
Re-runnable: clears prior seed data first.
"""

import datetime as dt

from django.core.management.base import BaseCommand

from core.models import Milestone, Project, RiskItem, Sprint, Staff, Task, Unavailability
from engine.sprint import compute_velocity, week_start

TODAY = dt.date.today()


def _monday(weeks_ago: int) -> dt.date:
    return week_start(TODAY) - dt.timedelta(weeks=weeks_ago)


class Command(BaseCommand):
    help = "Seed Jimothy with a varied example portfolio covering every feature."

    def handle(self, *args, **options):
        Task.objects.all().delete()
        Milestone.objects.all().delete()
        RiskItem.objects.all().delete()
        Unavailability.objects.all().delete()
        Sprint.objects.all().delete()
        Project.objects.all().delete()
        Staff.objects.all().delete()

        jordan = Staff.objects.create(
            name="Jordan", role="Program Manager", nominal_hours_per_day=8,
            focus_factor=0.60, is_manager=True)
        priya = Staff.objects.create(
            name="Priya", role="Field Coordinator", nominal_hours_per_day=8,
            focus_factor=0.75)
        sam = Staff.objects.create(
            name="Sam", role="Communications Lead", nominal_hours_per_day=6,
            focus_factor=0.75)
        alex = Staff.objects.create(
            name="Alex", role="Operations Assistant", nominal_hours_per_day=8,
            focus_factor=0.80)

        Unavailability.objects.create(
            staff=priya, start_date=TODAY + dt.timedelta(days=4),
            end_date=TODAY + dt.timedelta(days=5), reason="Field safety training")
        Unavailability.objects.create(
            staff=sam, start_date=TODAY + dt.timedelta(days=1),
            end_date=TODAY + dt.timedelta(days=1), reason="Half-day appointment")

        # --- Critical: grant renewal, hard deadline ---
        grant = Project.objects.create(
            name="Community Outreach Grant Renewal", priority_class=4,
            deadline=TODAY + dt.timedelta(days=10), budget_staff_days=18,
            sponsor_notes="Multi-year renewal; needs a co-authored narrative section "
                          "from an external partner org.")
        m_submit = Milestone.objects.create(
            project=grant, name="Submission deadline", due_date=TODAY + dt.timedelta(days=10))
        Task.objects.create(
            project=grant, milestone=m_submit, title="Close remaining sections of the narrative",
            status="doing", assignee=jordan, est_optimistic=6, est_likely=10, est_pessimistic=18,
            delay_profile="cliff", tags="proposal,writing", last_touched=TODAY)
        Task.objects.create(
            project=grant, milestone=m_submit, title="Get partner org's budget narrative back",
            status="waiting-external", assignee=jordan, est_likely=2,
            delay_profile="cliff", tags="proposal,coordination",
            last_touched=TODAY - dt.timedelta(days=2))
        Task.objects.create(
            project=grant, title="Finalize evaluation metrics section",
            status="blocked", assignee=jordan, est_likely=3, delay_profile="cliff",
            tags="proposal,writing", blocked_by="waiting on last year's outcome numbers from Alex",
            blocked_since=TODAY - dt.timedelta(days=3), last_touched=TODAY - dt.timedelta(days=3))
        RiskItem.objects.create(
            project=grant, description="Partner org's section arrives late, compresses review time",
            probability=3, impact=4, trigger_date=TODAY + dt.timedelta(days=6), owner="Jordan")

        # --- High: board-approval-pending equipment upgrade ---
        equipment = Project.objects.create(
            name="Field Equipment Upgrade Proposal", priority_class=3,
            deadline=TODAY + dt.timedelta(days=16),
            sponsor_notes="Pending board approval; replaces aging field kits for the crew.")
        m_board = Milestone.objects.create(
            project=equipment, name="Board vote", due_date=TODAY + dt.timedelta(days=16))
        Task.objects.create(
            project=equipment, milestone=m_board, title="Finalize proposal doc for board packet",
            status="todo", assignee=priya, est_optimistic=2, est_likely=4, est_pessimistic=8,
            deadline=TODAY + dt.timedelta(days=9), delay_profile="cliff",
            tags="proposal", last_touched=TODAY - dt.timedelta(days=5))
        Task.objects.create(
            project=equipment, title="Collect three vendor quotes",
            status="doing", assignee=priya, est_likely=5, delay_profile="linear",
            deadline=TODAY + dt.timedelta(days=5), tags="procurement",
            last_touched=TODAY - dt.timedelta(days=1))

        # --- Normal: recurring weekly reporting, with real completion history ---
        reporting = Project.objects.create(
            name="Weekly Client Status Reporting", priority_class=2,
            sponsor_notes="Recurring: a weekly status update plus a monthly rollup.")
        for weeks_ago, hours in ((4, 1.6), (3, 2.1), (2, 1.9)):
            Task.objects.create(
                project=reporting, title="Send weekly client status update",
                status="done", assignee=sam, est_optimistic=1, est_likely=1.5,
                est_pessimistic=2.5, actual_hours=hours,
                completed=TODAY - dt.timedelta(weeks=weeks_ago),
                delay_profile="linear", tags="reporting", recur_every_days=7,
                last_touched=TODAY - dt.timedelta(weeks=weeks_ago))
        Task.objects.create(
            project=reporting, title="Send weekly client status update",
            status="todo", assignee=sam, est_likely=1.5, delay_profile="linear",
            deadline=TODAY + dt.timedelta(days=2), tags="reporting", recur_every_days=7,
            last_touched=TODAY - dt.timedelta(days=5))
        # extra completed throughput on this project so its Monte Carlo forecast
        # has enough distinct weeks of history to sample from
        for weeks_ago, hours in ((5, 3.0), (4, 2.5), (3, 4.0), (2, 3.5), (1, 2.0)):
            Task.objects.create(
                project=reporting,
                title="Monthly rollup for week of %s" % (TODAY - dt.timedelta(weeks=weeks_ago)),
                status="done", assignee=alex, est_likely=3, actual_hours=hours,
                completed=TODAY - dt.timedelta(weeks=weeks_ago), delay_profile="linear",
                tags="reporting,ops", last_touched=TODAY - dt.timedelta(weeks=weeks_ago))
        Task.objects.create(
            project=reporting, title="Draft this month's rollup",
            status="todo", assignee=alex, est_likely=3, delay_profile="linear",
            deadline=TODAY + dt.timedelta(days=4), tags="reporting,ops", last_touched=TODAY)
        # no estimate yet, on purpose — shows up in Today's "Needs triage" section
        Task.objects.create(
            project=reporting, title="Investigate a lighter-weight rollup template",
            status="todo", assignee=None, delay_profile="slow_burn", tags="ops")

        # --- Normal: dogfooding this tool ---
        jimothy = Project.objects.create(
            name="Jimothy (this tool)", priority_class=2,
            sponsor_notes="Personal PM tool build, in progress.")
        Task.objects.create(
            project=jimothy, title="Run the Phase 0 deployment spike on a locked-down machine",
            status="todo", assignee=jordan, est_likely=1, delay_profile="slow_burn",
            tags="deployment", last_touched=TODAY)
        Task.objects.create(
            project=jimothy, title="Build the Tier 3 browser-only proof of concept",
            status="todo", assignee=jordan, est_likely=4, delay_profile="slow_burn",
            tags="deployment", last_touched=TODAY - dt.timedelta(days=10))

        # --- Backburner ---
        website = Project.objects.create(
            name="Website Refresh", priority_class=1, status="pending",
            sponsor_notes="Someday/maybe — no committed timeline yet.")
        Task.objects.create(
            project=website, title="Collect feedback on current site's pain points",
            status="todo", assignee=alex, est_likely=2, delay_profile="slow_burn",
            tags="design", last_touched=TODAY - dt.timedelta(days=20))

        # --- Sprints: last week (closed out) and this week (in progress) ---
        last_sprint = Sprint.objects.create(week_start=_monday(1))
        committed_last = [t for t in [
            Task.objects.filter(title="Send weekly client status update", status="done")
                .order_by("-completed").first(),
            Task.objects.filter(title="Collect three vendor quotes").first(),
        ] if t]
        last_sprint.committed.add(*committed_last)
        last_sprint.velocity_actual = compute_velocity([t.to_engine() for t in committed_last])
        last_sprint.retro_note = "Vendor calls ate more time than planned; rollup slipped a day."
        last_sprint.save()

        this_sprint = Sprint.objects.create(week_start=_monday(0))
        committed_this = [t for t in [
            Task.objects.filter(title__startswith="Close remaining sections").first(),
            Task.objects.filter(title="Finalize proposal doc for board packet").first(),
            Task.objects.filter(title="Draft this month's rollup").first(),
        ] if t]
        this_sprint.committed.add(*committed_this)

        self.stdout.write(self.style.SUCCESS(
            "Seeded %d projects, %d tasks, %d staff." % (
                Project.objects.count(), Task.objects.count(), Staff.objects.count())))
