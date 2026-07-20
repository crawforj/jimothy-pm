# Phase 0 — deployment spike kit

Goal: find the highest tier from [PROJECT_PLAN.md §8b](../PROJECT_PLAN.md)
that works on your target machine. Everything here is **read-only and
self-contained**: no installs, no admin, no system changes, no network calls
(one loopback connection to itself in the Python test, nothing external).

## Getting the kit onto the machine

Copy this `phase0/` folder over however files normally reach that machine
(OneDrive, email to yourself, approved transfer). If you'll test Tier 1 with
embeddable Python, also bring the zip (download at home if python.org is
blocked there):

- <https://www.python.org/downloads/windows/> → "Windows embeddable package
  (64-bit)" for the latest 3.12/3.13 release (~11 MB zip)

## Tier 1 — user-space Python

1. Extract the embeddable zip to `phase0\python-embed\` (so
   `phase0\python-embed\python.exe` exists). Skip this step if the machine
   already has an approved Python (`py -V` or `python -V` in cmd).
2. Double-click `run_tier1.bat` (or run `python spike_check.py` yourself).
3. It prints a `JIMOTHY-SPIKE-RESULT` block and saves `spike_result.txt`.

Interpreting it:

- **All core checks PASS** (sqlite, localhost port, loopback HTTP, profile
  write) → Tier 1 works; Django-on-localhost is a go.
- **python.exe won't start at all** (blocked/AppLocker message) → Tier 1 is
  out with embeddable Python. If an org-approved Python exists, run the same
  script under it — that result decides **Tier 2**. Don't attempt to work
  around a block; note the exact message and move down the ladder.
- `outlook_classic_com` FAIL just means calendar sync (§7c) falls back to
  focus factors — it doesn't block any tier.
- `task_scheduler_query` PASS is necessary but not sufficient for scheduled
  briefings; actually creating a user task is tested later, in Phase 4, not
  in this read-only spike.
- `pip` FAIL under embeddable Python is normal and fixable (get-pip.py).

## Tier 3 — browser probe

1. Double-click `tier3_check.html` (opens in Edge).
2. **Reload the page once**, then click "Copy results to clipboard".

Interpreting it:

- **WebAssembly, IndexedDB, Web Worker PASS** → Tier 3 is viable.
- `indexeddb_persistence` needs that one reload to show PASS. If it still
  fails after reload, the browser wipes site data on exit (some gov images
  do) — Tier 3 then needs the export-file habit every session, worth knowing.
- `fetch_local_sibling` FAIL is **expected** when opened from a folder
  (file://): it just confirms the real Tier 3 build must be one HTML file
  with all assets inlined, which is the plan anyway.
- `file_system_access_api` absent on file:// is likewise expected; explicit
  export/import buttons are the fallback.

## What to send back

The `JIMOTHY-SPIKE-RESULT` block (or `spike_result.txt`) and the
`JIMOTHY-TIER3-RESULT` block. Those two decide the build target for Phase 1.
