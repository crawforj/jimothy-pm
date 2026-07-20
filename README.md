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

```bash
git clone <this repo's URL>
cd jimothy
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Open <http://127.0.0.1:8000/> and you'll land on a populated portfolio, not
an empty screen — `seed_demo` loads a varied example (a grant deadline, a
recurring weekly report, a board-pending proposal, several completed tasks)
with every date computed relative to today, so it's never stale no matter
when you run it. It's part of the normal setup, not an optional extra —
skip it only once you're ready to clear it out and enter your own portfolio
(it always wipes prior seed data before reloading, so it's safe to re-run,
and once you have real data in Jimothy, running it again would erase that
too — just don't run it again after that point). Requires Python 3.12+.

Copy `.env.example` to `.env` and set a real `DJANGO_SECRET_KEY` before
running this anywhere but your own machine — see the comments in that file.

## Contributing

Bug reports, feature ideas, and pull requests are welcome — see
[CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, how the test suite works,
and the project's conventions.

## License

MIT — see [LICENSE](LICENSE).
