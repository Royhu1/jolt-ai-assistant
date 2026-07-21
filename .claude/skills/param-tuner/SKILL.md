---
name: param-tuner
description: |
  Segmentation algorithm parameter tuning for the JOLT report generator.
  Use when the user wants to review, diagnose, or optimize trip/charging
  segmentation parameters for a specific vehicle. Triggers on:
  (1) "optimize parameters for <vehicle>", "tune segmentation for <vehicle>"
  (2) "review validation figures for <vehicle>"
  (3) "check if trips are correctly segmented for <vehicle>"
  (4) "/param-tuner <vehicle>"
  Works by reading the Excel report to find days with trip data, then
  systematically reviewing validation figures to diagnose segmentation issues
  and recommending parameter changes.
  Routing boundary: isolated wrongly-segmented days that a GLOBAL parameter
  change cannot fix (without regressing correct days) are NOT tuning work —
  route them to /report-finetuner (per-leg xlsx post-processing) instead.
---

# Segmentation Parameter Tuner — Router

Systematically review validation figures for a vehicle, diagnose segmentation
issues, and adjust algorithm parameters to produce optimal trip/charging boundaries.

This skill is split into two layers (pattern adapted from nature-skills/nature-figure):

- A **static layer** under `static/` holding versioned, reusable content fragments: the
  seven-step tuning workflow, the holistic-optimization discipline, and a per-mode
  quick-start.
- A **dynamic layer** (this file plus `manifest.yaml`) that resolves the tuning mode and
  loads only the fragment needed for the current job. The symptom→parameter tables, the
  parameter table, the record formats and the per-vehicle case studies live in on-demand
  `references/`.

Do not tune from memory or from this router alone. Always load the fragments from disk as
described below.

## Routing protocol

Follow these five steps every time the skill is invoked.

### 1. Load the manifest and the core layer

Read [manifest.yaml](manifest.yaml). It declares the `mode` axis, the blocking
vehicle-data gate, and the on-demand reference table.

Also read every file listed under `always_load`:
[static/core/workflow.md](static/core/workflow.md) (the seven-step tuning workflow,
steps 0–6: prior experience → locate data → select review set → review figures →
diagnose → apply and verify → finalize) and
[static/core/principles.md](static/core/principles.md) (the holistic-optimization core
principle in four phases, the evaluations-log key rules, and the guidelines). These apply
to every tuning run.

### 2. Locate the vehicle and its data — a blocking gate

Identify the vehicle registration from user input. The vehicle must be configured in
`src/jolt_toolkit/configs/vehicles.json` / `pipelines.json` and have a report directory
with validation figures under `excel_report_database/{version}/{reg}/` — workflow step 1
cannot proceed otherwise. An unconfigured vehicle is `/vehicle-onboarding` territory
(onboarding itself runs this skill once the first report exists).

### 3. Resolve the mode and load the matching fragment

When starting, present both modes to the user — there is no silent default:

- **`quick`** — stratified sample, one adjustment iteration, spot-check; suitable for
  vehicles with known similar characteristics to a previously tuned vehicle.
  → Read [static/fragments/mode/quick.md](static/fragments/mode/quick.md).
- **`thorough`** — all valid figures, multiple iterations until convergence; suitable for
  first-time optimization or vehicles with unique data characteristics.
  → Read [static/fragments/mode/thorough.md](static/fragments/mode/thorough.md).

Do not load the other mode's fragment.

### 4. Run the tuning loop using the loaded material

Follow `static/core/workflow.md` steps 0–6 in order, applying the mode fragment where the
workflow delegates to it (review-set selection in step 2, re-check scope in step 5.3), and
obey `static/core/principles.md` throughout: holistic optimization over outlier-chasing,
one parameter at a time, record every round in `evaluations/{REG}_review_results.md`, and
`--fast --debug` validation → patcher backfill — never plain `--debug`.

### 5. Reach for references only when needed

Open files under `references/` on demand per the manifest table:
[evaluation-criteria.md](references/evaluation-criteria.md) when assessing a figure's four
panels (discharge trips / mass clustering / charging events: symptom → diagnosis →
parameter), [parameter-reference.md](references/parameter-reference.md) for each
parameter's config location / default / effect,
[record-format.md](references/record-format.md) when writing the evaluations log or the
post-run case study, and the per-vehicle case studies `references/<REG>.md` at step 0 for
prior experience with similar vehicles.

After finalizing, report the parameter changes and the final review summary to the user;
the case study and evaluations log persist for the next session.

## Why this split

- The workflow and the optimization discipline are versioned, always-loaded contracts —
  the rules that must never drift (one parameter at a time, `--fast --debug` → patcher
  backfill, never plain `--debug`) no longer sit buried mid-file in a monolithic SKILL.md.
- Each invocation stays cheap: only the chosen mode's quick-start enters context, and the
  symptom tables / parameter table / record templates load only when a step needs them.
- The accumulated experience keeps growing exactly where it always did: per-vehicle case
  studies in `references/<REG>.md`, per-figure review logs in `evaluations/` — the
  restructure moved none of them.
- The router itself is short on purpose. Update fragments and references, not this file,
  when adding scope.
- This structure mirrors nature-figure's static/dynamic split, adapted to the JOLT skill
  anatomy v2 (`README.md` + `manifest.yaml` + `references/` + `evaluations/` per
  `.claude/rules/skill-design.md`); the human-facing map + pipeline live in `README.md`.
