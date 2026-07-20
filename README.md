# Jimothy

A fun, encouraging project-management / scrum-master tool for a single manager
orchestrating a portfolio of projects and a small staff — on one machine, at
five time horizons simultaneously (today, week, month, quarter, year).

Jimothy is a decision-support engine for the person doing the juggling, not
a team-collaboration platform. There's no login, no multi-tenancy, no
cloud dependency — it's one person's local Django app with a SQLite file.

- Loosely follows the nine classic PMBOK knowledge areas, scrum-flavored
  (the week is the sprint; Friday close-out computes velocity)
- Multi-horizon prioritization engine (WSJF-style cost-of-delay, critical-path
  criticality, staleness, unblock value) with a backward-scheduling
  feasibility check
- PERT three-point estimates with per-person/per-tag calibration from actuals,
  plus Monte Carlo P50/P85 completion forecasting once enough history exists
- Recurring tasks that learn their own estimate from completion history
- Staffing capacity tracked in staff-days, with a forward capacity timeline
  per person
- Coach, not a nag: wins-first briefings, a "one thing right now" Focus Mode,
  honest and non-shaming warnings

**Status:** actively developed — Today, Focus, Week, Month, Quarter, Year,
Projects, Staff, and Reports are all built and working. See
[PROJECT_PLAN.md](PROJECT_PLAN.md) for the full design rationale and
[USER_GUIDE.md](USER_GUIDE.md) for a walkthrough of every page.

## Quick start

Whichever path you use, you'll land on a populated portfolio, not an empty
screen — an example project set (a grant deadline, a recurring weekly
report, a board-pending proposal, several completed tasks) loads
automatically, with every date computed relative to today so it's never
stale no matter when you install it.

> **New to the command line?** Every gray code box below (like the one right
> under Option A) is a set of commands, not something you paste into a
> file or into the Docker Desktop app. They go into a **terminal**:
> - **Windows:** click Start, type `PowerShell`, press Enter — a window
>   with a blinking cursor opens. Type or paste a line, press Enter, wait
>   for it to finish, then do the next line. (Right-click to paste; Ctrl+V
>   doesn't always work in Windows terminals.)
> - **macOS:** open **Terminal** from Spotlight (Cmd+Space, type
>   "Terminal"). **Linux:** you already know where yours is.
>
> Leave that window open while Jimothy is running — closing it stops the
> app. Option B's `setup.bat` skips all of this: just double-click the file.

### Try it instantly — no install at all (recommended if you just want to look)

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/crawforj/jimothy-pm)

Click that button. GitHub builds and runs Jimothy in a temporary cloud
environment — nothing touches your computer, no terminal, no Docker, no
Python install, not even a `git clone`. After a minute or two of "Setting
up your codespace," a browser preview pops up automatically already
showing Jimothy running. Requires a (free) GitHub account. This is the
single easiest way to see whether Jimothy is for you before installing it
for real with one of the options below.

### Download and run (no install at all)

One file, no Python, no Docker, no terminal (well — Linux needs one `chmod`).
It sets itself up in the same folder you put it in, loads example data, and
opens your browser automatically once it's ready. Your data (`db.sqlite3`,
next to the binary) stays there between launches — back it up by copying
that one file.

- **Windows: [⬇ Download Jimothy.exe](https://github.com/crawforj/jimothy-pm/releases/latest/download/Jimothy.exe)**
  — double-click it. Windows will show an "Unknown publisher" warning the
  first time (this build isn't code-signed) — click **More info → Run anyway**.
- **Linux: [⬇ Download Jimothy-linux](https://github.com/crawforj/jimothy-pm/releases/latest/download/Jimothy-linux)**
  — `chmod +x Jimothy-linux && ./Jimothy-linux`. Built on Debian 12
  (bookworm) for broad compatibility; if your distro's glibc is
  significantly older than that, use Docker instead.
- **macOS**: not built yet — no Mac hardware available to build or test one.
  Use Docker, the setup scripts, or GitHub Codespaces below in the meantime.

### Option A — Docker (no Python install needed)

If you have [Docker Desktop](https://www.docker.com/products/docker-desktop/)
and nothing else, this is the least fiddly path — it never touches your
system's Python at all. Open a terminal (see above) and run these three
lines, one at a time:

```bash
git clone https://github.com/crawforj/jimothy-pm.git
cd jimothy-pm
docker compose up
```

That third command will print a lot of scrolling text (it's downloading and
building — normal) and settle once you see a line like "Watching for file
changes." That's your signal it's ready. Now open
<http://127.0.0.1:8000/> in your actual web browser. `Ctrl+C` back in the
terminal stops it; running `docker compose up` again picks up right where
you left off (your data persists in `db.sqlite3` next to the code).

### Option B — one-command setup script (Python, no manual venv/activate)

If you have Python 3.12+ installed, these scripts handle everything else —
creating the virtual environment, installing dependencies, generating a
real secret key, and loading the example data — in one step:

**Windows:** double-click `setup.bat` (or run it from a terminal).
**macOS/Linux:** `./setup.sh`

Both are safe to re-run — re-running only sets up what's missing and never
re-loads example data over a real portfolio you've already started
entering.

### Option C — manual setup

For full control, or if you want to see exactly what's happening:

```bash
git clone https://github.com/crawforj/jimothy-pm.git
cd jimothy-pm
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env    # then edit .env and set a real DJANGO_SECRET_KEY --
                         # generate one with:
                         # python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Requires Python 3.12+. Open <http://127.0.0.1:8000/>.

### Troubleshooting

- **Windows: "running scripts is disabled on this system"** — this is
  PowerShell's default execution policy blocking `.ps1` files, not anything
  specific to Jimothy. `setup.bat` already works around it (it invokes
  `setup.ps1` with `-ExecutionPolicy Bypass` for just that one run, nothing
  persistent). If you're running `setup.ps1` directly instead of via the
  `.bat`, either do the same (`powershell -ExecutionPolicy Bypass -File
  setup.ps1`) or use Option A/C instead.
- **"python: command not found" / "python is not recognized"** — Python
  isn't installed, or wasn't added to PATH during install. Reinstall from
  [python.org](https://www.python.org/downloads/) and check "Add python.exe
  to PATH" (Windows) — or try `python3` instead of `python` (macOS/Linux,
  where `python` alone sometimes isn't aliased).
- **"That port is already in use"** — something else is already using
  8000. Run on a different port: `python manage.py runserver 8001` (or,
  for Docker, edit the `"8000:8000"` line in `docker-compose.yml`).
- **"No module named django"** — your virtual environment isn't active, or
  dependencies aren't installed. Re-run the setup script, or manually
  `pip install -r requirements.txt` with the `.venv` active.

## Contributing

Bug reports, feature ideas, and pull requests are welcome — see
[CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, how the test suite works,
and the project's conventions.

## License

MIT — see [LICENSE](LICENSE).
