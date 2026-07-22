"""CalendarProvider abstraction (plan §7c: "build the fetcher behind an
interface from day one"). Concrete providers (graph_provider.py,
google_provider.py) implement this; callers (views, sync_calendar,
desktop_app.py) only ever talk to this interface."""

from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from dataclasses import dataclass

from engine.calendar_capacity import BusyStatus


@dataclass
class ProviderStatus:
    connected: bool
    account_label: str | None = None
    error: str | None = None


@dataclass
class RawCalendarEvent:
    source_id: str
    start: dt.datetime
    end: dt.datetime
    busy_status: BusyStatus
    all_day: bool
    subject: str


class CalendarProvider(ABC):
    key: str
    display_name: str

    @abstractmethod
    def is_configured(self) -> bool:
        """True once a client ID exists for this provider (baked-in or
        env-overridden) -- independent of whether anyone has connected an
        account yet."""

    @abstractmethod
    def status(self) -> ProviderStatus:
        """Reads the token cache only -- no network call, safe to call on
        every Settings-page load."""

    @abstractmethod
    def start_auth(self, request) -> str:
        """Stashes whatever flow state this provider needs in
        request.session, returns the URL to redirect the browser to."""

    @abstractmethod
    def handle_callback(self, request) -> None:
        """Completes the token exchange using request.session's stashed
        state plus request.GET's query params, persists the result via
        core.calendarsync.tokens.save_token. Raises on failure -- the
        calling view decides how to surface that to the user."""

    @abstractmethod
    def fetch_events(self, window_start: dt.date, window_end: dt.date) -> list[RawCalendarEvent]:
        """Refreshes the access token as needed and pulls events for the
        given date window. Raises on failure."""

    @abstractmethod
    def disconnect(self) -> None:
        """Clears the stored token. Does not revoke it server-side (out of
        scope for v1) -- signing out of the account elsewhere is the
        equivalent of a hard revoke if that's ever needed."""

    @abstractmethod
    def ensure_jimothy_calendar(self) -> str:
        """Returns the id of a dedicated 'Jimothy' calendar, creating it via
        the API the first time it's needed. All writes target only this
        calendar -- Jimothy never creates, edits, or deletes anything in
        the user's own primary calendar."""

    @abstractmethod
    def create_event(self, subject: str, start: dt.datetime, end: dt.datetime,
                      all_day: bool) -> str:
        """Creates an event in the Jimothy calendar, returns its source_id."""

    @abstractmethod
    def update_event(self, source_id: str, subject: str, start: dt.datetime,
                      end: dt.datetime, all_day: bool) -> None:
        """Updates an event Jimothy previously created via create_event."""

    @abstractmethod
    def delete_event(self, source_id: str) -> None:
        """Deletes an event Jimothy previously created. A no-op, not an
        error, if it's already gone (same tolerance as disconnect())."""
