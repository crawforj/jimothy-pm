"""Orchestrates calendar writes (plan §7c): pushing project milestones and
Focus-mode blocks into each connected provider's dedicated 'Jimothy'
calendar. One-directional -- Jimothy only ever touches events tracked in
PushedCalendarEvent, i.e. events it created itself.

Every function here loops the two providers independently and swallows
per-provider failures (log + skip), mirroring sync_calendar.py's existing
pattern -- a network hiccup or an under-scoped token on one provider must
never block the other, or bubble up into a model signal / view and break
an otherwise-unrelated save."""

from __future__ import annotations

import datetime as dt
import logging

from core.calendarsync import tokens
from core.calendarsync.google_provider import GoogleCalendarProvider
from core.calendarsync.graph_provider import GraphCalendarProvider
from core.models import PushedCalendarEvent

logger = logging.getLogger(__name__)


def _providers():
    return (GraphCalendarProvider(), GoogleCalendarProvider())


def _active_providers():
    for provider in _providers():
        if (provider.is_configured() and provider.status().connected
                and tokens.push_enabled(provider.key)):
            yield provider


def _push(*, milestone=None, task=None, subject: str, start: dt.datetime,
          end: dt.datetime, all_day: bool) -> None:
    lookup = {"milestone": milestone} if milestone else {"task": task}
    for provider in _active_providers():
        existing = PushedCalendarEvent.objects.filter(provider=provider.key, **lookup).first()
        try:
            if existing:
                provider.update_event(existing.source_id, subject, start, end, all_day)
            else:
                source_id = provider.create_event(subject, start, end, all_day)
                PushedCalendarEvent.objects.create(provider=provider.key, source_id=source_id,
                                                   **lookup)
        except Exception:
            logger.exception("Jimothy %s calendar push failed", provider.key)


def _remove(*, milestone=None, task=None) -> None:
    lookup = {"milestone": milestone} if milestone else {"task": task}
    for row in PushedCalendarEvent.objects.filter(**lookup):
        provider = next((p for p in _providers() if p.key == row.provider), None)
        if provider:
            try:
                provider.delete_event(row.source_id)
            except Exception:
                logger.exception("Jimothy %s calendar delete failed", provider.key)
        row.delete()


def push_milestone(milestone) -> None:
    if not milestone.due_date or milestone.done:
        remove_milestone_push(milestone)
        return
    subject = "%s — %s" % (milestone.project.name, milestone.name)
    start = dt.datetime.combine(milestone.due_date, dt.time.min)
    end = start + dt.timedelta(days=1)
    _push(milestone=milestone, subject=subject, start=start, end=end, all_day=True)


def remove_milestone_push(milestone) -> None:
    _remove(milestone=milestone)


def push_focus_block(task, start: dt.datetime, end: dt.datetime) -> None:
    subject = "Focus: %s" % task.title
    _push(task=task, subject=subject, start=start, end=end, all_day=False)


def remove_focus_block(task) -> None:
    _remove(task=task)
