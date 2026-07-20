"""Jimothy Phase 0 deployment spike — Tier 1/2 capability check.

Run this on the target machine under any Python you can start:
    python spike_check.py

Pure stdlib, read-only: it creates nothing outside its own folder except a
temp file in %TEMP%, changes no system state, makes no network requests
beyond a loopback connection to itself.

It prints (and writes to spike_result.txt) a PASS/FAIL block to send back.
"""

import json
import os
import platform
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time

RESULTS = []


def check(name, fn):
    try:
        detail = fn()
        RESULTS.append((name, "PASS", detail or ""))
    except Exception as exc:  # noqa: BLE001 - report everything, crash never
        RESULTS.append((name, "FAIL", "%s: %s" % (type(exc).__name__, exc)))


def python_info():
    return "%s | %s" % (sys.version.split()[0], sys.executable)


def sqlite_roundtrip():
    path = os.path.join(tempfile.gettempdir(), "jimothy_spike.sqlite3")
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE IF NOT EXISTS t (x)")
    con.execute("INSERT INTO t VALUES (42)")
    val = con.execute("SELECT x FROM t").fetchone()[0]
    con.close()
    os.remove(path)
    assert val == 42
    return "sqlite %s ok" % sqlite3.sqlite_version


def bind_high_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return "bound 127.0.0.1:%d" % port


def loopback_http():
    # Prove a localhost web app is reachable from this user session.
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.request import urlopen

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"jimothy")

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        body = urlopen("http://127.0.0.1:%d/" % port, timeout=5).read()
    finally:
        srv.shutdown()
    assert body == b"jimothy"
    return "GET http://127.0.0.1:%d ok" % port


def user_profile_writable():
    target = os.path.join(os.environ["USERPROFILE"], "jimothy_spike_tmp.txt")
    with open(target, "w") as f:
        f.write("ok")
    os.remove(target)
    return target


def onedrive_present():
    for var in ("OneDriveCommercial", "OneDrive", "OneDriveConsumer"):
        path = os.environ.get(var)
        if path and os.path.isdir(path):
            return "%s=%s" % (var, path)
    raise FileNotFoundError("no OneDrive env var points to a folder")


def task_scheduler_readable():
    # Read-only probe. Being able to *query* is necessary but not sufficient
    # for creating user-level tasks; we deliberately do not create one here.
    out = subprocess.run(
        ["schtasks", "/query", "/fo", "LIST"],
        capture_output=True, timeout=20,
    )
    assert out.returncode == 0, out.stderr.decode(errors="replace")[:200]
    return "schtasks /query ok (%d bytes)" % len(out.stdout)


def outlook_com_registered():
    import winreg

    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Outlook.Application\CLSID") as k:
        clsid = winreg.QueryValueEx(k, "")[0]
    return "classic Outlook COM registered (%s)" % clsid


def ctypes_loads():
    import ctypes

    ctypes.windll.kernel32.GetTickCount()
    return "ctypes/windll ok"


def pip_available():
    out = subprocess.run(
        [sys.executable, "-m", "pip", "--version"],
        capture_output=True, timeout=30,
    )
    assert out.returncode == 0, "no pip (normal for embeddable; get-pip.py fixes it)"
    return out.stdout.decode(errors="replace").strip()[:80]


def main():
    check("python", python_info)
    check("platform", lambda: "%s %s" % (platform.system(), platform.version()))
    check("sqlite_file_db", sqlite_roundtrip)
    check("bind_localhost_port", bind_high_port)
    check("loopback_http_server", loopback_http)
    check("write_user_profile", user_profile_writable)
    check("onedrive_folder", onedrive_present)
    check("task_scheduler_query", task_scheduler_readable)
    check("outlook_classic_com", outlook_com_registered)
    check("ctypes", ctypes_loads)
    check("pip", pip_available)

    core = {"sqlite_file_db", "bind_localhost_port", "loopback_http_server",
            "write_user_profile"}
    core_ok = all(s == "PASS" for n, s, _ in RESULTS if n in core)
    verdict = ("TIER 1/2 VIABLE - core checks passed" if core_ok
               else "CORE CHECK FAILED - likely Tier 3 (browser) territory")

    lines = ["=== JIMOTHY-SPIKE-RESULT v1 ==="]
    for name, status, detail in RESULTS:
        lines.append("%-22s %-4s %s" % (name, status, detail))
    lines.append("verdict: " + verdict)
    lines.append("json: " + json.dumps(
        {n: s for n, s, _ in RESULTS}, separators=(",", ":")))
    lines.append("=== END ===")
    report = "\n".join(lines)

    print(report)
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "spike_result.txt")
    try:
        with open(out_path, "w") as f:
            f.write(report + "\n")
        print("\n(saved to %s)" % out_path)
    except OSError as exc:
        print("\n(could not save report next to script: %s)" % exc)


if __name__ == "__main__":
    main()
