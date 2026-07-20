# Jimothy — User Guide

*A coach, not a nag. Your portfolio, sorted, every morning.*

> **Where this fits:** this guide covers how to actually run and use Jimothy
> today. For the full design rationale and the long-term roadmap, see
> [PROJECT_PLAN.md](PROJECT_PLAN.md). This doc will grow as more phases land.

---

## 1. What's actually running right now

Jimothy is being built in phases (see [PROJECT_PLAN.md §9](PROJECT_PLAN.md#9-build-phases)).
As of this guide, **Phase 1–3 are in place, plus most of Phase 4 except
anything that needs Outlook or the real deployment machine**:

| Working today | Not built yet |
|---|---|
| Django app with Staff / Project / Milestone / Task / Risk / Sprint / WorkLog / Unavailability models | Outlook calendar sync (reads or writes) |
| Full admin CRUD for your portfolio at `/admin/`, with natural-language date entry (§4) | Morning-briefing *email* (the text version renders — see §10) |
| **Today, Week, Month, Quarter, Year** views | Deployment beyond your own machine (Phase 0 spike kit exists but hasn't been run) |
| **Projects, Staff, Reports** dashboards | |
| Priority scoring engine (urgency, criticality, staleness, unblock value, WSJF-style delay profiles) | |
| WIP-aware daily packing per person, with over-WIP warnings | |
| Feasibility warnings ("this project is tracking N days late") | |
| Reference-class calibration from completed-task history | |
| Sprint commit / Friday close-out / velocity, **with auto-carryover of unfinished work** (§6) | |
| Simple earned value (PV/EV/AC, SPI/CPI) on Quarter, Projects, and Reports (§7, §9) | |
| **Focus Mode** — one task at a time, with a start/done timer (§5b) | |
| **Settings** — the five scoring weights, tunable without touching code (§5c) | |
| **Recurring tasks** — the next occurrence spawns automatically on completion, with a **learned estimate** once ≥3 completions exist (§4) | |
| **Needs-triage section** on Today for tasks with no estimate yet (§3) | |
| **Forward capacity timeline** on Staff — 6 weeks of load vs. capacity per person (§8) | |
| **Monte Carlo completion forecast** (P50/P85) on each project's Report page, once ≥4 weeks of that project's own throughput history exists (§9) | |
| `seed_demo`, `closeout`, `backup`, `briefing` management commands (§10) | |

See [PROJECT_PLAN.md §11](PROJECT_PLAN.md#11-competitive-gap-closing-roadmap)
for the prioritized list of what's next, benchmarked against tools like
Sunsama, Motion, and Linear.

If a feature isn't in the left column, it's still a paragraph in the plan, not
a button in the app. This guide only describes what you can click on today.

---

## 2. Getting set up

**Prerequisites:** Python 3.12+ (or just Docker — see below). No database
server, no accounts, no cloud dependency — everything is a local SQLite
file.

**Fastest path:** run `setup.bat` (Windows, double-click it) or `./setup.sh`
(macOS/Linux) from the project folder — it creates the virtual environment,
installs dependencies, generates a real secret key into `.env`, migrates,
and loads the example portfolio, all in one step. Safe to re-run; it never
re-loads example data over a real portfolio you've already started
entering. Have Docker instead? `docker compose up` does the same thing
without touching your system's Python at all. See the main
[README](README.md#quick-start) for all three setup options in detail.

**Manual path**, from the `jimothy/` project folder:

```powershell
pip install -r requirements.txt
python manage.py migrate      # creates db.sqlite3 and all tables
python manage.py seed_demo    # loads an example portfolio, dates always current
python manage.py runserver
```

Then open **<http://127.0.0.1:8000/>** — that's the Today view, Jimothy's
home page. Bookmark it.

There's no login and no user accounts (single machine, single user, by
design — see [PROJECT_PLAN.md §7](PROJECT_PLAN.md#7-ui)). If you want the
Django admin username/password prompt out of the way, create a superuser once:

```powershell
python manage.py createsuperuser
```

### About `seed_demo`

`python manage.py seed_demo` wipes and reloads a varied example portfolio (a
grant renewal under deadline pressure, a board-approval-pending proposal,
recurring weekly reporting with real completion history, and Jimothy's own
build) so every view has something real to show instead of placeholder
fixtures — including enough history to activate calibration, the
recurring-task learned estimate, and the Monte Carlo forecast on first run.
It's safe to re-run any time — it always clears prior seed data first, and
every date is relative to whenever you run it, so it's never stale. Once
you're entering your real, ongoing portfolio by hand, you won't need this
again.

---

## 3. The Today view, walked through

This is the whole product surface right now, top to bottom:

1. **Greeting + summary line** — a rotating, low-key greeting (Jimothy's
   voice — see [§7b](PROJECT_PLAN.md#7b-personality--motivation-layer-jimothy-is-fun))
   plus today's date and a count of active projects / open tasks.
2. **"Worth a look"** — feasibility warnings. These only appear when the
   engine's backward schedule shows a project's remaining work can't fit
   before its deadline at the current pace. Framed as a choice, not an
   alarm ("moving these two Backburner tasks buys the deadline back").
3. **Needs triage** — any open task with no `est_likely` yet, listed before
   everything else with a direct link to add an estimate. This is plan §5's
   "estimation debt view": until a task has an estimate it can't really be
   scheduled, so Jimothy surfaces it loudly instead of letting it sit
   silently in the backlog. (It's still included in the scored queue below
   with a reasonable fallback — this section is a visibility nudge, not a
   hard gate.)
4. **Chase list** — every `blocked` or `waiting-external` task, up front, so
   the things you need to follow up on (not do) don't get buried under
   today's task list.
5. **Today, per person** — one card per active staff member (that's just
   "John" until you add others in admin). Each card shows:
   - hours free today vs. nominal hours (focus-factor adjusted — see §5)
   - a numbered, already-prioritized task list packed into today's capacity
   - an over-WIP warning if too many tasks are already `doing` at once
   - each entry's estimated hours and originating project
6. **Unassigned, top of queue** — the ten highest-scored tasks that don't
   have an assignee yet, so nothing important silently falls through the
   cracks just because no one owns it.

If a section has nothing to show (no warnings, no blockers, no unassigned
work), it simply doesn't render — the page stays short on a good day.

---

## 4. Entering your portfolio

There are no forms in the Today view itself yet — all data entry happens
through **Django admin** at <http://127.0.0.1:8000/admin/>. It's plain and
functional rather than pretty, but it's the fastest path to a real portfolio
today. Order to enter things in:

**Every date field** (deadline, due date, trigger date, unavailability
dates) accepts plain text, not just a calendar click: type `2026-08-01`, or
`today`, `tomorrow`, `next friday`, `in 3 days` — whichever's fastest.
Anything it can't parse gets rejected with a hint rather than silently
guessing wrong.

### Staff
Name, role, `nominal_hours_per_day` (default 8), `focus_factor` (default
0.75; use **0.60 for yourself if you're the manager** — see
[§6b](PROJECT_PLAN.md#6b-meeting-load--guidance-and-default)), whether
they're a manager, and active/inactive. **Unavailability** (PTO, training,
field days) can be added inline on the same staff page — a day covered by an
unavailability entry shows 0h available on Today and doesn't get packed with
work.

### Projects
Name, **priority class** (Critical / High / Normal / Backburner — this is
the biggest lever on task ordering), deadline, `budget_staff_days` if one's
been prescribed to you, status, and free-text sponsor notes / out-of-scope
notes. Milestones and risk items can be added inline on the same project
page.

### Milestones
Belong to a project; a due date and a done flag. Tasks can point at a
milestone instead of carrying their own deadline — the engine uses whichever
is earlier.

### Tasks — the ones that matter most
- **Status:** `todo` / `doing` / `blocked` / `waiting-external` / `done`.
  `blocked` and `waiting-external` both surface on the chase list, but mean
  different things: blocked is something stopping *you*; waiting-external is
  something you're chasing someone else for.
- **Assignee**, and the **three-point estimate** — optimistic / likely /
  pessimistic hours. Likely is the only one that's required; if you only
  give `est_likely`, the engine treats it as a certain estimate (no
  variance). More on why the spread matters in §5.
- **Deadline** (optional — falls back to the milestone's due date if unset).
- **Delay profile** — this is the field with the most leverage on ordering
  and is easy to skip by accident:
  - `cliff` — worthless after the date (grant deadlines, board packets).
    Urgency ramps hard as the date nears.
  - `linear` — value erodes steadily (routine reports).
  - `slow_burn` — no real deadline; only the staleness term applies
    pressure, so it won't compete with dated work until it's been sitting a
    while.
- **Tags** — comma-separated, free text (e.g. `proposal,writing`). These
  drive the reference-class calibration in §5 and will drive report grouping
  later.
- **Depends on** — other tasks that must finish first. This feeds
  criticality (is this task on a project's critical path?) and unblock
  value (how much does finishing this open up?).
- **Blocked by / blocked since** — only relevant when status is `blocked`;
  shows on the chase list.
- **Actual hours** — fill in once work is done or as you go. This is what
  powers the calibration loop (§5) and, later, budget burn.
- **Recur every (days)** — leave blank for a one-off task. Set it and, the
  moment this task is marked `done` (from admin, Focus Mode, wherever), a
  fresh `todo` copy is created automatically with the same project and tags,
  deadlined that many days after completion. Good for the literally-recurring
  stuff — weekly reports, recurring checks — so it doesn't have to be
  re-entered by hand each time. **Its estimate isn't just copied forever,
  either:** once the same project+title has completed at least 3 times, the
  next copy's three-point estimate is learned from the actual hours those
  completions took (min/median/max) instead of repeating whatever the first
  instance happened to guess. Below 3 completions it still copies the
  previous instance's estimate, same as day one.

### Risk items
Belong to a project: description, probability (1–5), impact (1–5), trigger
date, owner, mitigation notes. Not yet surfaced in the Today view — they'll
appear in horizon views once those are built.

**Rule of thumb for a first real portfolio:** enter Staff first, then your
active Projects with priority class and deadline, then Tasks with at least a
status, assignee, and `est_likely`. Everything else (delay profile, tags,
dependencies) sharpens the ordering but isn't required to get a usable Today
view on day one.

---

## 5. How the ordering actually works (plain English)

Every open task gets a score from five ingredients — see
[PROJECT_PLAN.md §4](PROJECT_PLAN.md#4-the-prioritization-engine-the-heart-of-the-tool)
for the full math:

- **Urgency** — cost of delay ÷ how much work is left, shaped by the delay
  profile. A small task due Friday can outrank a big important task that
  still has runway (this is deliberate — it's the WSJF idea).
- **Project priority** — the Critical/High/Normal/Backburner class you set.
- **Criticality** — is this task on a project's critical path, with zero
  slack in the dependency chain?
- **Staleness** — a gentle nudge for anything untouched for a while, so
  slow-burn work doesn't rot silently.
- **Unblock value** — how many downstream tasks (and people) are waiting on
  this one.

Two things happen automatically on top of the raw score:

- **WIP limits.** Each person is capped at 2 tasks `doing` at once (3 for
  the manager). Going over triggers the gentle over-WIP warning rather than
  silently packing more in.
- **Calibration.** Once tasks have both an estimate and logged actual hours,
  Jimothy compares them per person and per tag ("fieldwork tasks tend to run
  1.4× the estimate for this person") and quietly applies that uplift to
  future estimates of the same kind. This has no effect until some tasks
  have actuals recorded — there's nothing to calibrate from on day one.

Nothing here is a black box you have to trust blindly — every input (project
priority, delay profile, estimates, tags) is something you set directly in
admin, and the weights themselves are meant to be tunable (not yet exposed
in a settings screen, but visible in `engine/scoring.py` if you want to see
exactly what's happening).

---

## 5b. Focus Mode — one thing at a time

**Focus** (top nav) shows exactly one task: the top of the packed queue for
one person, full screen, nothing else. The rest of today's list is
deliberately hidden — this is the anti-doomscroll view from plan §7b, for
when the ordered list itself is the distraction.

- **Start** begins a timer (a running "Nh Nm Ns" counter).
- **Done** marks the task complete and, if it was timed, logs the elapsed
  time as a `WorkLog` entry and adds it to the task's `actual_hours` —
  automatically, no separate data-entry step. That's real data feeding
  calibration (§5) and earned value (§9) the moment you use it.
- **"Not this one — skip for today"** pulls the next task up instead,
  without marking anything done or touching its status. The skip only lasts
  for today's session.
- If more than one active staff member exists, a small switcher at the top
  lets you view anyone's one thing, not just your own.

## 5c. Settings — tuning the scoring weights

**Settings** exposes the five weights behind every priority score (plan
§4's `score = w1·urgency + w2·priority + w3·criticality + w4·staleness +
w5·unblock`) as plain number fields — no black box, no code edit required.
Raise urgency's weight and deadline pressure dominates ordering more;
raise unblock's and tasks that free up downstream work rise faster. Changes
apply everywhere the queue is used (Today, Week, Month, Quarter, Focus) the
next time a page loads. **Reset to defaults** puts all five back to the
plan's original values (4.0 / 2.0 / 1.5 / 0.5 / 1.0).

---

## 6. Week — the sprint loop

The **Week** view (top nav) is this week's sprint board, Monday to Sunday.
It has three parts:

- **Commitment vs. capacity** — total hours committed this week vs. total
  available hours across active staff. Going over isn't an error, just a
  warning — something will roll forward, and that's normal.
- **Sprint board** — five columns (To do / Doing / Blocked / Waiting on
  external / Done) built from whatever's committed. Click **uncommit** on any
  task to pull it back out.
- **Commit candidates** — the top of the scored queue that isn't committed
  yet. Click **commit** to add a task to this week's sprint.

**Friday close-out**, at the bottom of the page: type a one-line retro note
(a rotating prompt suggests a question) and click **Close out this sprint**.
That computes **velocity** — hours of committed work that actually got
`done` this week, PERT-expected size, with calibration applied — and saves
it on the `Sprint` record. There's also a CLI equivalent:
`python manage.py closeout` does the same close-out from the terminal,
prompting for the retro note there instead of a web form.

**Carryover is automatic** (Linear-Cycles-style): the first time you open
Week after a new week starts, whatever was committed last week but never
finished gets re-committed to the new week for you — no manual re-click
required. You'll still see it show up as already-committed, not sitting in
the candidates list.

There's no navigation to past or future weeks yet — only the current one.

---

## 7. Month, Quarter, Year

Three roll-up views over the same portfolio, at increasing altitude:

- **Month** — every milestone due in the next 8 weeks, with days remaining,
  open-task count, remaining hours, and a "critical path" badge for
  milestones with a zero-slack task in their chain.
- **Quarter** — one card per active project: priority, deadline, a
  feasibility warning if it's tracking past deadline at current pace, a
  budget-burn line (actual / earned / planned staff-days plus a plain-English
  schedule/budget summary — see §9), and any open risk whose trigger date
  falls in the current calendar quarter.
- **Year** — total staff-days consumed vs. the portfolio's summed
  `budget_staff_days`, every dated project's deadline in the next 12 months,
  and a **deadline-density table**: a count of project deadlines + milestone
  due dates per month for the next year, so a pileup three months out is
  visible now instead of a surprise later. The bars next to each count are a
  secondary visual cue — the numbers are the real data, screen-reader and
  table-first by design.

---

## 8. Projects & Staff dashboards

- **Projects** — every project, one row each, with status, priority,
  deadline, open-task count, burn (actual vs. planned staff-days), and
  feasibility slip. This is a *dashboard*, not a form — editing still happens
  in `/admin/` (linked from each row); admin already does full CRUD, so this
  page isn't duplicating it.
- **Staff** — roster with each person's available hours/day (nominal ×
  focus factor), any upcoming unavailability, and their calibration factors
  (overall and per-tag) once there's enough completed-task history to
  compute one — same 4-sample minimum as the Today view's calibration.
  Below the roster info, each person also gets a **6-week forward capacity
  timeline**: assigned remaining hours bucketed into the week containing
  each task's effective deadline, shown as a bar against that week's
  capacity. A week with more assigned than available gets an "over
  capacity" pill (not just a red bar — status is never color-alone here).
  Tasks with no real deadline (slow-burn work) don't appear in this view;
  it's specifically a *dated* forward look, not everything on someone's
  plate.

---

## 9. Reports

**Reports** lists active projects; each one links to a weekly-status page
with earned value (planned / earned / actual staff-days, plus the same
plain-English SPI/CPI summary as Quarter — e.g. "running 12% behind
schedule, 8% under budget"), a **completion forecast**, milestones, open
risks, anything blocked or waiting on an external party, and recently
completed tasks. Screen-reader and WCAG-friendly, like every other page.
There's no email delivery yet — open the page and read it, or print it,
same as any other report.

**The completion forecast** runs Monte Carlo simulation
(`engine/montecarlo.py`) against *that project's own* pace: it samples the
project's actual completed-work hours per week over the last 12 weeks a
few thousand times, burning down the remaining work, and reports P50/P85
completion dates ("50% chance done by Aug 22, 85% by Sep 12"). It needs at
least 4 weeks of that specific project's own completed-task history — until
then it says so plainly rather than guessing from thin data. This is
deliberately per-project, not a portfolio-wide average: a project's own
pace is what predicts when *it* finishes.

**A note on earned value:** PV only counts a task once its deadline has
passed, and EV only counts a task once it's marked `done` — so a fresh
project with no logged history will show "not enough logged history yet"
rather than a misleading 0%. That's expected, not a bug.

---

## 10. Other management commands

Beyond `seed_demo` (§2) and `closeout` (§6):

- **`python manage.py briefing`** — renders today's briefing (greeting,
  warnings, chase list, per-person queue) as plain text to the terminal.
  This is the same content the Today page shows, in a script-friendly form.
  It does **not** send an email — Outlook COM integration is still gated on
  PROJECT_PLAN.md's open item #4 (classic vs. new Outlook on the target
  machine); wiring `briefing` up to actually send is a small follow-up once
  that's answered.
- **`python manage.py backup`** — copies `db.sqlite3` to
  `backups/jimothy-YYYY-MM-DD.sqlite3` (gitignored). OneDrive already
  versions the live database file, so this is for a clean point-in-time copy
  before a risky change, not primary backup.

---

## 11. Where things live, if you want to look under the hood

```
config/            Django project settings, URLs
core/               Models, admin, views, services.py (shared query→engine
                    glue), forms.py (NaturalDateField), phrases.py (all the
                    copy), templates/core/ (base.html + one template per page)
core/management/commands/   seed_demo, closeout, backup, briefing
engine/             Pure-Python scoring/scheduling/EV/sprint engine — no
                    Django imports, unit-tested in engine/tests/, designed to
                    also run inside a browser via Pyodide later (§8b)
phase0/             Deployment spike kit for a locked-down, no-admin machine —
                    see phase0/README.md
```

---

## 12. FAQ / troubleshooting

**The Today view is empty / says "No active staff yet."**
Add at least one Staff record (marked active) in `/admin/`, and give them at
least one open task. Or just run `python manage.py seed_demo`.

**A task I know about isn't showing up anywhere.**
Only tasks with status other than `done` show up. Check the task's status
and assignee in admin — unassigned tasks land in "Unassigned, top of queue"
(capped at the top 10 by score), not in anyone's daily list.

**The engine crashed / Today view rendered but looks wrong.**
The view is written to fail soft — if scoring throws an exception it logs
the error and renders an empty-but-working page rather than a 500. Check the
console `runserver` is running in for a traceback if this happens.

**Can other people on my team use this?**
Not yet, and it's not really the design — see
[PROJECT_PLAN.md open item #2](PROJECT_PLAN.md#10-open-items-user-input-wanted).
It's built as a single-manager decision-support tool, not team collaboration
software.

**Where do I report the rest of the feature list / answer open questions?**
[PROJECT_PLAN.md §10](PROJECT_PLAN.md#10-open-items-user-input-wanted) has
the running list of things still waiting on your input.

**Quarter/Projects/Reports shows "not enough logged history yet" instead of numbers.**
Expected on a fresh project — earned value needs a task past its deadline
(for PV) or actually marked `done` with actual hours logged (for EV/AC) before
there's anything to compute. It fills in as you use the tool, not
retroactively.

**Staff shows "No calibration history yet" for everyone.**
Same reason as calibration on Today (§5) — needs at least 4 completed tasks
with both an estimate and actual hours logged for a given person or tag
before a factor is trustworthy enough to show.

**The Week board says I'm over-committed — is that a problem?**
No — it's informational, not a hard stop. Whatever's still open when the
week ends gets auto-carried into next week's commitment for you (§6);
nothing is lost or needs re-entering.
