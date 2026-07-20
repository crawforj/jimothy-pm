"""Friday sprint close-out from the command line (plan §8's planned command
list) — the CLI equivalent of the Week view's close-out form."""

from django.core.management.base import BaseCommand

from core import phrases
from core.services import build_uplifts, get_or_create_sprint
from engine.sprint import compute_velocity


class Command(BaseCommand):
    help = "Close out the current week's sprint: compute velocity, record a retro note."

    def handle(self, *args, **options):
        sprint = get_or_create_sprint()
        committed = list(sprint.committed.all())

        if not committed:
            self.stdout.write(self.style.WARNING(
                "Nothing committed to the sprint starting %s — nothing to close out."
                % sprint.week_start))
            return

        e_committed = [t.to_engine() for t in committed]
        uplifts = build_uplifts(e_committed)
        velocity = compute_velocity(e_committed, uplifts)
        sprint.velocity_actual = velocity

        self.stdout.write(phrases.closeout_message(velocity))
        self.stdout.write(phrases.retro_prompt())
        note = input("> ").strip()
        sprint.retro_note = note
        sprint.save()
        self.stdout.write(self.style.SUCCESS("Sprint closed out."))
