# Question categories and how to answer them

### 1. Fleet overview — operators and vehicles

Read `src/jolt_toolkit/configs/plot_config.json` → `company_assignment.simple`
AND `company_assignment.round_robin` for operator → vehicle mapping, and
`src/jolt_toolkit/configs/vehicles.json` for vehicle specs (make, model, capacity).
Note: since v2.2.5 the authoritative per-leg operator is the `Operator` column in
the xlsx reports (SRF-derived); plot_config is the configured assignment only.

Present as a table:

| Operator | Vehicles | Make/Model |
|----------|---------|------------|
| KNOWLES | AV24LXJ, AV24LXK, AV24LXL | ... |
| ...      | ...     | ... |

### 2. Data collection date ranges

Read `.claude/skills/generate-excel-report/test_data_config.json` for the standard date
ranges used in batch report generation. Present per vehicle and grouped by operator.

For each vehicle, show:
- Registration
- Operator
- Earliest start date
- Latest end date
- Number of date range windows defined

### 3. Generated reports status

List directories under `excel_report_database/` using Glob (`excel_report_database/**/`) to identify which
versions and vehicles have reports already generated. Check for `.xlsx` files
under `excel_report_database/<version>/<reg>/`.

Summarise: version → list of vehicles with reports → approximate file count.

### 4. Pipeline and algorithm parameters

Read `src/jolt_toolkit/configs/vehicles.json` to find which pipeline a vehicle
uses, then read `src/jolt_toolkit/configs/pipelines.json` for that pipeline's
parameters.

Present key parameters in a table:

| Parameter | Value | Description |
|-----------|-------|-------------|
| branch | speed / standard | Segmentation algorithm |
| min_stop_duration_min | 5.0 | Zero-speed duration to end trip |
| min_trip_duration_min | 2.0 | Minimum trip duration |
| ... | ... | ... |

### 5. Vehicle specifications

From `plot_config.json` → `vehicle_specs` or `vehicles.json`:
- Make and model
- Effective battery capacity (kWh)
- Tractor weight (kg)
- Nominal GVW

### 6. Simulation experiment results

Read `research_projects/simulation/results/EP_simulation_report.md` for a summary.
For specific numerical data, read the relevant CSV from
`research_projects/simulation/results/tables/`.

Key findings to highlight:
- Baseline EP₀ (42 t, dry road, 20°C, no wind, flat) — read the current value from the
  report's summary, do not quote a memorised number
- Sensitivity ranking (highest ΔEP first): road surface > CdA > elevation > temperature > wind > stop-start
- All linear factors (mass, Crr, CdA) have R² = 1.000

### 7. Recent changes

Read the current week's changelog file from `changelogs/changelog_YYYYMMDD_YYYYMMDD.md`.
Today's date is available from context. Find the file matching the current week
(Monday–Sunday), and summarise recent tasks.

### 8. Package version and branch

Read `pyproject.toml` for the version. Run `git branch --show-current` (read-only)
to confirm the current branch.
