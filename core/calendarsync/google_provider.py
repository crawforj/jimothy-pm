"""Google Calendar provider -- OAuth via google_auth_oauthlib.flow.Flow
(the web-app Flow, not InstalledAppFlow) with a fixed redirect_uri, same
reasoning as graph_provider.py: Jimothy is already the local server."""

from __future__ import annotations

import datetime as dt
import json

import requests
from django.conf import settings
from django.utils import timezone
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from core.calendarsync import tokens
from core.calendarsync.base import CalendarProvider, ProviderStatus, RawCalendarEvent
from engine.calendar_capacity import BusyStatus

# calendar.app.created (plan §7c writes) is Google's narrowest write scope:
# "Make secondary calendars associated with this app, and see, create,
# change, and delete events on those calendars. Doesn't allow the app to
# see or change any other calendar" -- a materially tighter guarantee than
# Graph's Calendars.ReadWrite (which has no such "only what it created"
# scope at all). Kept alongside calendar.readonly rather than replacing it,
# since reads still need the whole primary calendar, not just Jimothy's own.
_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.app.created",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]
_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
_CALENDAR_LIST_URL = "https://www.googleapis.com/calendar/v3/users/me/calendarList"
_CALENDARS_URL = "https://www.googleapis.com/calendar/v3/calendars"
_JIMOTHY_CALENDAR_NAME = "Jimothy"


def _client_config() -> dict:
    return {
        "web": {
            "client_id": settings.GOOGLE_CALENDAR_CLIENT_ID,
            "client_secret": settings.GOOGLE_CALENDAR_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def _parse_event_time(obj: dict) -> tuple[dt.datetime, bool]:
    """Returns (start_or_end, all_day)."""
    if "dateTime" in obj:
        return dt.datetime.fromisoformat(obj["dateTime"]), False
    naive = dt.datetime.combine(dt.date.fromisoformat(obj["date"]), dt.time.min)
    return timezone.make_aware(naive), True


def _busy_status(item: dict) -> BusyStatus:
    if item.get("eventType") == "outOfOffice":
        return BusyStatus.OUT_OF_OFFICE
    if item.get("status") == "tentative":
        return BusyStatus.TENTATIVE
    if item.get("transparency") == "transparent":
        return BusyStatus.FREE
    return BusyStatus.BUSY


class GoogleCalendarProvider(CalendarProvider):
    key = "google"
    display_name = "Google Calendar"

    def is_configured(self) -> bool:
        return bool(settings.GOOGLE_CALENDAR_CLIENT_ID and settings.GOOGLE_CALENDAR_CLIENT_SECRET)

    def status(self) -> ProviderStatus:
        data = tokens.load_token(self.key)
        if not data:
            return ProviderStatus(connected=False)
        return ProviderStatus(connected=True, account_label=data.get("account_label"))

    def start_auth(self, request) -> str:
        flow = Flow.from_client_config(
            _client_config(), scopes=_SCOPES,
            redirect_uri=settings.GOOGLE_CALENDAR_REDIRECT_URI)
        auth_url, state = flow.authorization_url(access_type="offline", prompt="consent")
        request.session["google_oauth_state"] = state
        return auth_url

    def handle_callback(self, request) -> None:
        state = request.session.pop("google_oauth_state", None)
        if not state:
            raise ValueError("No pending Google sign-in for this browser session.")
        flow = Flow.from_client_config(
            _client_config(), scopes=_SCOPES, state=state,
            redirect_uri=settings.GOOGLE_CALENDAR_REDIRECT_URI)
        flow.fetch_token(authorization_response=request.build_absolute_uri())

        creds = flow.credentials
        account_label = None
        try:
            resp = requests.get(_USERINFO_URL,
                                headers={"Authorization": "Bearer %s" % creds.token}, timeout=10)
            if resp.ok:
                account_label = resp.json().get("email")
        except requests.RequestException:
            pass   # cosmetic only -- a missing label never blocks connecting

        tokens.save_token(self.key, {
            "credentials": json.loads(creds.to_json()),
            "account_label": account_label,
        })

    def _credentials(self) -> Credentials:
        data = tokens.load_token(self.key)
        if not data:
            raise ValueError("Not connected to Google.")
        creds = Credentials.from_authorized_user_info(data["credentials"], _SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleAuthRequest())
            data["credentials"] = json.loads(creds.to_json())
            tokens.save_token(self.key, data)
        return creds

    def fetch_events(self, window_start: dt.date, window_end: dt.date) -> list[RawCalendarEvent]:
        creds = self._credentials()
        headers = {"Authorization": "Bearer %s" % creds.token}
        params = {
            "timeMin": dt.datetime.combine(window_start, dt.time.min, dt.timezone.utc).isoformat(),
            "timeMax": dt.datetime.combine(window_end, dt.time.min, dt.timezone.utc).isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 250,
        }
        events: list[RawCalendarEvent] = []
        page_token = None
        while True:
            if page_token:
                params["pageToken"] = page_token
            resp = requests.get(_EVENTS_URL, headers=headers, params=params, timeout=15)
            resp.raise_for_status()
            payload = resp.json()
            for item in payload.get("items", []):
                if item.get("status") == "cancelled":
                    continue
                start, all_day = _parse_event_time(item["start"])
                end, _ = _parse_event_time(item["end"])
                events.append(RawCalendarEvent(
                    source_id=item["id"], start=start, end=end,
                    busy_status=_busy_status(item), all_day=all_day,
                    subject=item.get("summary", ""),
                ))
            page_token = payload.get("nextPageToken")
            if not page_token:
                break
        return events

    def disconnect(self) -> None:
        tokens.clear_token(self.key)

    def _headers(self) -> dict:
        return {"Authorization": "Bearer %s" % self._credentials().token}

    def ensure_jimothy_calendar(self) -> str:
        data = tokens.load_token(self.key) or {}
        cached_id = data.get("jimothy_calendar_id")
        if cached_id:
            return cached_id

        resp = requests.get(_CALENDAR_LIST_URL, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        existing = next((c for c in resp.json().get("items", [])
                         if c.get("summary") == _JIMOTHY_CALENDAR_NAME), None)
        if existing:
            calendar_id = existing["id"]
        else:
            resp = requests.post(_CALENDARS_URL, headers=self._headers(),
                                 json={"summary": _JIMOTHY_CALENDAR_NAME}, timeout=15)
            resp.raise_for_status()
            calendar_id = resp.json()["id"]

        data["jimothy_calendar_id"] = calendar_id
        tokens.save_token(self.key, data)
        return calendar_id

    def _event_body(self, subject: str, start: dt.datetime, end: dt.datetime,
                     all_day: bool) -> dict:
        if all_day:
            return {"summary": subject,
                   "start": {"date": start.date().isoformat()},
                   "end": {"date": end.date().isoformat()}}
        return {"summary": subject,
               "start": {"dateTime": start.isoformat()},
               "end": {"dateTime": end.isoformat()}}

    def create_event(self, subject: str, start: dt.datetime, end: dt.datetime,
                      all_day: bool) -> str:
        calendar_id = self.ensure_jimothy_calendar()
        resp = requests.post(
            "%s/calendars/%s/events" % (_CALENDARS_URL, calendar_id), headers=self._headers(),
            json=self._event_body(subject, start, end, all_day), timeout=15)
        resp.raise_for_status()
        return resp.json()["id"]

    def update_event(self, source_id: str, subject: str, start: dt.datetime,
                      end: dt.datetime, all_day: bool) -> None:
        calendar_id = self.ensure_jimothy_calendar()
        resp = requests.patch(
            "%s/calendars/%s/events/%s" % (_CALENDARS_URL, calendar_id, source_id),
            headers=self._headers(), json=self._event_body(subject, start, end, all_day),
            timeout=15)
        resp.raise_for_status()

    def delete_event(self, source_id: str) -> None:
        calendar_id = self.ensure_jimothy_calendar()
        resp = requests.delete(
            "%s/calendars/%s/events/%s" % (_CALENDARS_URL, calendar_id, source_id),
            headers=self._headers(), timeout=15)
        if resp.status_code not in (404, 410):
            resp.raise_for_status()
