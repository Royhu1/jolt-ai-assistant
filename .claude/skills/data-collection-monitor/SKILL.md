---
name: data-collection-monitor
description: |
  Periodic (designed for /loop, default weekly) fleet data-collection check. For every
  watched vehicle it EXTENDS the canonical excel_report_database/<version>/ forward in
  time with the latest jolt_toolkit — generating reports ONLY for periods after the
  latest existing coverage and SKIPPING any period whose .xlsx already exists, so it
  never overwrites an existing report or its raw data (append-only). It then refreshes
  the data-availability dashboard and emits a fixed-template PDF "data collection digest"
  (a single fleet data-collection overview table: operator, energy type, telematics /
  SRF-logger leg + charger-transaction counts + last-seen times, trips, charges, active
  days, distance) for the
  most-recent window into data_collection_reports/, and updates MONITOR_STATUS.md (which
  shows the active loop cadence / last run / next due).
  Triggers on:
  (1) "/loop weekly /data-collection-monitor" (the intended use — a recurring data-intake check)
  (2) "check whether any new data has recently been collected for the watched vehicles / refresh the dashboard and produce a data-collection report"
  (3) "run the fleet data-collection monitor / generate the data collection digest"
  (4) "/data-collection-monitor [--cadence weekly]"
  When run under /loop with no cadence recorded yet, ASK the user for the cadence on the
  FIRST run only (see §2). Routes report-generator CODE changes to the jolt-toolkit-dev
  agent — this skill only orchestrates existing CLIs.
---

# data-collection-monitor — periodic fleet data-collection check

A **periodic check** (designed for `/loop`, default once a week): for every "watched
vehicle", check whether **new data has recently been collected and appeared on the SRF
platform**, merge that new data into the canonical report database **incrementally,
append-only, never overwriting**, refresh the data-availability dashboard, and emit a
**fixed-template PDF data-collection digest** (a detailed table).

Division of labour with the other skills:
- `/generate-excel-report`, `/generate-data-dashboard`, `/generate-pdf-report` are **manual,
  one-off** generation tools; this skill is the **automated, periodic, incremental** check
  orchestration that reuses the same `jolt_toolkit` code behind them (no re-implementation,
  no changes to `src/jolt_toolkit/`).
- The PDF this skill emits is a **data-collection ledger** (which vehicle collected how many
  new trip / charge events), not the **energy-performance analysis briefing** for industrial
  partners that `/generate-pdf-report` produces.

## 1. What it does each time (one loop iteration)

For every watched vehicle:
1. Scan `excel_report_database/<version>/<REG>/` and find the **latest day already covered**,
   `last_covered`.
2. Use the **latest** `jolt_toolkit` to **extend the report database forward**: generate
   reports only for the gap after `last_covered`, and **skip if the target period file
   already exists** — no existing report / raw data file is ever rewritten (append-only).
   This step itself is the "ask SRF whether there is new data".
3. Read the trip and charge event detail within the **lookback window** (corresponds to the
   cadence, default the past 7 days).
4. Refresh the main dashboard (`excel_report_database/<version>/dashboard/data_dashboard.html`).
5. Emit `data_collection_reports/data_collection_digest_<start>_<end>.pdf` and update
   `data_collection_reports/MONITOR_STATUS.md`.

The version number is **taken dynamically from the installed `jolt_toolkit.__version__`**
(unless `--version` is given explicitly), so it always uses the current latest version
(e.g. 2.2.6 / 2.2.7…). The watched-vehicle list is in `watched_vehicles.json` (default all 17).

## 2. Trigger and `/loop` usage (incl. "ask cadence on first run" and "cadence display")

Intended to be triggered periodically via `/loop`, e.g. once a week. The interaction rule on
the **first** trigger within a loop:

1. Read `data_collection_reports/MONITOR_STATUS.md`.
2. **If that file does not exist (= the first run of this loop)**: use `AskUserQuestion` to ask
   the user for the **trigger cadence** (daily / **weekly (default)** / fortnightly / monthly).
   The lookback window defaults to follow the cadence (weekly → 7 days); the user may specify
   otherwise. Then run with `--cadence <value> [--window-days N]`.
3. **On every subsequent trigger**: read the cadence back from `MONITOR_STATUS.md` and reuse
   it, **do not ask again**; after the run the file is rewritten, refreshing last run / next
   due.

**Where the cadence is shown:** `MONITOR_STATUS.md` shows at the top, fixed, **Cadence (loop
period) / Lookback / Last run / Next run / Watched vehicles / latest digest**, plus a one-line
"new data this time?" summary per vehicle. Each reply should also echo the cadence and
next-due at the end, so the user can confirm at any time that the loop is still running and
what the period is.

> **About a genuine "weekly" schedule:** `/loop`'s dynamic self-pacing (ScheduleWakeup) is at
> most ~1 hour per step, so it cannot do a one-week interval; a true weekly trigger is handled
> by the harness's scheduled task (cron). This skill does not create a cron itself — the user
> decides the schedule with `/loop`; the skill only "does the work when triggered + maintains
> its own cadence state".

## 3. How to run

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

## 4. Behaviour conventions (finalised)

- **Append-only, never overwrite**: generate only for the gap after `last_covered`; skip if the
  target period file already exists. Historical reports / raw data (incl. `raw_telematics/`)
  are never rewritten. This naturally produces "weekly incremental slice" files within the
  current quarter (e.g. `..._20260610_20260615.xlsx`) that do not overlap the historical
  quarter files, so the dashboard does not double-count.
- **Dynamic version**: defaults to `jolt_toolkit.__version__`; merged into the main database
  `excel_report_database/<version>/`, refreshing the main dashboard — new data is reflected
  directly in the main database and main dashboard you use daily.
- **No validation figures** (`save_figures=False`); by default writes raw CSV + inspect HTML
  (for human drill-down checks; `--no-raw` skips them for speed). Collection-volume stats
  (telematics / SRF logger leg counts) are taken from the xlsx `Telematics Link` / `SRF Logger
  Link` columns, not dependent on raw files.
- Failure isolation: a single vehicle's generation failure only records `ERROR` for that
  vehicle and does not interrupt the whole-fleet check.
- **Charger backfill sweep (v2.2.8+)**: SRF charge-point transactions can be uploaded
  days/weeks after the vehicle telematics, and report generation only fuses what exists at
  generation time — so each run first sweeps ALL existing reports of the watched version with
  `python -m jolt_toolkit.report_generator.charger_patcher <db_root> --persist-raw`
  (idempotent: only empty `Charger Link` cells are filled; `raw_charger/
  charger_transactions.csv` is merge-accumulated per vehicle — the very file the digest's
  Charger columns and the dashboard raw base read). Disable with `--no-charger-sweep`. This
  is the ONLY sanctioned in-place update to existing reports (it appends previously-missing
  charger facts; it never alters energies or segmentation).

## 5. Artefacts (new folder)

`data_collection_reports/` (gitignored, artefacts not committed):
- `data_collection_digest_<YYYYMMDD>_<YYYYMMDD>.pdf` + same-name `.html` (one whole-fleet
  digest per trigger).
- `MONITOR_STATUS.md` (loop cadence / last / next / per-vehicle summary — see §2).

PDF content: **a single "whole-fleet data-collection overview table"** (no summary cards, no
per-vehicle detail sections; title bar centred, the time range in red). One row per vehicle,
14 columns: **Vehicle / Operator / Make-Model / Energy type (EV·Diesel) / Telematics data /
SRF logger / Charger data / Trips / Charges / Active days / Distance (km) / Latest telematics /
Latest SRF logger / Latest charger**.
- *Telematics data* / *SRF logger* = the number of legs **within the window** supported by SRF
  FPS telematics / SRF logger respectively (count of non-empty `Telematics Link` / `SRF Logger
  Link` in the Report sheet); *Charger data* = the number of charge-point transactions in the
  window (rows of `raw_charger/charger_transactions.csv` whose `start_time` falls in the window).
- *Latest telematics* / *Latest SRF logger* / *Latest charger* = the **most recent data time
  across the whole database** for that source (newest files scanned first): **green** = falls
  within this window, **amber** = the last time was before the window (possibly long ago),
  **grey "—"** = that source has never been collected.
- *Energy type* is taken from vehicles.json `fuel_type` (DIESEL → Diesel, otherwise EV);
  *Operator* is taken from `plot_config.json` `company_assignment` (incl. `round_robin` matched
  by date range against the window-end day).
- Layout: font sizes are **3×** the base version, so a large landscape canvas (≈720×450 mm,
  with left/right margins) is used so the 14 columns do not wrap and the whole fleet fits
  (a digital PDF, mainly for on-screen reading, header repeated per page, some columns centred).

## 6. Discipline

- **Do not change any code / config in `src/jolt_toolkit/`** (jolt-toolkit-dev's territory);
  this skill only orchestrates the existing `JOLTReportGenerator` and dashboard CLI. To change
  report-generation logic → raise a request to jolt-toolkit-dev.
- **Do not bump the version number** (the check is a routine refresh); artefacts not committed
  to git (the skill itself is shared via git).
- Append a Q&A record to `changelogs/changelog_<Monday>_<Sunday>.md` at the end of the
  conversation.
- HTML→PDF uses this machine's headless Chrome/Edge (`build_digest_pdf.py`, vendored from
  generate-pdf-report's `build_pdf.py`, zero extra dependencies).
