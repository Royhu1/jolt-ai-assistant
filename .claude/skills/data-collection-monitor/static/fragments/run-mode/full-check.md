# Run mode: full-check — the standard loop iteration (DEFAULT)

The standard periodic check: SRF check → append-only extend the report database →
refresh the dashboard → digest PDF + `MONITOR_STATUS.md`. Use for every /loop iteration
and every "check for new data / produce the data-collection report" request.

## What it does each time (one loop iteration)

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

## How to run

Run from the **repo root** (needs `SRF_API_KEY` in the root `.env`, and `excel_report_database/`):

```bash
# Standard single check (all 17 vehicles, weekly / 7-day lookback, latest version)
PYTHONUTF8=1 python .claude/skills/data-collection-monitor/run_monitor.py --cadence weekly

# A subset / custom lookback window
PYTHONUTF8=1 python .claude/skills/data-collection-monitor/run_monitor.py --veh YK73WFN,AV24LXJ --window-days 7
```

Common switches: `--version X.Y.Z` (defaults to the installed version), `--end-date
YYYY-MM-DD` (defaults to today UTC), `--no-raw` (skip raw CSV, faster but no raw stats),
`--fast` (skip Logger/Charger fetching), `--force` (regenerate even if the period file already
exists), `--no-dashboard` / `--no-pdf` / `--no-charger-sweep`.

Preconditions: use the `jolt` conda env; `SRF_API_KEY` in `.env`; under OneDrive, first close
any `.xlsx` open in Excel (a locked workbook is skipped on read with a warning).

## Checklist

1. Resolve the cadence first (blocking gate on the first /loop run —
   `references/loop-usage.md`).
2. Run the standard command with the resolved `--cadence <value> [--window-days N]`.
3. Confirm the digest PDF/HTML and `MONITOR_STATUS.md` landed in `data_collection_reports/`
   and the main dashboard was refreshed (digest spec: `references/digest-spec.md`).
4. Echo the cadence and next-due at the end of the reply.
