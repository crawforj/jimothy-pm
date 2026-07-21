"""One-file backup of db.sqlite3, with old-copy pruning so this is safe to
run on an automatic daily schedule (see desktop_app.py's auto-backup thread)
without growing without bound. OneDrive or similar sync tools may already
version the live file for some users; this is a guaranteed, tool-independent
point-in-time copy either way."""

import datetime as dt
import shutil

from django.conf import settings
from django.core.management.base import BaseCommand

DEFAULT_KEEP = 14


class Command(BaseCommand):
    help = "Copy db.sqlite3 to backups/jimothy-YYYY-MM-DD.sqlite3, pruning older copies."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep",
            type=int,
            default=DEFAULT_KEEP,
            help="Number of most recent backups to retain (default: %d). 0 keeps all." % DEFAULT_KEEP,
        )

    def handle(self, *args, **options):
        src = settings.DATABASES["default"]["NAME"]
        if not src.exists():
            self.stdout.write(self.style.ERROR("No db.sqlite3 found at %s" % src))
            return

        # DATA_DIR, not BASE_DIR -- in a packaged build BASE_DIR resolves
        # inside PyInstaller's temp extraction folder, which is deleted when
        # the app exits, silently losing every backup written there.
        backups_dir = settings.DATA_DIR / "backups"
        backups_dir.mkdir(exist_ok=True)
        dest = backups_dir / ("jimothy-%s.sqlite3" % dt.date.today().isoformat())
        shutil.copy2(src, dest)
        self.stdout.write(self.style.SUCCESS("Backed up to %s" % dest))

        keep = options["keep"]
        if keep > 0:
            existing = sorted(backups_dir.glob("jimothy-*.sqlite3"))
            for old in existing[:-keep]:
                old.unlink()
