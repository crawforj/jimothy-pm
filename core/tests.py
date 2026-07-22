"""Django test-client coverage for the calendar-sync views (core/views.py's
calendar_* functions and settings_view's calendar_rows). Not a browser test
suite (CONTRIBUTING.md's "no browser test suite" note is about that,
Selenium-style) -- this is the standard Django TestCase/Client pattern,
covering response codes, redirects, and messages without ever hitting a
real Microsoft/Google account. The engine's own known-answer tests stay in
engine/tests/test_engine.py; this file is for the Django layer only."""

import datetime as dt
import tempfile
from pathlib import Path
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from core.calendarsync.base import ProviderStatus
from core.context_processors import mascot_mood
from core.models import Milestone, Project, PushedCalendarEvent, Staff, Task
from core.views import _forecast_chart_data, _heatmap_data
from engine.schedule import WeekLoad

_FAKE_GRAPH_SETTINGS = dict(MICROSOFT_GRAPH_CLIENT_ID="test-graph-client-id")
_FAKE_GOOGLE_SETTINGS = dict(GOOGLE_CALENDAR_CLIENT_ID="test-google-client-id",
                             GOOGLE_CALENDAR_CLIENT_SECRET="test-google-secret")
_TODAY = dt.date(2026, 7, 21)


class SettingsCalendarSectionTests(TestCase):
    def test_unconfigured_providers_show_not_available(self):
        resp = self.client.get(reverse("settings"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Not available in this build", count=2)
        self.assertNotContains(resp, "Connect Microsoft Outlook")

    @override_settings(**_FAKE_GRAPH_SETTINGS)
    def test_configured_provider_shows_connect_link(self):
        resp = self.client.get(reverse("settings"))
        self.assertContains(resp, "Connect Microsoft Outlook")
        # Google still unconfigured in this test -- both states render on
        # the same page without one masking the other.
        self.assertContains(resp, "Not available in this build", count=1)

    def test_no_sync_now_button_when_nothing_connected(self):
        resp = self.client.get(reverse("settings"))
        self.assertNotContains(resp, "Sync now")


class CalendarConnectTests(TestCase):
    def test_connect_graph_unconfigured_redirects_with_error(self):
        resp = self.client.get(reverse("calendar_connect_graph"), follow=True)
        self.assertRedirects(resp, reverse("settings"))
        self.assertContains(resp, "isn&#x27;t available in this build")

    def test_connect_google_unconfigured_redirects_with_error(self):
        resp = self.client.get(reverse("calendar_connect_google"), follow=True)
        self.assertRedirects(resp, reverse("settings"))
        self.assertContains(resp, "isn&#x27;t available in this build")

    @override_settings(**_FAKE_GRAPH_SETTINGS)
    def test_connect_graph_configured_redirects_to_microsoft(self):
        resp = self.client.get(reverse("calendar_connect_graph"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login.microsoftonline.com", resp.url)

    @override_settings(**_FAKE_GOOGLE_SETTINGS)
    def test_connect_google_configured_redirects_to_google(self):
        resp = self.client.get(reverse("calendar_connect_google"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("accounts.google.com", resp.url)


class CalendarCallbackTests(TestCase):
    """A callback hit without ever visiting Connect first (no pending flow
    stashed in the session) is exactly what a stray/replayed/forged request
    to these URLs looks like -- must degrade to an error message, never a
    500, regardless of whether the provider is configured."""

    def test_graph_callback_without_pending_flow_does_not_crash(self):
        resp = self.client.get(reverse("calendar_oauth_graph_callback"), follow=True)
        self.assertRedirects(resp, reverse("settings"))
        self.assertContains(resp, "Couldn&#x27;t connect to Microsoft Outlook")

    def test_google_callback_without_pending_flow_does_not_crash(self):
        resp = self.client.get(reverse("calendar_oauth_google_callback"), follow=True)
        self.assertRedirects(resp, reverse("settings"))
        self.assertContains(resp, "Couldn&#x27;t connect to Google Calendar")


class CalendarDisconnectTests(TestCase):
    def test_get_not_allowed(self):
        resp = self.client.get(reverse("calendar_disconnect", args=["graph"]))
        self.assertEqual(resp.status_code, 405)

    def test_post_with_nothing_connected_does_not_crash(self):
        resp = self.client.post(reverse("calendar_disconnect", args=["graph"]), follow=True)
        self.assertRedirects(resp, reverse("settings"))

    def test_unknown_provider_key_does_not_crash(self):
        resp = self.client.post(reverse("calendar_disconnect", args=["bogus"]), follow=True)
        self.assertRedirects(resp, reverse("settings"))


class CalendarSyncNowTests(TestCase):
    def test_get_not_allowed(self):
        resp = self.client.get(reverse("calendar_sync_now"))
        self.assertEqual(resp.status_code, 405)

    def test_post_with_nothing_connected_does_not_crash(self):
        """No Staff row, no configured provider -- sync_calendar's own
        "no manager Staff row" / "not configured" guards should make this
        a clean no-op, not an error."""
        resp = self.client.post(reverse("calendar_sync_now"), follow=True)
        self.assertRedirects(resp, reverse("settings"))
        self.assertContains(resp, "Calendar sync complete.")


class ForecastChartDataTests(TestCase):
    """_forecast_chart_data() is the report_detail.html forecast range
    bar's position/status math -- a pure function despite living in
    views.py, so no DB or client needed to exercise it directly."""

    def _forecast(self, p50_days, p85_days):
        return {"p50": _TODAY + dt.timedelta(days=p50_days),
                "p85": _TODAY + dt.timedelta(days=p85_days)}

    def test_no_deadline_has_no_marker(self):
        data = _forecast_chart_data(self._forecast(30, 50), _TODAY, None)
        self.assertIsNone(data["deadline_pct"])
        self.assertIsNone(data["deadline_status"])

    def test_deadline_after_p85_is_ok(self):
        data = _forecast_chart_data(self._forecast(30, 50), _TODAY,
                                    _TODAY + dt.timedelta(days=70))
        self.assertEqual(data["deadline_status"], "ok")
        self.assertEqual(data["deadline_pct"], 92.6)

    def test_deadline_between_p50_and_p85_is_warn(self):
        data = _forecast_chart_data(self._forecast(30, 50), _TODAY,
                                    _TODAY + dt.timedelta(days=40))
        self.assertEqual(data["deadline_status"], "warn")

    def test_deadline_before_p50_is_warn(self):
        data = _forecast_chart_data(self._forecast(30, 50), _TODAY,
                                    _TODAY + dt.timedelta(days=10))
        self.assertEqual(data["deadline_status"], "warn")

    def test_already_passed_deadline_has_no_marker(self):
        """An overdue deadline is the Today page's feasibility-warning's
        job, not this chart's -- must not draw a marker off the left edge
        or crash on a negative position."""
        data = _forecast_chart_data(self._forecast(30, 50), _TODAY,
                                    _TODAY - dt.timedelta(days=5))
        self.assertIsNone(data["deadline_pct"])
        self.assertIsNone(data["deadline_status"])

    def test_p50_and_p85_percentages_always_ordered(self):
        data = _forecast_chart_data(self._forecast(30, 50), _TODAY, None)
        self.assertLess(data["p50_pct"], data["p85_pct"])
        self.assertGreaterEqual(data["range_width_pct"], 0)

    def test_no_forecast_returns_none(self):
        self.assertIsNone(_forecast_chart_data(None, _TODAY, None))


class HeatmapDataTests(TestCase):
    def test_no_active_staff_returns_none(self):
        weeks, rows = _heatmap_data([], {})
        self.assertIsNone(weeks)
        self.assertIsNone(rows)

    def test_week_headers_come_from_first_staff_member(self):
        s = Staff.objects.create(name="Alex")
        load = {s.pk: [WeekLoad(week_start=_TODAY, load_hours=10, capacity_hours=30)]}
        weeks, rows = _heatmap_data([s], load)
        self.assertEqual(weeks, [_TODAY])
        self.assertEqual(rows[0]["staff"], s)

    def test_mix_pct_scales_within_the_contrast_safe_range(self):
        """Cell intensity must stay inside the measured-safe 6-40% band
        (see _heatmap_data's docstring) at both ends of pct, not the full
        0-100% -- that's what keeps this app's light text legible against
        its own cell background at any load level."""
        s = Staff.objects.create(name="Alex")
        load = {s.pk: [
            WeekLoad(week_start=_TODAY, load_hours=0, capacity_hours=30),           # 0%
            WeekLoad(week_start=_TODAY, load_hours=30, capacity_hours=30),          # 100%
        ]}
        _, rows = _heatmap_data([s], load)
        self.assertEqual(rows[0]["cells"][0]["mix_pct"], 6.0)
        self.assertEqual(rows[0]["cells"][1]["mix_pct"], 40.0)

    def test_over_capacity_flag_carries_through(self):
        s = Staff.objects.create(name="Alex")
        load = {s.pk: [WeekLoad(week_start=_TODAY, load_hours=40, capacity_hours=30)]}
        _, rows = _heatmap_data([s], load)
        self.assertTrue(rows[0]["cells"][0]["over_capacity"])

    def test_renders_on_staff_page_with_no_crash(self):
        Staff.objects.create(name="Alex", active=True)
        resp = self.client.get(reverse("staff"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Team capacity")


class WeekMoveStatusTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="p")
        self.task = Task.objects.create(project=self.project, title="t", status="todo")

    def test_valid_status_change_persists(self):
        resp = self.client.post(reverse("week_move", args=[self.task.pk]),
                                {"status": "doing"})
        self.assertRedirects(resp, reverse("week"))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "doing")
        self.assertEqual(self.task.last_touched, dt.date.today())

    def test_invalid_status_is_a_no_op_not_a_500(self):
        resp = self.client.post(reverse("week_move", args=[self.task.pk]),
                                {"status": "not-a-real-status"})
        self.assertRedirects(resp, reverse("week"))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "todo")

    def test_missing_status_is_a_no_op(self):
        resp = self.client.post(reverse("week_move", args=[self.task.pk]), {})
        self.assertRedirects(resp, reverse("week"))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "todo")

    def test_get_not_allowed(self):
        resp = self.client.get(reverse("week_move", args=[self.task.pk]))
        self.assertEqual(resp.status_code, 405)

    def test_nonexistent_task_404s(self):
        resp = self.client.post(reverse("week_move", args=[999999]), {"status": "doing"})
        self.assertEqual(resp.status_code, 404)


class MascotMoodTests(TestCase):
    """The mascot's mood is a decorative echo of the same feasibility
    signal Today's own accessible "Worth a look" warnings already carry
    in full -- these tests only check the context processor's own
    branches, not the image swap (that's a template detail already
    exercised implicitly by every other test in this file rendering a
    page)."""

    def test_empty_portfolio_is_neutral(self):
        self.assertEqual(mascot_mood(None)["mascot_mood"], "neutral")

    def test_on_track_project_is_ok(self):
        Staff.objects.create(name="Alex", active=True)
        Project.objects.create(name="p", deadline=dt.date.today() + dt.timedelta(days=365))
        self.assertEqual(mascot_mood(None)["mascot_mood"], "ok")

    def test_slipping_project_is_warn(self):
        staff = Staff.objects.create(name="Alex", active=True)
        project = Project.objects.create(name="p", deadline=dt.date.today() + dt.timedelta(days=1))
        Task.objects.create(project=project, title="huge task", status="todo",
                            assignee=staff, est_likely=200,
                            deadline=dt.date.today() + dt.timedelta(days=1))
        self.assertEqual(mascot_mood(None)["mascot_mood"], "warn")

    def test_renders_correct_image_on_today_page(self):
        Staff.objects.create(name="Alex", active=True)
        Project.objects.create(name="p", deadline=dt.date.today() + dt.timedelta(days=365))
        resp = self.client.get(reverse("today"))
        self.assertContains(resp, "jimothy-ok.svg")


class DownloadBackupTests(TestCase):
    # The test DB is an in-memory sqlite ("file:memorydb_default?...", no
    # real path on disk), but the view opens settings.DATABASES's NAME as a
    # real file -- which is true for every actual deployment (packaged exe,
    # Docker, Codespaces, dev server) but not the test runner. Point NAME at
    # a real, valid, on-disk sqlite file just for this test.
    def test_returns_a_sqlite_file_attachment(self):
        import sqlite3

        with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as tmp:
            db_path = tmp.name
        # sqlite3 doesn't actually write the file header to disk until the
        # first real write -- connecting and closing alone leaves it empty.
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE t (x)")
        conn.commit()
        conn.close()

        with override_settings(DATABASES={
            "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": db_path},
        }):
            resp = self.client.get(reverse("download_backup"))

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp["Content-Disposition"].startswith("attachment;"))
        self.assertIn(".sqlite3", resp["Content-Disposition"])
        # SQLite files start with this fixed 16-byte header regardless of contents.
        self.assertTrue(b"".join(resp.streaming_content).startswith(b"SQLite format 3\x00"))

    def test_linked_from_settings_page(self):
        resp = self.client.get(reverse("settings"))
        self.assertContains(resp, reverse("download_backup"))


def _use_temp_data_dir(testcase):
    """Isolates tokens.py's real file writes (calendar_tokens/) to a
    throwaway temp dir for the test's duration -- without this, any test
    that actually calls set_push_enabled/save_token would write real files
    into this repo's own working directory."""
    tmpdir = tempfile.TemporaryDirectory()
    testcase.addCleanup(tmpdir.cleanup)
    patcher = override_settings(DATA_DIR=Path(tmpdir.name))
    patcher.enable()
    testcase.addCleanup(patcher.disable)


class _FakeCalendarProvider:
    """A minimal stand-in for GraphCalendarProvider/GoogleCalendarProvider
    implementing only what push.py calls -- lets push.py's orchestration
    logic be tested directly without ever making a real HTTP request."""

    def __init__(self, key="graph"):
        self.key = key
        self.display_name = key
        self.created = []
        self.updated = []
        self.deleted = []
        self._next_id = 1

    def is_configured(self):
        return True

    def status(self):
        return ProviderStatus(connected=True)

    def create_event(self, subject, start, end, all_day):
        source_id = "%s-evt-%d" % (self.key, self._next_id)
        self._next_id += 1
        self.created.append(source_id)
        return source_id

    def update_event(self, source_id, subject, start, end, all_day):
        self.updated.append(source_id)

    def delete_event(self, source_id):
        self.deleted.append(source_id)


class PushMilestoneTests(TestCase):
    def setUp(self):
        self.fake = _FakeCalendarProvider()
        providers_patch = mock.patch("core.calendarsync.push._providers",
                                     return_value=(self.fake,))
        providers_patch.start()
        self.addCleanup(providers_patch.stop)
        enabled_patch = mock.patch("core.calendarsync.push.tokens.push_enabled",
                                   return_value=True)
        enabled_patch.start()
        self.addCleanup(enabled_patch.stop)
        self.project = Project.objects.create(name="p")

    def test_milestone_with_due_date_creates_pushed_event(self):
        milestone = Milestone.objects.create(project=self.project, name="m",
                                             due_date=dt.date(2026, 8, 1))
        self.assertEqual(len(self.fake.created), 1)
        self.assertTrue(PushedCalendarEvent.objects.filter(
            milestone=milestone, provider="graph").exists())

    def test_saving_again_updates_rather_than_duplicates(self):
        milestone = Milestone.objects.create(project=self.project, name="m",
                                             due_date=dt.date(2026, 8, 1))
        milestone.name = "m2"
        milestone.save()
        self.assertEqual(len(self.fake.created), 1)
        self.assertEqual(len(self.fake.updated), 1)
        self.assertEqual(PushedCalendarEvent.objects.filter(milestone=milestone).count(), 1)

    def test_marking_done_removes_the_push(self):
        milestone = Milestone.objects.create(project=self.project, name="m",
                                             due_date=dt.date(2026, 8, 1))
        milestone.done = True
        milestone.save()
        self.assertEqual(len(self.fake.deleted), 1)
        self.assertFalse(PushedCalendarEvent.objects.filter(milestone=milestone).exists())

    def test_clearing_due_date_removes_the_push(self):
        milestone = Milestone.objects.create(project=self.project, name="m",
                                             due_date=dt.date(2026, 8, 1))
        milestone.due_date = None
        milestone.save()
        self.assertEqual(len(self.fake.deleted), 1)

    def test_deleting_milestone_removes_the_push(self):
        milestone = Milestone.objects.create(project=self.project, name="m",
                                             due_date=dt.date(2026, 8, 1))
        milestone.delete()
        self.assertEqual(len(self.fake.deleted), 1)
        self.assertFalse(PushedCalendarEvent.objects.filter(milestone_id=milestone.pk).exists())

    def test_milestone_without_due_date_never_pushes(self):
        Milestone.objects.create(project=self.project, name="m")
        self.assertEqual(len(self.fake.created), 0)

    def test_provider_failure_does_not_raise(self):
        self.fake.create_event = mock.Mock(side_effect=ValueError("boom"))
        Milestone.objects.create(project=self.project, name="m", due_date=dt.date(2026, 8, 1))
        # No exception means the signal receiver swallowed it, matching
        # sync_calendar.py's own per-provider try/except.


class FocusCalendarPushTests(TestCase):
    def setUp(self):
        self.fake = _FakeCalendarProvider()
        providers_patch = mock.patch("core.calendarsync.push._providers",
                                     return_value=(self.fake,))
        providers_patch.start()
        self.addCleanup(providers_patch.stop)
        enabled_patch = mock.patch("core.calendarsync.push.tokens.push_enabled",
                                   return_value=True)
        enabled_patch.start()
        self.addCleanup(enabled_patch.stop)
        self.manager = Staff.objects.create(name="Manager", is_manager=True, active=True)
        self.other = Staff.objects.create(name="Other", is_manager=False, active=True)
        project = Project.objects.create(name="p")
        self.task = Task.objects.create(project=project, title="t", status="todo", est_likely=2.0)

    def test_starting_focus_as_manager_pushes_a_block(self):
        self.client.post(reverse("focus_start", args=[self.task.pk]),
                         {"staff_id": self.manager.pk})
        self.assertEqual(len(self.fake.created), 1)

    def test_starting_focus_as_non_manager_does_not_push(self):
        self.client.post(reverse("focus_start", args=[self.task.pk]),
                         {"staff_id": self.other.pk})
        self.assertEqual(len(self.fake.created), 0)

    def test_finishing_focus_removes_the_block(self):
        self.client.post(reverse("focus_start", args=[self.task.pk]),
                         {"staff_id": self.manager.pk})
        self.client.post(reverse("focus_done", args=[self.task.pk]),
                         {"staff_id": self.manager.pk})
        self.assertEqual(len(self.fake.deleted), 1)

    def test_skipping_focus_removes_the_block(self):
        self.client.post(reverse("focus_start", args=[self.task.pk]),
                         {"staff_id": self.manager.pk})
        self.client.post(reverse("focus_skip", args=[self.task.pk]),
                         {"staff_id": self.manager.pk})
        self.assertEqual(len(self.fake.deleted), 1)


class CalendarTogglePushTests(TestCase):
    def setUp(self):
        _use_temp_data_dir(self)

    def test_get_not_allowed(self):
        resp = self.client.get(reverse("calendar_toggle_push", args=["graph"]))
        self.assertEqual(resp.status_code, 405)

    def test_unknown_provider_key_does_not_crash(self):
        resp = self.client.post(reverse("calendar_toggle_push", args=["bogus"]), follow=True)
        self.assertRedirects(resp, reverse("settings"))

    def test_toggling_flips_state(self):
        from core.calendarsync import tokens

        self.assertFalse(tokens.push_enabled("graph"))
        self.client.post(reverse("calendar_toggle_push", args=["graph"]))
        self.assertTrue(tokens.push_enabled("graph"))
        self.client.post(reverse("calendar_toggle_push", args=["graph"]))
        self.assertFalse(tokens.push_enabled("graph"))

    @override_settings(**_FAKE_GRAPH_SETTINGS)
    def test_reflected_on_settings_page(self):
        from core.calendarsync import tokens

        tokens.save_token("graph", {"account_label": "me@example.com"})
        tokens.set_push_enabled("graph", True)
        resp = self.client.get(reverse("settings"))
        self.assertContains(resp, "Turn off calendar writes")
