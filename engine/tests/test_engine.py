"""Known-answer tests for the Jimothy engine. Run: python -m unittest discover engine"""

import datetime as dt
import unittest

from engine.calendar_capacity import BusyBlock, BusyStatus, day_capacity
from engine.dateparse import parse_natural_date
from engine.estimate import (HistoryRecord, calibration_factors, pert_expected,
                             pert_stddev, template_estimate, uplift_for)
from engine.ev import HOURS_PER_STAFF_DAY, burndown_series, project_ev
from engine.model import DelayProfile, PriorityClass, Project, Staff, Status, Task
from engine.montecarlo import completion_percentiles, probability_by
from engine.schedule import (BATCH_SCORE_TOLERANCE, SWITCH_PENALTY, CycleError,
                             compute_criticality, feasibility, pack_day, topo_order,
                             weekly_load)
from engine.scoring import ScoredTask, Weights, effective_deadlines, score_tasks
from engine.sprint import committed_capacity, compute_velocity, roll_forward, week_start

TODAY = dt.date(2026, 7, 17)


def task(id, project_id=1, **kw):
    kw.setdefault("title", "t%d" % id)
    return Task(id=id, project_id=project_id, **kw)


class TestPert(unittest.TestCase):
    def test_expected_known_answer(self):
        # classic: O=2, M=4, P=12 -> (2 + 16 + 12)/6 = 5.0
        self.assertEqual(pert_expected(2, 4, 12), 5.0)

    def test_stddev(self):
        self.assertAlmostEqual(pert_stddev(2, 4, 12), 10 / 6)

    def test_task_expected_with_uplift(self):
        t = task(1, est_optimistic=2, est_likely=4, est_pessimistic=12)
        self.assertAlmostEqual(t.expected_hours(uplift=1.4), 7.0)

    def test_remaining_never_negative(self):
        t = task(1, est_likely=2, actual_hours=10)
        self.assertEqual(t.remaining_hours(), 0.0)


class TestCalibration(unittest.TestCase):
    def test_median_not_mean(self):
        hist = [HistoryRecord(1, ["field"], 10, r) for r in (11, 12, 13, 100)]
        f = calibration_factors(hist)
        self.assertAlmostEqual(f[(1, "field")], 1.25)  # median of 1.1,1.2,1.3,10

    def test_min_samples_gate(self):
        hist = [HistoryRecord(1, ["field"], 10, 15)] * 3
        self.assertEqual(calibration_factors(hist), {})

    def test_uplift_specificity(self):
        f = {(1, "field"): 1.4, (1, None): 1.1, (None, "field"): 1.6}
        self.assertEqual(uplift_for(f, 1, ["field"]), 1.4)   # staff+tag wins
        self.assertEqual(uplift_for(f, 1, ["office"]), 1.1)  # staff fallback
        self.assertEqual(uplift_for(f, 2, ["field"]), 1.6)   # tag fallback
        self.assertEqual(uplift_for(f, 2, ["office"]), 1.0)  # default


class TestScoring(unittest.TestCase):
    def test_big_far_task_beats_small_near_task(self):
        """Plan §4: 40h due in 3 weeks outranks 30min due Friday."""
        projects = [Project(id=1, name="p")]
        big = task(1, est_likely=40, deadline=TODAY + dt.timedelta(days=21))
        small = task(2, est_likely=0.5, deadline=TODAY + dt.timedelta(days=1))
        scored = score_tasks([big, small], projects, TODAY)
        self.assertEqual(scored[0].task.id, 1)

    def test_cliff_past_deadline_is_dead(self):
        projects = [Project(id=1, name="p")]
        t = task(1, est_likely=4, deadline=TODAY - dt.timedelta(days=1),
                 delay_profile=DelayProfile.CLIFF)
        s = score_tasks([t], projects, TODAY)[0]
        self.assertTrue(s.dead)
        self.assertLess(s.score, 0)

    def test_overdue_linear_is_max_urgency(self):
        projects = [Project(id=1, name="p")]
        t = task(1, est_likely=4, deadline=TODAY - dt.timedelta(days=3))
        s = score_tasks([t], projects, TODAY)[0]
        self.assertEqual(s.urgency, 1.0)
        self.assertFalse(s.dead)

    def test_project_priority_orders_equal_tasks(self):
        projects = [
            Project(id=1, name="critical", priority_class=PriorityClass.CRITICAL),
            Project(id=2, name="backburner", priority_class=PriorityClass.BACKBURNER),
        ]
        a = task(1, project_id=1, est_likely=4)
        b = task(2, project_id=2, est_likely=4)
        scored = score_tasks([a, b], projects, TODAY)
        self.assertEqual(scored[0].task.id, 1)

    def test_effective_deadline_backchains_through_dependency(self):
        """B (16h, due day 10) depends on A -> A inherits ~day 10 minus ~3 days."""
        projects = {1: Project(id=1, name="p")}
        a = task(1)
        b = task(2, est_likely=16, deadline=TODAY + dt.timedelta(days=10),
                 depends_on=[1])
        eff = effective_deadlines([a, b], projects)
        self.assertEqual(eff[2], TODAY + dt.timedelta(days=10))
        self.assertEqual(eff[1], TODAY + dt.timedelta(days=7))

    def test_slow_burn_zero_urgency_staleness_still_lifts(self):
        projects = [Project(id=1, name="p")]
        fresh = task(1, est_likely=4, delay_profile=DelayProfile.SLOW_BURN,
                     last_touched=TODAY)
        stale = task(2, est_likely=4, delay_profile=DelayProfile.SLOW_BURN,
                     last_touched=TODAY - dt.timedelta(days=60))
        scored = score_tasks([fresh, stale], projects, TODAY)
        self.assertEqual(scored[0].task.id, 2)

    def test_done_tasks_excluded(self):
        projects = [Project(id=1, name="p")]
        t = task(1, est_likely=4, status=Status.DONE)
        self.assertEqual(score_tasks([t], projects, TODAY), [])


class TestTopo(unittest.TestCase):
    def test_orders_dependencies_first(self):
        a, b, c = task(1), task(2, depends_on=[1]), task(3, depends_on=[2])
        order = [t.id for t in topo_order([c, b, a])]
        self.assertEqual(order, [1, 2, 3])

    def test_cycle_raises_with_ids(self):
        a = task(1, depends_on=[2])
        b = task(2, depends_on=[1])
        with self.assertRaises(CycleError) as cm:
            topo_order([a, b])
        self.assertIn("[1, 2]", str(cm.exception))


class TestPackDay(unittest.TestCase):
    def _scored(self, tasks, projects=None):
        projects = projects or [Project(id=i, name="p%d" % i)
                                for i in {t.project_id for t in tasks}]
        return score_tasks(tasks, projects, TODAY)

    def test_wip_cap_respected(self):
        staff = Staff(id=1, name="a")  # WIP limit 2
        tasks = [task(i, project_id=i, assignee_id=1, est_likely=1,
                      deadline=TODAY + dt.timedelta(days=2)) for i in (1, 2, 3)]
        plan = pack_day(self._scored(tasks), staff)
        projects_hit = {next(t for t in tasks if t.id == tid).project_id
                        for tid, _ in plan.entries}
        self.assertLessEqual(len(projects_hit), 2)

    def test_batching_preferred_over_marginal_score(self):
        """Two same-project tasks get batched before an alternating plan."""
        staff = Staff(id=1, name="a")
        t1 = task(1, project_id=1, assignee_id=1, est_likely=2,
                  deadline=TODAY + dt.timedelta(days=3))
        t2 = task(2, project_id=2, assignee_id=1, est_likely=2,
                  deadline=TODAY + dt.timedelta(days=3))
        t3 = task(3, project_id=1, assignee_id=1, est_likely=2,
                  deadline=TODAY + dt.timedelta(days=4))
        plan = pack_day(self._scored([t1, t2, t3]), staff)
        order = [tid for tid, _ in plan.entries]
        if 3 in order and 2 in order:
            self.assertLess(order.index(3), order.index(2))
        self.assertLessEqual(plan.switches, 1)

    def test_day_capacity_respected(self):
        staff = Staff(id=1, name="a", nominal_hours_per_day=8, focus_factor=0.75)
        tasks = [task(i, assignee_id=1, est_likely=4,
                      deadline=TODAY + dt.timedelta(days=2)) for i in (1, 2, 3)]
        plan = pack_day(self._scored(tasks), staff)
        self.assertLessEqual(sum(h for _, h in plan.entries), 6.0 + 1e-9)


class TestFeasibility(unittest.TestCase):
    def test_known_slip(self):
        """60h of work, one person at 6h/day, deadline in 5 working days:
        needs 10 working days -> finishes ~1 calendar week late."""
        projects = [Project(id=1, name="p",
                            deadline=dt.date(2026, 7, 24))]  # Friday, 5 wd out
        staff = [Staff(id=1, name="a")]  # 6.0h/day available
        tasks = [task(i, assignee_id=1, est_likely=12) for i in range(1, 6)]
        scored = score_tasks(tasks, projects, TODAY)
        fc = feasibility(scored, staff, TODAY)[0]
        self.assertEqual(fc.finish_date, dt.date(2026, 7, 30))
        self.assertEqual(fc.slip_days, 6)

    def test_fits_no_slip(self):
        projects = [Project(id=1, name="p", deadline=TODAY + dt.timedelta(days=10))]
        staff = [Staff(id=1, name="a")]
        tasks = [task(1, assignee_id=1, est_likely=12)]
        fc = feasibility(score_tasks(tasks, projects, TODAY), staff, TODAY)[0]
        self.assertEqual(fc.slip_days, 0)

    def test_dependency_serializes_work(self):
        projects = [Project(id=1, name="p")]
        staff = [Staff(id=1, name="a"), Staff(id=2, name="b")]
        t1 = task(1, assignee_id=1, est_likely=6)
        t2 = task(2, assignee_id=2, est_likely=6, depends_on=[1])
        fc = feasibility(score_tasks([t1, t2], projects, TODAY), staff, TODAY)[0]
        # t2 cannot start until t1 finishes: 2 working days total, Fri->Mon
        self.assertEqual(fc.finish_date, dt.date(2026, 7, 20))


class TestMonteCarlo(unittest.TestCase):
    HIST = [10, 12, 8, 11, 9, 10, 12, 10]  # ~10.25 h/week

    def test_deterministic_with_seed(self):
        a = completion_percentiles(100, self.HIST, TODAY, seed=42)
        b = completion_percentiles(100, self.HIST, TODAY, seed=42)
        self.assertEqual(a, b)

    def test_percentiles_ordered_and_sane(self):
        out = completion_percentiles(100, self.HIST, TODAY, seed=1)
        self.assertLessEqual(out[50], out[85])
        # 100h at ~10h/wk: 9-13 weeks is the plausible envelope
        self.assertGreaterEqual(out[50], TODAY + dt.timedelta(weeks=8))
        self.assertLessEqual(out[85], TODAY + dt.timedelta(weeks=14))

    def test_zero_work_finishes_now(self):
        out = completion_percentiles(0, self.HIST, TODAY, seed=1)
        self.assertEqual(out[50], TODAY)

    def test_thin_history_refused(self):
        with self.assertRaises(ValueError):
            completion_percentiles(100, [10, 10], TODAY)

    def test_probability_extremes(self):
        never = probability_by(TODAY + dt.timedelta(weeks=2), 1000,
                               self.HIST, TODAY, seed=1)
        surely = probability_by(TODAY + dt.timedelta(weeks=52), 100,
                                self.HIST, TODAY, seed=1)
        self.assertEqual(never, 0.0)
        self.assertEqual(surely, 1.0)


class TestReviewFixes(unittest.TestCase):
    """Regression tests for the 2026-07-18 code-review findings."""

    def test_unestimated_task_not_negligible_when_deadline_close(self):
        """Fix: no estimate must not collapse to near-zero urgency."""
        projects = [Project(id=1, name="p")]
        unestimated = task(1, deadline=TODAY + dt.timedelta(days=1))
        scored = score_tasks([unestimated], projects, TODAY)[0]
        self.assertGreater(scored.urgency, 0.3)

    def test_pack_day_skips_substantively_finished_task(self):
        """Fix: remaining_hours()==0 because the work is done (not because
        it's unestimated) must not get padded into a phantom 0.5h chunk."""
        staff = Staff(id=1, name="a")
        projects = [Project(id=1, name="p")]
        finished = task(1, assignee_id=1, est_likely=4, actual_hours=4,
                        status=Status.DOING, deadline=TODAY + dt.timedelta(days=2))
        plan = pack_day(score_tasks([finished], projects, TODAY), staff)
        self.assertEqual(plan.entries, [])

    def test_pack_day_still_pads_genuinely_unestimated_task(self):
        """The 0.5h fallback should still apply to truly unestimated work."""
        staff = Staff(id=1, name="a")
        projects = [Project(id=1, name="p")]
        unestimated = task(1, assignee_id=1, deadline=TODAY + dt.timedelta(days=2))
        plan = pack_day(score_tasks([unestimated], projects, TODAY), staff)
        self.assertEqual(len(plan.entries), 1)
        self.assertEqual(plan.entries[0][1], 0.5)

    def test_pack_day_distinct_projects_not_switch_count(self):
        """DayPlan exposes the real WIP signal (distinct projects touched vs.
        its cap), independent of how many transitions packing needed."""
        staff = Staff(id=1, name="a")
        projects = [Project(id=1, name="p1"), Project(id=2, name="p2")]
        batched = [
            task(1, project_id=1, assignee_id=1, est_likely=1,
                deadline=TODAY + dt.timedelta(days=3)),
            task(2, project_id=1, assignee_id=1, est_likely=1,
                deadline=TODAY + dt.timedelta(days=3)),
            task(3, project_id=2, assignee_id=1, est_likely=1,
                deadline=TODAY + dt.timedelta(days=4)),
            task(4, project_id=2, assignee_id=1, est_likely=1,
                deadline=TODAY + dt.timedelta(days=4)),
        ]
        plan = pack_day(score_tasks(batched, projects, TODAY), staff)
        self.assertEqual(plan.distinct_projects, 2)
        self.assertEqual(plan.wip_limit, 2)
        self.assertTrue(plan.at_wip_cap)

    def test_batch_score_tolerance_derived_from_switch_penalty(self):
        self.assertAlmostEqual(BATCH_SCORE_TOLERANCE, 1 - 2 * SWITCH_PENALTY)

    def test_feasibility_unassigned_pool_not_regranted_same_day(self):
        """Fix: the shared unassigned-task pool must not reset to a fresh
        25% slice mid-day just because it was drained to exactly 0.0."""
        projects = [Project(id=1, name="p1"), Project(id=2, name="p2")]
        staff = [Staff(id=1, name="a"), Staff(id=2, name="b")]  # 6h/day each
        a = task(1, project_id=1, est_likely=3)   # unassigned
        b = task(2, project_id=2, est_likely=3)   # unassigned
        scored = score_tasks([a, b], projects, TODAY)
        forecasts = {fc.project_id: fc for fc in feasibility(scored, staff, TODAY)}
        finishes = sorted(fc.finish_date for fc in forecasts.values())
        # Pool = 25% of 12h = 3h/day, exactly enough for one 3h task today.
        self.assertEqual(finishes[0], TODAY)
        self.assertEqual(finishes[1], TODAY + dt.timedelta(days=3))  # next Monday

    def test_feasibility_project_deadline_is_earliest_not_first_scored(self):
        """Fix: slip must be computed against the earliest task deadline in
        a project, not whichever task happens to sort first by score."""
        staff = [Staff(id=1, name="a")]
        t_far = task(1, est_likely=1, deadline=TODAY + dt.timedelta(days=60))
        t_near = task(2, est_likely=1, deadline=TODAY + dt.timedelta(days=2))
        # Deliberately place the far-deadline (higher-scored) task first.
        scored = [
            ScoredTask(task=t_far, score=10.0, urgency=0.1, dead=False,
                      effective_deadline=t_far.deadline),
            ScoredTask(task=t_near, score=1.0, urgency=0.9, dead=False,
                      effective_deadline=t_near.deadline),
        ]
        fc = feasibility(scored, staff, TODAY)[0]
        self.assertEqual(fc.deadline, t_near.deadline)

    def test_compute_criticality_zero_slack_chain(self):
        """A->B is the project's only critical (zero-slack) chain; parallel
        task C has slack and scores lower criticality."""
        a = task(1, est_likely=6)
        b = task(2, est_likely=6, depends_on=[1])
        c = task(3, est_likely=2)
        crit = compute_criticality([a, b, c])
        self.assertEqual(crit[1], 1.0)
        self.assertEqual(crit[2], 1.0)
        self.assertLess(crit[3], 1.0)

    def test_compute_criticality_ignores_done_tasks(self):
        a = task(1, est_likely=6, status=Status.DONE)
        b = task(2, est_likely=6, depends_on=[1])
        crit = compute_criticality([a, b])
        self.assertNotIn(1, crit)
        self.assertIn(2, crit)

    def test_score_tasks_criticality_weight_applied(self):
        """Fix: the criticality weight must actually move the score."""
        projects = [Project(id=1, name="p")]
        a = task(1, est_likely=4)
        b = task(2, est_likely=4)
        crit = {1: 1.0, 2: 0.0}
        scored = score_tasks([a, b], projects, TODAY, criticality=crit)
        sa = next(s for s in scored if s.task.id == 1)
        sb = next(s for s in scored if s.task.id == 2)
        self.assertGreater(sa.score, sb.score)
        self.assertEqual(sa.components["criticality"], 1.0)

    def test_score_tasks_criticality_optional(self):
        """Callers that omit criticality (e.g. existing tests) still work,
        scoring every task 0.0 on that component."""
        projects = [Project(id=1, name="p")]
        a = task(1, est_likely=4)
        scored = score_tasks([a], projects, TODAY)[0]
        self.assertEqual(scored.components["criticality"], 0.0)


class TestEV(unittest.TestCase):
    def test_known_pv_ev_ac(self):
        project = Project(id=1, name="p", deadline=TODAY + dt.timedelta(days=30))
        # 8h task due yesterday, done, 10h actual -> PV counts it (deadline passed),
        # EV counts it at its 8h estimate, AC counts the 10h actually spent.
        t1 = task(1, est_likely=8, actual_hours=10, status=Status.DONE,
                  deadline=TODAY - dt.timedelta(days=1))
        # 16h task due next month, still open -> doesn't count toward PV yet.
        t2 = task(2, est_likely=16, deadline=TODAY + dt.timedelta(days=30))
        m = project_ev([t1, t2], project, TODAY)
        self.assertEqual(m.pv, 1.0)   # 8h / 8h-per-day
        self.assertEqual(m.ev, 1.0)
        self.assertEqual(m.ac, 1.25)  # 10h / 8h-per-day
        self.assertEqual(m.spi, 1.0)  # on schedule
        self.assertEqual(m.cpi, 0.8)  # over budget (spent more than earned)

    def test_none_when_nothing_due_or_spent(self):
        project = Project(id=1, name="p")
        t = task(1, est_likely=4, deadline=TODAY + dt.timedelta(days=10))
        m = project_ev([t], project, TODAY)
        self.assertIsNone(m.spi)  # nothing due yet -> PV is 0
        self.assertIsNone(m.cpi)  # nothing logged yet -> AC is 0

    def test_falls_back_to_project_deadline(self):
        project = Project(id=1, name="p", deadline=TODAY - dt.timedelta(days=1))
        t = task(1, est_likely=8)  # no own deadline -> inherits project's
        m = project_ev([t], project, TODAY)
        self.assertEqual(m.pv, 1.0)


class TestBurndown(unittest.TestCase):
    def _weeks(self, n):
        return [TODAY - dt.timedelta(weeks=i) for i in range(n, 0, -1)]

    def test_steady_decline_from_known_throughput(self):
        # 3 weeks of 8h (1 staff-day) each completed, 2 staff-days left today
        # -> reconstructing backward should show 5, 4, 3 staff-days at each
        # week's start, ending at today's real 2.
        weeks = self._weeks(3)
        series = burndown_series(
            remaining_now_hours=2 * HOURS_PER_STAFF_DAY,
            weekly_throughput_hours=[8.0, 8.0, 8.0],
            week_starts=weeks, today=TODAY, deadline=None)
        self.assertEqual([p.remaining for p in series], [5.0, 4.0, 3.0, 2.0])
        self.assertEqual([p.date for p in series], weeks + [TODAY])

    def test_all_zero_week_produces_no_change(self):
        weeks = self._weeks(2)
        series = burndown_series(
            remaining_now_hours=4 * HOURS_PER_STAFF_DAY,
            weekly_throughput_hours=[0.0, 0.0],
            week_starts=weeks, today=TODAY, deadline=None)
        self.assertEqual([p.remaining for p in series], [4.0, 4.0, 4.0])

    def test_final_point_is_todays_actual_value_not_last_full_week(self):
        # Throughput lists only cover *full* weeks (project_weekly_throughput's
        # own convention) -- today's own in-progress-week completions should
        # still show up as the final point, not get silently dropped.
        weeks = self._weeks(1)
        series = burndown_series(
            remaining_now_hours=1 * HOURS_PER_STAFF_DAY,
            weekly_throughput_hours=[8.0],
            week_starts=weeks, today=TODAY, deadline=None)
        self.assertEqual(series[-1].date, TODAY)
        self.assertEqual(series[-1].remaining, 1.0)

    def test_no_deadline_leaves_ideal_none_throughout(self):
        series = burndown_series(
            remaining_now_hours=8.0, weekly_throughput_hours=[0.0],
            week_starts=self._weeks(1), today=TODAY, deadline=None)
        self.assertTrue(all(p.ideal is None for p in series))

    def test_ideal_line_endpoints(self):
        # Zero throughput -> remaining stays flat at 10 staff-days
        # throughout, isolating the ideal-line math. Deadline is exactly 70
        # days after the series' start, with a point at the start, one at
        # the halfway mark (35 days), and today landing exactly on the
        # deadline itself (70 days) -> ideal should read 10, 5, then 0.
        start = TODAY - dt.timedelta(days=70)
        halfway = start + dt.timedelta(days=35)
        deadline = start + dt.timedelta(days=70)
        series = burndown_series(
            remaining_now_hours=10 * HOURS_PER_STAFF_DAY,
            weekly_throughput_hours=[0.0, 0.0],
            week_starts=[start, halfway], today=deadline, deadline=deadline)
        self.assertEqual([p.ideal for p in series], [10.0, 5.0, 0.0])

    def test_deadline_already_passed_floors_ideal_at_zero(self):
        weeks = self._weeks(1)
        series = burndown_series(
            remaining_now_hours=8.0, weekly_throughput_hours=[0.0],
            week_starts=weeks, today=TODAY,
            deadline=weeks[0] - dt.timedelta(days=1))
        self.assertTrue(all(p.ideal == 0.0 for p in series))

    def test_remaining_never_negative(self):
        # Throughput history overstates what's left today can only mean
        # scope was completed faster than tracked -- still must not report
        # a nonsensical negative remaining figure.
        series = burndown_series(
            remaining_now_hours=0.0, weekly_throughput_hours=[8.0],
            week_starts=self._weeks(1), today=TODAY, deadline=None)
        self.assertTrue(all(p.remaining >= 0.0 for p in series))


class TestSprint(unittest.TestCase):
    def test_week_start_is_monday(self):
        # 2026-07-17 is a Friday
        self.assertEqual(week_start(dt.date(2026, 7, 17)), dt.date(2026, 7, 13))
        self.assertEqual(week_start(dt.date(2026, 7, 13)), dt.date(2026, 7, 13))

    def test_velocity_only_counts_done(self):
        done = task(1, est_likely=6, status=Status.DONE)
        open_ = task(2, est_likely=10, status=Status.DOING)
        self.assertEqual(compute_velocity([done, open_]), 6.0)

    def test_velocity_applies_uplift(self):
        done = task(1, est_likely=6, status=Status.DONE)
        self.assertEqual(compute_velocity([done], uplifts={1: 1.5}), 9.0)

    def test_committed_capacity(self):
        self.assertEqual(committed_capacity([6.0, 4.5], working_days=5), 52.5)

    def test_roll_forward_excludes_done(self):
        done = task(1, est_likely=6, status=Status.DONE)
        blocked = task(2, est_likely=4, status=Status.BLOCKED)
        self.assertEqual(roll_forward([done, blocked]), [blocked])


class TestDateParse(unittest.TestCase):
    # TODAY is Friday 2026-07-17 (see module constant above)

    def test_today_tomorrow_yesterday(self):
        self.assertEqual(parse_natural_date("today", TODAY), TODAY)
        self.assertEqual(parse_natural_date("Tomorrow", TODAY), TODAY + dt.timedelta(days=1))
        self.assertEqual(parse_natural_date("yesterday", TODAY), TODAY - dt.timedelta(days=1))

    def test_relative_in_n_units(self):
        self.assertEqual(parse_natural_date("in 3 days", TODAY), TODAY + dt.timedelta(days=3))
        self.assertEqual(parse_natural_date("in 2 weeks", TODAY), TODAY + dt.timedelta(days=14))
        self.assertEqual(parse_natural_date("5 days from now", TODAY), TODAY + dt.timedelta(days=5))

    def test_next_weekday_skips_today(self):
        # today IS Friday, so "next friday" must mean a week from now, not today
        self.assertEqual(parse_natural_date("next friday", TODAY), TODAY + dt.timedelta(days=7))
        self.assertEqual(parse_natural_date("next monday", TODAY), TODAY + dt.timedelta(days=3))

    def test_this_weekday_can_be_today(self):
        self.assertEqual(parse_natural_date("this friday", TODAY), TODAY)

    def test_bare_weekday_means_next_occurrence(self):
        self.assertEqual(parse_natural_date("friday", TODAY), TODAY + dt.timedelta(days=7))
        self.assertEqual(parse_natural_date("Monday", TODAY), TODAY + dt.timedelta(days=3))

    def test_unrecognized_returns_none(self):
        self.assertIsNone(parse_natural_date("sometime next quarter", TODAY))
        self.assertIsNone(parse_natural_date("", TODAY))


class TestTemplateEstimate(unittest.TestCase):
    def test_below_min_samples_returns_none(self):
        self.assertIsNone(template_estimate([2.0, 3.0]))

    def test_learns_median_min_max(self):
        est = template_estimate([2.0, 3.0, 4.0, 3.0])
        self.assertEqual(est, (2.0, 3.0, 4.0))

    def test_zero_spread_gets_nonzero_envelope(self):
        opt, likely, pess = template_estimate([2.0, 2.0, 2.0])
        self.assertEqual(likely, 2.0)
        self.assertGreater(pess, opt)


class TestWeeklyLoad(unittest.TestCase):
    def _scored(self, tasks, projects=None):
        projects = projects or [Project(id=i, name="p%d" % i)
                                for i in {t.project_id for t in tasks}]
        return score_tasks(tasks, projects, TODAY)

    def test_buckets_by_deadline_week(self):
        staff = [Staff(id=1, name="a")]
        # TODAY (Fri 2026-07-17) is in the week of 07-13; +7 days (07-24) is
        # in the following week (07-20), a clean way to land in bucket[1].
        near = task(1, assignee_id=1, est_likely=6, deadline=TODAY + dt.timedelta(days=1))
        far = task(2, assignee_id=1, est_likely=6, deadline=TODAY + dt.timedelta(days=7))
        load = weekly_load(self._scored([near, far]), staff, TODAY, weeks=4)
        weeks = load[1]
        self.assertEqual(weeks[0].week_start, week_start(TODAY))
        self.assertEqual(weeks[0].load_hours, 6.0)
        self.assertEqual(weeks[1].load_hours, 6.0)

    def test_overdue_task_buckets_into_current_week(self):
        staff = [Staff(id=1, name="a")]
        overdue = task(1, assignee_id=1, est_likely=4,
                       deadline=TODAY - dt.timedelta(days=10))
        load = weekly_load(self._scored([overdue]), staff, TODAY, weeks=3)
        self.assertEqual(load[1][0].load_hours, 4.0)

    def test_beyond_horizon_piles_into_last_week(self):
        staff = [Staff(id=1, name="a")]
        far = task(1, assignee_id=1, est_likely=5, deadline=TODAY + dt.timedelta(days=90))
        load = weekly_load(self._scored([far]), staff, TODAY, weeks=3)
        self.assertEqual(load[1][-1].load_hours, 5.0)
        self.assertEqual(sum(w.load_hours for w in load[1][:-1]), 0.0)

    def test_undated_task_excluded(self):
        staff = [Staff(id=1, name="a")]
        undated = task(1, assignee_id=1, est_likely=5, delay_profile=DelayProfile.SLOW_BURN)
        load = weekly_load(self._scored([undated]), staff, TODAY, weeks=3)
        self.assertEqual(sum(w.load_hours for w in load[1]), 0.0)

    def test_capacity_and_over_capacity_flag(self):
        staff = [Staff(id=1, name="a", nominal_hours_per_day=8, focus_factor=0.75)]
        heavy = task(1, assignee_id=1, est_likely=40, deadline=TODAY + dt.timedelta(days=1))
        load = weekly_load(self._scored([heavy]), staff, TODAY, weeks=1)
        wk = load[1][0]
        self.assertEqual(wk.capacity_hours, 30.0)   # 8*0.75*5
        self.assertTrue(wk.over_capacity)
        self.assertEqual(wk.pct, 100)                # capped, doesn't overflow the bar


class TestCalendarCapacity(unittest.TestCase):
    def _at(self, hour, minute=0):
        return dt.datetime.combine(TODAY, dt.time(hour, minute))

    def test_busy_meeting_subtracted_then_haircut(self):
        blocks = [BusyBlock(self._at(9), self._at(11), BusyStatus.BUSY)]
        cap = day_capacity(TODAY, 8.0, blocks)
        self.assertEqual(cap.meeting_hours, 2.0)
        self.assertEqual(cap.available_hours, 5.1)   # (8-2)*0.85
        self.assertFalse(cap.has_tentative)

    def test_tentative_not_subtracted_but_flagged(self):
        blocks = [BusyBlock(self._at(9), self._at(11), BusyStatus.TENTATIVE)]
        cap = day_capacity(TODAY, 8.0, blocks)
        self.assertEqual(cap.meeting_hours, 0.0)
        self.assertEqual(cap.available_hours, 6.8)    # 8*0.85
        self.assertTrue(cap.has_tentative)

    def test_free_block_ignored(self):
        blocks = [BusyBlock(self._at(8), self._at(17), BusyStatus.FREE)]
        cap = day_capacity(TODAY, 8.0, blocks)
        self.assertEqual(cap.meeting_hours, 0.0)
        self.assertFalse(cap.has_tentative)

    def test_out_of_office_all_day_zeroes_day(self):
        blocks = [BusyBlock(self._at(0), self._at(0), BusyStatus.OUT_OF_OFFICE, all_day=True)]
        cap = day_capacity(TODAY, 8.0, blocks)
        self.assertEqual(cap.meeting_hours, 8.0)
        self.assertEqual(cap.available_hours, 0.0)

    def test_busy_block_clipped_to_workday(self):
        blocks = [BusyBlock(self._at(7), self._at(9), BusyStatus.BUSY)]
        cap = day_capacity(TODAY, 8.0, blocks, workday_start=dt.time(8, 0))
        self.assertEqual(cap.meeting_hours, 1.0)      # only 8-9, not 7-9

    def test_overlapping_busy_blocks_not_double_counted(self):
        blocks = [BusyBlock(self._at(9), self._at(11), BusyStatus.BUSY),
                 BusyBlock(self._at(10), self._at(12), BusyStatus.BUSY)]
        cap = day_capacity(TODAY, 8.0, blocks)
        self.assertEqual(cap.meeting_hours, 3.0)      # union 9-12, not 4.0

    def test_double_booked_floors_at_zero_not_negative(self):
        blocks = [BusyBlock(self._at(8), self._at(17), BusyStatus.BUSY),
                 BusyBlock(self._at(8), self._at(17), BusyStatus.OUT_OF_OFFICE)]
        cap = day_capacity(TODAY, 8.0, blocks)
        self.assertEqual(cap.available_hours, 0.0)
        self.assertGreaterEqual(cap.available_hours, 0.0)

    def test_multiple_tentative_and_busy_mixed(self):
        blocks = [BusyBlock(self._at(9), self._at(10), BusyStatus.BUSY),
                 BusyBlock(self._at(14), self._at(15), BusyStatus.TENTATIVE)]
        cap = day_capacity(TODAY, 8.0, blocks)
        self.assertEqual(cap.meeting_hours, 1.0)
        self.assertTrue(cap.has_tentative)


if __name__ == "__main__":
    unittest.main()
