"""Monte Carlo completion forecasting from historical weekly throughput.

No estimates needed once history exists: sample real past weekly throughput
(hours of task work completed per week) with replacement until the remaining
work is burned down, thousands of times, and read completion dates off the
resulting distribution. See PROJECT_PLAN.md §5.
"""

from __future__ import annotations

import datetime as dt
import random


def completion_percentiles(
    remaining_hours: float,
    weekly_throughput_history: list[float],
    start: dt.date,
    percentiles: tuple[int, ...] = (50, 85),
    simulations: int = 5000,
    seed: int | None = None,
    max_weeks: int = 520,
) -> dict[int, dt.date]:
    """P50/P85 (etc.) completion dates for a block of remaining work.

    Requires ≥4 weeks of history; below that the sample is too thin to mean
    anything and callers should stick to PERT dates.
    """
    history = [h for h in weekly_throughput_history if h >= 0]
    if len(history) < 4:
        raise ValueError("need >=4 weeks of throughput history, got %d"
                         % len(history))
    if remaining_hours <= 0:
        return {p: start for p in percentiles}
    if max(history) <= 0:
        raise ValueError("all-zero throughput history cannot finish any work")

    rng = random.Random(seed)
    weeks_needed: list[int] = []
    for _ in range(simulations):
        left = remaining_hours
        weeks = 0
        while left > 0 and weeks < max_weeks:
            left -= rng.choice(history)
            weeks += 1
        weeks_needed.append(weeks)
    weeks_needed.sort()

    out: dict[int, dt.date] = {}
    for p in percentiles:
        idx = min(int(len(weeks_needed) * p / 100), len(weeks_needed) - 1)
        out[p] = start + dt.timedelta(weeks=weeks_needed[idx])
    return out


def probability_by(
    deadline: dt.date,
    remaining_hours: float,
    weekly_throughput_history: list[float],
    start: dt.date,
    simulations: int = 5000,
    seed: int | None = None,
) -> float:
    """Fraction of simulations that finish on or before the deadline —
    the feasibility check's 'probability of hitting the date'."""
    history = [h for h in weekly_throughput_history if h >= 0]
    if len(history) < 4 or max(history, default=0) <= 0:
        raise ValueError("insufficient throughput history")
    if remaining_hours <= 0:
        return 1.0
    budget_weeks = max((deadline - start).days / 7.0, 0.0)
    rng = random.Random(seed)
    hits = 0
    for _ in range(simulations):
        left = remaining_hours
        weeks = 0
        while left > 0 and weeks <= budget_weeks:
            left -= rng.choice(history)
            weeks += 1
        if left <= 0 and weeks <= budget_weeks:
            hits += 1
    return hits / simulations
