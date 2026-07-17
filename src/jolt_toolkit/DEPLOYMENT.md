# jolt_toolkit — deployment guide

> For an engineer deploying the **Excel-report generation path** (`REG + start/end
> dates → .xlsx`) on the SRF platform. This covers only the core report path; the
> AUX tooling (dashboards, fine-tuning, parameter identification) is out of platform
> scope — see the last section. Architecture reference → [README.md](README.md).

## What it does

Given a vehicle registration and a date range, `jolt_toolkit` fetches SRF
telematics / logger / charger data, runs charge/discharge segmentation, and writes a
formatted multi-sheet Excel report. It is a pure batch tool: one invocation per
`(vehicle, period)` produces one `.xlsx`. No server, no database, no long-running
process.

## Install

```bash
pip install .            # from the package directory (the dir containing pyproject.toml)
# optional extras:
pip install '.[params]'  # + scikit-learn, only for C_rr/C_dA identification (not the report path)
pip install '.[dev]'     # + pytest / black / isort / mypy (for running the test suite)
```

Python **≥ 3.10**. A wheel install ships the config JSONs and the HTML/asset templates
(declared as package-data), so a non-editable install is self-contained — no repo
checkout is required to generate a report.

Verify the install:

```bash
jolt-report --help                 # console script (exit 0)
python -c "import jolt_toolkit; print(jolt_toolkit.__version__)"
```

## Entry points

Three equivalent forms (identical flags):

```bash
jolt-report -veh KY24LHT -ds 2025-01-01 -de 2025-01-31 [--fast] [--debug] [--raw-only] [--out-dir DIR]
python -m jolt_toolkit.report_generator.cli -veh KY24LHT -ds 2025-01-01 -de 2025-01-31
```

Or from Python:

```python
from jolt_toolkit.report_generator import JOLTReportGenerator
gen = JOLTReportGenerator(report_output_folder="/data/reports", fast_mode=False)
path = gen.generate_report("KY24LHT", "2025-01-01", "2025-01-31")   # → str path or None
```

`date_end` is **inclusive**. `cli.main()` returns exit code **2** (with a clear
message) if `SRF_API_KEY` is unset or a required argument is missing, **0** on success.

## Environment variables & secrets

| Variable | Required | Purpose | Default |
|----------|----------|---------|---------|
| `SRF_API_KEY` | **yes** | SRF platform API key (Bearer token) | — (fail fast, rc 2) |
| `OPENWEATHER_API_KEYS` | no | comma-separated OpenWeather keys; only the optional weather post-step uses them | — (weather skipped) |
| `JOLT_CONFIG_DIR` | recommended | directory holding the three config JSONs **and the writable capacity ledger** | packaged `configs/` (read-only under site-packages) |
| `JOLT_CACHE_DIR` | recommended | cache root | `./cache` (relative to CWD) |
| `SRF_API_ROOT` | no | SRF REST API root | `https://data.csrf.ac.uk/api/` |
| `WEATHER_CACHE_FILE` / `WEATHER_CACHE_FILE_FINE` | no | override the weather cache file paths | under `JOLT_CACHE_DIR` |

**Secrets handling**: the CLI loads a `.env` from the working directory if present
(via `python-dotenv`, `override=False` — it never overwrites an already-set env var),
then reads the environment. On the platform, inject `SRF_API_KEY` (and
`OPENWEATHER_API_KEYS`) through the secret manager / environment rather than committing
a `.env`. Nothing is logged that contains the key.

## Writable state — the capacity ledger (important)

`configs/vehicles.json` is **not purely static config**: after each EV report the
generator writes back that vehicle's measured battery capacity
(`effective_capacity_kwh` + the `effective_capacity_quarterly` ledger). A packaged
install puts `configs/` under a read-only `site-packages`, so:

> **Copy `configs/` to a writable location and point `JOLT_CONFIG_DIR` at it.**

```bash
cp -r "$(python -c 'import jolt_toolkit.configs, os; print(os.path.dirname(jolt_toolkit.configs.__file__))')" /var/lib/jolt/configs
export JOLT_CONFIG_DIR=/var/lib/jolt/configs
```

All three JSONs are then read from — and the ledger written to — that directory. The
write-back is guarded by a `filelock.FileLock` on `vehicles.json.lock`, and only ever
appends/updates capacity fields (from `charge`/`discharge` donor segments; fallbacks
are never written). If you prefer immutable config, the report still generates
correctly with a read-only `configs/` — the capacity write-back simply no-ops with a
logged warning, and reports fall back to `srf_capacity_kwh`.

## Caches

Set `JOLT_CACHE_DIR` to a persistent, writable directory. Layout:

| Sub-path | Content | Notes |
|----------|---------|-------|
| `srf_http/` | SRF REST HTTP responses (`SeparateBodyFileCache`) | grows with the number of distinct API calls |
| `srf_raw/` | FPS leg raw telematics CSVs (keyed by `leg.uri`) | the bulk of the growth — one CSV per leg; can reach GBs for a full-fleet history |
| `postcode_cache.json` | GPS → postcode lookups (0.001° precision) | small |
| `.weather_cache.json` / `weather/.weather_cache_fine.json` | OpenWeather results (~1 km × 1 h key) | **should be persisted to protect the OpenWeather quota** |

Caches are **safe to persist between runs** and hit deterministically — re-running the
same `(vehicle, period)` re-uses cached SRF responses and raw CSVs instead of
re-fetching. Persisting the weather cache in particular avoids re-spending the
OpenWeather quota (the fine patcher can otherwise 429 the account). Nothing in the
cache is secret. Growth is roughly proportional to the volume of distinct legs
processed; size it for the full fleet-history you intend to (re)generate.

## Output contract

```
<out_dir>/<REG>/jolt_report_<REG>_<start>_<end>.xlsx
```

`<out_dir>` = `--out-dir` (default `./excel_report_database/<package_version>`);
`<start>`/`<end>` are `YYYYMMDD`. The workbook has three sheets: **Report** (one row
per segment), **Graphs** (fixed-axis scatter charts), **Definitions** (column glossary).

`--debug` additionally writes, under `<out_dir>/<REG>/`:
`raw_telematics/*.csv` (per-leg raw data), `validation_figures/*.png` (segmentation
figures) and `inspect_*.html` (an offline figure browser). `--raw-only` writes the raw
CSV + inspect HTML but skips the baked figures. Production report runs need none of
these — use plain mode (or `--fast` to skip the Logger/Charger fetch entirely).

## Optional weather post-step

Weather columns are back-filled after generation (they are not part of the core write).
The default coarse patcher is quota-friendly (~2 OpenWeather lookups per trip):

```bash
python -m jolt_toolkit.report_generator.weather_patch <folder-or-xlsx>
# default coarse; add --fine-grained only if you accept the ~17k-calls/vehicle volume
```

Requires `OPENWEATHER_API_KEYS`. Safe to re-run (cached).

## Concurrency

- The `vehicles.json` capacity write-back is `FileLock`-guarded, so concurrent runs
  cannot corrupt the ledger. Still, **run at most one generation per vehicle at a time**
  — two concurrent runs of the *same* vehicle would race on that vehicle's ledger
  entry (last writer wins) and duplicate SRF fetches.
- Different vehicles can be generated in parallel safely (separate ledger keys, shared
  read-only caches). The SRF client is created per `JOLTReportGenerator` instance.

## Not part of the platform scope

These are in-repo developer/analysis tooling, **not** the deployed report path — do not
wire them into the platform:

- **Dashboards** (`data_dashboard*.py`) — offline HTML data-availability views.
- **Fine-tuning** (`finetune.py`, `validation_generator.py`, `rerender_inspect.py`) —
  interactive segmentation correction producing `*_finetuned` artefacts.
- **Parameter identification** (`vehicle_params_identificator/`) — C_rr/C_dA, needs the
  `[params]` extra.
- **Migration scripts** (`scripts/recompute_from_cache.py`, `refresh_inspect_html.py`).

These modules keep their pre-v3 style (Chinese comments) and are exercised by the repo
skills, not by a platform deploy.

## Known quirks — do NOT "fix" these silently

An integrator reading the code may be tempted to "clean up" the following. Each is
deliberate; changing it alters output or breaks a contract.

- **Two header layouts.** EV reports use `HEADERS` (50 columns), diesel uses
  `DIESEL_HEADERS` (26 columns) — diesel is a **distinct** set (no SOC/battery/charging
  columns; carries `Fuel Used (L)` / `Fuel Consumption (L/100km)`), not a truncation of
  EV. `Operator` is the last column in **both**. Do not unify them.
- **Append-only column contract.** Patchers write into **hardcoded 1-based column
  indices** (e.g. temperature = EV column 38). New columns must be appended at the end,
  never inserted. Import-time assertions (`_COL_* == HEADERS.index(<name>)+1` in the
  three patchers, `tests/test_column_contracts.py`) fail loudly if HEADERS is reordered —
  respect them rather than deleting them.
- **`=NA()` cell contract.** Empty EP cells are written as the Excel `=NA()` formula with
  an **empty cached value** (`_write_na`). Under `openpyxl(data_only=True)`/pandas they
  read back as `#N/A` (or, for a single-pass writer, could leak `0`). Downstream readers
  must guard with a safe-number helper; `capacity_backfill` relies on the Stop-row
  `=NA()` cells being droppable. Do not replace `=NA()` with literal blanks or zeros.
- **Coarse wind-direction mean is a legacy quirk.** `WeatherPatcher` averages wind
  direction **arithmetically** (so 359°/1° can average to 180°). This is knowingly
  retained — the fine patcher fixed it with sin/cos averaging, but changing the coarse
  path would alter historical numbers. Leave it.
- **SOC = 0 is invalid, not empty battery.** The segmentation treats a telematics `SOC == 0`
  as a missing reading (set to NaN), not a flat battery. Do not "correct" this.
