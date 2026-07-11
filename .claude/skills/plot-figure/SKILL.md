---
name: plot-figure
description: |
  Generate energy-performance analysis figures from JOLT xlsx reports
  (EP vs mass scatter + fit lines, range vs mass, per-operation / per-OEM charts).
  Figures are written under a user-specified --out-dir (named/ + anon/ subdirs);
  the old top-level figures/ directory is deprecated (past outputs moved to archive/).
  Every run PERSISTS a self-contained, editable plotting script in the target
  workspace's code/ (or scripts/) folder and runs it from there — never
  plot-and-delete — so the figure stays reproducible and tweakable later.
  Triggers on:
  (1) "plot EP vs GVM / range vs mass for <vehicle>"
  (2) "generate / update analysis figures from reports"
  (3) "/plot-figure"
  Routing boundary: plot_config.json and anything under src/jolt_toolkit/ belong to
  the jolt-toolkit-dev agent; this skill only reads them.
---

# Plot Figure — Router

This skill is split into two layers (pattern adapted from nature-skills/nature-figure):

- A **static layer** under `static/` holding versioned, reusable content fragments: the
  style contract, the persistence contract, and a per-mode quick-start.
- A **dynamic layer** (this file plus `manifest.yaml`) that resolves the generation mode
  and loads only the fragment needed for the current job. The figure catalogue, data
  contract, fit models and output-format guidance live in on-demand `references/`.

Do not apply the figure logic from memory or from this router alone. Always load the
fragments from disk as described below. **The rendered output is contract-fixed**: figures
must be visually identical to the `templates/` exemplars — this refactor changes how the
skill is organised, never what the figures look like.

## Routing protocol

Follow these five steps every time the skill is invoked.

### 1. Load the manifest and the core layer

Read [manifest.yaml](manifest.yaml). It declares the `mode` axis, the blocking output
gate, and the on-demand reference table.

Also read every file listed under `always_load`:
[static/core/style-contract.md](static/core/style-contract.md) (authoritative style
constants, PNG-300dpi default, source-of-truth rule, `templates/` gallery) and
[static/core/persistence-contract.md](static/core/persistence-contract.md) (the
mandatory persisted-script rules). These apply to every figure job.

### 2. Resolve the output destination — a blocking gate

Every run needs an explicit destination: `--out-dir` for the standard set, or the target
workspace's figures dir for a bespoke figure. The old top-level `figures/<version>/` is
deprecated (moved to `archive/figures/`) — never write there. If the destination workspace
is ambiguous in bespoke mode, ask the user; default to the workspace that owns the
destination `figures/` directory.

### 3. Resolve the mode and load the matching fragment

- **`bespoke` (DEFAULT)** — anything customised: one figure type, a custom grouping or
  exclusion, a paper/analysis-specific panel, a figure that will be tuned later.
  → Read [static/fragments/mode/bespoke.md](static/fragments/mode/bespoke.md).
- **`standard-set`** — only when the user asks for the whole standard batch regenerated
  as-is (drives `data_analysis_workspace/shared/generate_figures.py`).
  → Read [static/fragments/mode/standard-set.md](static/fragments/mode/standard-set.md).

Do not load the other mode's fragment.

### 4. Build the figure using the loaded material

Apply in this order: style contract (constants exactly) → persistence contract (bespoke
mode: persisted `plot_<name>.py`, never plot-and-delete) → the mode fragment's workflow.
Ensure the source reports exist for the chosen version under
`excel_report_database/<version>/` first (regenerate via `generate-excel-report` if
missing; skip `--debug` to preserve patched weather data).

### 5. Reach for references only when needed

Open files under `references/` on demand per the manifest table:
[figure-catalogue.md](references/figure-catalogue.md) for figure families / filenames /
sub-variants, [data-contract.md](references/data-contract.md) for xlsx columns +
`plot_config.json` fields + quality filters, [fit-models.md](references/fit-models.md)
for linear/reciprocal fits and error bands, and
[output-formats.md](references/output-formats.md) when the user asks for non-PNG output
or about LaTeX/PowerPoint embedding.

After generating, QA the output against the `templates/` gallery, then report the
persisted script path (bespoke) or the output directory (standard-set) to the user.
Log reusable lessons in `evaluations/` per its README.

## Why this split

- The style and persistence contracts are versioned, always-loaded, and no longer buried
  in one long SKILL.md — the two rules that must never drift are the two that always load.
- Each invocation stays cheap: only the selected mode's quick-start enters context, and
  the catalogue/data/fit depth loads only when a step needs it.
- The router itself is short on purpose. Update fragments and references, not this file,
  when adding scope.
- This structure mirrors nature-figure's static/dynamic split, adapted to the JOLT skill
  anatomy (`PIPELINE.md` + `references/` + `evaluations/` per `.claude/rules/skill-design.md`).
