"""Pull calendar events for the primary/manager Staff row from every
connected provider (plan §7c). Read-only, v1: both Connect buttons on
Settings are global (one Microsoft connection, one Google connection per
running instance), tied to whichever Staff row has is_manager=True --
Staff.calendar_shared stays inert until a later phase lets individual staff
connect their own calendars."""

import datetime as dt
import logging

from django.core.management.base import BaseCommand

from core.calendarsync.graph_provider import GraphCalendarProvider
from core.calendarsync.google_provider import GoogleCalendarProvider
from core.models import CalendarEvent, Staff

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Sync connected calendars (Microsoft Graph, Google) into CalendarEvent."

    def add_arguments(self, parser):
        parser.add_argument("--weeks-back", type=int, default=2)
        parser.add_argument("--weeks-forward", type=int, default=6)

    def handle(self, *args, **options):
        primary = Staff.objects.filter(is_manager=True, active=True).first()
        if primary is None:
            self.stdout.write(self.style.WARNING(
                "No active manager Staff row to sync calendars into."))
            return

        today = dt.date.today()
        window_start = today - dt.timedelta(weeks=options["weeks_back"])
        window_end = today + dt.timedelta(weeks=options["weeks_forward"])

        for provider in (GraphCalendarProvider(), GoogleCalendarProvider()):
            if not provider.is_configured():
                continue
            if not provider.status().connected:
                continue
            try:
                raw_events = provider.fetch_events(window_start, window_end)
            except Exception:
                logger.exception("Jimothy %s calendar sync failed", provider.key)
                self.stdout.write(self.style.WARNING(
                    "%s sync failed -- see log." % provider.display_name))
                continue

            seen_ids = []
            for raw in raw_events:
                CalendarEvent.objects.update_or_create(
                    staff=primary, provider=provider.key, source_id=raw.source_id,
                    defaults=dict(start=raw.start, end=raw.end,
                                 busy_status=raw.busy_status.value,
                                 all_day=raw.all_day, subject=raw.subject))
                seen_ids.append(raw.source_id)

            # Prune events this run didn't see again -- cancelled/moved
            # meetings, or anything that fell outside the rolling window.
            CalendarEvent.objects.filter(
                staff=primary, provider=provider.key
            ).exclude(source_id__in=seen_ids).delete()

            self.stdout.write(self.style.SUCCESS(
                "%s: synced %d events" % (provider.display_name, len(raw_events))))
