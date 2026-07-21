---
name: generate-data-dashboard
description: |
  Generate (or refresh) the JOLT data-availability dashboard — a single
  self-contained offline data_dashboard.html for a report-database version,
  by running the skill-owned dashboard runner (code/generate_dashboard.py).
  Shows, per vehicle, which days have telematics / logger / charger data
  (Events vs Raw-data bases), plus vehicle stats and operator info.
  Output: excel_report_database/X.Y.Z/dashboard/data_dashboard.html.
  Triggers on:
  (1) "generate a data availability dashboard from the data of version X.Y.Z"
  (2) "generate / refresh the data availability dashboard (for version X.Y.Z)"
  (3) "/generate-data-dashboard X.Y.Z"
  (4) regenerate the dashboard after new Excel reports / raw data were added
  (5) dashboard CODE changes (layout, detection rules, new panels) — since
  v3.1.0 this skill is the self-contained OWNER of the dashboard code
  (code/data_dashboard.py + code/data_dashboard_detail.py + vendored uPlot);
  route to jolt-toolkit-dev only when a NEW xlsx field / package-shared name
  is needed.
  The weekly data-collection-monitor refreshes this dashboard automatically
  (it drives this skill's runner CLI) — invoke this skill directly only for
  one-off or historical-version refreshes.
---

# Generate Data-Availability Dashboard — Router

A self-contained dashboard generator split into two layers (anatomy v2, pattern
adapted from nature-skills/nature-figure), sized per the proportionality rule in
`.claude/rules/skill-design.md`:

- A **static layer**: `static/core/conventions.md` — the always-loaded conventions
  (inputs to confirm, preconditions, no-version-bump / never-commit rules).
- A **dynamic layer** (this file plus `manifest.yaml`) that loads the run-and-verify
  reference only when actually executing the CLI.

There is a single execution path — run the skill-owned runner
`code/generate_dashboard.py` — so there are no axes, gates or fragments. Since
v3.1.0 all dashboard logic lives in THIS skill's `code/` (`data_dashboard.py`,
`data_dashboard_detail.py`, vendored `assets/uplot/`) — behaviour/layout/detection
changes are made here; route to `jolt-toolkit-dev` only when a new xlsx field or
package-shared name (`HEADERS`, segmentation constants, config loaders) is needed.

## Routing protocol

Follow these four steps every time the skill is invoked.

### 1. Load the manifest and the core layer

Read [manifest.yaml](manifest.yaml), then every file listed under `always_load`:
[static/core/conventions.md](static/core/conventions.md).

### 2. Resolve version and output path

Per the core conventions ("Inputs to confirm with the user"): the report-database
version (default: the current `jolt_toolkit.__version__` from
`src/jolt_toolkit/__init__.py`) and the output path (default in-place under
`excel_report_database/<version>/dashboard/`); ask only if ambiguous. Check the
preconditions (local files only, Excel-lock caveat, `jolt` env / `PYTHONPATH=src`).

### 3. Run the CLI

Read [references/run-and-verify.md](references/run-and-verify.md) and run the
skill-owned runner exactly as written there (with any `--db-root` / `--out` /
`--details` overrides the user asked for). Include the CLI's per-vehicle summary
table in the reply.

### 4. Verify and report

Apply the "Verify after generating" checklist from the same reference (self-contained
HTML, every vehicle present in the `const DATA` blob, no vehicle skipped), then report
the output path. Never bump the package version or commit the output (see conventions).

The human-facing map + pipeline live in [README.md](README.md). Update the core file
and the reference, not this router, when the workflow changes.
