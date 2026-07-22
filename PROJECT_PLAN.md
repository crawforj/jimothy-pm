# Jimothy — Single-Manager Project Management & Scrum Master Tool

**Status:** Phases 1–3 built, plus most of Phase 4. See
[USER_GUIDE.md](USER_GUIDE.md) for what actually runs today and
[§11](#11-competitive-gap-closing-roadmap) for what's next.
**Runs on:** one machine (Windows/macOS/Linux), local SQLite, no team-facing
server -- calendar sync (§7c) is the one feature with a cloud round-trip
(OAuth against Microsoft Graph/Google Calendar), opt-in per provider

---

## 1. Concept

Jimothy is a personal project-management and scrum-master tool for **one manager
orchestrating a portfolio of projects and a small staff**. The user feeds it
project definitions, deadlines, staffing budget, and staff capacity; Jimothy
maintains a live, prioritized picture of what should happen **today, this week,
this month, this quarter, and this year — simultaneously**. It is not a team
collaboration tool; it is a decision-support engine for the person doing the
juggling.

Design north star: every morning, Jimothy answers three questions in under 10
seconds:

1. **What should I (and each staff member) work on today, in what order?**
2. **What is at risk of missing its deadline, and how far out is the collision?**
3. **Am I over/under my staffing budget and capacity at each horizon?**

## 2. PMBOK alignment (the nine knowledge areas)

Jimothy follows the classic nine PMBOK knowledge areas, loosely — each maps to
a concrete feature, not a ceremony:

| Knowledge area | Jimothy feature |
|---|---|
| **Integration** | Portfolio dashboard; single prioritized queue across all projects; change log when scope/dates move |
| **Scope** | Project → milestone → task WBS; explicit "out of scope" notes per project; scope-creep flag when task count grows >X% after baseline |
| **Schedule (Time)** | Deadlines, dependencies, critical-path & slack computation, multi-horizon calendar views |
| **Cost** | Staffing budget in hours and dollars; burn tracking; simple earned-value metrics (SPI/CPI) per project |
| **Quality** | Definition-of-done checklist per task type; rework tracking (tasks reopened after "done") |
| **Human Resources** | Staff roster, hourly cost, weekly capacity, skills tags, vacation/unavailability calendar; resource leveling |
| **Communications** | Morning briefing (on-screen + optional Outlook email); weekly status report generator per project |
| **Risk** | Lightweight risk register per project (probability × impact, owner, trigger date); risks surface in horizon views when trigger approaches |
| **Procurement** | Minimal: external-dependency tasks flagged "waiting on vendor/third party" with follow-up dates (these behave differently in prioritization — you chase, not do) |

Scrum-master overlay (PMBOK-compatible, agile-flavored):
- The **week is the sprint**. Weekly planning commits tasks against capacity;
  Friday close-out computes velocity and rolls incomplete work forward.
- **Velocity per person** feeds back into estimate calibration (§5).
- **Blocked** is a first-class task state with a "blocked by whom/what + since
  when" field; standup view leads with blockers.
- Lightweight **retrospective note** at sprint close (one text field — friction
  log, not ceremony).

## 3. Core data model (SQLite)

```
Staff(id, name, role, nominal_hours_per_day, focus_factor,     -- §6b defaults 0.75 / 0.60 mgr
      calendar_shared, skills, active)
Unavailability(staff_id, start_date, end_date, reason)          -- PTO, training
CalendarEvent(staff_id, provider, source_id, start, end,        -- §7c OAuth calendar sync
              busy_status, all_day, subject)                    -- subject only for the manager's own events
Project(id, name, priority_class, deadline, baseline_task_count,
        budget_staff_days, status, sponsor_notes, out_of_scope) -- budget prescribed externally, §6
Milestone(id, project_id, name, due_date, status)
Task(id, project_id, milestone_id, title, status,               -- todo/doing/blocked/waiting-external/done
     assignee_id, estimate_optimistic, estimate_likely, estimate_pessimistic,
     actual_hours, deadline_override, depends_on[], done_definition,
     reopened_count, blocked_by, blocked_since, created, completed)
RiskItem(id, project_id, description, probability_1_5, impact_1_5,
         trigger_date, owner, mitigation, status)
Sprint(id, week_start, committed_task_ids[], velocity_actual, retro_note)
WorkLog(id, task_id, staff_id, date, hours)                     -- optional granularity
ChangeLog(id, entity, entity_id, field, old, new, timestamp)    -- integration/audit
```

## 4. The prioritization engine (the heart of the tool)

Every open task gets a **priority score** recomputed on demand:

```
score = w1·urgency + w2·project_priority + w3·criticality + w4·staleness + w5·unblock_value
```

- **urgency** — nonlinear function of (effective deadline − today) ÷ remaining
  estimated hours. A task 3 weeks out that needs 40 staff-hours is *more urgent*
  than a task due Friday needing 30 minutes. Effective deadline = earliest of
  task deadline, milestone due date, or backward-chained dependency deadline.
- **project_priority** — manager-set class (Critical / High / Normal / Backburner).
- **criticality** — is the task on a project's critical path (zero slack)?
- **staleness** — gentle boost for tasks untouched >N days (nothing rots silently).
- **unblock_value** — number of downstream tasks (and people) this task unblocks.

Weights are visible and tunable in settings — no black box.

**Cost-of-delay urgency profiles (WSJF-inspired).** The urgency term is really
cost of delay ÷ job size, per Reinertsen/SAFe's Weighted Shortest Job First —
which is why a moderately important 2-hour task due soon can outrank a huge
important task with runway. Each task/milestone gets a **delay profile**:

- **Cliff** — worthless after the date (grant deadline, board packet). Urgency
  ramps steeply as the cliff approaches; after it, the task auto-flags dead.
- **Linear** — value erodes steadily (routine reports).
- **Slow burn** — no real date; staleness term is the only pressure.

**WIP limits & context-switch cost (personal kanban).** The Doing column is
capped (default 2 per person, 3 for the manager). Research pegs context
switching at ≥10% lost per switch, so the daily packer also prefers plans with
fewer project switches — batching two tasks from the same project beats
alternating projects even when raw scores say otherwise. Over-WIP is a visible
warning, phrased Jimothy-style ("finish something first — future you says
thanks").

**Horizon roll-ups** are views over the same scored queue:
- **Today:** top-scored tasks per person, packed into today's available hours
  (capacity minus meetings/unavailability). Blockers and external follow-ups
  ("chase list") shown first.
- **Week (sprint):** committed set vs. capacity; over-commitment warning in hours.
- **Month:** milestone timeline; tasks aggregated to milestones; slack per milestone.
- **Quarter:** project-level Gantt-ish bars, budget burn vs. plan, risk triggers landing this quarter.
- **Year:** portfolio roadmap; annual staffing-budget consumption; deadline density map (spot the pileups months out).

**Feasibility check (the killer feature):** backward-schedule all remaining
work against real capacity. If Project X's remaining 120 hours can't fit before
its deadline given everyone's committed load, Jimothy says so **now** — with the
projected slip date and which lower-priority work would have to move to fix it.

## 5. Staff time estimation

- **Three-point (PERT) estimates** per task: optimistic / most-likely /
  pessimistic → expected = (O + 4M + P) / 6, with variance retained so
  project-level completion dates carry an uncertainty band, not a single date.
- **Calibration loop:** actuals vs. estimates per person and per task tag
  produce a rolling **estimate-accuracy factor** (e.g., "Alice's 'fieldwork'
  tasks run 1.4× her estimate"). Applied automatically to forecasts; shown
  transparently.
- **Templates:** recurring task types (e.g., "monthly report," "board packet")
  carry default estimates learned from history.
- Estimation debt view: tasks with no estimate can't be scheduled — surfaced
  loudly so the queue stays honest.
- **Monte Carlo completion forecasting (the pro upgrade).** Once ~8 weeks of
  history exist, Jimothy stops giving single dates. It samples the team's
  actual weekly throughput distribution a few thousand times and reports
  **P50 / P85 completion dates** per project ("50% chance done by Oct 3, 85% by
  Oct 24"). The feasibility check (§4) then reports *probability of hitting
  the deadline*, not a binary yes/no — far harder to argue with, and it needs
  no estimates at all once throughput history exists. Pure-Python, a few dozen
  lines in the engine.
- **Reference-class forecasting (outside view).** The calibration factors are a
  personal version of Kahneman/Flyvbjerg's debiasing method: task tags define
  reference classes ("fieldwork", "board packet", "new-tech"), and each class
  carries its empirical overrun distribution from history. New estimates get
  the class uplift applied automatically — the antidote to the planning
  fallacy, which no amount of good intention fixes from the inside view.

## 6. Staffing budget & cost

- **Budget unit is staff-days**, and the budget is **prescribed from outside**
  (handed down, not negotiated inside Jimothy). Jimothy therefore treats budget
  as a hard constraint to track against, not a number to plan: each project has
  `budget_staff_days`, and the interesting outputs are burn, remaining, and
  projected-at-completion vs. the prescribed figure — with early warning when
  the forecast (PERT estimates × calibration factors) exceeds what was granted.
- One staff-day = one person's **available** hours for a day (nominal hours ×
  focus factor, §6b) — so budgets are compared against realistic capacity, not
  8.0 idealized hours. Internally everything is stored in hours; staff-days are
  the display unit everywhere the user sees budget.
- Burn = logged/actual hours ÷ available-hours-per-day, shown as staff-days.
  Simple earned value per project:
  - PV (planned value) from the backward schedule, EV from completed-task
    estimates, AC from actuals → **SPI** and **CPI** with plain-English labels
    ("running 12% behind schedule, 5% under budget").
- Quarterly and annual roll-ups of total staff-days consumed vs. total
  prescribed budget across the portfolio.
- Team size per project is typically **≤ 5 people**; the resource-leveling and
  Today views are designed around that scale (no pagination gymnastics, one
  screen shows everyone).

## 6b. Meeting load — guidance and default

You don't need to measure meeting load up front; industry rule of thumb plus a
self-correcting loop is enough:

- **Start with a global focus factor of 0.75**: of a nominal 8-hour day, count
  **6 hours** as available for planned task work. This is the standard
  knowledge-worker planning assumption (meetings, email, interruptions,
  context-switching eat the rest). For yourself as the manager, start at
  **0.60** (≈5 hrs/day) — managers reliably lose more to coordination.
- Focus factor is a per-person field with those defaults; nobody enters
  meeting schedules. Exceptional all-day events (training, field days) go in
  the existing Unavailability table instead.
- **Jimothy self-corrects:** after a few sprints, measured throughput (actual
  task hours completed per person per week vs. nominal hours) reveals each
  person's true focus factor. Jimothy displays "planned 0.75 / observed 0.68 —
  adopt?" and one click updates it. So the initial guess only has to be
  roughly right for the first month.
- All capacity math (daily packing, sprint commitment meter, feasibility
  scheduler, staff-day conversion in §6) uses focus-adjusted hours — never raw
  nominal hours.
- **Where Outlook calendar data exists (§7c), it supersedes the flat factor:**
  available hours = nominal − actual meeting hours from the calendar, with a
  smaller interruption haircut (~0.85) applied to the non-meeting remainder.
  The flat focus factor stays as the fallback for staff without shared
  calendars and for far-future planning beyond the calendar sync window.

## 7c. Calendar sync (Microsoft Graph + Google Calendar)

Read-mostly integration, OAuth-based against **Microsoft Graph** and
**Google Calendar** — not local Outlook COM automation, which was the
original design here until jimothy-pm became a public, cross-platform
product (Windows/macOS/Linux binaries): COM only exists on Windows with
classic Outlook installed, would leave macOS/Linux and "new Outlook" users
with nothing, and can't reach Google at all. Graph works against either
Outlook client and any OS, which is what actually resolves §10 item 4 below
rather than deferring around it.

A `CalendarProvider` interface (`core/calendarsync/base.py`) is implemented
once per provider (`graph_provider.py`, `google_provider.py`); callers
(views, `sync_calendar`, `desktop_app.py`'s background loop) only ever talk
to the interface. Both OAuth app registrations (Azure Portal, Google Cloud
Console) are one-time setup only True Ascent Labs LLC can do; the public
binary ships with those client IDs baked in (env-var overridable for
self-hosters running their own registration) so Connect works out of the
box for every downloader — see USER_GUIDE.md's "Connecting your calendar."

**Reads (core, v1's only scope — writes below are a later phase):**
- `manage.py sync_calendar` pulls events for a rolling window (default next
  6 weeks + past 2 weeks) from whichever provider(s) are connected: start,
  end, busy status, all-day flag, subject.
- Stored as `CalendarEvent(staff_id, provider, source_id, start, end,
  busy_status, all_day, subject)`, upserted on `(staff, provider,
  source_id)`. Only Busy/Out-of-Office statuses count against capacity;
  Free/Tentative don't (tentative shown as a soft warning on the day) --
  see `engine/calendar_capacity.py` for the pure hours math.
- Feeds capacity math per §6b: `pack_day`'s existing `hours_available`
  override (already built for the flat-factor case) is what real calendar
  data plugs into. Today, Focus, and the morning briefing all use it.
- v1 scope: both Connect buttons (Settings) are global, tied to whichever
  Staff row has `is_manager=True` -- one Microsoft connection, one Google
  connection per running instance, not per-staff-member. `calendar_shared`
  keeps its existing meaning (gates whether *subject text* is ever stored
  for a non-primary staff row) but is inert until a later phase lets
  individual staff connect their own calendars.

**Writes (done, 2026-07-21):**
- Project **milestones/deadlines pushed as all-day events** into a dedicated
  "Jimothy" calendar (`core/calendarsync/push.py`, wired via a `post_save`/
  `pre_delete` signal on `Milestone` — `core/signals.py`), never the user's
  main calendar. Graph uses `Calendars.ReadWrite` (no narrower scope
  exists); Google uses `calendar.app.created`, a materially tighter
  "only what this app made" permission.
- **Focus blocks:** starting a task in Focus Mode reserves a calendar
  block sized to its estimate (0.5-4h); finishing or skipping it removes
  the block. Manager-only, matching calendar connections being
  global/manager-scoped, not per-staff.
- One-directional per item, enforced by `PushedCalendarEvent`: Jimothy
  only ever updates or deletes an event it created itself, tracked by
  that table, never anything else in either calendar. Off by default —
  an explicit per-provider toggle on Settings, separate from just being
  connected.

**Scheduling:**
- Sync runs on demand from Settings' "Sync now," plus automatically every
  24h from `desktop_app.py`'s background thread when the packaged app is
  running and at least one provider is connected (silent/no-op otherwise).
- Build phase: reads land in **Phase 3** (they make capacity real); writes are
  **Phase 4** polish.

## 7. UI

**Local Django app** (SQLite, `runserver` on localhost, bookmark it) — chosen
over TUI/Excel because Django ships fast and the five horizon views are
naturally tabbed pages. No auth needed (single machine, single user) but
keep Django's admin as the free power-user data editor.

Pages:
1. **Today** (default) — per-person ordered list, blockers first, chase list, capacity bar
2. **Week** — sprint board (todo/doing/blocked/done columns) + commitment-vs-capacity meter
3. **Month / Quarter / Year** — timeline views per §4
4. **Projects** — CRUD, WBS editor, risk register, budget/burn, EV metrics
5. **Staff** — roster, capacity, unavailability calendar, calibration factors
6. **Reports** — weekly status per project (HTML, screen-reader/WCAG-friendly
   per standing rule), morning briefing preview

Optional (phase 4): Outlook COM morning-briefing email via a scheduled task,
using a small local wrapper script.

## 7b. Personality & motivation layer (Jimothy is fun)

Jimothy is a **coach, not a nag**. Explicit design requirement: using it should
improve mood and focus, not add guilt. Concretely:

- **Voice:** every generated message (briefing, warnings, close-out) is written
  in Jimothy's voice — warm, a little funny, always concrete. A tone dial in
  settings (Professional / Friendly / Full Jimothy) controls how much
  personality leaks into reports vs. the daily screens.
- **Wins are celebrated first.** Morning briefing opens with yesterday's
  completions and streaks before it mentions what's due. Friday close-out leads
  with velocity and shipped work, then the roll-forward.
- **Focus mode:** a "what's my ONE thing right now" button — full-screen single
  task from the top of today's queue, with a start/done timer. The backlog is
  hidden on purpose; anti-doomscroll by design.
- **Encouragement is honest, never hollow.** Feasibility warnings (§4) are
  framed as choices with a way out ("moving these two Backburner tasks buys the
  deadline back"), never as red-alert shame. No overdue-task wall of red;
  overdue items just re-enter today's queue at higher urgency.
- **Streaks & momentum:** consecutive days with the top-priority task touched,
  weeks with sprint commitment met. Displayed small — motivating, not gamified
  to death.
- **Retro prompt with personality:** one Friday question, rotating and light
  ("What made this week dumber than it needed to be?"), stored as the sprint
  retro note.
- All copy lives in a `phrases.py` message bank — easy to tune the humor
  without touching logic.

## 8. Architecture

- Python 3.12+, Django 6, SQLite file DB (one-file backup; lives in the project
  folder, OneDrive gives free versioned backup)
- No JS framework — server-rendered templates + a sprinkle of HTMX for the
  sprint board drag/status changes
- Scoring/scheduling engine as a **pure-Python module (`jimothy/engine/`)
  with no Django imports and no OS calls** — unit-testable, reusable if the UI
  changes, and critically: **runnable under Pyodide in a browser** (see §8b
  Tier 3). This constraint is now load-bearing, not just hygiene.
- `manage.py` custom commands: `briefing` (render/send morning email),
  `closeout` (Friday sprint close + velocity), `backup`

## 8b. Deployment on a locked-down machine (no admin)

Constraint: some environments (corporate or government machines with minimal
privileges) allow no installers, no admin elevation, possibly AppLocker-style
application allow-listing, but a modern Edge/Chrome browser is always present.
**Phase 0 is a deployment spike** that tests these tiers in order on the actual
machine; everything above the data layer is designed to survive a forced move
down the ladder.

**Tier 1 — user-space Python (best case).** Python needs no admin: either an
existing approved interpreter, or the **python.org "Windows embeddable
package"** — a zip extracted into your user profile; `python.exe` runs directly
from there with zero installation or registry writes. Django's `runserver` on
localhost binds a high port (no admin needed), SQLite is a file (no service),
and user-level Task Scheduler tasks can handle the morning briefing.
*Failure mode:* AppLocker publisher/path rules can block unsigned exes
running from user-writable directories. Quick test: extract the zip, run
`python.exe -V`. If blocked, drop to Tier 2/3 — do not attempt workarounds;
ask IT or move down the ladder.

**Tier 2 — approved-host piggyback.** If arbitrary exes are blocked but some
scripting host is approved (an org-installed Python, Anaconda, or even
Excel/VBA as a last resort), run the engine under the approved host. The
pure-Python engine + SQLite file need nothing else; the UI degrades to
generated static HTML reports opened in the browser (no server process at all
— `jimothy build` writes today's dashboard as HTML to disk).

**Tier 3 — zero-footprint browser app (the creative one).** A **single HTML
file opened in Edge**. SQLite runs *inside the browser* via WASM (sql.js), the
engine runs via **Pyodide** (CPython compiled to WASM) — so the exact same
`engine/` module executes unchanged. Data persists in the browser's IndexedDB
with one-click export/import of the `.sqlite` file to OneDrive (backup +
machine portability). Nothing is installed, no exe ever runs, no server exists
— it is bytes interpreted by an already-approved browser, which survives
essentially any lockdown short of banning HTML files. The File System Access
API can streamline saving to a real OneDrive-synced file where the browser
allows it; explicit export/import is the guaranteed fallback.

**Design consequences (apply from Phase 1 regardless of tier):**
- The engine stays pure-Python, dependency-light (stdlib + nothing exotic —
  Pyodide must load it).
- All UI templates render from a plain JSON "view model" the engine emits, so
  the same rendering works server-side (Django), static (Tier 2), or
  client-side (Tier 3).
- The SQLite file is the *only* state, and its schema is the contract; any tier
  can pick up another tier's file.
- Calendar sync (§7c) needs outbound HTTPS to Microsoft/Google, which a
  locked-down machine may not allow -- absent that, it degrades gracefully
  to the flat focus factor, same as any Staff row that's never connected
  anything. No local-COM dependency to worry about at any tier anymore.

## 9. Build phases

| Phase | Scope | Definition of done |
|---|---|---|
| **0. Deployment spike** | Test §8b tiers on the actual target machine (embeddable Python → approved host → browser/Pyodide) | Know which tier the build targets; ladder documented |
| **1. Skeleton + data** | Django project, models, admin, fixtures; project/task/staff CRUD; engine emits JSON view models from day one | Can enter a real portfolio and see it in admin |
| **2. Engine** | Scoring (incl. delay profiles + WIP-aware packing), dependency/critical-path, backward feasibility scheduler, PERT roll-ups; unit tests with known-answer scenarios | Engine tests pass; Today + Week views render real ordered queues |
| **3. Horizons + sprint loop** | Month/Quarter/Year views, sprint commit/closeout, velocity, calibration + reference-class factors, calendar reads (§7c) | One full simulated sprint cycle round-trips correctly |
| **4. Comms + polish** | Reports page, morning briefing (screen + optional email), EV metrics, Monte Carlo forecasts, risk-trigger surfacing, calendar writes, WCAG pass | Daily-driver ready |

Phases 1–2 are the MVP: even without the horizon views, a correctly ordered
"Today" list justifies the tool.

## 10. Open items (user input wanted)

Resolved 2026-07-17: budget is **staff-days, prescribed externally** (§6);
team size **≤ 5 per project** (§6); meeting load handled via **focus-factor
default + calendar supersession** (§6b, §7c); Outlook calendar integration
added (§7c).

Still open:

1. **Truncated feature list** — the original request ended at "Features:
   estimate staff time," — what else was on the list?
2. Will staff ever look at Jimothy directly, or does the manager relay
   everything? (Affects whether per-person views need printable/emailable form.)
3. Where actual hours come from — quick daily logging in Jimothy vs. rough
   weekly true-up vs. import from timesheets. (Default assumption: rough
   weekly true-up at sprint close, since it's the lightest habit.)

**Resolved 2026-07-21:** item 4 ("classic vs. new Outlook on this machine,"
deferred 2026-07-18) is moot -- calendar sync (§7c) is now Microsoft
Graph/Google Calendar OAuth, not local Outlook COM automation, so it works
identically regardless of which Outlook client (or OS) is installed. Reads
are built; writes (milestones/focus-blocks pushed to a calendar) remain a
separate, still-unbuilt later phase. The morning briefing *email* specifically
(as opposed to calendar reads) is a different, still-open question --
Outlook COM vs. Graph vs. plain SMTP for actually sending it.

Partially addressed 2026-07-18: item 3 now has a real option, not just a
default assumption — **Focus Mode** (§7b) offers quick timer-based logging
(start/done on one task, elapsed hours auto-logged to `WorkLog` and rolled
into `actual_hours`) as an alternative to weekly true-up. Whether that
becomes the primary habit or stays a supplement is still the user's call.

## 11. Competitive gap-closing roadmap

Added 2026-07-18, from a market comparison against the tools actually
closest to Jimothy's design point — not team-collaboration suites (Jira,
Asana-as-a-whole) but single-user daily-planning/auto-scheduling tools
(Sunsama, Motion) plus the specific pieces of team tools that do
resource/capacity math well (Linear's Cycles, Asana's Workload,
Monday.com's automations). Full comparison and sourcing in the chat history
of the session that added this section; the filter applied throughout:
**adopt what strengthens single-manager decision support, skip what exists
mainly to configure a multi-user system.**

### Do next — small, unblocked, high daily-use value

**All four shipped 2026-07-18** — see [USER_GUIDE.md](USER_GUIDE.md) for how
to use them.

1. ~~**Recurring tasks.**~~ **Done.** `Task.recur_every_days`; a `save()`
   hook spawns the next occurrence (same project/tags/estimate, deadline
   offset by the interval) on the transition into `status=done`, regardless
   of whether that happened via Focus Mode, admin, or any future path.
2. ~~**Auto-carryover for the sprint loop.**~~ **Done.**
   `core/services.py::get_or_create_sprint()` auto-recommits the previous
   week's incomplete committed tasks the first time a new week's `Sprint` is
   touched — and gives `engine/sprint.py::roll_forward()` its first real
   caller.
3. ~~**Lightweight natural-language date entry.**~~ **Done.**
   `engine/dateparse.py` (pure Python, unit-tested) plus a
   `NaturalDateField` wired into every admin `DateField` via
   `formfield_overrides` — accepts "next friday", "in 3 days", or a plain
   ISO date in a text box instead of a click-only calendar widget.
4. ~~**A triage step for new tasks.**~~ **Done, in a smaller form than
   originally scoped.** Rather than a `needs_triage` flag that excludes a
   task from scoring, Today now surfaces every task with no estimate
   (`est_likely` is null) in its own "Needs triage" section above the
   scored queue — implementing plan §5's "estimation debt view" directly.
   Scoring itself is unchanged: an untriaged task still gets a reasonable
   fallback score (§4's one-nominal-day assumption) rather than being
   excluded outright. Revisit true exclusion-from-scoring only if
   visibility alone proves insufficient in practice.

### Do later — bigger or design-sensitive

**All three shipped 2026-07-18** — see [USER_GUIDE.md](USER_GUIDE.md) for
how to use them.

5. ~~**A forward capacity timeline**, Asana Workload-style.~~ **Done.**
   `engine/schedule.py::weekly_load()` buckets each person's assigned
   remaining hours by the week containing its effective deadline, against
   that week's capacity; shown on the Staff page as a 6-week table with a
   proportional bar per week. Over-capacity weeks are flagged by a text
   pill ("over capacity"), not color alone.
6. ~~**Learned default estimates on recurring-task templates.**~~ **Done.**
   `engine/estimate.py::template_estimate()` derives a fresh three-point
   estimate (min/median/max) from the last 8 completions of the same
   project+title; `Task._spawn_next_occurrence()` uses it once ≥3 samples
   exist, falling back to copying the previous instance's estimate below
   that.
7. ~~**Wire `engine/montecarlo.py` into a page.**~~ **Done.**
   `core/services.py::project_monte_carlo()` (+ `project_weekly_throughput()`)
   feeds each project's own last-12-weeks completed-work pace into the
   existing Monte Carlo math; P50/P85 completion dates now show on that
   project's Report page once ≥4 weeks of the *project's own* throughput
   history exists (deliberately per-project, not portfolio-wide — plan §5's
   "team's actual weekly throughput" is about the work on that project, not
   everything the manager touches).

### Deliberately skip — fits competitors, not Jimothy

8. **A general automation/rules builder** (Monday.com's 400+ "when X then Y"
   templates). This is exactly the multi-user configuration overhead §1
   defines Jimothy against ("a decision-support engine for the person doing
   the juggling," not a system to administer). If a specific automation
   proves genuinely needed, add it as an opinionated hard-coded behavior
   (like #2 above) rather than a general engine.
9. **Custom fields / user-built saved views** (Notion/ClickUp-style).
   Undermines the prescriptive five-horizon design (§7) — Jimothy's value is
   *not* asking the user to build their own views.
10. **LLM-generated summaries.** The single most-requested 2026 buyer
    feature industry-wide, and a deliberate non-goal here: an LLM API call
    breaks the offline/dependency-light/Pyodide-portable architecture (§8)
    for a personal tool where `phrases.py`'s deterministic "coach" voice
    already fills that role without a network dependency or output drift.
    Revisit only if a narrow use case emerges that templated copy genuinely
    can't cover.
11. **A native mobile app.** A real gap (every competitor has one) but
    resolving it — expose the server on the LAN? refresh a Tier-3-style
    static export on a schedule? — is a design decision that conflicts with
    the local-only, no-server-exposed architecture (§8), not a build task.
    Flag as a future open item rather than build blind.
