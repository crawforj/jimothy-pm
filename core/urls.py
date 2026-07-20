from django.urls import path

from core import views

urlpatterns = [
    path("", views.today, name="today"),
    path("week/", views.week, name="week"),
    path("week/commit/<int:task_id>/", views.week_commit, name="week_commit"),
    path("week/closeout/", views.week_closeout, name="week_closeout"),
    path("month/", views.month, name="month"),
    path("quarter/", views.quarter, name="quarter"),
    path("year/", views.year, name="year"),
    path("projects/", views.projects, name="projects"),
    path("staff/", views.staff, name="staff"),
    path("reports/", views.reports_index, name="reports_index"),
    path("reports/<int:project_id>/", views.report_detail, name="report_detail"),
    path("focus/", views.focus, name="focus"),
    path("focus/start/<int:task_id>/", views.focus_start, name="focus_start"),
    path("focus/done/<int:task_id>/", views.focus_done, name="focus_done"),
    path("focus/skip/<int:task_id>/", views.focus_skip, name="focus_skip"),
    path("settings/", views.settings_view, name="settings"),
]
