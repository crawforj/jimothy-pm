# Security Policy

Jimothy is a single-user, local-first tool — no accounts, no multi-tenancy,
and by default it only binds to `127.0.0.1`. Most of the usual web-app attack
surface (session hijacking across users, cross-tenant data leaks) doesn't
apply to the default use case. That said, a few things matter if you deploy
it anywhere beyond your own machine:

## Configuration

- **Always set a real `DJANGO_SECRET_KEY`** (see `.env.example`) before
  running this anywhere but local development. The fallback value in
  `config/settings.py` is intentionally marked insecure and is for local
  dev only.
- **Set `DJANGO_DEBUG=False`** for anything other than local development.
  Debug mode exposes stack traces and settings values.
- If you bind Jimothy beyond `127.0.0.1` (e.g. to make it reachable on a
  LAN), set `DJANGO_ALLOWED_HOSTS` and put it behind your own
  authentication — Jimothy itself has no login.

## Reporting a vulnerability

If you find a security issue, please **do not open a public GitHub issue**.
Use GitHub's private vulnerability reporting (Security tab → "Report a
vulnerability") on this repository instead. We'll acknowledge reports
within a few days.
