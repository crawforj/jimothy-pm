"""One-file backup of db.sqlite3 (plan §8's planned command list). OneDrive
already versions the live file (plan §8); this is for a clean point-in-time
copy before risky changes."""

import datetime as dt
import shutil

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Copy db.sqlite3 to backups/jimothy-YYYY-MM-DD.sqlite3."

    def handle(self, *args, **options):
        src = settings.DATABASES["default"]["NAME"]
        if not src.exists():
            self.stdout.write(self.style.ERROR("No db.sqlite3 found at %s" % src))
            return
        backups_dir = settings.BASE_DIR / "backups"
        backups_dir.mkdir(exist_ok=True)
        dest = backups_dir / ("jimothy-%s.sqlite3" % dt.date.today().isoformat())
        shutil.copy2(src, dest)
        self.stdout.write(self.style.SUCCESS("Backed up to %s" % dest))
