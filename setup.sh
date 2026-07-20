#!/usr/bin/env bash
# One-command setup for Jimothy (macOS/Linux/WSL). Safe to re-run — only
# loads example data on a genuinely fresh install (skips it if db.sqlite3
# already exists, so it never wipes a real portfolio).
set -e

cd "$(dirname "$0")"

PYTHON=${PYTHON:-python3}
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    PYTHON=python
fi
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "Python was not found. Install Python 3.12+ from https://www.python.org/downloads/"
    echo "and try again."
    exit 1
fi

PY_VERSION=$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 12 ]; }; then
    echo "Jimothy needs Python 3.12+. Found $PY_VERSION."
    echo "Install a newer version from https://www.python.org/downloads/ and try again."
    exit 1
fi

FRESH_INSTALL=1
[ -f db.sqlite3 ] && FRESH_INSTALL=0

if [ ! -d .venv ]; then
    echo "Creating a virtual environment (.venv)..."
    "$PYTHON" -m venv .venv
fi

VENV_PY=.venv/bin/python
[ -f "$VENV_PY" ] || VENV_PY=.venv/Scripts/python.exe   # Git Bash on Windows

echo "Installing dependencies..."
"$VENV_PY" -m pip install --quiet --upgrade pip
"$VENV_PY" -m pip install --quiet -r requirements.txt

if [ ! -f .env ]; then
    echo "Creating .env with a freshly generated secret key..."
    # Done entirely in Python, not shell string substitution -- the
    # generated key's charset includes #, $, and other characters that
    # would break sed/regex delimiters depending on what comes out.
    "$VENV_PY" - <<'PYEOF'
from django.core.management.utils import get_random_secret_key

key = get_random_secret_key()
with open(".env.example") as f:
    lines = f.readlines()
with open(".env", "w") as f:
    for line in lines:
        if line.startswith("DJANGO_SECRET_KEY="):
            f.write("DJANGO_SECRET_KEY=%s\n" % key)
        else:
            f.write(line)
PYEOF
fi

echo "Setting up the database..."
"$VENV_PY" manage.py migrate

if [ "$FRESH_INSTALL" = "1" ]; then
    echo "Loading example data..."
    "$VENV_PY" manage.py seed_demo
fi

echo ""
echo "Ready. Starting the server -- open http://127.0.0.1:8000/ in your browser."
echo "(Press Ctrl+C to stop it.)"
"$VENV_PY" manage.py runserver
