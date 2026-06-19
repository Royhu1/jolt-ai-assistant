# generate-excel-report — Pipeline

> Drives the report-generation CLI (a thin wrapper) → `jolt_toolkit` fetches SRF
> telematics, segments it into trips/charges, and writes one `.xlsx` per period.

**Invoke:** `/generate-excel-report <REG> <period>` · **In:** SRF telematics (live API) ·
**Out:** `excel_report_database/<version>/<REG>/jolt_report_<REG>_<start>_<end>.xlsx`

## Flow

1. **Confirm inputs** — registration, date range (inclusive `-ds`/`-de`), the active
   `jolt_toolkit.__version__`, and the output dir (defaults to the version sub-dir).
2. **Preconditions** — `.env` has `SRF_API_KEY`; the vehicle is configured in
   `vehicles.json` / `pipelines.json` (if not → hand off to `/vehicle-onboarding` first).
3. **Span** — a single period ≤ ~1 quarter calls `generate_report.py`; a longer range calls
   `batch_generate.py`, which auto-splits into one report per meteorological quarter
   (DJF/MAM/JJA/SON, inclusive-end, non-overlapping).
4. **Fetch + segment** — the CLI pulls SRF legs (telematics) + optionally SRF Logger / Charger;
   `jolt_toolkit` segments per the vehicle's pipeline params and computes KPIs (EP, SoC, mass,
   distance, energy).
5. **Write** — the `.xlsx` Report sheet; `--debug` also writes validation figures + raw CSV +
   inspect HTML, `--raw-only` writes raw + HTML without baked figures, `--fast` skips
   Logger/Charger (non-final only).
6. **Weather (separate post-step)** — `weather_patch` backfills temperature columns
   cache-first from OpenWeather; elevation needs no API (read from the GPS-altitude channel).

**Owner:** algorithms live in `jolt_toolkit` (route code changes to `jolt-toolkit-dev`); this
skill only drives the CLI. **Next:** `/param-tuner`, `/report-finetuner`, `/plot-figure`,
`/generate-pdf-report`.
