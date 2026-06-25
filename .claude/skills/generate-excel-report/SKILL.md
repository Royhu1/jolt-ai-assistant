---
name: generate-excel-report
description: |
  Generate a formatted JOLT Excel report (.xlsx) for a vehicle over a date range,
  by driving the report-generation CLI (generate_report.py / batch_generate.py),
  which calls the jolt_toolkit package. Output goes to excel_report_database/<version>/.
  Triggers on:
  (1) "generate the Excel report for <REG> in <period>"
  (2) "generate the excel report for <REG> in <period>"
  (3) "/generate-excel-report <REG> <period>"
  (4) batch-generate the standard test vehicles
  If the target vehicle is not yet configured, hand off to /vehicle-onboarding first.
---

# Generate Excel Report — JOLT report-generation CLI wrapper

Produce JOLT `.xlsx` reports from SRF telematics. This skill is a thin driver over the
report-generation CLI; the actual algorithms live in the `jolt_toolkit` package
(owned by the `jolt-toolkit-dev` agent — route code changes there, not here).

## Trigger

Use this skill when the user asks to:
- Generate / regenerate an Excel report for one vehicle and date range
- Batch-generate the standard test fleet
- Run `/generate-excel-report <REG> <period>`

## Inputs to confirm with the user (ask if not given)

- **Vehicle registration** (e.g. `YK73WFN`).
- **Date range** — start and end (`YYYY-MM-DD`, both **inclusive**). A "year" / "month"
  phrasing should be resolved to explicit `-ds` / `-de` dates.
  - **Default report span = one meteorological quarter (inclusive end, no overlap).**
    When the user asks for "all data" / "the whole period for vehicle X" / a span longer
    than a quarter, do **not** produce one giant report — split it into **one report per
    meteorological quarter**: DJF (winter, `12-01`→`02-28/29`), MAM (spring,
    `03-01`→`05-31`), JJA (summer, `06-01`→`08-31`), SON (autumn, `09-01`→`11-30`). Each
    period's `end` is the **last included day** (inclusive); consecutive periods do **not**
    share a boundary day and do **not** overlap. The first period is clipped to `-ds`, the
    last to `-de` (so the final stub can be short, e.g. `…_20260601_20260609`).
    - *Why inclusive-end loses no data:* `fetch_events` queries `start_time` up to
      `date_end` combined with `datetime.time.max` (23:59:59.999999), so an inclusive-end
      label such as `…0228` still covers all of 02-28, and the next period (starting the
      following day at 00:00) does not re-count the same leg.
  - **The span is configurable** — default = meteorological quarters, but ask the user
    first and let them override. Use `batch_generate.py --veh … --ds … --de …` for the
    quarter default; add `--months N` as an equal-length escape hatch (e.g. `--months 1`
    for monthly, also inclusive-end / no-overlap). For a single full-range report, call
    `generate_report.py` directly.
  - **If the user gives NO date range, ASK — do not silently pick one.** Present explicit
    options and mark the recommended one:
    - **(recommended) Standard `test_data_config.json` ranges** — the fixed per-vehicle
      quarter list kept for cross-version comparison (`batch_generate.py` with no
      `--ds/--de`). ⚠️ Its `end` dates are **hand-maintained and can be stale**, so this
      reproduces the *configured* span — **not necessarily "up to today"**.
    - **Full / up-to-now ("all data")** — when the user wants everything to the present, derive
      the end from the **current date, NOT from `test_data_config.json`** (whose ends lag
      reality). Use `batch_generate.py --veh <REG> --ds <data-start> --de <today>`
      (auto-splits into meteorological quarters). For the whole fleet, extend each
      vehicle's range to today rather than trusting the config's frozen ends.
    - **A specific period** the user names (resolve "year"/"month" phrasing to explicit
      `-ds`/`-de`).
- **Mode** (optional):
  - `--debug` — also write validation figures + raw telematics CSV + inspect HTML
    (needed before `/param-tuner` or `/report-finetuner`).
  - `--raw-only` — like `--debug` (saves raw telematics CSV + inspect HTML) but **skips
    drawing the baked validation figures** during generation. Use this for the **batch
    regenerate → overlay-regenerate** workflow: when you will re-draw figures afterwards
    with `ValidationGenerator.regenerate` (new overlay style), drawing them at generate
    time too just wastes ~half the time. The inspect HTML still references the figures —
    they are produced by the later regenerate step. This is an **additive opt-in**; it
    does not change `--debug` (which still draws figures).
  - `--fast` — skip SRF Logger + Charger fetching. **Do NOT use `--fast` for a final /
    canonical report** — it skips the Logger/Charger patchers (logger columns end up
    `=NA()`). Use full mode (or re-patch afterwards) for deliverables.

## Preconditions

1. `.env` must contain `SRF_API_KEY` (and `OPENWEATHER_API_KEYS` for the separate
   weather-patching step).
2. The vehicle must already be configured in `src/jolt_toolkit/configs/`
   (`vehicles.json` / `pipelines.json`). If it is **not**, run `/vehicle-onboarding <REG>`
   first — that configures the pipeline and produces the first report.
3. **Confirm the toolkit version + output directory before generating anything.**
   This is a mandatory pre-step for every run (single or batch):
   - **(a) Toolkit version** — confirm which `jolt_toolkit.__version__` (= the
     `pyproject.toml` `version`) is in effect. Check with
     `python -c "import jolt_toolkit; print(jolt_toolkit.__version__)"`.
   - **(b) Output directory** — defaults to `excel_report_database/<__version__>/<REG>/`,
     because the CLIs build the path from `__version__`
     (`./excel_report_database/{__version__}`). Confirm this is the directory the user
     wants, or override it with `--out-dir`.
   - **Why this matters:** the editable-install version number is **shared across the
     whole conda env**, so two concurrent sessions on different versions (or one session
     that re-`pip install`s a new version mid-run) will silently write into each other's
     `excel_report_database/<ver>/` directory (cf. the recent 2.2.3 / 2.2.4 split
     incident). Pinning version + output dir up front keeps a batch run self-consistent.

## How to run

Single vehicle, single period (≤ ~3 months):

```bash
python .claude/skills/generate-excel-report/generate_report.py -veh YK73WFN -ds 2025-03-01 -de 2025-05-31
# add --debug for validation figures + raw CSV; --raw-only for raw + HTML without baked figures
# --fast only for quick non-final runs
# --out-dir ./excel_report_database/2.2.5   # override the version-derived output dir
```

Single vehicle, long range → auto-split into one report per meteorological quarter (default):

```bash
# whole range for one vehicle, meteorological-quarter reports (the default span, inclusive end)
python .claude/skills/generate-excel-report/batch_generate.py --veh YK73WFN --ds 2024-06-01 --de 2026-06-09
# equal-length escape hatch (e.g. monthly) or a forced output dir
python .claude/skills/generate-excel-report/batch_generate.py --veh YK73WFN --ds 2024-06-01 --de 2025-12-01 --months 1 --out-dir ./excel_report_database/2.2.5
# raw-only (fast) batch regenerate; figures re-drawn later by the overlay regenerate step
python .claude/skills/generate-excel-report/batch_generate.py --raw-only
```

The split helper is `batch_generate.split_into_periods(date_start, date_end, months=None)`
— `months=None` (default) splits into meteorological quarters (DJF/MAM/JJA/SON) with
**inclusive-end, non-overlapping** periods (first clipped to `date_start`, last to
`date_end`); `months=N` is an equal-length N-month escape hatch (also inclusive-end).

Batch (standard test fleet + date ranges from `test_data_config.json`):

```bash
python .claude/skills/generate-excel-report/batch_generate.py            # whole fleet
python .claude/skills/generate-excel-report/batch_generate.py --veh YK73WFN  # one configured vehicle
```

The report is written to `excel_report_database/<version>/<REG>/jolt_report_<REG>_<start>_<end>.xlsx`.
With `--debug`: plus `inspect_*.html`, `validation_figures/` and `raw_telematics/`.
With `--raw-only`: same as `--debug` but **no** `validation_figures/` at generate time
(re-drawn later by the overlay regenerate step; `inspect_*.html` still written).

## Weather & elevation: cache-first by default

- **Weather** columns are **not** filled during report generation — they are added by a
  separate post-step, the default being the coarse `WeatherPatcher`
  (`jolt_toolkit.report_generator.weather_patch.patch_weather`, mode `"coarse"`). That
  patcher is **cache-first**: it looks every unique `(lat, lon, dt)` up in the local
  `_WeatherCache` (`./cache/.weather_cache.json`) and only calls the OpenWeather API for
  the misses, caching what it fetches. This is the default precisely to avoid hammering
  OpenWeather (the account trips into HTTP 429 easily); fine-grained per-GPS-point
  patching is opt-in only and is *not* used for routine report generation.
- **Elevation** ("Elevation Difference (m)") needs **no external API at all** — it is read
  straight from the vehicle's own GPS-altitude channel in the raw telematics
  (`altitude_col` → `_get_elevation_diff`). There is therefore no SRTM call (and nothing
  to rate-limit) in the report-generation pipeline; the only SRTM usage in the repo is a
  one-off academic-paper script for a vehicle that lacks an on-board altitude channel
  (outside this skill's scope).

## After generating

- **⚠️ Weather backfill — REQUIRED to finish a report; this is the step most often
  forgotten on a batch / full-fleet regen.** Report generation does **not** fill the
  weather columns (`Average Temperature (C)` / `Pressure` / `Humidity` / `Wind Speed` /
  `Wind Direction` / `Weather Type`) — they come from the separate coarse weather patch
  (see "Weather & elevation: cache-first by default" above). **After every generate /
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
- **Dashboard refresh** (also part of "finishing" a batch / full-fleet regen) →
  `/generate-data-dashboard <version>`.
- For segmentation review / tuning → `/param-tuner <REG>`.
- For manual segmentation corrections on the produced xlsx → `/report-finetuner <REG> <period>`.
- For analysis figures from the reports → `/plot-figure`.

> **Definition of a complete full-fleet regen** = `batch_generate` (all vehicles) **+**
> weather backfill (every vehicle dir) **+** dashboard refresh. Skipping the weather step
> is the known failure mode that leaves the version with blank weather columns.
