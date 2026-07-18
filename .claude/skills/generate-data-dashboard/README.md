# generate-data-dashboard — data-availability dashboard (self-contained code owner)

> Runs the skill-owned dashboard generator: scans one version's report database and
> builds a single self-contained, offline `data_dashboard.html`. Since v3.1.0 the
> dashboard code lives in this skill's `code/` (moved out of the `jolt_toolkit`
> package — this skill is its self-contained owner, like `generate-pdf-report`).
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
├── code/           # skill-owned dashboard code (canonical home since v3.1.0):
│   ├── generate_dashboard.py       # thin CLI runner (same args as the former package CLI)
│   ├── data_dashboard.py           # dashboard generator (scan + render)
│   ├── data_dashboard_detail.py    # per-vehicle drill-down detail pages
│   └── assets/uplot/               # vendored uPlot JS/CSS (+ PROVENANCE.txt)
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
# from the repo root (jolt_toolkit importable: `jolt` conda env or PYTHONPATH=src)
python .claude/skills/generate-data-dashboard/code/generate_dashboard.py --version 2.2.8
# → excel_report_database/2.2.8/dashboard/data_dashboard.html (open offline by double-click)
# overrides: --db-root <reports root>   --out <html path>
```

Full run details (including the optional `--details` per-vehicle drill-down pages) and
the post-generation verify checklist: [references/run-and-verify.md](references/run-and-verify.md).
Preconditions (local-files-only, OneDrive/Excel-lock caveat, `jolt` env / `PYTHONPATH=src`)
and conventions: [static/core/conventions.md](static/core/conventions.md).

## Ownership and neighbours

Since v3.1.0 all detection/layout logic lives in THIS skill's `code/`
(`data_dashboard.py` / `data_dashboard_detail.py` / vendored `assets/uplot/`) —
**route dashboard CODE changes here, not to `jolt-toolkit-dev`**. The code still
imports the `jolt_toolkit` package read-only for shared names (`HEADERS` /
`DIESEL_HEADERS`, segmentation constants such as `_agg_mass` / `resolve_mass_agg` /
`cluster_mass_data`, and the config loaders); route to `jolt-toolkit-dev` only when a
new xlsx field or package-shared name is needed. A routine refresh — never bump the
package version, never commit the output (gitignored). The
`data-collection-monitor` skill drives this runner CLI in its weekly refresh (CLI
contract: `--version` / `--db-root` / `--out` / `--details`). Regenerate after
`/generate-excel-report` regens, or after a `/data-collection-monitor` run that
skipped the refresh (`--no-dashboard` / `--dry-run`) — a normal monitor run already
refreshes the dashboard automatically.
