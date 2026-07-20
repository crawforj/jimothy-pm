"""Jimothy engine: pure-Python prioritization and scheduling core.

Hard constraints (see PROJECT_PLAN.md §8, §8b):
- stdlib only, no Django imports, no OS calls, no I/O — must run unchanged
  under CPython and Pyodide.
- All public functions take plain dataclasses/dicts in and return plain
  dicts (view models) or dataclasses out.
"""

from engine.model import DelayProfile, PriorityClass, Project, Staff, Status, Task
from engine.scoring import Weights, score_tasks
from engine.schedule import compute_criticality, feasibility, pack_day, topo_order
from engine.estimate import HistoryRecord, calibration_factors, pert_expected, pert_stddev, uplift_for
from engine.montecarlo import completion_percentiles

__all__ = [
    "DelayProfile", "PriorityClass", "Project", "Staff", "Status", "Task",
    "Weights", "score_tasks",
    "compute_criticality", "feasibility", "pack_day", "topo_order",
    "HistoryRecord", "pert_expected", "pert_stddev", "calibration_factors", "uplift_for",
    "completion_percentiles",
]
