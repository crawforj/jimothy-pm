from django.contrib import admin
from django.db import models as django_models

from core.forms import NaturalDateField
from core.models import (CalendarEvent, Milestone, Project, RiskItem, ScoringSettings,
                         Sprint, Staff, Task, Unavailability, WorkLog)

# Plain text date entry everywhere (accepts "next friday", "in 3 days", or a
# straight ISO date) instead of the click-only admin calendar widget (plan
# §11 item 3). Supplying "widget" here too, not just "form_class", matters:
# admin.ModelAdmin.formfield_for_dbfield forces AdminDateWidget onto every
# DateField unless a widget is already present in the override kwargs.
NATURAL_DATE_OVERRIDES = {
    django_models.DateField: {
        "form_class": NaturalDateField,
        "widget": NaturalDateField.widget,
    },
}


class UnavailabilityInline(admin.TabularInline):
    model = Unavailability
    extra = 0
    formfield_overrides = NATURAL_DATE_OVERRIDES


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ("name", "role", "nominal_hours_per_day", "focus_factor",
                    "is_manager", "active")
    inlines = [UnavailabilityInline]


class MilestoneInline(admin.TabularInline):
    model = Milestone
    extra = 0
    formfield_overrides = NATURAL_DATE_OVERRIDES


class RiskInline(admin.TabularInline):
    model = RiskItem
    extra = 0
    formfield_overrides = NATURAL_DATE_OVERRIDES


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "priority_class", "deadline", "budget_staff_days", "status")
    list_filter = ("priority_class", "status")
    inlines = [MilestoneInline, RiskInline]
    formfield_overrides = NATURAL_DATE_OVERRIDES


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "status", "assignee", "est_likely",
                    "deadline", "delay_profile", "recur_every_days")
    list_filter = ("status", "project", "assignee")
    search_fields = ("title", "tags")
    filter_horizontal = ("depends_on",)
    formfield_overrides = NATURAL_DATE_OVERRIDES


@admin.register(Milestone)
class MilestoneAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "due_date", "done")
    list_filter = ("project", "done")
    formfield_overrides = NATURAL_DATE_OVERRIDES


@admin.register(RiskItem)
class RiskItemAdmin(admin.ModelAdmin):
    list_display = ("description", "project", "probability", "impact", "trigger_date", "open")
    list_filter = ("project", "open")
    formfield_overrides = NATURAL_DATE_OVERRIDES


@admin.register(Sprint)
class SprintAdmin(admin.ModelAdmin):
    list_display = ("week_start", "velocity_actual")
    formfield_overrides = NATURAL_DATE_OVERRIDES


@admin.register(WorkLog)
class WorkLogAdmin(admin.ModelAdmin):
    list_display = ("task", "staff", "date", "hours")
    formfield_overrides = NATURAL_DATE_OVERRIDES


@admin.register(CalendarEvent)
class CalendarEventAdmin(admin.ModelAdmin):
    list_display = ("staff", "provider", "start", "end", "busy_status", "all_day")
    list_filter = ("provider", "busy_status", "staff")
    date_hierarchy = "start"

    def has_add_permission(self, request):
        return False


admin.site.register(ScoringSettings)
admin.site.site_header = "Jimothy admin"
admin.site.site_title = "Jimothy"
