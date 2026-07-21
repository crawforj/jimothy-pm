"""Microsoft Graph calendar provider -- public-client OAuth (msal), no
client secret. Uses initiate_auth_code_flow()/acquire_token_by_auth_code_flow(),
the web-app-style API, not msal's own embedded local server, since Jimothy
is already the local server handling the redirect."""

from __future__ import annotations

import datetime as dt
import re

import msal
import requests
from django.conf import settings

from core.calendarsync import tokens
from core.calendarsync.base import CalendarProvider, ProviderStatus, RawCalendarEvent
from engine.calendar_capacity import BusyStatus

_SCOPES = ["Calendars.Read"]
_GRAPH_BASE = "https://graph.microsoft.com/v1.0"

_SHOWAS_MAP = {
    "free": BusyStatus.FREE,
    "tentative": BusyStatus.TENTATIVE,
    "busy": BusyStatus.BUSY,
    "oof": BusyStatus.OUT_OF_OFFICE,
    "workingElsewhere": BusyStatus.FREE,
}


def _parse_graph_datetime(value: str) -> dt.datetime:
    # Graph can return up to 7 fractional-second digits (100ns ticks);
    # datetime.fromisoformat only accepts up to 6.
    value = re.sub(r"(\.\d{6})\d+$", r"\1", value)
    return dt.datetime.fromisoformat(value).replace(tzinfo=dt.timezone.utc)


class GraphCalendarProvider(CalendarProvider):
    key = "graph"
    display_name = "Microsoft Outlook"

    def is_configured(self) -> bool:
        return bool(settings.MICROSOFT_GRAPH_CLIENT_ID)

    def _cache(self) -> msal.SerializableTokenCache:
        cache = msal.SerializableTokenCache()
        data = tokens.load_token(self.key)
        if data and data.get("msal_cache"):
            cache.deserialize(data["msal_cache"])
        return cache

    def _app(self, cache: msal.SerializableTokenCache) -> msal.PublicClientApplication:
        return msal.PublicClientApplication(
            settings.MICROSOFT_GRAPH_CLIENT_ID,
            authority=settings.MICROSOFT_GRAPH_AUTHORITY,
            token_cache=cache,
        )

    def _save_cache_if_changed(self, cache: msal.SerializableTokenCache) -> None:
        if cache.has_state_changed:
            data = tokens.load_token(self.key) or {}
            data["msal_cache"] = cache.serialize()
            tokens.save_token(self.key, data)

    def status(self) -> ProviderStatus:
        data = tokens.load_token(self.key)
        if not data:
            return ProviderStatus(connected=False)
        return ProviderStatus(connected=True, account_label=data.get("account_label"))

    def start_auth(self, request) -> str:
        app = self._app(self._cache())
        flow = app.initiate_auth_code_flow(
            scopes=_SCOPES, redirect_uri=settings.MICROSOFT_GRAPH_REDIRECT_URI)
        request.session["graph_auth_flow"] = flow
        return flow["auth_uri"]

    def handle_callback(self, request) -> None:
        flow = request.session.pop("graph_auth_flow", None)
        if not flow:
            raise ValueError("No pending Microsoft sign-in for this browser session.")
        cache = msal.SerializableTokenCache()
        app = self._app(cache)
        result = app.acquire_token_by_auth_code_flow(flow, request.GET.dict())
        if "error" in result:
            raise ValueError(result.get("error_description", result["error"]))
        account_label = (result.get("id_token_claims") or {}).get("preferred_username")
        tokens.save_token(self.key, {
            "msal_cache": cache.serialize(),
            "account_label": account_label,
        })

    def fetch_events(self, window_start: dt.date, window_end: dt.date) -> list[RawCalendarEvent]:
        cache = self._cache()
        app = self._app(cache)
        accounts = app.get_accounts()
        if not accounts:
            raise ValueError("Not connected to Microsoft.")
        result = app.acquire_token_silent(_SCOPES, account=accounts[0])
        self._save_cache_if_changed(cache)
        if not result or "access_token" not in result:
            raise ValueError("Microsoft sign-in expired -- reconnect from Settings.")

        headers = {
            "Authorization": "Bearer %s" % result["access_token"],
            "Prefer": 'outlook.timezone="UTC"',
        }
        params = {
            "startDateTime": dt.datetime.combine(window_start, dt.time.min).isoformat(),
            "endDateTime": dt.datetime.combine(window_end, dt.time.min).isoformat(),
            "$top": "100",
            "$select": "id,subject,start,end,isAllDay,showAs",
        }
        events: list[RawCalendarEvent] = []
        url = "%s/me/calendarView" % _GRAPH_BASE
        while url:
            resp = requests.get(url, headers=headers, params=params, timeout=15)
            resp.raise_for_status()
            payload = resp.json()
            for item in payload.get("value", []):
                events.append(RawCalendarEvent(
                    source_id=item["id"],
                    start=_parse_graph_datetime(item["start"]["dateTime"]),
                    end=_parse_graph_datetime(item["end"]["dateTime"]),
                    busy_status=_SHOWAS_MAP.get(item.get("showAs"), BusyStatus.BUSY),
                    all_day=item.get("isAllDay", False),
                    subject=item.get("subject", ""),
                ))
            url = payload.get("@odata.nextLink")
            params = None   # nextLink already carries the full query string

        return events

    def disconnect(self) -> None:
        tokens.clear_token(self.key)
