"""Entry point for the packaged Windows/macOS/Linux builds (PyInstaller) --
not used by normal development (that's manage.py, same as always). This
exists because the packaged app needs things manage.py doesn't: redirect
writable data next to the binary (see config/settings.py's DATA_DIR), seed
on first run only, auto-open a browser instead of expecting the user to
know a URL, take a daily automatic backup, and offer `--install-autostart`
so it can relaunch itself at login without the user remembering to.
"""

import os
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

if sys.platform == "win32":
    # Windows consoles default to "QuickEdit Mode": a single accidental
    # click inside the window pauses the ENTIRE process (all threads,
    # including the one about to open the browser) until the user presses
    # Enter/Esc to release the text-selection state it started. From the
    # outside this looks exactly like "the window opened blank and nothing
    # happens until I press Enter" -- a real, well-documented Windows
    # console behavior, not a bug in what's printed or how it's flushed.
    # Disabling it here is the standard fix (must OR in
    # ENABLE_EXTENDED_FLAGS when clearing ENABLE_QUICK_EDIT_MODE, or the
    # mode change is silently ignored). Best-effort: if this ever fails
    # (e.g. no real console attached), the app should still run normally.
    try:
        import ctypes

        STD_INPUT_HANDLE = -10
        ENABLE_EXTENDED_FLAGS = 0x0080
        ENABLE_QUICK_EDIT_MODE = 0x0040
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(STD_INPUT_HANDLE)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            new_mode = (mode.value & ~ENABLE_QUICK_EDIT_MODE) | ENABLE_EXTENDED_FLAGS
            kernel32.SetConsoleMode(handle, new_mode)
    except Exception:
        pass

# Handle --install-autostart / --uninstall-autostart before anything else --
# neither needs Django, and this way they stay instant (no migrate, no .env
# generation) rather than a side effect of the normal startup path.
if len(sys.argv) > 1 and sys.argv[1] in ("--install-autostart", "--uninstall-autostart"):
    import desktop_autostart

    print(desktop_autostart.install() if sys.argv[1] == "--install-autostart" else desktop_autostart.uninstall())
    sys.exit(0)

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
BACKUP_INTERVAL_SECONDS = 24 * 60 * 60


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


def _auto_backup_loop() -> None:
    """Take a `backup` right away (covers a session that gets closed within
    a day) and then once every 24h for as long as the app stays open. Never
    fatal -- a failed backup shouldn't take the whole app down."""
    while True:
        try:
            call_command("backup")
        except Exception as exc:
            print("Automatic backup failed (Jimothy keeps running):", exc)
        time.sleep(BACKUP_INTERVAL_SECONDS)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "backup":
        call_command("backup")
        return

    fresh_install = not (settings.DATA_DIR / "db.sqlite3").exists()

    call_command("migrate", verbosity=1)
    if fresh_install:
        call_command("seed_demo")

    threading.Thread(target=_open_browser_when_ready, args=(URL,), daemon=True).start()
    threading.Thread(target=_auto_backup_loop, daemon=True).start()

    print()
    print("Jimothy is running. This window is its log -- closing it stops the app.")
    print("If your browser didn't open automatically, go to:", URL)
    print("Your data is backed up daily to the 'backups' folder next to this app.")
    print("To start Jimothy automatically at login, run it again with --install-autostart.")
    print()

    call_command("runserver", "127.0.0.1:8000", use_reloader=False)


if __name__ == "__main__":
    main()
