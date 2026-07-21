"""Template context available on every page (registered in
config/settings.py's TEMPLATES). Currently just the mascot's mood --
kept separate from core/services.py since it's presentation, not
query->engine glue reused by a specific view."""

import datetime as dt

from core.services import portfolio_feasibility, portfolio_scoring


def mascot_mood(request):
    """Fifth of the requested visual/interactive features: the mascot
    echoes portfolio health, reusing the same feasibility signal Today's
    "Worth a look" warnings already show in full, accessible text --
    this is a decorative echo of information that's already presented
    accessibly elsewhere, not the sole conveyance of it (mascot alt text
    stays "" for exactly that reason).

    Deliberately recomputes portfolio_scoring/portfolio_feasibility on
    every page load rather than caching across requests or views -- this
    app's whole dataset is small enough (one person's real portfolio)
    that this is a non-issue, and simplicity wins over a cross-request
    cache for a decorative touch.
    """
    today = dt.date.today()
    scored, staff, projects_qs, _tasks_qs, uplifts = portfolio_scoring(today)
    if not staff or not projects_qs:
        return {"mascot_mood": "neutral"}
    forecasts = portfolio_feasibility(scored, staff, today, uplifts)
    at_risk = any(fc.slip_days > 0 for fc in forecasts.values())
    return {"mascot_mood": "warn" if at_risk else "ok"}
