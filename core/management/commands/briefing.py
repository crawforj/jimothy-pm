"""Render the morning briefing as plain text (plan §8's planned command
list). Rendering only -- sending it via email stays a separate, still-open
question (classic vs. new Outlook on the sending machine); see
USER_GUIDE.md. Calendar *reads* (this command's hours-available figure) are
unrelated and covered by §7c's OAuth-based sync."""

import datetime as dt

from django.core.management.base import BaseCommand

from core import phrases
from core.models import Staff, Task
from core.services import portfolio_feasibility, portfolio_scoring, staff_day_capacity
from engine.schedule import pack_day


class Command(BaseCommand):
    help = "Render today's briefing as plain text to stdout."

    def handle(self, *args, **options):
        today_date = dt.date.today()
        scored, staff, projects_qs, tasks_qs, uplifts = portfolio_scoring(today_date)
        task_by_id = {t.pk: t for t in tasks_qs}
        project_by_id = {p.pk: p for p in projects_qs}

        self.stdout.write(phrases.greeting())
        self.stdout.write(today_date.strftime("%A, %B %d, %Y"))
        self.stdout.write("")

        forecasts = portfolio_feasibility(scored, staff, today_date, uplifts)
        for pid, fc in forecasts.items():
            if fc.slip_days > 0:
                pname = project_by_id.get(pid)
                if pname:
                    self.stdout.write("WORTH A LOOK: " + phrases.feasibility_warning(pname.name, fc.slip_days))
        self.stdout.write("")

        blocked = [t for t in tasks_qs if t.status == "blocked"]
        waiting = [t for t in tasks_qs if t.status == "waiting-external"]
        if blocked or waiting:
            self.stdout.write("CHASE LIST:")
            for t in blocked:
                self.stdout.write("  - %s (%s) - blocked" % (t.title, t.project.name))
            for t in waiting:
                self.stdout.write("  - %s (%s) - waiting on external party" % (t.title, t.project.name))
            self.stdout.write("")

        for s in Staff.objects.filter(active=True):
            if s.unavailable_on(today_date):
                hours_available = 0.0
            else:
                cal_capacity = staff_day_capacity(s, today_date)
                hours_available = cal_capacity.available_hours if cal_capacity else None
            plan = pack_day(scored, s.to_engine(), hours_available=hours_available)
            self.stdout.write("%s (%.1fh free):" % (s.name, plan.hours_free))
            if not plan.entries:
                self.stdout.write("  " + phrases.no_tasks_message())
            for i, (tid, hours) in enumerate(plan.entries, start=1):
                t = task_by_id[tid]
                self.stdout.write("  %d. %s (%s) - %.1fh" % (i, t.title, t.project.name, hours))
            self.stdout.write("")
