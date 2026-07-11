---
name: data-collection-monitor
description: |
  Periodic (designed for /loop, default weekly) fleet data-collection check. For every
  watched vehicle it EXTENDS the canonical excel_report_database/<version>/ forward in
  time with the latest jolt_toolkit — generating reports ONLY for periods after the
  latest existing coverage and SKIPPING any period whose .xlsx already exists, so it
  never overwrites an existing report or its raw data (append-only). It then refreshes
  the data-availability dashboard and emits a fixed-template PDF "data collection digest"
  (a single fleet data-collection overview table: operator, energy type, telematics /
  SRF-logger leg + charger-transaction counts + last-seen times, trips, charges, active
  days, distance) for the
  most-recent window into data_collection_reports/, and updates MONITOR_STATUS.md (which
  shows the active loop cadence / last run / next due).
  Triggers on:
  (1) "/loop weekly /data-collection-monitor" (the intended use — a recurring data-intake check)
  (2) "check whether any new data has recently been collected for the watched vehicles / refresh the dashboard and produce a data-collection report"
  (3) "run the fleet data-collection monitor / generate the data collection digest"
  (4) "/data-collection-monitor [--cadence weekly]"
  When run under /loop with no cadence recorded yet, ASK the user for the cadence on the
  FIRST run only (see §2). Routes report-generator CODE changes to the jolt-toolkit-dev
  agent — this skill only orchestrates existing CLIs.
---

# Data Collection Monitor — Router

This skill is split into two layers (pattern adapted from nature-skills/nature-figure):

- A **static layer** under `static/` holding versioned, reusable content fragments: the
  behaviour-conventions + discipline contract, and a per-run-mode quick-start.
- A **dynamic layer** (this file plus `manifest.yaml`) that resolves the run mode and
  loads only the fragment needed for the current job. The `/loop` cadence rules and the
  digest artefact spec live in on-demand `references/`.

Do not run the monitor from memory or from this router alone. Always load the fragments
from disk as described below. **The behaviour is contract-fixed**: the report database is
APPEND-ONLY — never overwrite an existing report or its raw data — this refactor changes
how the skill is organised, never what a monitor run does.

## Routing protocol

Follow these five steps every time the skill is invoked.

### 1. Load the manifest and the core layer

Read [manifest.yaml](manifest.yaml). It declares the `run-mode` axis, the blocking
first-run cadence gate, and the on-demand reference table.

Also read the file listed under `always_load`:
[static/core/conventions.md](static/core/conventions.md) — the finalised behaviour
conventions (append-only, dynamic version, no validation figures, failure isolation,
charger backfill sweep) plus the discipline rules (no `src/jolt_toolkit/` edits, no
version bump, changelog record). These apply to every monitor run.

### 2. Resolve the cadence — a blocking gate on the first /loop run

Read `data_collection_reports/MONITOR_STATUS.md`. If it does not exist (= the first run
of this loop), ASK the user for the trigger cadence (daily / weekly (default) /
fortnightly / monthly) — on the FIRST run only. On every subsequent trigger, read the
cadence back from `MONITOR_STATUS.md` and reuse it — do not ask again. Full rules
(cadence display, lookback window, the harness-cron note):
[references/loop-usage.md](references/loop-usage.md) — the "§2" cited in the
frontmatter above.

### 3. Resolve the run mode and load the matching fragment

- **`full-check` (DEFAULT)** — the standard loop iteration: SRF check → append-only
  extend the report database → refresh the dashboard → digest PDF + `MONITOR_STATUS.md`.
  → Read [static/fragments/run-mode/full-check.md](static/fragments/run-mode/full-check.md).
- **`template-only`** — ONLY when the user explicitly asks to test the digest PDF /
  template on existing data (no SRF, no dashboard refresh).
  → Read [static/fragments/run-mode/template-only.md](static/fragments/run-mode/template-only.md).

Do not load the other mode's fragment.

### 4. Run using the loaded material

Apply in this order: the conventions contract (append-only above all) → the mode
fragment's command block (repo root, `jolt` conda env). This skill only orchestrates the
existing CLIs (`run_monitor.py` → `jolt_toolkit`); never re-implement them, and route any
report-generator code change to the jolt-toolkit-dev agent.

### 5. Reach for references only when needed

Open files under `references/` on demand per the manifest table:
[loop-usage.md](references/loop-usage.md) for the /loop wiring, cadence state and
`MONITOR_STATUS.md` layout; [digest-spec.md](references/digest-spec.md) for the digest
artefact paths, the 14-column table spec and its colour semantics.

After the run, confirm the artefacts landed in `data_collection_reports/`, echo the
cadence and next-due at the end of the reply (per the loop-usage rules), and log
reusable lessons in `evaluations/` per its README.

## Why this split

- The append-only discipline is THE contract of this skill; it is versioned, always
  loaded, and no longer buried mid-file in a monolithic SKILL.md.
- Each invocation stays cheap: only the selected run mode's quick-start enters context,
  and the /loop-cadence and digest-spec depth loads only when a step needs it.
- The router itself is short on purpose. Update fragments and references, not this file,
  when adding scope.
- This structure mirrors nature-figure's static/dynamic split, adapted to the JOLT skill
  anatomy v2 (`README.md` + `manifest.yaml` + `references/` + `evaluations/` per
  `.claude/rules/skill-design.md`); the human-facing map + pipeline live in `README.md`.
