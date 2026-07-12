# generate-data-dashboard — data-availability dashboard (jolt_toolkit CLI wrapper)

> Runs the `jolt_toolkit` dashboard CLI (a thin wrapper): scans one version's report
> database and builds a single self-contained, offline `data_dashboard.html`.
> This README is the skill's human-facing single source of truth; `SKILL.md` is the
> agent-facing router over `manifest.yaml`.

**Invoke:** `/generate-data-dashboard <version>` · **In:** local files only (no network) ·
**Out:** `excel_report_database/<version>/dashboard/data_dashboard.html`

## Directory map

```
generate-data-dashboard/
├── SKILL.md        # router: routing protocol only (agent entry point)
├── manifest.yaml   # always_load core + on-demand reference table (no axes — single path)
├── README.md       # this file — human-facing map + pipeline
├── static/core/    # conventions.md (always loaded: inputs to confirm, preconditions, conventions)
└── references/     # run-and-verify.md (exact command + overrides + verify checklist)
```

## Pipeline

1. **Confirm** — the version to scan (default: the current `jolt_toolkit` version in
   `pyproject.toml`, 2.2.8 at the time of writing) and the output path (default in-place).
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

## How to run

```bash
python -m jolt_toolkit.report_generator.data_dashboard --version 2.2.8
# → excel_report_database/2.2.8/dashboard/data_dashboard.html (open offline by double-click)
# overrides: --db-root <reports root>   --out <html path>
```

Full run details (including the optional `--details` per-vehicle drill-down pages) and
the post-generation verify checklist: [references/run-and-verify.md](references/run-and-verify.md).
Preconditions (local-files-only, OneDrive/Excel-lock caveat, `jolt` env / `PYTHONPATH=src`)
and conventions: [static/core/conventions.md](static/core/conventions.md).

## Ownership and neighbours

All detection/layout logic lives in `jolt_toolkit.report_generator.data_dashboard`
(route changes to `jolt-toolkit-dev`); this skill only RUNS it. A routine refresh — never bump
the version, never commit the output (gitignored). Full dashboard documentation:
`src/jolt_toolkit/README.md` ("Data-availability dashboard" section + the
`data_dashboard.py` module-table row). Regenerate it after `/generate-excel-report`
regens, or after a `/data-collection-monitor` run that skipped the refresh
(`--no-dashboard` / `--dry-run`) — a normal monitor run already refreshes the
dashboard automatically.
