# v3.1.0 Platform Slimming & Capability Re-homing — Architecture Plan

> Owner: `project-architect` (ADR-002). Implementation branch:
> `refactor/v3.1.0-platform-slim` in worktree `.claude/worktrees/v310-slim`.
> Baseline for behaviour verification: the v3.0.0 outputs in
> `tmp/v300_compare/candidate_300/` (7 vehicles, already proven ≡ 2.2.8).

## 0. Goals & user decisions (2026-07-17)

1. `src/jolt_toolkit` contains ONLY the report-generation surface the SRF platform needs
   (plus the sanctioned shared `analysis/` layer — **user decision: keep**).
2. AUX capabilities move to skill/agent-owned code with the SAME functionality:
   dashboards, finetune, validation figures + inspect HTML rendering, params
   identification.
3. NEW capability: not-yet-onboarded registrations get a **general fallback pipeline** —
   **BOTH EV and diesel guaranteed to produce an xlsx**; the platform must never surface
   an 'onboard first' prompt (user decision 2026-07-17, final). Ultimate fallback: a
   valid, possibly sparse report (rows only for what the data supports; worst case a
   structurally complete empty report + warnings in the log, never a crash).
4. `jolt-toolkit-dev` agent's positioning/doc updated to the shrunken scope.
5. Verification: existing-vehicle xlsx output must remain IDENTICAL (golden compare vs
   `candidate_300`); AUX functionality must keep working through its new homes.
6. Version: **3.1.0** (user decision; removals' consumers are all re-homed in-repo in the same change).

## 1. Allocation map (capability → new home)

| Capability | v3.0.0 location (package) | New home & owner | Consumers to rewire |
|---|---|---|---|
| Data-availability dashboard + per-vehicle detail pages + vendored uPlot | `report_generator/data_dashboard.py` (1.9k), `data_dashboard_detail.py` (2.1k), `assets/uplot/` | `.claude/skills/generate-data-dashboard/code/` (skill becomes self-contained code owner, like generate-pdf-report) | `data-collection-monitor/run_monitor.py:414` (`python -m jolt_toolkit...data_dashboard` → skill CLI); generate-data-dashboard SKILL.md/README |
| Finetune library (Merge/Split/Delete ops, xlsx reconstruct/rewrite) | `report_generator/finetune.py` (1.8k) | `.claude/skills/report-finetuner/code/finetune.py` | `report-finetuner` agent doc (import path); its figure/HTML regeneration functions now delegate to the report-visuals CLI (see below) instead of importing plotting code |
| Validation figures (EV painter + overlay boxes export), diesel figure painter, overlay-regenerate (ValidationGenerator + diesel), inspect-HTML viewer + template, rerender CLI, refresh script | `segmentation/validation_figure.py` (1.4k), plotting part of `diesel_pipeline.py`, `validation_generator.py`, `html_viewer.py` + `assets/inspect_viewer_template.html`, `rerender_inspect.py`, `scripts/refresh_inspect_html.py` | **NEW skill `.claude/skills/report-visuals/`** — self-contained rendering code + a single CLI (`code/render_visuals.py`): paint/repaint validation figures (EV+diesel, one-per-day overlay path) and (re)write inspect HTML for a vehicle dir / period / finetuned set | `generate-excel-report` skill (debug workflow chains this CLI after generation); `report-finetuner` (post-op repaint via CLI `--finetuned`); `param-tuner` (consumes figures, read-only — doc pointer only); `vehicle-onboarding` (initial figures step) |
| C_rr/C_dA parameter identification | `vehicle_params_identificator/` (11 files) | `research_projects/parameter_identify/code/` (the `param-identifier` agent's workspace; runnable standalone) | `param-identifier` agent doc; pyproject `[params]` extra (scikit-learn) removed |
| Cached-recompute migration tool | `scripts/recompute_from_cache.py` | `.claude/skills/generate-excel-report/tools/recompute_from_cache.py` | none (manual tool); imports package publics |
| STAYS in package | `_generator.py`, `segmentation/` (minus validation_figure), `columns/charts/row_builder/excel_writer`, `capacity.py`, `capacity_backfill.py`, `diesel_pipeline.py` (minus plotting), patchers + `xlsx_patch_common.py` + `weather_fetcher/` (openweather + fine_grained) + `weather_patch(er)`, `operators.py`, `pedal_histogram.py`, `data_class/ data_fetcher/ paths/ cli`, `configs/`, `analysis/` | — | — |

**Coupling rule reaffirmed**: skills reuse each other ONLY via CLI contracts (precedent:
data-collection-monitor drives the report CLI); importable-Python sharing belongs to the
package (`analysis/`) — no cross-skill imports.

## 2. Key design seams

### 2a. Figure painting leaves the package without double computation
`run_segment_detection` currently paints inline when given an out_dir. Change (package):
replace the tail plotting block with an optional **`figure_hook` callable** parameter —
when provided, it is invoked with EXACTLY the arguments `plot_leg_validation` receives
today (augmented df incl. mass_cluster, both segment lists, resolved params, out path,
export flag). Package no longer imports matplotlib; the report-visuals skill passes its
own painter as the hook (identical figures, single pass). `_HAS_MPL` gating and
`plot_leg_validation`移出后, the facade `segment_algorithms.py` drops those names
(breaking → part of 4.0.0; all consumers re-homed in the same change).

### 2b. `--debug` semantics in the package
In-package `--debug`/`--raw-only` both persist raw CSVs (+ raw logger/charger as today);
NO figures, NO inspect HTML from the package. The `generate-excel-report` skill's debug
workflow becomes: generate (raw persisted) → invoke `/report-visuals` CLI to paint
figures + inspect HTML (the overlay-regenerate path is ALREADY the canonical figure
producer since v2.2.6, so end artefacts are unchanged). CLI help text updated; clear
log line points to the skill.

### 2c. General fallback pipeline for un-onboarded registrations (EV guaranteed)
New module `report_generator/general_pipeline.py` (name final at implementation):
- Trigger: reg not in `VEHICLE_CONFIG` → build a **runtime vehicle config** (never
  written to vehicles.json):
  1. SRF lookup: resolve `srf_reg` (try verbatim, then canonical `XX## XXX` spacing);
     pull make/model/`fuel_capacity` (→ srf_capacity_kwh) and fuel type when exposed.
  2. Column auto-detection from the first fetched leg's raw telematics: match against
     the candidate sets used across the fleet (soc, wheel_based_speed|speed, ac/dc/
     total/moving/recup counters, mass, gnss_altitude…). Missing column ⇒ that feature
     degrades (no mass split/merge without mass col; soc_estimate energy without
     counters; no elevation correction without altitude).
  3. Pipeline params: `default_soc` (exists in pipelines.json) as the base; branch =
     soc if SOC column present else speed.
- Capacity: `srf_capacity_kwh` (or None → soc_estimate rows carry NaN energy rather
  than failing); **no vehicles.json write-back for un-onboarded regs** (no invented
  entries; log the computed capacity instead).
- Diesel: if SRF metadata identifies diesel → the diesel pipeline with the standard
  SRFLOGGER_V1 channel set + DEFAULT_DIESEL_LHV; each missing channel degrades that
  metric to NaN (fuel columns NaN without LFC; distance from the best available source),
  never an error. If fuel type is unknown, run the EV path (its degradation ladder
  handles counter-less vehicles).
- GUARANTEE (both fuel types): the minimum viable report is whatever legs exist +
  (SOC or speed or logger channels); everything else degrades gracefully; zero usable
  data ⇒ a structurally complete empty report with header + log warnings — the platform
  never sees an 'onboard first' error. Add contract tests with synthetic minimal configs.
- Log banner marks the run as "general fallback pipeline (vehicle not onboarded)".
- Boundary with `/vehicle-onboarding` documented both sides: fallback = instant, generic
  quality; onboarding = tuned pipeline + validation + registration in the fleet.

### 2d. No paid weather-API calls by default (platform contract)
User requirement (2026-07-17): platform-side report generation must NOT call the paid
OpenWeather API by default. Current state already complies — `generate_report()` fills
weather columns from the SRF Logger weather channel (LoggerPatcher, no OpenWeather);
OpenWeather is only reached via the separate, explicit post-step
(`python -m jolt_toolkit.report_generator.weather_patch`). v3.1.0 hardens this into a
contract: (a) the general fallback pipeline likewise makes zero OpenWeather calls;
(b) `cli.py` never invokes weather patching; (c) DEPLOYMENT.md documents "default
generation = zero paid API calls; the OpenWeather backfill post-step is optional,
quota-consuming, and excluded from the platform default workflow"; (d) the post-step
without OPENWEATHER_API_KEYS fails fast with a clear message (never silently burns a
default key).

## 3. Phases (each = verified commit(s) on the branch)

- **P1 — Skill-side scaffolding (general-purpose agents under this plan)**: create
  `report-visuals` skill (SKILL.md router + manifest + README + moved code + CLI);
  move dashboard code into `generate-data-dashboard/code/` + runner; move finetune lib
  into `report-finetuner/code/` + rewire its regeneration to the visuals CLI; move
  params package to `research_projects/parameter_identify/code/`; move recompute tool.
  During P1 the package still carries the originals (copy-first) — nothing breaks.
- **P2 — Package slimming (jolt-toolkit-dev)**: delete moved modules from the package;
  `figure_hook` seam in detection; debug semantics; facades updated (dropped names
  documented as v4 breaking list); dependency audit (matplotlib expected to drop from
  core deps — verify scipy/others by grep); `tests/` updated; version → 3.1.0.
- **P3 — General pipeline (jolt-toolkit-dev)**: as §2c + tests.
- **P4 — Governance sync (project-architect)**: jolt-toolkit-dev agent doc (scope
  shrink), report-finetuner / param-identifier / generate-data-dashboard /
  data-collection-monitor / generate-excel-report / vehicle-onboarding doc + manifest
  version bumps; root README two index tables; package README + DEPLOYMENT.md
  (un-onboarded section); registry check green.
- **P5 — Verification**: (i) golden compare — regenerate the 7-vehicle set with v3.1.0 code
  from the same vehicles.json snapshot → cell-by-cell vs `candidate_300`, must be 0
  diffs; (ii) un-onboarded EV test — JOLT_CONFIG_DIR pointing at a pruned configs copy
  (target reg removed) → generation must SUCCEED via the fallback; (iii) AUX smokes —
  visuals CLI repaints a YK73WFN day (figures + inspect HTML produced; HTML
  byte-compare vs pre-move where inputs identical), dashboard regenerated via skill
  runner, finetune lib import + a scratch-copy op + CLI-delegated repaint;
  (iv) contract tests + `check_skill_registry.py` + independence check all green.

## 4. Out of scope
- English translation of the moved AUX code (stays pre-v3 style inside skills; a later
  project can tidy).
- Any change to numeric processing for onboarded vehicles.
- The dist-repo sync for James (separate pending item; v4 makes the curation trivial —
  the whole package is now the platform surface).

## 5. Execution status (updated 2026-07-18)

| Phase | Status | Commits (branch `refactor/v3.1.0-platform-slim`) |
|-------|--------|--------------------------------------------------|
| P1 — skill-side scaffolding (copy-first) | **Done** | `40bc628` (report-visuals skill), `d3cf0b9` (dashboard → skill), `d43384f` (finetune → skill), `c2d5577` (params → research workspace), `27bbf44` (recompute tool → skill) |
| P2 — package slimming | **Done** (23 files / ~12.3k lines removed; figure_hook seam; matplotlib out of deps; 230 tests passed; EV+diesel fast smokes = 0 diffs) | `ee212e4` |
| P2b — skill-side rewiring (figure_hook adoption + CLI-delegated finetuned rendering) | **Done** (repaint byte-identical to the P1 smoke; finetuned wrapper smoke green) | `4416361` |
| P3 — general fallback pipeline | **Done** (+19 tests → 249 passed; un-onboarded EV + diesel smokes green, onboarded regression 0 diffs, nonexistent reg → exit 3) | `cb3834e` |
| P4 — governance sync | **Done** (jolt-toolkit-dev scope shrink; root README rows; package README v3.1.0 migration notes + DEPLOYMENT contracts; vehicle-onboarding boundary note 2.0.2; capacity.py docstring path; straggler sweep; registry + independence checks green) | P4 commit (this change) |
| P5 — verification | **DONE (2026-07-18)** — 7-vehicle golden compare v3.1.0 vs v3.0.0 `candidate_300`: **7/7 IDENTICAL, 0 differing cells** (`tmp/v310_compare/comparison_report_310_vs_300.md`); AUX smokes covered in P1/P2b (repaint PNGs byte-identical, dashboard parity, finetuned repaint); un-onboarded EV/diesel + nonexistent-reg tests in P3; suite 249 passed / 2 skipped | — |

Detailed change log: main repo `tmp/v310_changes_log.md`.
