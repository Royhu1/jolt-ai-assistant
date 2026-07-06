# generate-data-dashboard — Pipeline

> Runs the `jolt_toolkit` dashboard CLI (a thin wrapper): scans one version's report
> database and builds a single self-contained, offline `data_dashboard.html`.

**Invoke:** `/generate-data-dashboard <version>` · **In:** local files only (no network) ·
**Out:** `excel_report_database/<version>/dashboard/data_dashboard.html`

## Flow

1. **Confirm** — the version to scan (default `2.2.7`) and the output path (default in-place).
2. **Read (local only)** — per vehicle: `jolt_report_*.xlsx` (skips `_finetuned`), the raw
   dirs (`raw_telematics/`, `raw_logger_v1/`, `raw_logger_v2/`,
   `raw_charger/charger_transactions.csv`), and configs (`vehicles.json` + `plot_config.json`
   for make/model, capacity, operator + colours).
3. **Detect availability** — per vehicle, per day: which days have telematics / logger /
   charger data, on both Events and Raw-data bases.
4. **Render** — embed a `const DATA` blob and emit a self-contained HTML (no CDN / external
   `<link>`; opens offline by double-click).
5. **Report** — print the per-vehicle summary table (events vs raw day counts) so coverage can
   be sanity-checked at a glance.

**Owner:** all detection/layout logic lives in `jolt_toolkit.report_generator.data_dashboard`
(route changes to `jolt-toolkit-dev`); this skill only RUNS it. A routine refresh — never bump
the version, never commit the output (gitignored).
