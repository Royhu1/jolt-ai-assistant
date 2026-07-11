---
name: generate-excel-report
description: |
  Generate a formatted JOLT Excel report (.xlsx) for a vehicle over a date range,
  by driving the report-generation CLI (generate_report.py / batch_generate.py),
  which calls the jolt_toolkit package. Output goes to excel_report_database/<version>/.
  Triggers on:
  (1) "generate the Excel report for <REG> in <period>"
  (2) "generate the excel report for <REG> in <period>"
  (3) "/generate-excel-report <REG> <period>"
  (4) batch-generate the standard test vehicles
  If the target vehicle is not yet configured, hand off to /vehicle-onboarding first.
---

# Generate Excel Report — Router

Produce JOLT `.xlsx` reports from SRF telematics. This skill is a thin driver over the
report-generation CLI; the actual algorithms live in the `jolt_toolkit` package
(owned by the `jolt-toolkit-dev` agent — route code changes there, not here).

The skill is split into two layers (pattern adapted from nature-skills/nature-figure):

- A **static layer** under `static/` holding the always-loaded run conventions and one
  quick-start fragment per run mode.
- A **dynamic layer** (this file plus `manifest.yaml`) that resolves the run mode and
  loads only the fragment needed for the current job. The mandatory post-generation
  checklist lives in `references/`.

Do not run the CLIs from memory or from this router alone — always load the fragments
from disk as described below. The commands, flags and conventions there are
contract-grade: this refactor changes how the skill is organised, never how reports
are generated.

## Routing protocol

Follow these five steps every time the skill is invoked.

### 1. Load the manifest and the core layer

Read [manifest.yaml](manifest.yaml). It declares the `mode` axis, the blocking gates,
and the on-demand reference table.

Also read every file listed under `always_load`:
[static/core/conventions.md](static/core/conventions.md) — the inputs to confirm with
the user (date-range / meteorological-quarter split rules, `--debug` / `--raw-only` /
`--fast` semantics and warnings), the blocking preconditions, the output artefact
paths, and the weather/elevation cache-first contract. These apply to every run.

### 2. Resolve the gates — blocking

- **Vehicle configured** — the vehicle must exist in `src/jolt_toolkit/configs/`
  (`vehicles.json` / `pipelines.json`); if not, hand off to `/vehicle-onboarding <REG>`
  first.
- **Inputs confirmed** — registration, date range (if the user gives NO range, ASK —
  never silently pick one), optional flags, and the mandatory toolkit-version +
  output-directory confirmation, all per the core conventions.

### 3. Resolve the mode and load the matching fragment

- **`single`** — one vehicle, one explicit period ≤ ~3 months (or a deliberately single
  full-range report) → one `.xlsx` via `generate_report.py`.
  → Read [static/fragments/mode/single.md](static/fragments/mode/single.md).
- **`batch`** — the standard test fleet, multiple vehicles, or a whole-range /
  longer-than-a-quarter span auto-split into meteorological-quarter reports via
  `batch_generate.py`.
  → Read [static/fragments/mode/batch.md](static/fragments/mode/batch.md).

Do not load the other mode's fragment.

### 4. Run the CLI per the loaded fragment

Use the fragment's command lines exactly, applying the core conventions (flag choice,
span splitting, `--out-dir`). Reports land in
`excel_report_database/<version>/<REG>/` per the core "Output artefacts" section.

### 5. Finish the run — ALWAYS open references/after-generating.md

Generation alone does not finish a report. Before declaring any run complete, read
[references/after-generating.md](references/after-generating.md) and follow it:
weather backfill is **required** (the most-forgotten step), and a batch / full-fleet
regen additionally needs the charger backfill sweep + dashboard refresh. Log reusable
lessons in `evaluations/` per its README.

## Why this split

- The date-range/quarter conventions, flag warnings and version/output-dir pre-step are
  always loaded and no longer buried mid-file — the rules that must never drift are the
  ones that always load.
- Each invocation stays cheap: only the selected mode's quick-start enters context, and
  the post-run checklist loads exactly when the run reaches it.
- The router itself is short on purpose. Update fragments and references, not this
  file, when adding scope.
- Structure per JOLT skill anatomy v2 (`.claude/rules/skill-design.md`); the
  human-facing map + pipeline live in [README.md](README.md).
