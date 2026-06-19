---
name: generate-data-dashboard
description: |
  Generate (or refresh) the JOLT data-availability dashboard — a single
  self-contained offline data_dashboard.html for a report-database version,
  by running the jolt_toolkit dashboard CLI. Shows, per vehicle, which days
  have telematics / logger / charger data (Events vs Raw-data bases), plus
  vehicle stats and operator info. Output: excel_report_database/X.Y.Z/data_dashboard.html.
  Triggers on:
  (1) "基于 X.Y.Z 版本的数据生成一个 data availability dashboard"
  (2) "generate / refresh the data availability dashboard (for version X.Y.Z)"
  (3) "/generate-data-dashboard X.Y.Z"
  (4) regenerate the dashboard after new Excel reports / raw data were added
  Route CODE changes to the dashboard (layout, detection rules, new panels)
  to the jolt-toolkit-dev agent instead — this skill only RUNS the generator.
---

# Generate Data-Availability Dashboard — jolt_toolkit CLI wrapper

Produce `data_dashboard.html` for one report-database version. This skill is a thin
driver over `jolt_toolkit.report_generator.data_dashboard`; all logic lives in the
package (owned by the `jolt-toolkit-dev` agent — route any behaviour/layout change there).

## Inputs to confirm with the user (ask only if ambiguous)

- **Version** — the `excel_report_database/<version>/` sub-directory to scan
  (e.g. `2.2.5`). **Default to `2.2.5`** (the current canonical/latest version) if not given.
- **Output path** — defaults to `excel_report_database/<version>/data_dashboard.html`;
  only override (`--out`) if the user asks.

## Preconditions

- No network/API keys needed — the generator reads only local files:
  - `excel_report_database/<version>/<REG>/jolt_report_*.xlsx` (skips `*_finetuned`)
  - raw dirs: `raw_telematics/`, `raw_logger_v1/`, `raw_logger_v2/`,
    `raw_charger/charger_transactions.csv`
  - configs: `src/jolt_toolkit/configs/vehicles.json` + `plot_config.json`
    (make/model, capacity, operator assignment + colours)
- OneDrive caveat: ask the user to close any of the version's `.xlsx` open in Excel
  first — a locked workbook fails the scan.
- Run from the repo root with the `jolt` conda env. If `import jolt_toolkit` resolves
  to a stale editable install, prefix with `PYTHONPATH=src`.

## How to run

```bash
python -m jolt_toolkit.report_generator.data_dashboard --version 2.2.5
# → excel_report_database/2.2.5/data_dashboard.html (open offline by double-click)
# overrides: --db-root <reports root>   --out <html path>
```

The CLI prints a per-vehicle summary table (events vs raw day counts per category)
— include it in the reply so the user can sanity-check coverage at a glance.

## Verify after generating

1. The HTML file was (re)written and is self-contained — no `http(s)://` /
   CDN / `<link>` references (it must open offline by double-click).
2. The embedded `const DATA` blob contains every vehicle directory present under
   `excel_report_database/<version>/` (compare against `ls`).
3. Console summary table shows no vehicle skipped due to a locked/unreadable file.

## Conventions

- Regenerating the dashboard is a **routine artefact refresh** — do NOT bump the
  `jolt_toolkit` package version for it.
- The output lives under gitignored `excel_report_database/` — never commit it.
- What the dashboard shows (for reference when answering follow-ups): full
  documentation lives in `src/jolt_toolkit/README.md` ("Data-availability
  dashboard" section + the `data_dashboard.py` module-table row).
