"""Entry point for the packaged Windows build (PyInstaller) -- not used by
normal development (that's manage.py, same as always). This exists because
the packaged app needs things manage.py doesn't: redirect writable data
next to the .exe (see config/settings.py's DATA_DIR), seed on first run
only, and auto-open a browser instead of expecting the user to know a URL.
"""

import os
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

# Same frozen-path logic as config/settings.py's DATA_DIR -- duplicated
# (not imported) because this has to run *before* django.setup(), which is
# when settings.py actually reads the .env file. A packaged .exe ships
# alone, with no .env.example next to it to use as a template, so this
# just writes a minimal one with a freshly generated real secret key --
# matching what setup.sh/setup.ps1 already do for the other install paths,
# instead of every copy of the .exe silently sharing one hardcoded key.
if getattr(sys, "frozen", False):
    _data_dir = Path(sys.executable).resolve().parent
else:
    _data_dir = Path(__file__).resolve().parent

_env_file = _data_dir / ".env"
if not _env_file.exists():
    from django.core.management.utils import get_random_secret_key
    _env_file.write_text("DJANGO_SECRET_KEY=%s\n" % get_random_secret_key())

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.core.management import call_command  # noqa: E402

URL = "http://127.0.0.1:8000/"


def _open_browser_when_ready(url: str, timeout: float = 25.0) -> None:
    """Poll until the server actually answers, then open the browser --
    opening immediately would show a "can't connect" page while Django is
    still starting up."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    webbrowser.open(url)


def main() -> None:
    fresh_install = not (settings.DATA_DIR / "db.sqlite3").exists()

    call_command("migrate", verbosity=1)
    if fresh_install:
        call_command("seed_demo")

    threading.Thread(target=_open_browser_when_ready, args=(URL,), daemon=True).start()

    print()
    print("Jimothy is running. This window is its log -- closing it stops the app.")
    print("If your browser didn't open automatically, go to:", URL)
    print()

    call_command("runserver", "127.0.0.1:8000", use_reloader=False)


if __name__ == "__main__":
    main()
