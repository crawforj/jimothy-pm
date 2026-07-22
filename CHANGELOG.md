# Changelog

All notable changes to Jimothy are documented here. Loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions follow semver
in spirit (new features → minor bump, fixes-only → patch; there's no
external API yet, so nothing has needed a major bump).

## [Unreleased]

## [0.4.0] - 2026-07-21

### Added

- Calendar writes (plan §7c): project milestones/deadlines and live
  Focus Mode sessions push into a dedicated "Jimothy" calendar, never the
  user's own — off by default via a per-provider Settings toggle. Google
  gets a narrower "only what this app created" scope
  (`calendar.app.created`); Microsoft Graph has no equivalent and needs
  the broader `Calendars.ReadWrite`, called out plainly in the Settings
  copy.
- A one-click "Download a backup of your data" link on Settings — a
  browser-only way to get a real `.sqlite3` file out of a Docker volume
  or a Codespace, no terminal required.

### Changed

- README promotes GitHub Codespaces from a "just for looking" demo to a
  genuine day-to-day install path: how to resume it, its idle/auto-delete
  behavior, its free tier.

## [0.3.0] - 2026-07-21

### Added

- A truly zero-clone Docker install:
  `docker run -p 8000:8000 -v jimothy-data:/data -e JIMOTHY_DATA_DIR=/data --name jimothy ghcr.io/crawforj/jimothy-pm:latest`
  — no `git clone`, no local build.
- Burndown chart and a Monte Carlo forecast range bar on the project
  Report page, a team capacity heatmap on Staff, drag-and-drop status
  changes on the Week sprint board (with a fully keyboard-accessible
  dropdown as the underlying control, not a mouse-only replacement), and
  a mascot mood tied to portfolio health.

## [0.2.0] - 2026-07-21

### Added

- Read-only calendar sync: connect Microsoft Outlook or Google Calendar
  from Settings so real meeting time replaces the flat capacity estimate
  on Today, Focus, and the morning briefing.
- Daily auto-backup and `--install-autostart` for the packaged builds
  (originally v0.1.2).

### Fixed

- Windows console appearing to freeze on launch — Console QuickEdit Mode
  (originally v0.1.3).

## [0.1.1] - 2026-07-21

### Added

- First real macOS build (`Jimothy-macos`), built and smoke-tested on
  GitHub's own `macos-latest` runner.

### Fixed

- Two Codespaces bugs: CSRF trusted origins, a blank preview panel.
- `release.yml` now grants itself `contents: write` explicitly (the
  default `GITHUB_TOKEN` is read-only), fixing release-asset uploads.

## [0.1.0] - 2026-07-21

### Added

- Initial standalone executables (Windows, Linux) — no Python, Docker, or
  git required. Self-seeds an example portfolio and opens a browser
  automatically on first launch.
