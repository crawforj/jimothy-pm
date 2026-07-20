"""PERT math, calibration factors, reference-class uplifts."""

from __future__ import annotations

import statistics
from dataclasses import dataclass


def pert_expected(o: float, m: float, p: float) -> float:
    return (o + 4 * m + p) / 6.0


def pert_stddev(o: float, m: float, p: float) -> float:
    return (p - o) / 6.0


@dataclass
class HistoryRecord:
    """One completed task's estimate-vs-actual, for calibration."""
    staff_id: int | None
    tags: list[str]
    estimated_hours: float
    actual_hours: float

    @property
    def overrun(self) -> float:
        if self.estimated_hours <= 0:
            return 1.0
        return self.actual_hours / self.estimated_hours


def calibration_factors(
    history: list[HistoryRecord],
    min_samples: int = 4,
) -> dict[tuple[int | None, str | None], float]:
    """Median overrun ratio per (staff, tag), per staff, and per tag.

    Median, not mean: one 10× disaster shouldn't poison the factor. Keys:
    (staff_id, tag), (staff_id, None), (None, tag). Below min_samples a
    group yields no factor — silence beats noise. Callers look up the most
    specific key available and fall back, defaulting to 1.0.
    """
    groups: dict[tuple[int | None, str | None], list[float]] = {}
    for rec in history:
        keys = [(rec.staff_id, None)]
        keys += [(rec.staff_id, tag) for tag in rec.tags]
        keys += [(None, tag) for tag in rec.tags]
        for k in keys:
            groups.setdefault(k, []).append(rec.overrun)
    return {k: round(statistics.median(v), 2)
            for k, v in groups.items() if len(v) >= min_samples}


def template_estimate(
    history_actuals: list[float],
    min_samples: int = 3,
) -> tuple[float, float, float] | None:
    """A fresh three-point estimate for a recurring-task template, learned
    from the last few completions' actual hours (plan §11 item 6) — instead
    of a recurring task forever copying whatever its very first instance
    happened to guess.

    Median as the "likely" value (matches calibration_factors' bias toward
    the typical case over outliers), min/max of the sample as optimistic/
    pessimistic. Below min_samples, returns None — the caller should fall
    back to the template's existing estimate; too little history is worse
    than no update at all.
    """
    if len(history_actuals) < min_samples:
        return None
    optimistic = min(history_actuals)
    pessimistic = max(history_actuals)
    likely = statistics.median(history_actuals)
    if pessimistic == optimistic:
        # a zero-spread sample would collapse pert_stddev to 0; keep a
        # nonzero envelope so downstream variance math stays meaningful
        pessimistic = optimistic * 1.2 if optimistic > 0 else 0.5
    return (round(optimistic, 2), round(likely, 2), round(pessimistic, 2))


def uplift_for(
    factors: dict[tuple[int | None, str | None], float],
    staff_id: int | None,
    tags: list[str],
) -> float:
    """Most specific factor wins: (staff, tag) → (staff,) → (tag,) → 1.0.
    With several tags, use the largest (most pessimistic) matching uplift —
    reference-class forecasting corrects optimism, so ties break upward."""
    candidates = []
    for tag in tags:
        if (staff_id, tag) in factors:
            candidates.append(factors[(staff_id, tag)])
    if candidates:
        return max(candidates)
    if (staff_id, None) in factors:
        return factors[(staff_id, None)]
    for tag in tags:
        if (None, tag) in factors:
            candidates.append(factors[(None, tag)])
    return max(candidates) if candidates else 1.0
