---
name: generate-data-dashboard
description: |
  Generate (or refresh) the JOLT data-availability dashboard — a single
  self-contained offline data_dashboard.html for a report-database version,
  by running the jolt_toolkit dashboard CLI. Shows, per vehicle, which days
  have telematics / logger / charger data (Events vs Raw-data bases), plus
  vehicle stats and operator info. Output: excel_report_database/X.Y.Z/dashboard/data_dashboard.html.
  Triggers on:
  (1) "generate a data availability dashboard from the data of version X.Y.Z"
  (2) "generate / refresh the data availability dashboard (for version X.Y.Z)"
  (3) "/generate-data-dashboard X.Y.Z"
  (4) regenerate the dashboard after new Excel reports / raw data were added
  Route CODE changes to the dashboard (layout, detection rules, new panels)
  to the jolt-toolkit-dev agent instead — this skill only RUNS the generator.
  The weekly data-collection-monitor refreshes this dashboard automatically as
  part of its run — invoke this skill directly only for one-off or
  historical-version refreshes.
---

# Generate Data-Availability Dashboard — Router

A thin CLI wrapper split into two layers (anatomy v2, pattern adapted from
nature-skills/nature-figure), sized per the proportionality rule in
`.claude/rules/skill-design.md`:

- A **static layer**: `static/core/conventions.md` — the always-loaded conventions
  (inputs to confirm, preconditions, no-version-bump / never-commit rules).
- A **dynamic layer** (this file plus `manifest.yaml`) that loads the run-and-verify
  reference only when actually executing the CLI.

There is a single execution path — run the `jolt_toolkit` dashboard CLI — so there are
no axes, gates or fragments. All dashboard logic lives in
`jolt_toolkit.report_generator.data_dashboard`, owned by the `jolt-toolkit-dev` agent —
route any behaviour/layout/detection change there; this skill only RUNS the generator.

## Routing protocol

Follow these four steps every time the skill is invoked.

### 1. Load the manifest and the core layer

Read [manifest.yaml](manifest.yaml), then every file listed under `always_load`:
[static/core/conventions.md](static/core/conventions.md).

### 2. Resolve version and output path

Per the core conventions ("Inputs to confirm with the user"): the report-database
version (default: the current `jolt_toolkit` version in `pyproject.toml` — 2.2.8 at
the time of writing) and the output path (default in-place under
`excel_report_database/<version>/dashboard/`); ask only if ambiguous. Check the
preconditions (local files only, Excel-lock caveat, `jolt` env / `PYTHONPATH=src`).

### 3. Run the CLI

Read [references/run-and-verify.md](references/run-and-verify.md) and run the command
exactly as written there (with any `--db-root` / `--out` / `--details` overrides the
user asked for). Include the CLI's per-vehicle summary table in the reply.

### 4. Verify and report

Apply the "Verify after generating" checklist from the same reference (self-contained
HTML, every vehicle present in the `const DATA` blob, no vehicle skipped), then report
the output path. Never bump the package version or commit the output (see conventions).

The human-facing map + pipeline live in [README.md](README.md). Update the core file
and the reference, not this router, when the workflow changes.
