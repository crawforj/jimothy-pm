"""Django test-client coverage for the calendar-sync views (core/views.py's
calendar_* functions and settings_view's calendar_rows). Not a browser test
suite (CONTRIBUTING.md's "no browser test suite" note is about that,
Selenium-style) -- this is the standard Django TestCase/Client pattern,
covering response codes, redirects, and messages without ever hitting a
real Microsoft/Google account. The engine's own known-answer tests stay in
engine/tests/test_engine.py; this file is for the Django layer only."""

from django.test import TestCase, override_settings
from django.urls import reverse

_FAKE_GRAPH_SETTINGS = dict(MICROSOFT_GRAPH_CLIENT_ID="test-graph-client-id")
_FAKE_GOOGLE_SETTINGS = dict(GOOGLE_CALENDAR_CLIENT_ID="test-google-client-id",
                             GOOGLE_CALENDAR_CLIENT_SECRET="test-google-secret")


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
