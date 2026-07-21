"""Per-provider OAuth token-cache file I/O, kept in DATA_DIR (same directory
as db.sqlite3 and .env -- already redirects correctly next to a packaged
binary) rather than the SQLite DB. Deliberately outside backup.py's scope:
these are regenerable by reauthenticating, not portfolio data."""

import json
from pathlib import Path

from django.conf import settings


def _dir() -> Path:
    return settings.DATA_DIR / "calendar_tokens"


def token_path(provider_key: str) -> Path:
    return _dir() / ("%s.json" % provider_key)


def load_token(provider_key: str) -> dict | None:
    path = token_path(provider_key)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def save_token(provider_key: str, data: dict) -> None:
    _dir().mkdir(parents=True, exist_ok=True)
    token_path(provider_key).write_text(json.dumps(data))


def clear_token(provider_key: str) -> None:
    path = token_path(provider_key)
    if path.exists():
        path.unlink()
