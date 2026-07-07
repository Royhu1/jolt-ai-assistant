# data-collection-monitor — Pipeline

> A periodic (designed for `/loop`) fleet data-intake check: append-only extends the
> report database forward, refreshes the dashboard, and emits a data-collection digest.

**Invoke:** `/loop weekly /data-collection-monitor` (or `/data-collection-monitor`) · **In:**
SRF telematics (live) + `excel_report_database/<version>/` · **Out:**
`data_collection_reports/` (digest PDF/HTML + `MONITOR_STATUS.md`) + refreshed main dashboard

## Flow (one loop iteration)

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
