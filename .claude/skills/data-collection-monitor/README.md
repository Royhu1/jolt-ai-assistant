# data-collection-monitor — periodic fleet data-collection check

> A periodic (designed for `/loop`, default weekly) fleet data-intake check: append-only
> extends the report database forward, refreshes the dashboard, and emits a
> data-collection digest. This README is the skill's human-facing single source of truth;
> `SKILL.md` is the agent-facing router over `manifest.yaml`.

**Invoke:** `/loop weekly /data-collection-monitor` (or `/data-collection-monitor`) · **In:**
SRF telematics (live) + `excel_report_database/<version>/` · **Out:**
`data_collection_reports/` (digest PDF/HTML + `MONITOR_STATUS.md`) + refreshed main dashboard

A **periodic check** (designed for `/loop`, default once a week): for every "watched
vehicle", check whether **new data has recently been collected and appeared on the SRF
platform**, merge that new data into the canonical report database **incrementally,
append-only, never overwriting**, refresh the data-availability dashboard, and emit a
**fixed-template PDF data-collection digest** (a detailed table).

## Directory map

```
data-collection-monitor/
├── SKILL.md              # router: routing protocol only (agent entry point)
├── manifest.yaml         # always_load + run-mode axis + first-run cadence gate + on-demand references
├── README.md             # this file — human-facing map + pipeline
├── static/
│   ├── core/             # conventions.md — behaviour conventions + discipline (always loaded)
│   └── fragments/
│       └── run-mode/     # full-check.md | template-only.md (exactly one loaded per run)
├── references/           # loop-usage.md (/loop + cadence rules) · digest-spec.md (artefact spec)
├── run_monitor.py        # orchestrator CLI: SRF check → append-only extend → dashboard → digest
├── build_digest_pdf.py   # HTML→PDF via headless Chrome/Edge (vendored from generate-pdf-report)
├── templates/            # digest_template.html.j2 — the fixed digest template
├── watched_vehicles.json # watched-vehicle list + default cadence/lookback
└── evaluations/          # per-run experience log
```

## Pipeline

Flow of one loop iteration:

1. **Cadence** — read `MONITOR_STATUS.md`; on the very first run (file absent) ask the user
   for the cadence (daily / weekly default / fortnightly / monthly), then reuse it silently.
1b. **Charger backfill sweep (v2.2.8+)** — re-patch ALL existing reports of the watched
   version via the `charger_patcher` CLI with `--persist-raw` (late-arriving SRF charge-point
   transactions; idempotent, fills only empty Charger Link cells, merge-accumulates
   `raw_charger/charger_transactions.csv`). `--no-charger-sweep` disables.
2. **Extend (append-only)** — per watched vehicle (`watched_vehicles.json`, default 16): find
   `last_covered`, then run the latest `jolt_toolkit` to generate reports ONLY for the gap
   after it, SKIPPING any period whose `.xlsx` exists — this is the "ask SRF for new data"
   step, and it never overwrites existing reports or raw data.
3. **Read window** — collect trip/charge detail within the lookback window (cadence-derived,
   default 7 days).
4. **Refresh dashboard** — regenerate `excel_report_database/<version>/data_dashboard.html`.
5. **Digest** — build the single 14-column whole-fleet overview table → HTML → headless-Chrome
   PDF (`build_digest_pdf.py`) → `data_collection_digest_<start>_<end>.pdf`.
6. **Status** — rewrite `MONITOR_STATUS.md` (cadence / last run / next due / per-vehicle
   "new data this time?"); echo cadence + next-due in the reply.

**Discipline:** orchestrates existing CLIs only — no `src/jolt_toolkit/` changes (route to
`jolt-toolkit-dev`), no version bump; per-vehicle failures are isolated (recorded `ERROR`, the
run continues). Artefacts gitignored. **vs.** `/generate-pdf-report`: this PDF is a
data-collection ledger, not an energy-performance briefing.

## How to run

Run from the **repo root** (needs `SRF_API_KEY` in the root `.env`, and `excel_report_database/`):

```bash
# Standard single check (all 16 vehicles, weekly / 7-day lookback, latest version)
PYTHONUTF8=1 python .claude/skills/data-collection-monitor/run_monitor.py --cadence weekly

# A subset / custom lookback window
PYTHONUTF8=1 python .claude/skills/data-collection-monitor/run_monitor.py --veh YK73WFN,AV24LXJ --window-days 7

# Quick PDF/template check on existing data only (no SRF, no dashboard refresh)
PYTHONUTF8=1 python .claude/skills/data-collection-monitor/run_monitor.py --dry-run
```

Common switches: `--version X.Y.Z` (defaults to the installed version), `--end-date
YYYY-MM-DD` (defaults to today UTC), `--no-raw` (skip raw CSV, faster but no raw stats),
`--fast` (skip Logger/Charger fetching), `--force` (regenerate even if the period file already
exists), `--no-dashboard` / `--no-pdf` / `--no-charger-sweep`.

Preconditions: use the `jolt` conda env; `SRF_API_KEY` in `.env`; under OneDrive, first close
any `.xlsx` open in Excel (a locked workbook is skipped on read with a warning).

## Artefacts

`data_collection_reports/` (gitignored, artefacts not committed): one
`data_collection_digest_<YYYYMMDD>_<YYYYMMDD>.pdf` + same-name `.html` per trigger, plus
`MONITOR_STATUS.md` (loop cadence / last run / next due / per-vehicle summary). Full spec —
the single 14-column whole-fleet table, per-column definitions, green/amber/grey colour
semantics, layout — in [references/digest-spec.md](references/digest-spec.md).

## Ownership and neighbours (division of labour with the other skills)

- `/generate-excel-report`, `/generate-data-dashboard`, `/generate-pdf-report` are **manual,
  one-off** generation tools; this skill is the **automated, periodic, incremental** check
  orchestration that reuses the same `jolt_toolkit` code behind them (no re-implementation,
  no changes to `src/jolt_toolkit/`).
- The PDF this skill emits is a **data-collection ledger** (which vehicle collected how many
  new trip / charge events), not the **energy-performance analysis briefing** for industrial
  partners that `/generate-pdf-report` produces.
- Report-generator CODE changes route to the `jolt-toolkit-dev` agent — this skill only
  orchestrates existing CLIs.
