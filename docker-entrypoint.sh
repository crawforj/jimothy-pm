#!/bin/sh
# Shared by both Docker paths (see README): Option A's docker-compose.yml
# (build-from-source, bind-mounts the repo at /app, no JIMOTHY_DATA_DIR set)
# and the zero-clone `docker run` path (prebuilt image, JIMOTHY_DATA_DIR=/data
# backed by a named volume). Same image, same script either way -- only the
# env var differs. Mirrors config/settings.py's DATA_DIR fallback exactly.
set -e

DATA_DIR="${JIMOTHY_DATA_DIR:-/app}"
mkdir -p "$DATA_DIR"

# Auto-generate a real secret key on first run, the same way desktop_app.py
# already does for the packaged builds -- otherwise a from-scratch `docker
# run` (no docker-compose.yml environment: block to supply one) would have
# no secret key at all. Persisted into DATA_DIR, not regenerated on restart
# (that would invalidate every session).
if [ -z "$DJANGO_SECRET_KEY" ] && [ ! -f "$DATA_DIR/.env" ]; then
  python -c "from django.core.management.utils import get_random_secret_key; print('DJANGO_SECRET_KEY=' + get_random_secret_key())" > "$DATA_DIR/.env"
fi

python manage.py migrate
if [ ! -f "$DATA_DIR/db.sqlite3.seeded" ]; then
  python manage.py seed_demo
  touch "$DATA_DIR/db.sqlite3.seeded"
fi

exec python manage.py runserver 0.0.0.0:8000
