# After generating — mandatory post-run checklist

> Open this after **every** generation run (single or batch), before declaring the run
> complete. Generation alone leaves the weather columns empty; the definition of a
> complete full-fleet regen is at the bottom.

- **⚠️ Weather backfill — REQUIRED to finish a report; this is the step most often
  forgotten on a batch / full-fleet regen.** Report generation does **not** fill the
  weather columns (`Average Temperature (C)` / `Pressure` / `Humidity` / `Wind Speed` /
  `Wind Direction` / `Weather Type`) — they come from the separate coarse weather patch
  (see "Weather & elevation: cache-first by default" in
  `static/core/conventions.md`). **After every generate /
  regenerate, run it** — and for a **batch / full-fleet regen, loop it over every vehicle
  directory** (a full regen overwrites each xlsx from scratch, so any previously-patched
  weather is wiped and must be re-applied):
  ```bash
  # one vehicle directory
  python -m jolt_toolkit.report_generator.weather_patch ./excel_report_database/<ver>/<REG>/
  # full fleet (PowerShell): $env:OPENWEATHER_API_KEYS=...; foreach REG dir → run the above
  ```
  Needs `OPENWEATHER_API_KEYS` in the environment; the patcher is **cache-first** and
  **skips already-patched rows**, so it is safe to re-run. OpenWeather trips into HTTP 429
  easily, so a cold backfill may need **several incremental runs across days** (the cache
  persists). **A regen without this step ships reports with empty weather columns** — after
  any full-fleet regen, verify weather coverage (non-null `Average Temperature (C)` per
  report) before treating the version as complete.
- **Charger backfill (v2.2.8+)** — charger transactions are fused at generation time, but
  SRF charge-point data can be uploaded **days/weeks after** the vehicle telematics, so a
  report generated "now" may legitimately miss transactions that appear later. After a batch /
  full-fleet regen (and periodically — the data-collection-monitor does this sweep weekly),
  re-patch the whole version directory:
  ```bash
  python -m jolt_toolkit.report_generator.charger_patcher ./excel_report_database/<ver> --persist-raw
  ```
  Idempotent: only **empty** `Charger Link` cells are filled (existing links untouched), and
  `--persist-raw` merge-accumulates each vehicle's `raw_charger/charger_transactions.csv`
  (dedup by transaction URI) — the file the dashboard raw base and the monitor digest read.
  Diesel vehicles are skipped automatically.
- **Dashboard refresh** (also part of "finishing" a batch / full-fleet regen) →
  `/generate-data-dashboard <version>`.
- For segmentation review / tuning → `/param-tuner <REG>`.
- For manual segmentation corrections on the produced xlsx → `/report-finetuner <REG> <period>`.
- For analysis figures from the reports → `/plot-figure`.

> **Definition of a complete full-fleet regen** = `batch_generate` (all vehicles) **+**
> weather backfill (every vehicle dir) **+** charger backfill sweep (whole version dir,
> `--persist-raw`) **+** dashboard refresh. Skipping the weather step is the known failure
> mode that leaves the version with blank weather columns; skipping the charger sweep leaves
> late-arriving charge-point transactions unfused and the raw_charger CSVs stale (the 2.2.7
> T88RNW/N88GNW "missing charger data" incident).
