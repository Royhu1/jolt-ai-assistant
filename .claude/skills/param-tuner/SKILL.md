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
---

# Segmentation Parameter Tuner

Systematically review validation figures for a vehicle, diagnose segmentation
issues, and adjust algorithm parameters to produce optimal trip/charging boundaries.

## Tuning modes

When starting, present both modes to the user:

### Quick mode

- Stratified sampling, review **max(30% of total trips, 30)** figures (whichever is larger)
- One iteration of parameter adjustment (propose → apply → spot-check)
- Spot-check: re-examine ~10 key figures (mix of previously problematic + correct)
- Suitable for vehicles with known similar characteristics to a previously tuned vehicle

### Thorough mode

- Review **all** valid validation figures (for every valid trip)
- Full day-by-day diagnosis table
- Multiple iterations until convergence
- Re-check **every** flagged AND previously correct day after each adjustment
- Suitable for first-time optimization or vehicles with unique data characteristics

---

## Directory structure

```
.claude/skills/param-tuner/
├── SKILL.md
├── references/          # optimisation case studies (per vehicle, written when done)
│   └── {REG}.md
└── evaluations/         # validation-figure review log (per vehicle, updated each round)
    └── {REG}_review_results.md
```

- `references/` — post-optimisation lessons learned, for reference on future similar vehicles
- `evaluations/` — per-figure assessment log of each review, updated across iterations,
  recording which figures still have issues

---

## Workflow

### 0. Check prior experience

Before starting:
1. Read `references/` for case studies of previously tuned vehicles.
   If the target vehicle shares characteristics (same make, similar operation pattern,
   similar data availability), use the prior case study to inform initial expectations
   and parameter starting points.
2. Read `evaluations/{REG}_review_results.md` if it exists — it contains prior review
   results and known remaining issues from previous optimization sessions.

### 1. Locate data

- Identify the vehicle registration from user input
- Read `src/jolt_toolkit/configs/vehicles.json` to get the vehicle's pipeline and parameters
- Read `src/jolt_toolkit/configs/pipelines.json` to get the current pipeline parameters
- Find the report directory: `excel_report_database/{version}/{reg}/`
- Read the Excel report to extract dates that have discharge trip data
- Count total validation figures available

### 2. Select review set

#### Thorough mode
Review all validation figures.

#### Quick mode — stratified sampling (≥ max(30% of trips, 30) figures)

1. **Count total validation figures** and compute target: `N = max(total * 0.3, 30)`

2. **Classify all figures** by SOC activity pattern:
   - **Active days**: days with discharge segments (SOC drops during driving)
   - **Charge-only days**: only charging events, no discharge
   - **Idle days**: no activity (flat SOC, no speed)

3. **Mandatory inclusions** (always review these):
   - ALL active days (these are the primary optimization targets)
   - ALL charge-only days (verify charge segmentation)

4. **Random supplement**: if mandatory set < N, randomly sample idle days
   until reaching N figures total. Idle days verify there are no false positives.

5. **Priority ordering**: review active days first, sorted by SOC range
   (days with largest SOC swing first — most likely to reveal segmentation issues).

### 3. Review validation figures

For each figure in the review set, evaluate across all four panels using the
criteria below. **Record results in `evaluations/{REG}_review_results.md`**
(create if not exists, append new round if exists). See [Evaluation record format](#evaluation-record-format) below.

**Efficiency tips**:
- After reviewing ~10 active days, check if a dominant pattern has emerged.
  If >70% of issues share the same root cause, note this early hypothesis
  but continue reviewing to confirm.
- For idle days, batch-review quickly: confirm 0 segments detected, flag
  any false positives immediately.

### 4. Diagnose and recommend

After reviewing, summarize findings and propose parameter changes.
Present changes as a table: parameter, current value, proposed value, reason.

### 5. Apply and verify

1. Edit the config file(s)
2. Reinstall: `pip install -e . -q`
3. **Fast validation** — first use `--fast --debug` to quickly check segmentation quality
   (telematics data only):
   ```bash
   python .claude/skills/generate-excel-report/batch_generate.py --debug --fast --veh {reg}
   ```
4. Re-check validation figures:
   - **Quick mode**: spot-check ~10 key figures (5 previously problematic + 5 previously correct)
   - **Thorough mode**: re-check every previously flagged AND previously correct day
5. **Update `evaluations/{REG}_review_results.md`**: add a new round section recording
   each re-checked figure's status (resolved / still problematic / newly broken).
   Update the summary table at the top of the file.
6. **Backfill via patchers** — once segmentation is verified, backfill Logger/Charger data
   with the patchers (avoids `--fast` overwriting existing data):
   ```python
   from jolt_toolkit.report_generator.charger_patcher import ChargerPatcher
   from jolt_toolkit.report_generator.logger_patcher import LoggerPatcher
   ChargerPatcher().patch_folder("excel_report_database/{version}/{reg}/")
   LoggerPatcher().patch_folder("excel_report_database/{version}/{reg}/")
   ```
   > **Important**: do NOT regenerate with `batch_generate.py --debug` (without `--fast`)
   > directly, because that overwrites the Logger/Charger data already backfilled by the
   > patchers. Correct flow: `--fast --debug` to validate → patcher backfill.

### 6. Finalize

1. **Create or update case study**: save optimization summary to
   `references/{reg}.md` in this skill's directory (see structure below)
2. **Ensure `evaluations/{REG}_review_results.md` is up to date**: the summary table
   should reflect the final state — which figures are OK, which still have issues.
   This file persists across sessions for future re-optimization.
3. Update `changelogs/changelog_YYYYMMDD_YYYYMMDD.md` (the current week's file)
4. Commit changes

---

## Evaluation criteria

### A. Discharge trips (Panel 1 + Panel 3)

| Symptom | Diagnosis | Parameter to adjust |
|---------|-----------|-------------------|
| Continuous driving split into multiple trips (short stops like traffic lights cause splits) | `min_stop_duration_min` too small | Increase `min_stop_duration_min` in `pipelines.json` -> speed_params |
| Distinct trips with long stop between them merged into one | `min_stop_duration_min` too large | Decrease `min_stop_duration_min` |
| Very short noise trips (seconds of sensor jitter) appear | `min_trip_duration_min` too small | Increase `min_trip_duration_min` |
| Valid short delivery trips missing from report | `min_trip_duration_min` too large | Decrease `min_trip_duration_min` |
| Trip shows SOC rising (includes charging period) | Trip boundary incorrect | Check speed data quality; review `speed_threshold_kmh` |
| Effective Capacity (C) far from nominal (>50% deviation) | Energy/SOC filter too loose | Adjust `cap_lo`/`cap_hi` via `nominal_kwh` |
| Energy anchors (triangles) missing on Panel 3 | Split by mass cleared anchors | Verify `_recompute_anchors` runs after split/merge |
| EP value unreasonably high or low | Odometer or energy data issue | Check raw data quality for that leg |

### B. Mass clustering (Panel 4)

| Symptom | Diagnosis | Parameter to adjust |
|---------|-----------|-------------------|
| Clearly different load levels (e.g. 20t vs 28t) shown as same cluster | Gap too large | Decrease `min_cluster_gap_kg` in `vehicles.json` |
| Normal sensor noise (~500kg) causes unnecessary cluster splits and trip splits | Gap too small | Increase `min_cluster_gap_kg` |
| Mass annotation shows unreasonable values (e.g. 0 or >50t) | Sensor outlier | Check raw mass data; may need outlier filtering |

### C. Charging events (Panel 1 + Panel 2)

| Symptom | Diagnosis | Parameter to adjust |
|---------|-----------|-------------------|
| Charge segment includes driving period (speed > 0) | `plateau_window_min` too large | Decrease `plateau_window_min` in charge_params |
| Tiny charge events (dSOC 1-2%) cluttering report | `min_soc_rise` too small | Increase `min_soc_rise` in charge_params |
| Valid charge event missing | `min_soc_rise` or `min_energy_kwh` too large | Decrease thresholds |
| AC+DC delta and Charger Meter mismatch | Charger matching or time offset issue | Check charger_transactions data |

---

## Parameter reference

| Parameter | Config location | Default | Effect |
|-----------|----------------|---------|--------|
| `min_stop_duration_min` | pipelines.json -> speed_params | 5.0 | Zero-speed duration (min) to end a trip |
| `min_trip_duration_min` | pipelines.json -> speed_params | 2.0 | Minimum trip duration (min); shorter trips discarded |
| `min_soc_drop` | pipelines.json -> speed_params | 1.0 | Minimum SOC decrease (%) for a valid trip |
| `min_energy_kwh` | pipelines.json -> speed_params | 1.0 | Minimum energy consumption (kWh) for a valid trip |
| `speed_threshold_kmh` | pipelines.json -> speed_params | 1.0 | Speed above this = moving (km/h) |
| `min_cluster_gap_kg` | vehicles.json -> vehicle config | 2000.0 | Minimum mass difference (kg) between clusters |
| `plateau_window_min` | pipelines.json -> charge_params | 60 | SOC plateau window for charge detection (min) |
| `min_soc_rise` | pipelines.json -> charge_params | 5.0 | Minimum SOC rise (%) for a valid charge event |

---

## Evaluation record format

`evaluations/{REG}_review_results.md` is the persistent review log for a vehicle.
It tracks every figure's status across multiple optimization rounds.

### File structure

```markdown
# {REG} — Validation Figure Review Results

> Pipeline: {pipeline_name} | Last reviewed: {date}

## Summary

| Status | Count | Percentage |
|--------|-------|------------|
| OK | — | — |
| Issue | — | — |
| Not reviewed | — | — |
| **Total** | — | — |

### Known remaining issues

- {brief list of unresolved problems, grouped by root cause}

---

## Round 1 — Initial review ({date})

Parameters: {current parameter snapshot}

### Per-figure results

| Figure | Type | Status | Issue | Root cause |
|--------|------|--------|-------|------------|
| validation_{REG}_2025-06-01_0000.png | Active | OK | — | — |
| validation_{REG}_2025-06-02_0000.png | Active | Issue | Over-segmentation: 1 trip split into 3 | min_stop_duration_min too small |
| ... | ... | ... | ... | ... |

### Round 1 summary

- Reviewed: N figures
- OK: X, Issue: Y
- Dominant pattern: {description}
- Proposed changes: {brief}

---

## Round 2 — After parameter adjustment ({date})

Parameters changed: {what changed}

### Re-checked figures

| Figure | Previous | Current | Notes |
|--------|----------|---------|-------|
| validation_{REG}_2025-06-02_0000.png | Issue | **Resolved** | Now correctly 1 trip |
| validation_{REG}_2025-06-05_0000.png | OK | OK | No regression |
| validation_{REG}_2025-06-08_0000.png | OK | **New issue** | ... |
| ... | ... | ... | ... |

### Round 2 summary

- Resolved: X issues
- New issues: Y
- Still problematic: Z
```

### Key rules

1. **Create on first review**: create the file during Step 3 of the first round
2. **Append new rounds**: each subsequent review (Step 5) adds a new `## Round N` section
3. **Always update the Summary table**: after each round, recalculate the top-level summary
   to reflect current state across all figures
4. **Update "Known remaining issues"**: after each round, list issues that persist
5. **Status values**: `OK`, `Issue`, `Resolved`, `New issue`, `Not reviewed`
6. **Type values**: `Active` (has discharge trips), `Charge-only`, `Idle`
7. **Keep it concise**: one row per figure, issue description in ≤15 words

---

## Case study reference files

After each optimization, save a summary to `references/{reg}.md` containing:

1. **Vehicle characteristics**: make/model, capacity, operation pattern, data availability
2. **Root causes found**: what was wrong and why
3. **Parameter changes**: before/after table with reasoning
4. **Results**: improvement summary
5. **Lessons learned**: generalizable insights for similar vehicles

Read relevant case studies at the start of each new optimization to leverage
prior experience. For example, if tuning a new Mercedes vehicle, read `references/YN25RSY.md`
first to understand Mercedes-specific data quirks.

---

## Core principle: holistic optimization

Parameter tuning must optimize **global** segmentation quality, not fix individual outliers at the
expense of overall accuracy. Follow this process strictly:

### Phase 1 — Audit (review set depends on mode)

1. Review validation figures per the selected mode's sampling strategy.
2. **Create `evaluations/{REG}_review_results.md`** (or append Round N if exists).
   Record per-figure results: figure name, type, status, issue description, root cause.
3. After reviewing, **summarize recurring patterns** — group issues by root cause rather
   than treating each individually. Update the Summary table and Known remaining issues.

### Phase 2 — Propose changes

4. Identify the **minimum set of parameter changes** that addresses the most common issues.
5. Present the proposal as a table (parameter, current, proposed, expected impact).
6. Explicitly note any trade-offs: "increasing X will fix A but may worsen B".

### Phase 3 — Apply and validate

7. Apply changes, reinstall (`pip install -e . -q`).
8. **Fast validation**: `python .claude/skills/generate-excel-report/batch_generate.py --debug --fast --veh {reg}` — quickly check segmentation using telematics data only.
9. Re-check validation figures per mode:
   - **Thorough**: every previously flagged + previously correct day
   - **Quick**: ~10 key figures (5 problematic + 5 correct)
10. **Append new Round to `evaluations/{REG}_review_results.md`**: record each re-checked
    figure's updated status (Resolved / still Issue / New issue). Update the Summary table.
11. **Backfill via patchers**: once segmentation is confirmed, backfill Logger/Charger data with `ChargerPatcher` + `LoggerPatcher`.

### Phase 4 — Finalize

10. If satisfactory, update documentation:
    - `evaluations/{REG}_review_results.md` — ensure Summary table reflects final state
    - `references/{reg}.md` — save case study for future reference
    - `changelogs/changelog_YYYYMMDD_YYYYMMDD.md` — record optimisation results (the current week's file)
11. Commit changes and present results for user review.

---

## Guidelines

- Adjust one parameter at a time; verify effect before changing another
- Review multiple days (not just one) to avoid overfitting to a single day
- Different vehicles may need different parameters due to different operation patterns
- Each vehicle has its own pipeline in pipelines.json; changes to one vehicle's pipeline do not affect others
- After parameter changes, always regenerate with `--debug --fast` to get validation figures
- Once segmentation is confirmed, backfill Logger/Charger data with `ChargerPatcher` + `LoggerPatcher`
- **Never** regenerate with `--debug` (without `--fast`) directly — that overwrites the data already backfilled by the patchers
- Check `references/` for prior experience with similar vehicles before starting
