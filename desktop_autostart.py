"""Register/unregister the packaged Jimothy build to launch automatically
when you log in -- invoked from desktop_app.py via `--install-autostart` /
`--uninstall-autostart`, before any Django setup happens (this has no
Django dependency at all).

Deliberately the same behavior on every OS: start at login, nothing more.
There's no "keep alive"/restart-on-crash service anywhere here -- if you
close the window (or log off) it stays closed until you log back in or run
it yourself, so it never fights a deliberate quit.

If you later move or rename the binary, the registered entry still points
at the old path -- run --uninstall-autostart, move the file, then
--install-autostart again from the new location.
"""

import os
import plistlib
import subprocess
import sys
from pathlib import Path

_LABEL = "com.trueascentlabs.jimothy"


def _exe_path() -> Path:
    if not getattr(sys, "frozen", False):
        raise RuntimeError(
            "Autostart registration is only meaningful for the packaged "
            "build (Jimothy.exe / Jimothy-macos / Jimothy-linux). During "
            "development, just run manage.py runserver directly."
        )
    return Path(sys.executable).resolve()


def install() -> str:
    exe = _exe_path()
    if sys.platform == "win32":
        return _install_windows(exe)
    if sys.platform == "darwin":
        return _install_macos(exe)
    return _install_linux(exe)


def uninstall() -> str:
    _exe_path()  # same "packaged build only" guard as install()
    if sys.platform == "win32":
        return _uninstall_windows()
    if sys.platform == "darwin":
        return _uninstall_macos()
    return _uninstall_linux()


# --- Windows: a shortcut-free .bat in the per-user Startup folder ---------

def _windows_bat_path() -> Path:
    appdata = Path(os.environ["APPDATA"])
    return appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "Jimothy.bat"


def _install_windows(exe: Path) -> str:
    bat = _windows_bat_path()
    bat.parent.mkdir(parents=True, exist_ok=True)
    # write_text's default newline handling already translates "\n" to the
    # platform line ending -- writing literal "\r\n" here double-translates
    # on Windows (\r\n -> \r\r\n) and corrupts the file.
    bat.write_text('@echo off\nstart "" "%s"\n' % exe)
    return (
        "Installed: Jimothy will start automatically next time you log in "
        "to Windows.\nTo undo: run Jimothy.exe --uninstall-autostart, or "
        "delete\n%s" % bat
    )


def _uninstall_windows() -> str:
    bat = _windows_bat_path()
    if bat.exists():
        bat.unlink()
        return "Removed. Jimothy will no longer start automatically at login."
    return "Nothing to remove -- autostart wasn't installed."


# --- macOS: a LaunchAgent plist --------------------------------------------

def _macos_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / (_LABEL + ".plist")


def _install_macos(exe: Path) -> str:
    plist_path = _macos_plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    with open(plist_path, "wb") as f:
        plistlib.dump(
            {"Label": _LABEL, "ProgramArguments": [str(exe)], "RunAtLoad": True},
            f,
        )
    # Reload in case an older version of the agent is already loaded.
    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    subprocess.run(["launchctl", "load", "-w", str(plist_path)], capture_output=True)
    return (
        "Installed: Jimothy will start automatically next time you log in "
        "to macOS.\nTo undo: run ./Jimothy-macos --uninstall-autostart, or "
        "delete\n%s" % plist_path
    )


def _uninstall_macos() -> str:
    plist_path = _macos_plist_path()
    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
        plist_path.unlink()
        return "Removed. Jimothy will no longer start automatically at login."
    return "Nothing to remove -- autostart wasn't installed."


# --- Linux: an XDG autostart .desktop entry --------------------------------

def _linux_desktop_path() -> Path:
    return Path.home() / ".config" / "autostart" / "jimothy.desktop"


def _install_linux(exe: Path) -> str:
    desktop = _linux_desktop_path()
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Jimothy\n"
        "Exec=%s\n"
        "X-GNOME-Autostart-enabled=true\n" % exe
    )
    return (
        "Installed: Jimothy will start automatically next time you log in "
        "(any XDG-autostart desktop -- GNOME, KDE, XFCE, etc.).\nTo undo: "
        "run ./Jimothy-linux --uninstall-autostart, or delete\n%s" % desktop
    )


def _uninstall_linux() -> str:
    desktop = _linux_desktop_path()
    if desktop.exists():
        desktop.unlink()
        return "Removed. Jimothy will no longer start automatically at login."
    return "Nothing to remove -- autostart wasn't installed."
