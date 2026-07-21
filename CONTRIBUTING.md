# Contributing to Jimothy

Thanks for considering it. This is a small, opinionated personal tool that's
being opened up, not a framework aiming to please everyone — see
[PROJECT_PLAN.md §11](PROJECT_PLAN.md#11-competitive-gap-closing-roadmap) for
a sense of what's deliberately in scope and what's deliberately not (e.g. no
team-collaboration features, no general automation builder). If you're
proposing something bigger than a bug fix or a small feature, please open an
issue first to talk it through before writing code.

## Dev setup

```bash
git clone <this repo's URL>
cd jimothy
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env    # fill in a real DJANGO_SECRET_KEY if you're not just running locally
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Requires Python 3.12+.

## Running the checks before you open a PR

```bash
python -m unittest discover engine         # the scoring/scheduling engine's own test suite
python manage.py test core                 # core/tests.py -- Django-layer view/response tests
python manage.py check                     # Django system checks
python manage.py makemigrations --check --dry-run   # no missing migrations
```

If you touched a template, also `runserver` and click through the affected
page(s) — there's no *browser* test suite (Selenium-style), so this is the
verification step for anything visual. `core/tests.py` covers response
codes, redirects, and rendered content via Django's test client, without a
real browser — see its calendar-sync tests for the pattern (including how
to exercise a view's "not configured"/error paths with
`django.test.override_settings` instead of a real external account).

## How the codebase is organized

- **`engine/`** is pure Python with zero Django imports and no OS calls —
  scoring, scheduling, EV, Monte Carlo forecasting, PERT/calibration math.
  This separation is load-bearing, not just tidy: the engine is designed to
  also run under Pyodide in a browser (see PROJECT_PLAN.md §8b), so it must
  stay dependency-light (stdlib only) and framework-free. New engine logic
  gets its own known-answer tests in `engine/tests/test_engine.py`, in the
  same style as what's already there.
- **`core/`** is the Django layer: models, admin, views, templates.
  - `core/services.py` holds query→engine glue that's shared across more
    than one view (`portfolio_scoring`, `project_ev_metrics`, etc.) — if
    you're duplicating a scoring/query pattern across two views, it
    probably belongs here instead.
  - `core/phrases.py` holds **all** user-facing copy — greetings, warnings,
    empty-state messages. Templates and views reference `phrases.py`
    functions/constants rather than hardcoding strings, so the tool's voice
    stays centralized and easy to tune.
  - `core/views.py::today()` is the reference pattern for a new view:
    build engine dataclasses via `.to_engine()`, score, and wrap engine
    calls in `try/except` that logs and degrades to an empty-but-working
    page rather than a 500.
- Templates extend `core/templates/core/base.html` and follow its
  accessibility patterns already in place: `aria-labelledby` on sections,
  a skip-to-content link, `visually-hidden` captions on tables whose
  content is already named by a heading. New pages should match this, not
  reinvent it.

## Code style

- No comments explaining *what* the code does — only *why*, when something
  is genuinely non-obvious (a workaround, a subtle invariant). Names should
  carry the "what."
- Don't add configurability, abstractions, or dependencies for hypothetical
  future use. If three similar lines are simpler than the abstraction that
  would replace them, keep the three lines.
- Match existing patterns before introducing new ones — if you're unsure
  how something should look, find the closest existing view/template/engine
  function and follow its shape.

## Reporting bugs / requesting features

Use the issue templates. For security issues, see [SECURITY.md](SECURITY.md)
instead of opening a public issue.
