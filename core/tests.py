"""Django test-client coverage for the calendar-sync views (core/views.py's
calendar_* functions and settings_view's calendar_rows). Not a browser test
suite (CONTRIBUTING.md's "no browser test suite" note is about that,
Selenium-style) -- this is the standard Django TestCase/Client pattern,
covering response codes, redirects, and messages without ever hitting a
real Microsoft/Google account. The engine's own known-answer tests stay in
engine/tests/test_engine.py; this file is for the Django layer only."""

import datetime as dt

from django.test import TestCase, override_settings
from django.urls import reverse

from core.views import _forecast_chart_data

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
