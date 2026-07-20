"""Django models — persistence layer mirroring PROJECT_PLAN.md §3.

These map 1:1 onto the engine dataclasses via to_engine() helpers; the engine
never imports Django (plan §8), so conversion happens here.
"""

import datetime as dt

from django.db import models

from engine.model import DelayProfile as EDelay
from engine.model import PriorityClass as EPriority
from engine.model import Project as EProject
from engine.model import Staff as EStaff
from engine.model import Status as EStatus
from engine.model import Task as ETask


class Staff(models.Model):
    name = models.CharField(max_length=100)
    role = models.CharField(max_length=100, blank=True)
    nominal_hours_per_day = models.FloatField(default=8.0)
    focus_factor = models.FloatField(default=0.75)
    is_manager = models.BooleanField(default=False)
    calendar_shared = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "staff"

    def __str__(self):
        return self.name

    def to_engine(self) -> EStaff:
        return EStaff(id=self.pk, name=self.name,
                      nominal_hours_per_day=self.nominal_hours_per_day,
                      focus_factor=self.focus_factor,
                      is_manager=self.is_manager)

    def unavailable_on(self, day) -> bool:
        return self.unavailability.filter(start_date__lte=day, end_date__gte=day).exists()


class Unavailability(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE,
                              related_name="unavailability")
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name_plural = "unavailability"
        ordering = ["start_date"]

    def __str__(self):
        return "%s: %s - %s" % (self.staff.name, self.start_date, self.end_date)


class Project(models.Model):
    PRIORITY_CHOICES = [(4, "Critical"), (3, "High"), (2, "Normal"), (1, "Backburner")]
    STATUS_CHOICES = [("active", "Active"), ("pending", "Pending approval"),
                      ("done", "Done"), ("shelved", "Shelved")]

    name = models.CharField(max_length=200)
    priority_class = models.IntegerField(choices=PRIORITY_CHOICES, default=2)
    deadline = models.DateField(null=True, blank=True)
    budget_staff_days = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    sponsor_notes = models.TextField(blank=True)
    out_of_scope = models.TextField(blank=True)

    def __str__(self):
        return self.name

    def to_engine(self) -> EProject:
        return EProject(id=self.pk, name=self.name,
                        priority_class=EPriority(self.priority_class),
                        deadline=self.deadline,
                        budget_staff_days=self.budget_staff_days)


class Milestone(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE,
                                related_name="milestones")
    name = models.CharField(max_length=200)
    due_date = models.DateField(null=True, blank=True)
    done = models.BooleanField(default=False)

    def __str__(self):
        return "%s — %s" % (self.project.name, self.name)


class Task(models.Model):
    STATUS_CHOICES = [(s.value, s.value) for s in EStatus]
    PROFILE_CHOICES = [(p.value, p.value) for p in EDelay]

    project = models.ForeignKey(Project, on_delete=models.CASCADE,
                                related_name="tasks")
    milestone = models.ForeignKey(Milestone, on_delete=models.SET_NULL,
                                  null=True, blank=True)
    title = models.CharField(max_length=300)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="todo")
    assignee = models.ForeignKey(Staff, on_delete=models.SET_NULL,
                                 null=True, blank=True)
    est_optimistic = models.FloatField(null=True, blank=True)
    est_likely = models.FloatField(null=True, blank=True)
    est_pessimistic = models.FloatField(null=True, blank=True)
    actual_hours = models.FloatField(default=0.0)
    deadline = models.DateField(null=True, blank=True)
    depends_on = models.ManyToManyField("self", symmetrical=False, blank=True,
                                        related_name="dependents")
    delay_profile = models.CharField(max_length=20, choices=PROFILE_CHOICES,
                                     default="linear")
    tags = models.CharField(max_length=200, blank=True,
                            help_text="comma-separated")
    done_definition = models.TextField(blank=True)
    blocked_by = models.CharField(max_length=200, blank=True)
    blocked_since = models.DateField(null=True, blank=True)
    reopened_count = models.IntegerField(default=0)
    last_touched = models.DateField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    completed = models.DateField(null=True, blank=True)
    recur_every_days = models.IntegerField(
        null=True, blank=True,
        help_text="Days until the next occurrence. Leave blank for a one-off task. "
                  "On completion, the next instance is created automatically.")

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        """On the transition into status=done for a recurring task, spawn
        the next occurrence (plan §11 item 1) — checked here rather than in
        a view, so it fires regardless of how the task got marked done
        (Focus Mode, admin, or any future path)."""
        just_completed = False
        if self.pk and self.recur_every_days:
            try:
                was_done = Task.objects.only("status").get(pk=self.pk).status == "done"
            except Task.DoesNotExist:
                was_done = False
            just_completed = not was_done and self.status == "done"
        super().save(*args, **kwargs)
        if just_completed:
            self._spawn_next_occurrence()

    def _spawn_next_occurrence(self):
        """Create the next instance. Its estimate is learned from the last
        few completions of this same template (project + title) once there's
        enough history (plan §11 item 6); otherwise it just copies this
        instance's own estimate, same as before."""
        from engine.estimate import template_estimate

        base_date = self.completed or dt.date.today()
        history = list(
            Task.objects.filter(project=self.project, title=self.title,
                                status="done", actual_hours__gt=0)
            .order_by("-completed").values_list("actual_hours", flat=True)[:8])
        learned = template_estimate(history)
        if learned:
            est_optimistic, est_likely, est_pessimistic = learned
        else:
            est_optimistic = self.est_optimistic
            est_likely = self.est_likely
            est_pessimistic = self.est_pessimistic

        Task.objects.create(
            project=self.project, milestone=self.milestone, title=self.title,
            status="todo", assignee=self.assignee,
            est_optimistic=est_optimistic, est_likely=est_likely,
            est_pessimistic=est_pessimistic,
            deadline=base_date + dt.timedelta(days=self.recur_every_days),
            delay_profile=self.delay_profile, tags=self.tags,
            done_definition=self.done_definition,
            recur_every_days=self.recur_every_days,
        )

    def to_engine(self) -> ETask:
        return ETask(
            id=self.pk, project_id=self.project_id, title=self.title,
            status=EStatus(self.status), assignee_id=self.assignee_id,
            est_optimistic=self.est_optimistic, est_likely=self.est_likely,
            est_pessimistic=self.est_pessimistic,
            actual_hours=self.actual_hours,
            deadline=self.deadline or (self.milestone.due_date if self.milestone else None),
            # .all() (not .values_list()) so a prefetch_related("depends_on")
            # on the caller's queryset is actually used instead of bypassed.
            depends_on=[d.pk for d in self.depends_on.all()],
            delay_profile=EDelay(self.delay_profile),
            tags=[t.strip() for t in self.tags.split(",") if t.strip()],
            last_touched=self.last_touched,
        )


class RiskItem(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE,
                                related_name="risks")
    description = models.CharField(max_length=300)
    probability = models.IntegerField(default=3)   # 1-5
    impact = models.IntegerField(default=3)        # 1-5
    trigger_date = models.DateField(null=True, blank=True)
    owner = models.CharField(max_length=100, blank=True)
    mitigation = models.TextField(blank=True)
    open = models.BooleanField(default=True)

    def __str__(self):
        return self.description


class Sprint(models.Model):
    week_start = models.DateField(unique=True)
    committed = models.ManyToManyField(Task, blank=True)
    velocity_actual = models.FloatField(null=True, blank=True)
    retro_note = models.TextField(blank=True)

    def __str__(self):
        return "Sprint of %s" % self.week_start


class ScoringSettings(models.Model):
    """Singleton (always pk=1): the five scoring weights from plan §4,
    tunable without touching engine code — "visible and tunable in
    settings, no black box"."""
    urgency = models.FloatField(default=4.0)
    priority = models.FloatField(default=2.0)
    criticality = models.FloatField(default=1.5)
    staleness = models.FloatField(default=0.5)
    unblock = models.FloatField(default=1.0)

    class Meta:
        verbose_name_plural = "scoring settings"

    def __str__(self):
        return "Scoring weights"

    @classmethod
    def load(cls) -> "ScoringSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def to_weights(self):
        from engine.scoring import Weights
        return Weights(urgency=self.urgency, priority=self.priority,
                       criticality=self.criticality, staleness=self.staleness,
                       unblock=self.unblock)


class WorkLog(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="worklogs")
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE)
    date = models.DateField()
    hours = models.FloatField()

    def __str__(self):
        return "%s: %.1fh on %s" % (self.staff.name, self.hours, self.task.title)
