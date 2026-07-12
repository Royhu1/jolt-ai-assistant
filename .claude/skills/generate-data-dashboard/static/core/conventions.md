# Conventions (always load)

Produce `data_dashboard.html` for one report-database version. This skill is a thin
driver over `jolt_toolkit.report_generator.data_dashboard`; all logic lives in the
package (owned by the `jolt-toolkit-dev` agent — route any behaviour/layout change there).

## Inputs to confirm with the user (ask only if ambiguous)

- **Version** — the `excel_report_database/<version>/` sub-directory to scan
  (e.g. `2.2.8`). **Default to the current `jolt_toolkit` version in `pyproject.toml`**
  (2.2.8 at the time of writing) — confirm before running.
- **Output path** — defaults to `excel_report_database/<version>/dashboard/data_dashboard.html`;
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

## Conventions

- Regenerating the dashboard is a **routine artefact refresh** — do NOT bump the
  `jolt_toolkit` package version for it.
- The output lives under gitignored `excel_report_database/` — never commit it.
- What the dashboard shows (for reference when answering follow-ups): full
  documentation lives in `src/jolt_toolkit/README.md` ("Data-availability
  dashboard" section + the `data_dashboard.py` module-table row).
