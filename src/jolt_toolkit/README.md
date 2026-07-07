# jolt_toolkit — package internal architecture documentation

> Developer-facing internal architecture reference. The src-layout has been used since v2.0.0-dev. Current version **v2.2.7**.
> Project overview & repo-wide usage → [root README.md](../../README.md) | Claude working conventions → [CLAUDE.md](../../CLAUDE.md)

## Installation and usage

### Installation

```bash
pip install -e .
```

Configure the `.env` file (project root):

```
SRF_API_KEY=your_api_key_here
```

### Running

#### Standard mode

```bash
python .claude/skills/generate-excel-report/generate_report.py -veh KY24LHT -ds 2025-01-01 -de 2025-01-31
```

Generates the Excel report into `excel_report_database/<version>/<registration>/`.

#### Debug mode

```bash
python .claude/skills/generate-excel-report/generate_report.py -veh KY24LHT -ds 2025-01-01 -de 2025-01-31 --debug
```

In addition to the Excel report, it also outputs:
- `raw_telematics/` — raw CSV data for each FPS leg
- `validation_figures/` — a 4-panel validation figure (SOC/speed, AC+DC energy, discharge energy, vehicle mass). The `--debug` live path writes one figure per leg, but the **canonical** figures are re-painted **one per calendar day** by the overlay-regenerate path (`ValidationGenerator.regenerate` for EV / `regenerate_diesel_validation` for diesel; see §Validation figures), which groups a day's per-leg raw CSVs, segments the concatenated day, and spans the full UTC day (00:00→24:00) with **all** that day's trip/charge bands on one figure.
- `inspect_*.html` — an HTML viewer for browsing the validation figures interactively (one sidebar entry per day)

#### Fast mode

```bash
python .claude/skills/generate-excel-report/generate_report.py -veh KY24LHT -ds 2025-01-01 -de 2025-01-31 --fast
```

Skips fetching and processing SRF Logger and Charger data, using only FPS telematics data. Suitable for fast iterative debugging or scenarios where charger/Logger data is not required.

#### CLI parameters

| Parameter | Description |
|------|------|
| `-veh` / `--vehicle_registration` | Vehicle registration (must be registered in `configs/vehicles.json`) |
| `-ds` / `--date_start` | Start date (YYYY-MM-DD) |
| `-de` / `--date_end` | End date (YYYY-MM-DD) |
| `--debug` | Enable debug mode |
| `--fast` | Skip Logger/Charger data, generate the report using only FPS data |

### Batch generation (version comparison)

`.claude/skills/generate-excel-report/test_data_config.json` defines the standard test vehicles and date ranges (consistent with the v1.0.0 report scope); the `batch_generate.py` CLI (now under `.claude/skills/generate-excel-report/`) generates them in batch according to that configuration:

```bash
python .claude/skills/generate-excel-report/batch_generate.py --debug --fast                # all vehicles
python .claude/skills/generate-excel-report/batch_generate.py --debug --fast --veh AV24LXK  # a single vehicle
```

Run after each algorithm or parameter change to keep results comparable across versions.

### Public API

```python
# report generation (single vehicle)
from jolt_toolkit.report_generator import JOLTReportGenerator
gen = JOLTReportGenerator(report_output_folder="./excel_report_database/2.2.2",
                         debug_mode=True, fast_mode=False,
                         # save_figures=False (with debug_mode=True) → keep raw CSV +
                         # inspect HTML but skip baked validation figures (CLI --raw-only)
                         save_figures=True)
gen.generate_report("AV24LXK", "2024-06-01", "2024-09-01")

# parameter identification
from jolt_toolkit.vehicle_params_identificator import identify_crr_cda
identify_crr_cda("YN25RSY", "2025-08-26", "2026-01-15")
```

For driving-cycle correction and other measured-data workflows that consume these reports, see [`data_analysis_workspace/README.md`](../../data_analysis_workspace/README.md).

## Package structure (v2.2.7)

```
src/jolt_toolkit/
├── __init__.py                    # package version (importlib.metadata + pyproject.toml fallback)
├── configs/                       # shared configuration (the three sub-packages access it via CONFIGS_DIR / get_config_path())
│   ├── vehicles.json
│   ├── pipelines.json
│   └── plot_config.json
├── report_generator/              # sub-package 1: report generation pipeline
│   ├── __init__.py                # exports generate_report(), patch_logger()
│   ├── _generator.py              # JOLTReportGenerator main flow orchestration
│   ├── segment_algorithms.py      # unified charge/discharge segmentation algorithm (EV path)
│   ├── diesel_pipeline.py         # diesel Logger-only branch (added in v2.2.2)
│   ├── operators.py               # per-leg operator-code resolution (v2.2.5): SRF trial.description / organisation.name cascade → `Operator` column
│   ├── report_builder.py          # Excel report generation + HTML viewer (incl. Stop row synthesis)
│   ├── finetune.py                # segmentation correction post-processing (apply operations → rewrite xlsx + figures + HTML)
│   ├── charger_patcher.py         # charger data patching
│   ├── logger_patcher.py          # Logger data patching
│   ├── weather_patcher.py         # OpenWeather API weather patching (coarse: origin/dest 2-point average)
│   ├── weather_patch.py           # unified weather-patch entry point — default coarse, fine opt-in (patch_weather + CLI)
│   ├── validation_generator.py    # EV overlay-regenerate path: re-paint validation figures + inspect HTML from raw_telematics CSVs. v2.2.6: groups a day's per-leg raw CSVs → ONE figure per calendar day (`_concat_day_raw`); diesel routes to `diesel_pipeline.regenerate_diesel_validation`
│   ├── rerender_inspect.py        # standalone CLI: re-render inspect_*.html from existing figures + .boxes.json sidecars (no figure regen); drives the current v2.2.6 viewer; skips *_finetuned
│   ├── data_dashboard.py          # data-availability dashboard generator (v2.2.3): scans the report DB → self-contained 3-panel interactive data_dashboard.html (+ optional --details drill-down). Operator overlay is DATA-DRIVEN from each report's `Operator` column (v2.2.6+): per-day operator → dated periods (1 distinct = Fixed, ≥2 = Round-robin); `plot_config.json` `company_assignment` is only a fallback for vehicles with no operator in the data; operators absent from `colors.company` (e.g. `HTL`) get a stable fallback colour; names show underscores as spaces
│   ├── data_dashboard_detail.py   # per-vehicle drill-down detail page (detail_<REG>.html): offline uPlot day-by-day channel viewer with event bands/markers + dashed per-event mean-mass line (report's mass_agg)
│   ├── pedal_histogram.py         # accelerator/brake pedal histogram computation
│   ├── data_fetcher.py            # SRF API data fetching
│   ├── data_class.py              # ServerData data class
│   ├── bootstrap.py               # initialisation helpers
│   ├── assets/uplot/              # vendored offline uPlot JS/CSS (+ PROVENANCE) inlined into detail pages
│   └── weather_fetcher/           # weather API client (cache, key rotation, fine-grained patching)
│       ├── __init__.py
│       ├── weather_fetcher.py     # OpenWeather REST calls
│       ├── weather_cache.py       # JSON cache
│       ├── weather_key_manager.py # multi-key rotation
│       └── fine_grained_patcher.py # v2.2.3: in-trip multi-sample fine-grained patching (see below)
├── scripts/                       # internal maintenance scripts (separate from CLI entry points, not part of the public API)
│   ├── __init__.py
│   ├── refresh_inspect_html.py    # batch-regenerate the inspect HTML viewer for existing xlsx
│   ├── backfill_propulsion_energy.py # backfill the `Propulsion Energy (kWh)` column into legacy xlsx (v2.2.3)
│   └── patch_ep_exclude_aux.py       # append the `EP_exclude_aux` column to existing xlsx (v2.2.4)
├── vehicle_params_identificator/  # sub-package 2: C_rr / C_dA parameter identification
│   ├── __init__.py                # exports identify_crr_cda()
│   ├── __main__.py                # python -m entry point
│   ├── config.py                  # physical constants, algorithm parameters, paths
│   ├── data_loader.py             # SRF Logger data download + CSV loading
│   ├── preprocessing.py           # cruise segment extraction
│   ├── identification.py          # linear constraint + K-Means identification
│   ├── run_identification.py      # CLI entry point
│   └── test_identification.py     # synthetic-data unit tests
├── analysis/                      # sub-package 3: shared analysis machinery promoted from data_analysis_workspace (2026-06-11)
│   ├── __init__.py                # re-exports the public API of the three modules below
│   ├── counters.py                # cumulative-counter interpolation at trip endpoints (build_interp / delta / to_utc + COL_* / MIN_DIST_KM)
│   ├── stats.py                   # OLS / HC1-OLS / VIF / standardised-beta fit block / within-group demeaning
│   └── physics.py                 # Arrhenius battery-efficiency model (eta_bat)
└── deprecated/                    # deprecated code (per-make processor)
```

**Public API**:

```python
from jolt_toolkit.report_generator import generate_report, patch_logger
from jolt_toolkit.vehicle_params_identificator import identify_crr_cda
from jolt_toolkit.analysis import (  # shared analysis helpers (sub-project independence)
    build_interp, delta, to_utc, COL_TOTAL, COL_PROP, COL_RECUP, MIN_DIST_KM,
    ols, ols_hc1, vif, fit_block, demean_within, MASS_SPREAD_MIN_KG,
    eta_bat,
)
```

### `analysis/` — shared analysis machinery (sub-project independence, 2026-06-11)

Stable analysis helpers that were being **cross-imported** between
`data_analysis_workspace` sub-projects (e.g. `regen_recovery_factors` used to
`sys.path`-inject and `import` from `ep_temperature_decomposition`) have been
promoted **verbatim** into the versioned toolkit, so each sub-project depends only
on `jolt_toolkit.analysis` and never on another sub-project. The function bodies
are byte-for-byte identical to their origins (only public symbol names, English
docstrings, provenance headers and type annotations were touched).

| Module | Public API | Provenance (repo-relative source) |
|----|----|----|
| `analysis/counters.py` | `build_interp` (was `_build_interp`), `delta` (was `_delta`), `to_utc` (was `_utc`), `COL_TOTAL`, `COL_PROP`, `COL_RECUP`, `MIN_DIST_KM` | `data_analysis_workspace/ep_temperature_decomposition/scripts/ep_temp_decomposition.py` |
| `analysis/stats.py` | `ols`, `ols_hc1`, `vif`, `fit_block` (was `_fit_block`), `demean_within`, `MASS_SPREAD_MIN_KG` | `ols` from `ep_temperature_decomposition`; the rest from `data_analysis_workspace/regen_recovery_factors/scripts/regen_recovery_factors.py` |
| `analysis/physics.py` | `eta_bat` | `research_projects/simulation/models/vehicle_physics.py` (canonical home as of v2.2.4) |

> `demean_within(df, cols, group_col="reg")` is the **only** signature change in
> this promotion: a `group_col` parameter was added (default `"reg"` preserves the
> original hard-coded behaviour exactly). `eta_bat` is self-contained (depends only
> on `numpy`, no module-level constants). The original sub-project scripts continue
> to work and are migrated to import from here separately.

**Analysis figure plotting** (standalone script, not part of the package):

```bash
PYTHONPATH=src python data_analysis_workspace/shared/generate_figures.py --version 2.2.2 [--anon]
```

**Data-availability dashboard** (v2.2.3) — scan a report-database version and render a single self-contained, **offline-interactive** HTML dashboard. Layout is three panels: a left vehicle selector, a middle stat block for the selected vehicle (type/make/model, battery capacity or weight class, data date range, total distance driven, trip/charge/stop counts, per-category day counts for **both** availability bases), and a right **traditional month-calendar** availability view (a vertically-scrolling wrap grid of month blocks, each a "Month YYYY" title + a Monday-first Mo–Su weekday row + a day grid). The calendar tracks **two independent availability bases**, switched by a segmented **Events / Raw data** toggle near the top of the right panel: **Events** (default) = days with processed legs in the generated Excel reports (the report-based detection, unchanged); **Raw data** = days with raw files fetched from SRF on disk (telematics from `raw_telematics/` filenames, logger from the union of `raw_logger_v1/` + `raw_logger_v2/` filenames, charger from `raw_charger/charger_transactions.csv` `start_time`). Raw mode is a pure raw-file view (no union with report data), so the two bases can be compared directly (e.g. LN25NKE has raw logger on 2025-09-29 with no processed legs → visible in Raw mode, absent in Events mode). The raw scan reads only the four named sub-directories, ignores dot-dirs / `*.bak_*` / `validation_figures*` / `raw_telematics_stub`, and drops dates outside `[2024-01-01, today+1]`. The month axis is **fleet-wide** — the global min→max month across *both* bases of *all* vehicles (≈2024-06 → 2026-06), identical for every vehicle and mode, so switching vehicle or toggling basis just re-fills the same blocks (days with no data render as light-grey cells with a dark number; days with data fill with the telematics/logger/charger vertical colour bands and a white day number). All vehicles' data (both bases) is embedded as an inline JSON blob and rendered client-side by vanilla JS (no frameworks/CDN). **Operator overlay** (sourced offline from `configs/plot_config.json`, no SRF API call): the middle panel adds an **Operator** block (trial type — Fixed / Round-robin / "—" — plus the assigned operator, a single coloured operator for fixed vehicles or the compact dated period sequence for round-robin ones, e.g. LN25NKE = DP World → JLP → Welch Transport → WS), and every **data-bearing** calendar day cell gets a 3px border in the colour of the operator who ran the vehicle on that date (`colors.company`); a round-robin day inside a gap between assignment periods gets a neutral grey (`#94a3b8`) border so gaps stay visible, and vehicles with no assignment (e.g. WU70GLV) get no border. A per-vehicle operator legend (hollow rings, to distinguish it from the solid-fill category swatches) lists only the relevant operators plus the neutral entry when applicable, recomputed on vehicle change and Events/Raw toggle. Leg counts and distances de-duplicate overlapping report files on `(start, end, leg-class)`:

```bash
python -m jolt_toolkit.report_generator.data_dashboard --version 2.2.3
# → excel_report_database/2.2.3/data_dashboard.html (open offline by double-click)
# overrides: --db-root <reports root>  --out <html path>
# drill-down: --details all|<REG,REG,…>  → also write detail_<REG>.html beside the dashboard
```

**Per-day drill-down detail pages** (`--details`, `data_dashboard_detail.py`) — for the requested vehicles the dashboard also writes a `detail_<REG>.html` beside it (calendar day cells of those vehicles become links). A detail page is a self-contained, **offline** day-by-day channel viewer built on **vendored uPlot** (JS/CSS inlined from `assets/uplot/`, no CDN): a channel selector (concepts from `CONCEPT_REGISTRY`, incl. a v2.2.7 cumulative **Total distance** / odometer channel in the Motion group), per-day prev/next ◀▶ arrows + day selector, a Logger Low/High resolution toggle, optional trip/charge **event bands** and **event markers** (per-event dSOC / kWh / capacity / EP on the SoC chart), and on the mass chart a dashed **per-event mean-mass line** computed with the report's resolved `mass_agg` (`segment_algorithms._agg_mass`) so it matches the Excel column and the validation figure. Bare-tractor / bobtail events the Excel report excludes are still shown, as a distinct muted-grey `(tractor)` dashed line. Operator periods/colours come from the same offline `build_operator_assignment(plot_cfg)` used by the dashboard.

**Re-render inspect HTML without regenerating figures** (`rerender_inspect.py`) — rewrites every `inspect_*.html` (skipping `*_finetuned`) for a report-database version from the validation figures + `<stem>.boxes.json` sidecars already on disk, by re-running `report_builder._write_html_viewer`. Because it delegates to the in-package viewer it always emits the current v2.2.6 interactive renderer (`renderInteractive`, reading both the new `{boxes, segments, soc_axis}` dict sidecar and legacy flat-list sidecars), so HTML-template fixes ship without an expensive figure regen:

```bash
python -m jolt_toolkit.report_generator.rerender_inspect --version 2.2.5 --db-root <reports root> [--reg <REG>]
```

## Report generation pipeline overview

```
.claude/skills/generate-excel-report/generate_report.py [--debug] [--fast]
  └─ JOLTReportGenerator.generate_report(registration, date_start, date_end)
       │
       ├─ 1. fetch_events()                    → ServerData
       ├─ 2. VEHICLE_CONFIG[reg]               → load vehicle config from JSON
       ├─ 3. [non-fast] fetch Charger/Logger data
       ├─ 4. process FPS legs one by one:
       │      ├─ leg.get_raw_data()            → DataFrame
       │      └─ run_segment_detection()       → (charge segments, discharge segments)
       ├─ 5. _seg_to_row()                     → Excel row tuple
       ├─ 6. _correct_effective_capacity()     → capacity correction post-processing
       ├─ 7. _insert_stop_rows()                → synthesise Stop rows in trip/charge gaps (v2.2.2+)
       ├─ 8. [non-fast] Logger weather data patching
       ├─ 9. _write_excel_report()             → .xlsx file
       └─ 10.[debug] plot_leg_validation()     → PNG validation figures
              [debug] _write_html_viewer()     → HTML viewer
```

## Module responsibilities

| Module | Responsibility |
|----|------|
| `report_generator/_generator.py` | orchestrates the fetch → segment → write main flow; EV branch + the v2.2.2 `is_diesel` branch switch |
| `report_generator/data_fetcher.py` | `fetch_events()` — queries the SRF API to obtain legs and charge events |
| `report_generator/segment_algorithms.py` | unified charge/discharge segmentation algorithm (SOC detection, speed detection, mass merge/split, energy source cascade) — EV path |
| `report_generator/diesel_pipeline.py` | **v2.2.2** `process_diesel_leg()` — SRFLOGGER_V1 Logger channels → trip rows (LFC / VDHR / CVW / CCVS / AMB), used by vehicles with `fuel_type=="DIESEL"` such as WU70GLV |
| `report_generator/report_builder.py` | `_seg_to_row()` — EV segment dict → Excel row; `_insert_stop_rows()` — synthesise Stop rows between trip/charge (v2.2.2); `_write_excel_report()` — formatted .xlsx (three colours: green/red/white); `_write_html_viewer()` — debug HTML viewer. **v2.2.3**: viewer chrome font sizes doubled + sidebar widened; the image sits in a JS-sized stage with an absolutely-positioned overlay layer that renders each figure's `<stem>.boxes.json` annotation boxes (all panels; ghosted by default, solid on hover) — box data is inlined into the HTML (no `file://` fetch), positioned by `figure-fraction × displayed-pixels` with a ha/va anchor transform, then **clamped** inside the displayed image rect so edge-hugging labels never spill out. Reader falls back to the legacy `<stem>.dsoc.json`. **v2.2.6**: auto-detects the sidecar shape — a **dict** `{boxes, segments, soc_axis}` drives the hover redesign (default triangles-only; per-segment full-height hotzone reveals a pinned info box at the SOC bottom-left + that segment's value labels, de-collided); a **flat list** keeps the legacy ghosted-on-hover behaviour (diesel + not-yet-re-painted EV figures) |
| `report_generator/finetune.py` | segmentation post-processing tools. Provides the `MergeOp` / `SplitOp` / `DeleteOp` operation dataclasses and the four public functions `apply_operations()` / `reconstruct_segs_from_xlsx()` / `regenerate_figures()` / `regenerate_inspect_html()`. Working with the operation list produced by manual LLM-vision figure review, it applies merge / split / delete corrections to an already-generated xlsx, producing `*_finetuned.xlsx` + `_finetuned.png` + `_finetuned.html` |
| `report_generator/pedal_histogram.py` | `compute_pedal_histogram()` — EEC2 accelerator / EBC1 brake pedal position histogram (discharge segments only & distance > 10 km) |
| `report_generator/validation_generator.py` | `ValidationGenerator` — standalone post-hoc regenerator of the EV segmentation validation figures + inspect HTML for an existing report directory (e.g. when a report was produced with `--fast`, which skips the inline Logger overlay). **v2.2.3**: Logger speed/mass overlay is rebuilt from the locally saved `raw_logger_*/logger_*.csv` (preferred, no SRF API round-trip; equivalent to `_load_logger_channel`), falling back to the SRF API over the **full** `raw_telematics` date span only when no local Logger CSV exists; and a single call now rewrites the inspect HTML for **every** non-finetuned period xlsx in the directory (`feat/full-range-report` multi-period layout). **v2.2.3**: regeneration runs with `export_dsoc_overlay=True`, so **all** panels' rounded-bbox data labels (dSOC, energy/charger-meter deltas, recuperation deltas, mass labels) are written out as a per-figure `<stem>.boxes.json` sidecar (figure-fraction coords) for the viewer's interactive overlay instead of being baked into the PNG. **v2.2.6**: this EV export now emits the tagged **dict** schema `{boxes (+seg/role/panel), segments, soc_axis}` that drives the viewer's hover redesign. The EV path above runs only for electric vehicles — `regenerate()` detects `fuel_type == "DIESEL"` and routes to `diesel_pipeline.regenerate_diesel_validation()` (rebuilds the 4-panel diesel figures + inspect HTML from local `raw_logger_*` CSVs, `export_overlay=True`), and `regenerate_folder()` processes any sub-dir with `raw_telematics/` **or** `raw_logger*` so mixed EV/diesel fleets are not skipped |
| `report_generator/data_dashboard.py` | **v2.2.3** data-availability dashboard generator. `scan_report_database(db_root, version)` reads the `Report` sheet of every `jolt_report_<REG>_<ds>_<de>.xlsx` (skipping `*_finetuned`) and returns `{REG: {date: set_of_categories}}`; `render_dashboard_html()` emits a single self-contained `data_dashboard.html` (inline CSS, no external assets — opens offline). Three panels: left = vehicle selector; middle = the selected vehicle's stat block (type/make/model, battery capacity or weight class, data date range, total distance, trip/charge/stop counts, per-category day counts for **both** availability bases, plus an **Operator** block); right = a **traditional month-calendar** view (v2.2.3): a vertically-scrolling wrap grid of "Month YYYY" blocks with Monday-first Mo–Su weekday headers, rendered on a **fleet-wide** month axis (`firstMonth`/`lastMonth` = global min/max month across **both** bases of all vehicles, embedded once and shared by every vehicle's calendar). A segmented **Events / Raw data** toggle switches the two independent availability bases without re-flowing the month blocks: **Events** (default) = days with processed legs in the reports; **Raw data** = days with raw files on disk (telematics/logger from `raw_telematics/` + `raw_logger_v1/v2/` filenames, charger from `raw_charger/charger_transactions.csv` `start_time`; only the four named sub-dirs are scanned, dot-dirs / `*.bak_*` / `validation_figures*` / `raw_telematics_stub` ignored and dates outside `[2024-01-01, today+1]` dropped). Each day cell shows its day-of-month number — no data = light-grey (`#f1f5f9`) cell with a dark number, data = the category vertical colour bands (telematics=blue / logger=green / charger=amber, multiple = an equal `to bottom` stripe split) with a white number. Availability: telematics = any leg row that date; **logger (EV + diesel, unified, v2.2.3)** = the **union** of (a) the `SRF Logger Link` cell carrying a hyperlink OR a non-empty value — checked on a **non-read-only** workbook so `cell.hyperlink` is populated (the display value is often blank while only the hyperlink target is set), present in both layouts — and (b) a non-empty pedal accelerator/decelerator histogram OR `Energy based on motor power (kWh)` (EV-only columns, absent from `DIESEL_HEADERS`); the two signals are complementary (some vehicles carry logger only via the link, others only via pedal histograms); charger (EV) = non-empty/non-zero AC/DC/charger-output/peak/avg charging data columns (the unreliable `Charger Link` hyperlink is deliberately not used). Imports `HEADERS`/`DIESEL_HEADERS` to keep signal column names in lock-step; per-row detection goes through each workbook's live header row (robust to both layouts — the EV-only logger/charger columns are simply absent for diesel reports), while the stat block's EV vs diesel split comes from each vehicle's `fuel_type` in `vehicles.json`. **Operator overlay**: `build_operator_assignment()` reads `configs/plot_config.json` (`_load_plot_config()`, no SRF API) → per-vehicle `trial_type` + compact `periods` (`[{c,s,e}]`, ISO bounds; `s`/`e`=`null` → open-ended whole-axis period for fixed vehicles) and fleet-level `operatorColors`/`operatorNames` maps, all embedded in the JSON blob; the JS resolves a date's operator by scanning the few periods and draws a 3px operator-coloured border on data-bearing calendar cells (neutral grey `#94a3b8` for round-robin gaps, none for unassigned vehicles), with a per-vehicle hollow-ring operator legend recomputed on vehicle change and Events/Raw toggle. CLI: `python -m jolt_toolkit.report_generator.data_dashboard --version 2.2.3` (defaults output to `excel_report_database/<version>/data_dashboard.html`; `--db-root` / `--out` overrides; `--details all|<REG,…>` also writes the drill-down `detail_<REG>.html` pages) |
| `report_generator/data_dashboard_detail.py` | Per-vehicle **drill-down detail page** generator (`--details`). `write_detail_pages()` emits a self-contained, **offline** `detail_<REG>.html` per requested vehicle: a uPlot day-by-day channel viewer (vendored `assets/uplot/` JS+CSS inlined, no CDN) with a channel selector, per-day prev/next ◀▶ arrows + day selector, Logger Low/High resolution toggle, optional trip/charge **event bands** and **event markers** (per-event dSOC / kWh / capacity / EP on the SoC chart), and a dashed **per-event mean-mass line** on the mass chart. Channels come from `CONCEPT_REGISTRY` (a `(source, raw_column)` → display-concept catalogue, resolved per vehicle by `resolve_vehicle_concepts`); the **Motion** group carries *Vehicle speed* and (v2.2.7) a cumulative **Total distance** concept (telematics `odometer` km, or high-res `hr_total_vehicle_distance` m→km; logger diesel VDHR `hr total vehicle distance` km — y autoscales as a cumulative counter). `_annotate_segment_mean_mass()` computes the mass line with the report's resolved `mass_agg` (`segment_algorithms._agg_mass` / `resolve_mass_agg`) over the in-window **loaded** clustered telematics (`mass_cluster.notna()`, matching the Excel column) or `> 0` logger readings. Unlike the report, the dashboard also **displays bare-tractor / bobtail events** (~10–11 t) — the readings `cluster_mass_data` drops as tractor-only are recovered via its opt-in `keep_tractor_only_label=True` flag and flagged `seg['massTractorOnly']`, drawn as a muted-grey `(tractor)` dashed line so they read distinctly from loaded mean-mass lines (the report's `Vehicle Mass (kg)` tractor exclusion is unchanged). Reuses the dashboard's `build_operator_assignment(plot_cfg)` for header operator periods/colours. `fetch_uplot()` is a one-off online vendoring helper (assets are otherwise checked in) |
| `report_generator/rerender_inspect.py` | Standalone CLI to **re-render `inspect_*.html`** for a report-database version **without regenerating figures** — re-runs `report_builder._write_html_viewer` against the on-disk validation figures + `<stem>.boxes.json` sidecars (skips `*_finetuned`, owned by report-finetuner). Delegating to the in-package viewer means it always emits the current v2.2.6 interactive renderer (`renderInteractive`, reading both the `{boxes, segments, soc_axis}` dict sidecar and legacy flat-list sidecars). CLI: `python -m jolt_toolkit.report_generator.rerender_inspect --version <X.Y.Z> --db-root <root> [--reg <REG>]` |
| `report_generator/charger_patcher.py` | `ChargerPatcher` — charger data patching tool; fetches charger events from the SRF API and patches the Charger Link into the xlsx |
| `report_generator/logger_patcher.py` | `LoggerPatcher` — Logger data patching tool; fetches Logger legs from the SRF API and patches the Logger Link and weather columns into the xlsx |
| `report_generator/weather_patcher.py` | `WeatherPatcher` — **coarse** (default) standalone weather patching tool; patches weather columns and weather type (Weather Type, e.g. Clear/Clouds/Rain) into an existing xlsx via the OpenWeather API by averaging the **origin + destination** of each leg (quota-friendly; used when there is no Logger data). **Patches driving / trip rows ONLY** (`is_trip_leg`): charge + Stop rows are skipped before their coordinates are collected, so they consume no API calls (≈ halves the unique-location lookups) |
| `report_generator/weather_patch.py` | **Unified weather-patch entry point.** `patch_weather(target, *, mode="coarse", …)` + a `python -m jolt_toolkit.report_generator.weather_patch` CLI. The single place where the default strategy lives: **`mode="coarse"` (default)** → `WeatherPatcher`; **`mode="fine"` (explicit opt-in only, `--fine-grained`)** → `FineGrainedWeatherPatcher`. Default is coarse because fine-grained's per-GPS-point sampling (~17k calls/vehicle, ~220k fleet-wide) trips the OpenWeather subscription into HTTP 429; the origin/dest average is close enough for the standard path |
| `report_generator/weather_fetcher/fine_grained_patcher.py` | **v2.2.3** `FineGrainedWeatherPatcher` — **fine-grained, explicit opt-in only** weather patching: in-trip raw_telematics GPS multi-sampling + 60 s down-sampling + sin/cos circular wind-direction averaging (fixes the old patcher's 359°/1° → 180° arithmetic-mean bug) + `(lat:.2f, lon:.2f, hour_bucket)` ~1 km × 1 h quantised cache key. Like the coarse patcher it patches **driving / trip rows ONLY** (`is_trip_leg`); charge + Stop rows are skipped (they need no weather and would waste quota). **Not the default** (high API volume → 429); reach it via `patch_weather(..., mode="fine")` |
| `scripts/refresh_inspect_html.py` | internal maintenance script: scans `excel_report_database/<ver>/` to regenerate the inspect HTML viewer for existing xlsx (without re-running the SRF API) |
| `scripts/backfill_propulsion_energy.py` | **v2.2.3** internal maintenance script: backfills the `Propulsion Energy (kWh)` column into legacy EV xlsx (line-interpolated differencing of RFMS snapshots) |
| `scripts/patch_ep_exclude_aux.py` | **v2.2.4** post-hoc patch script: appends the `EP_exclude_aux` column = `(propulsion − recuperation) / distance` to existing EV xlsx. Preferentially reads the existing `Propulsion Energy` / `Recuperation Energy` columns in the xlsx, and falls back to recomputing from `raw_telematics/raw_*.csv` when missing/empty. base only, skips `*_finetuned.xlsx`, idempotent overwrite |
| `report_generator/bootstrap.py` | helper initialisation (logging format, working directory location, etc.) |
| `report_generator/data_class.py` | `ServerData` data class |
| `configs/` | `vehicles.json` (vehicle registry), `pipelines.json` (segmentation parameters), `plot_config.json` (plotting colours and vehicle/operation metadata) |
| `vehicle_params_identificator/` | rolling-resistance / aerodynamic-drag parameter identification (C_rr, C_dA) |
| `deprecated/` | deprecated per-make processors (volvo.py, scania.py, renault.py, mercedes.py) |

## Configuration files

### `configs/vehicles.json`

Each vehicle entry:

| Field | Type | Description |
|----|------|------|
| `srf_reg` | `str` | registration name in the SRF API (e.g. `"KY24 LHT"`) |
| `nominal_kwh` | `float` | manufacturer nominal battery capacity (kWh), used for effective capacity range validation (cap_lo/cap_hi) |
| `srf_capacity_kwh` | `float` | SRF platform registered capacity (kWh), from API `fuel_capacity`; the ultimate fallback value for effective capacity and SOC estimate |
| `effective_capacity_kwh` | `float\|null` | effective capacity (kWh) = the **donor-count-weighted average over all reliable report periods** of `effective_capacity_quarterly` (`Σ(kwh·n) / Σn`, reliable = `n ≥ MIN_DONORS`); `null` before any donor-bearing report exists. Written / maintained automatically by `_persist_effective_capacity()` (live) and `capacity_backfill` (from existing reports). The key name is preserved so every reader (PDF range, dashboard, SOC seed) transparently gets the stable fleet-life average. |
| `effective_capacity_quarterly` | `dict\|absent` (EV only) | per-report-period effective-capacity ledger: `{ "YYYYMMDD_YYYYMMDD": {"kwh": float, "n": int} }`, key = the report period string (1:1 with each quarterly report). `n` = donor count (measured non-`soc_estimate` charge/discharge legs that period; charge-preferred, `kwh` = the ΔSOC-weighted donor mean, same definition as `_correct_effective_capacity`'s `avg_eff_cap`). Periods with `n < MIN_DONORS` (=5) are **sparse / unreliable**: excluded from the weighted average, and their stored `kwh` is backfilled to that average (`n` is kept so the sparse period is still identifiable). Absent for diesel and for EVs with no measured donors (e.g. SOC-only Mercedes), which keep their manual `effective_capacity_kwh` untouched. Lets the per-period capacity (battery ageing trajectory) be inspected and the average be recomputed incrementally without re-running reports. |
| `max_torque_nm` | `float\|null` | motor maximum torque (Nm), used for the EEC1 mode of parameter identification; set to `null` for vehicles without Logger data |
| `make` | `str` | vehicle manufacturer |
| `model` | `str` | vehicle model |
| `pipeline` | `str` | the corresponding pipeline key in `pipelines.json` |
| `mass_agg` | `str` (optional) | per-segment vehicle-mass aggregation method override (any of the eight `_agg_mass` methods — `"mean"` / `"median"` / `"iqr_median"` / `"mad_median"` / `"iqr_mean"` / `"mad_mean"` / `"mad_tw_mean"` / `"trimmed_mean"`, v2.2.6); takes precedence over the pipeline-level `mass_agg` (the method semantics are documented under `pipelines.json` below). Use for an individual vehicle that needs a different method from its **shared** pipeline's siblings. Currently set to `"mad_tw_mean"` for **EX74JXW** only (Scania BEV: its telematics GCVW channel both over-reads and *lags* the true load — high-spike clusters of 40–49 t and, right after a load change, a lag plateau the telematics samples *densely* in a short burst while the settled body is sampled *sparsely* over a much longer time. A `median ± 3·MAD` fence centred on the robust median shaves the spikes, then a **time-weighted** mean of the survivors weights each reading by the time it represents — so the brief dense lag burst contributes only its short duration, not its many samples, pulling the value toward the duration-dominant settled body (matching how the 1 Hz Logger averages the same window). `mad_tw_mean` is a refinement of `mad_mean`; without a time axis it degrades to `mad_mean`. A broad per-segment validation against the SRF Logger CVW — 88 driving segments over 21 logger-covered days across both report periods — ranked `mad_tw_mean` ahead of `mad_mean` on both MAE (1990 vs 2268 kg) and RMSE (2798 vs 3255 kg); see the method note under `pipelines.json` below). |
| `speed_col` | `str` | speed column name (e.g. `"wheel_based_speed"` or `"speed"`), used for speed segmentation and kinetic-energy correction |
| `ac_col` | `str` | AC energy counter column name in the telematics (may be omitted for Mercedes, which has no such column) |
| `dc_col` | `str` | DC energy counter column name in the telematics (may be omitted for Mercedes, which has no such column) |
| `total_energy_col` | `str` | total energy column name (see the energy counter relationships below) |
| `moving_energy_col` | `str` | wheel-driving energy column name (may be omitted for Mercedes, which has no such column) |
| `mass_col` | `str` | vehicle mass column name |
| `altitude_col` | `str` | altitude column name (e.g. `"gnss_altitude"`), used for elevation-corrected energy consumption computation |
| `min_cluster_gap_kg` | `float` | minimum mass clustering gap (kg), used by `merge_discharge_by_mass()` to merge same-mass trips |
| `split_long_stops_min` | `float` (optional) | long-stop split threshold (minutes). When present, `merge_discharge_by_mass()` refuses to merge two adjacent same-mass trips if the stationary gap between them is ≥ this value — splitting "drive → long park → drive" into two trips even when mass is unchanged. Omitted (default) = disabled, behaviour byte-identical to before. Currently set to `30` for the Nestlé Volvo line-haul pair (EV73SAL, YK73WFN — sparse point-to-point duty, any park ≥ 30 min is a genuine break) and `45` for urban / regional multi-drop fleets whose 30–45 min band is densely populated by routine delivery dwells (Renault N88GNW; Volvo FM urban rigids AV24LXJ / AV24LXK / AV24LXL; Renault E-Tech T tractor TA70WTL). |

> **Additional diesel fields** (effective when `fuel_type == "DIESEL"`): `leg_source`, `fuel_energy_col`,
> `fuel_rate_col`, `distance_col`, `diesel_lhv_kwh_per_l`, `speed_col_fallback`,
> `ambient_temp_col`, `weight_class_t` —— for a full example and field meanings see §Diesel pipeline (added in v2.2.2) below.

#### SRF telematics energy counter relationships

The energy columns in SRF raw telematics are all **cumulative counters** (Wh); the difference between adjacent rows is the energy change over that interval.
The relationships between the counters (verified empirically on YK73WFN):

```
total_electric_energy_used = electric_energy_propulsion + auxiliary − electric_energy_recuperation_watthours
```

| Counter | Meaning | Includes regen recovery |
|--------|------|----------------|
| `electric_energy_propulsion` | motor driving energy (cumulative) | no (forward drive only) |
| `electric_energy_recuperation_watthours` | regenerative braking recovered energy (cumulative) | — |
| `total_electric_energy_used` | net battery consumption = drive + auxiliary − regen recovery | **already deducted** |
| `total_electric_energy_used_plugged_in_included` | as above, including charger energy fed in | **already deducted** |
| `electric_energy_wheelbased_speed_over_zero` | net consumption while driving (vehicle speed > 0) | **already deducted** |

> In the report, `Energy Change (kWh)` and `Energy Performance (kWh/km)` are based on `total_energy_col`
> (usually `total_electric_energy_used_plugged_in_included`), and are **already the net value after regenerative braking recovery**.
> auxiliary (HVAC, BMS, DC-DC, etc.) accounts for about 5–7% of net consumption (YK73WFN empirical ~70 kWh/10 days).

> **`Propulsion Energy (kWh)` (EV column added in v2.2.3)**: comes from the telematics
> `electric_energy_propulsion` cumulative counter (Wh, monotonically increasing); the two endpoint values are obtained by **linear interpolation** between the nearest RFMS snapshots over the trip time window
> `[Start Time, End Time]`, then differenced / 1000 to convert to kWh. Unlike `Energy Change`: propulsion **does not deduct** regen recovery,
> and **does not include** auxiliary; it is commonly used to back-calculate motor + drivetrain efficiency η_BM. EV only;
> Charge / Stop rows write NaN; the diesel column set does not contain this column. See
> `report_builder._get_propulsion_energy()`.

> **`EP_exclude_aux` (EV column added in v2.2.4, the 49th column of HEADERS; since v2.2.5 the last column is `Operator`)**: the net traction energy consumption efficiency (kWh/km) after removing auxiliary/standstill
> loads (HVAC, low-voltage systems, etc.). The definition can be found in
> `data_analysis_workspace/energy_balance_check/report.md`:
> ```
> EP_exclude_aux = (propulsion − recuperation) / distance = EP − auxiliary / distance
> ```
> Based on the SRF identity `total = propulsion + auxiliary − recuperation`, for a discharge trip
> `EP = |Energy Change| / dist ≈ total / dist`, hence `EP − aux/dist =
> (propulsion − recuperation) / dist`. It directly uses the two trip-level quantities `Propulsion Energy (kWh)` and
> `Recuperation Energy (kWh)`, without depending on solving for aux.
> It can only be computed when both propulsion + recuperation are non-empty for that trip —— this naturally leaves
> EX74JXW / EX74JXY / YN25RSY / YN75NMA (counter NaN/missing) empty, while WU70GLV (diesel)
> uses `DIESEL_HEADERS` which does not contain this column. Charge / Stop rows write NaN.
> **The position is chosen at the end of HEADERS**: the hard-coded column indices of LoggerPatcher / WeatherPatcher
> (temp=38 / wind=41 / link=5 / mass=16 / kin=47 / propulsion=48) are all unaffected.
> See `report_builder._ep_exclude_aux()`; for legacy reports, backfill with
> `scripts/patch_ep_exclude_aux.py`.

> **`Operator` (column added in v2.2.5, the last column of BOTH `HEADERS` (50th)
> and `DIESEL_HEADERS` (26th))**: a single project operator CODE per leg (e.g.
> `JLP`, `SJG`, `HTL`, `NESTLE`, `WJF`, `DP_WORLD`, `KNOWLES`,
> `WELCH_TRANSPORT`, `WS`, `PORT_EXPRESS_DAIMLER`). Resolved by
> `report_generator/operators.py:derive_leg_operator()` via an **SRF-primary**
> cascade: (1) `leg.trip.trial.description` round-robin pattern
> `"JOLT Round Robin: <OP>-<OEM>"` → captured `<OP>` → code — this is the
> per-leg, time-varying signal for *shared / round-robin* vehicles (their
> `vehicle.organisation.name` is the generic umbrella "JOLT Partners"); (2)
> static `vehicle.organisation.name` for *dedicated* single-operator vehicles
> (e.g. `"JOLT Nestle-Volvo"` → `NESTLE`, `"William Jackson Food"` → `WJF`); (3)
> `vehicles.json` config fallback (`operators` time-ranged list or `operator`
> string, currently absent → no-op); (4) None. The cascade is memoised per
> report by the fetch-free `leg.trip.uri`. One company == one code (a dedicated
> vehicle reuses an existing round-robin token rather than minting a parallel
> code). Stop rows carry the operator from the neighbouring leg
> (`_stop_row_from_neighbours`). **The position is at the END of both header
> sets**, so every hard-coded column index (LoggerPatcher / WeatherPatcher /
> `_generator._IDX_*`, all ≤ 48 for EV) is unaffected; EV rows get the operator
> from the FPS loop in `_generator`, diesel rows from `process_diesel_leg`.

#### Three-tier battery capacity model

| Capacity | Source | Use | Field |
|------|------|------|------|
| **Nominal Capacity** | manufacturer datasheet | `cap_lo`/`cap_hi` range validation (`nominal × 0.5 ~ 2.0`) | `nominal_kwh` |
| **SRF Platform Capacity** | SRF API `fuel_capacity` | the ultimate fallback value for effective capacity and SOC estimate | `srf_capacity_kwh` |
| **Effective Capacity** | telematics data analysis | SOC estimate fallback (`delta_soc × effective_capacity`); the capacity value actually used in the report | `effective_capacity_kwh` (donor-weighted average over reliable periods) + `effective_capacity_quarterly` (per-period ledger) |

**Effective Capacity computation priority** (implemented in `_correct_effective_capacity()`):
1. **ΔSOC-weighted mean** of the non-soc_estimate effective capacity of charge segments (preferred)
2. **ΔSOC-weighted mean** of the non-soc_estimate effective capacity of discharge segments (alternative)
3. `srf_capacity_kwh` (fallback, e.g. when Mercedes has no energy counter columns)

**Within-donor-set aggregation — ΔSOC-weighted / combined-ratio (v2.2.7)**: a donor segment's implied capacity is `C_i = |ΔE_i| / (|ΔSOC_i|/100)`. SOC is integer-% quantised, so `C_i` is noisy **and upward-biased** for small `|ΔSOC|` (`σ_C/C ≈ 0.5/|ΔSOC|`, and by Jensen `E[1/ΔSOC] > 1/ΔSOC`); a **plain mean** of donor `C_i` is therefore inflated whenever the donor pool contains small-ΔSOC legs. Every within-donor-set aggregation (the per-period donor capacity in `_period_capacity_from_rows()`, the step-1 global/window donor means and the step-2 inlier-replacement mean in `_correct_effective_capacity()`, and — by delegation — `capacity_backfill._read_report_donor_capacity()`) uses the **ΔSOC-weighted mean** `C_eff = Σ(C_i·|ΔSOC_i|) / Σ|ΔSOC_i| = 100·Σ|ΔE_i| / Σ|ΔSOC_i|` (the combined-ratio estimator, helper `_soc_weighted_cap()`) instead of the plain mean. It uses all data (no arbitrary ΔSOC cutoff), smoothly down-weights the noisy short legs, and never divides by a single small ΔSOC — removing the small-ΔSOC inflation entirely. Verified on AV24LXJ discharge donors (n≈7.7 k): plain mean = 304.9, ΔSOC-weighted = 298.1 (near the ~297 nominal; the ≤2 % legs average 318.5 vs 291.0 for the ≥15 % legs, showing the bias). *Rejected alternatives*: a hard `|ΔSOC| ≥ X %` cutoff (threshold-sensitive — ≥5 % is fine but ≥10 % over-restricts and drifts, and discards data) and `ΔSOC²`/inverse-variance weighting (over-weights the largest legs and drifts low). The **charge-preferred-over-discharge** donor priority, the physical range gate, and the cross-quarter donor-**count**-weighted average (`_recompute_weighted_capacity`, `Σ(kwh·n)/Σn`) are unchanged — only the within-donor-set mean changed. Charge-rich vehicles barely move (their charge donors are all large-ΔSOC); the fix mainly corrects the discharge-fallback path and any small-ΔSOC contamination.

**Time-local capacity (v2.2.4)**: for long / full-range reports a single whole-period mean ignores battery ageing and seasonal temperature drift. The replacement capacity for each `soc_estimate` segment is therefore computed from the donor capacities in a **±`CAP_WINDOW_HALF_DAYS` (15 day, ≈ 1 month) window** around that segment's start time, keeping the charge-preferred-over-discharge priority **within the window**. If the window has no donors it widens progressively (doubling the half-width until donors appear or it covers the whole period — full coverage = the legacy global mean), then falls back to `fallback_kwh`. Short reports (≤ 3 months) span less than the widened window quickly, so they behave almost identically to pre-v2.2.4. The within-report `_correct_effective_capacity()` time-local logic (step 1 / step 2) is unchanged; only what gets *persisted* to `vehicles.json` changed (below).

**Persistence (per-period weighted-average ledger, v2.2.6+)**: `effective_capacity_kwh` used to be **overwritten** by each run's single whole-period mean, so the stored value drifted with whichever period was generated last and the battery's ageing trajectory was lost. It is now a **merge**: after generation, the report period's donor-based capacity `(kwh, n)` — `kwh` = the **ΔSOC-weighted** donor mean (see the within-donor-set block above), `n` = measured (non-`soc_estimate`) charge-preferred / discharge donor count, computed by `_period_capacity_from_rows()` on the corrected rows **before** Stop-row insertion — is written to `effective_capacity_quarterly[period_key]`, then `effective_capacity_kwh` is recomputed as the **donor-count-weighted average over all reliable periods** (`n ≥ MIN_DONORS`, default 5) via `_recompute_weighted_capacity()`. Sparse periods (`n < MIN_DONORS`) are excluded from the average and their stored `kwh` is backfilled to it (`n` kept). Fallback periods (no donor, e.g. SOC-only Mercedes) are not written and never overwrite the manual scalar. `capacity_backfill` (`python -m jolt_toolkit.report_generator.capacity_backfill --report-db excel_report_database/<ver>`) reproduces the exact same ledger from existing `.xlsx` reports without re-running them (it reads the `Report` sheet's `Battery Capacity (kWh)` / `SOC Change (%)` / `Energy Source` columns and reuses `_period_capacity_from_rows`; the `isinstance(src, str)` + `cap > 0` donor guard drops Stop rows, whose `=NA()` cells openpyxl `data_only` reads as `0`).

**SOC estimate capacity selection priority** (`_generator`): `effective_capacity_quarterly[this_period].kwh` when this period is reliable (`n ≥ MIN_DONORS`) > `effective_capacity_kwh` (the weighted average) > `srf_capacity_kwh` > `nominal_kwh`. This seeds each period's SOC-estimate legs with that period's own capacity; the per-leg time-local correction then supersedes it, so this choice only affects the last-resort fallback when a window has no donor at all (measured-leg values are unaffected).

**Computation flow**:
1. When the segmentation algorithm detects a charge/discharge event, it preferentially computes `delta_energy` from the AC/DC/total_energy columns
2. If the energy columns are unavailable (e.g. Mercedes), it estimates with `delta_soc × (effective_capacity_kwh or srf_capacity_kwh)` (`energy_source='soc_estimate'`)
3. After report generation, `_correct_effective_capacity()` computes the effective capacity by the charge-first logic, replacing the values of soc_estimate segments
4. The period's donor-based capacity is then merged into `effective_capacity_quarterly` and the weighted average recomputed back into `effective_capacity_kwh` (telematics donor source only; never overwrites the fallback / manual scalar) — see **Persistence** above

### `configs/pipelines.json`

Each pipeline entry contains:

| Group | Parameter | Description |
|------|------|------|
| *(top level)* | `merge_by_mass` | **bool, default `true`**. When `false`, `merge_discharge_by_mass` is skipped, preserving the trip boundaries carved out by `split_discharge_by_mass`. Applicable to vehicles whose mass signal is locked (a single value) or whose real load fluctuation falls within the same `min_cluster_gap_kg` bucket —— otherwise adjacent trips would be incorrectly merged into a single over-long In Transit because they share the same dominant cluster. Pipelines currently set to `false` in the fleet: `scania_speed_00` (EX74JXW), `scania_speed_01` (EX74JXY), `volvo_speed_03` (KY24LHT), `volvo_speed_04` (CMZ6260) |
| *(top level)* | `trip_endpoint_anchor` | **str, default `"first_motion"`** (backward compatible). Optional `"zero_speed"`: after split + merge + duration filtering, extend the trip start/end times outward to the nearest v == 0 sample (not exceeding `max_extend_minutes` minutes), in order to make trip endpoints on a low-frequency telematics heartbeat (e.g. the Scania 10 min grid) land on real zero-speed moments rather than high-speed transients such as 76 km/h. In zero_speed mode, the `Average Speed (km/h)` column uses the cumulative duration of the in-trip v > `speed_threshold_kmh` sub-interval as denominator (provided by the new `motion_duration_s` field in the seg dict), avoiding zero-speed tails diluting the speed. Pipelines in the fleet currently with zero_speed enabled: `scania_speed_00` (EX74JXW), `scania_speed_01` (EX74JXY), `volvo_speed_04` (CMZ6260) |
| *(top level)* | `max_extend_minutes` | **float, default `5.0`**. Effective only when `trip_endpoint_anchor=="zero_speed"`. The upper limit (minutes) of the endpoint extension window; if no v == 0 sample is encountered before the window is exceeded, it silently falls back to the first_motion endpoint |
| *(top level)* | `mass_agg` | **str, default `"mean"`** (v2.2.6). Per-segment vehicle-mass aggregation method, shared by the Excel `Vehicle Mass (kg)` column, the validation-figure Panel 4 annotation and the finetune recompute — all operating on the same window → valid (> 0) → moving-only (speed > `MOVING_SPEED_THRESHOLD_KMH`, falling back to all-valid when fewer than two moving samples) sample filter, so the figure and report agree. `"mean"` = arithmetic mean (legacy, bit-for-bit unchanged); `"median"` = plain median (matches the diesel pipeline `_trip_metrics`); `"iqr_median"` = Tukey-fenced median (drop samples outside `[q1 − 1.5·IQR, q3 + 1.5·IQR]`, then median of the inliers; when IQR == 0 the fence is skipped, as the median already ignores a minority spike) — robust to a transient telematics weight spike (e.g. a ~49 t reading on a true ~30 t trip); `"mad_median"` = MAD-fenced median (keep samples within `median ± _MAD_K·MAD` — raw median absolute deviation, `_MAD_K` = 3 — when MAD > 0 and ≥ 2 survive, else keep all, then median of the survivors) — because the fence is centred on the robust median rather than on the quartiles, it shaves a dense central body's one-sided HIGH-spike tail that the IQR fence leaves in (a cluster of spikes pins `q3`, so the `q3 + 1.5·IQR` fence stays too wide and the spikes survive); strengthens high-outlier rejection over `iqr_median` without ever dipping below the body. The two fences also have **mean** variants: `"iqr_mean"` and `"mad_mean"` apply the identical IQR / MAD inlier fence (so their kept set — and hence the `Vehicle Mass CV` — is byte-identical to the `*_median` sibling) but take the **mean** of the survivors instead of the median. When the cleaned body still carries a high-side *lag* / over-read tail (telematics that lags the true load, so even the cleaned median sits above the settled body) the mean reads *below* the median — useful for a vehicle whose telematics over-reads and lags. `"mad_tw_mean"` shares the `mad_mean` MAD fence but takes a **time-weighted** mean of the survivors (trapezoidal — each sample weighted by the time interval it represents, half the gap to each neighbour). Where the telematics is *bursty* — dense readings during a short transient (a lag plateau right after a load change) but sparse readings over the much longer settled cruise — count-weighting over-counts the dense burst; time-weighting lets it contribute only its short duration, pulling the value toward the duration-dominant settled body (the same way a uniform 1 Hz Logger averages the window). It requires a per-sample time axis threaded from `eventDatetime` (or the logger index / a numeric seconds axis) and **degrades exactly to `mad_mean` without one**, so it is always safe to select. `"trimmed_mean"` is the symmetric 20 % trimmed mean (drop the lowest & highest 20 % of samples, mean the central 60 %; matches `scipy.stats.trim_mean`), a two-sided robust reference. Each method is a two-step recipe — a fence (`mean`/`median` keep all; `iqr_*` Tukey 1.5·IQR; `mad_*` median ± 3·MAD; `trimmed_mean` 20 % per tail) then an estimator (median, mean, or — for `mad_tw_mean` — a time-weighted mean); the shared fence helpers (`_iqr_inliers` / `_mad_inliers` / `_trimmed_inliers`) keep the median and mean variants of a fence bit-identical in their inlier set (`mad_tw_mean` reuses the `mad_*` fence, so its `Vehicle Mass CV` equals `mad_mean`'s). Unknown value → `"mean"` with a warning. A vehicle-level `mass_agg` in `vehicles.json` overrides the pipeline value (precedence: **vehicle > pipeline > default**). Currently `"iqr_median"` on `volvo_speed_00` (AV24LXJ / AV24LXK / AV24LXL — the trio share this one pipeline), `volvo_speed_01` (EV73SAL), `volvo_speed_02` (YK73WFN), `scania_speed_00` (EX74JXW), `scania_speed_01` (EX74JXY), `mercedes_speed` (YN25RSY), `daf_speed_00` (LN25NKE) and `renault_speed` (N88GNW / TA70WTL — also shared with T88RNW, which has no GCVW signal so its mass is `nan` regardless); all other pipelines keep the default `"mean"`. Two routes feed this list. (1) **Aggregate-noise** (data-driven from the 2.2.5 reports' per-trip `Vehicle Mass CV`, the within-trip dispersion of the kept moving-valid GCVW samples): the materially-noisy vehicles carry CV > 5 % on ≥ 23 % of driving trips (median CV ≥ 2.3 %) — `scania_speed_00`, `scania_speed_01`, `mercedes_speed`, `daf_speed_00` (plus `volvo_speed_00`, set for AV24-trio consistency). (2) **Weakly-dominant opt-in**: `volvo_speed_01`, `volvo_speed_02` and `renault_speed` stay below 6 % of trips with CV > 5 % (median CV ≤ 0.6 %), i.e. clean on the aggregate metric, but a per-segment reconstruction of user-flagged validation figures exposed individual driving segments whose mean is dragged off by a transient GCVW spike (N88GNW 2025-06-05 and TA70WTL 2025-11-03: `iqr_median` recovers the robust mass by up to ~9 % on the affected segment while moving the clean majority by only ~0.2 %). Since `iqr_median` ≈ `mean` on clean segments and is strictly more robust on spiked ones, it is weakly dominant and safe to adopt for these speed pipelines. (3) **Per-vehicle override**: **EX74JXW** carries a vehicle-level `mass_agg: "mad_tw_mean"` in `vehicles.json` that overrides its `scania_speed_00` pipeline default (`iqr_median`). Its telematics GCVW both **over-reads and lags** the true load: high-spike clusters of 40–49 t on some segments, and — right after a load change — a lag plateau the telematics samples *densely* in a short burst while the settled body is sampled *sparsely* over a much longer time. EX74JXW telematics is strongly **bursty** (within driving segments the inter-sample gap has median 15 s but 46 % of gaps exceed 30 s, often ~600 s, interspersed with dense ~5 s bursts; CV(Δt) ≈ 1.4), so count-weighting over-weights whichever cluster the telematics happened to sample densely — and that is exactly the transient lag plateau. The flagship case 2025-10-11 13:41: the 26.7 t plateau is a dense 21-sample burst over **~106 s** at the trip's end, while the 20–21 t settled body spans **~2700 s** sparsely; count-weighted `mad_mean` reads 24.9 t, time-weighted `mad_tw_mean` reads 23.1 t (Logger 20.0 t). The method was settled by a **broad** per-segment validation against the SRF Logger CVW — every driving segment with Logger weight coverage in both report periods, **88 scorable segments over 21 days** (38 empty-load segments where the Logger reads ~11 t but no telematics method can see the load were excluded and reported separately). `mad_tw_mean` vs `mad_mean` over those 88 segments: MAE **1990** vs 2268 kg (−13 %), RMSE **2798** vs 3255, bias **+1402** vs +1768, and 30 vs 35 segments off by > 2 t (9 fixed, 4 newly off — net −5). The win is broad-based (it survives dropping the top-5 individual gains) and concentrated on the lag-plateau segments (e.g. 2025-10-12 20:28 31.1 → 23.6 t, Logger 21.2; 2025-10-13 20:55 29.6 → 22.8 t, Logger 20.6) while heavy trips are preserved (2025-10-13 11:24 stays 34.3 t) and the empty-load class is unchanged (irrecoverable for any telematics method). The trade is a handful of local regressions where the *wrong* cluster spans the longer time (2025-10-30 10:51 26.2 → 23.1 t, Logger 26.0) — outnumbered ~2:1 by the fixes. Time-weighting is also the more apples-to-apples comparison: the Logger truth is itself a (uniform 1 Hz) time-average, so weighting the telematics by duration matches its definition. The saga that led here: `mean` (49 t spikes inflate) → `iqr_median` (good but a spike cluster pins `q3` and drags it high) → `prefer_logger_mass` (reverted — telematics preferred by design) → `low_cluster` (over-corrected, dipped below the body) → `mad_median` → `mad_mean` (count-weighted mean of the MAD survivors) → **`mad_tw_mean`** (time-weighted, to stop a short dense lag burst dominating the mean). The telematics still cannot recover this vehicle's empty-load segments — the Logger CVW remains the cleaner source — but the telematics body is preferred by design and `mad_tw_mean` is its most reliable robust estimator. (Switching `mad_tw_mean ↔ mad_mean ↔ iqr_mean ↔ mad_median` later is a one-line `vehicles.json` change.) |
| `charge_params` | `plateau_window_min` | minimum plateau duration (minutes) |
| | `min_soc_rise` | minimum SOC rise percentage to be recognised as charging |
| | `min_energy_kwh` | minimum energy increase to be recognised as charging (kWh) |
| `discharge_params` | `plateau_window_min` | minimum plateau duration (minutes) |
| | `soc_rise_abort_pct` | the SOC-recovery threshold that aborts a discharge segment (%) |
| | `min_soc_drop` | minimum SOC drop percentage |
| | `min_energy_kwh` | minimum energy loss (kWh) |
| `speed_params` | `speed_threshold_kmh` | the driving-judgement speed threshold (km/h), speed branch only |
| | `min_stop_duration_min` | minimum stop duration (minutes); below this value it is bridged |
| | `min_trip_duration_min` | minimum trip duration (minutes); below this value it is discarded |
| | `min_soc_drop` | minimum SOC drop percentage (the speed branch uses a more lenient value) |
| | `min_energy_kwh` | minimum energy loss (kWh) (the speed branch uses a more lenient value) |

## Segmentation algorithms

The segmentation algorithm is the core of the report pipeline; it is responsible for identifying charge and discharge (driving) events from sparse telematics data.
All algorithms are implemented in `segment_algorithms.py`, with parameters loaded from `configs/pipelines.json`.

### Algorithm overview and flow

```
run_segment_detection(df_raw, reg, suffix, ...)
  │
  ├─ read VEHICLE_CONFIG[reg] → column name mapping, nominal_kwh
  ├─ read PIPELINE_CONFIGS[pipeline] → segmentation parameters
  │
  ├─ branch == 'soc':
  │   ├─ find_charge_segments_by_soc(df_raw, **charge_params)
  │   └─ find_discharge_segments_by_soc(df_raw, **discharge_params)
  │
  ├─ branch == 'speed':
  │   ├─ find_charge_segments_by_soc(df_raw, **charge_params)
  │   ├─ find_discharge_segments_by_speed(df_raw, **speed_params)
  │   │   └─ find_speed_trips() → trip time windows
  │   └─ [fallback] find_discharge_segments_by_soc() — if the speed column is missing/all zeros
  │
  ├─ cluster_mass_data(df_raw) → add mass_cluster column
  ├─ split_discharge_by_mass() — split where the cluster label changes
  ├─ merge_discharge_by_mass() — merge adjacent discharge segments with the same cluster (skipped when pipeline `merge_by_mass=false`)
  └─ [debug] plot_leg_validation() → 4-panel PNG validation figure
```

### 1. Charge detection (`find_charge_segments_by_soc`)

Detects charge events with continuously rising SOC from sparse telematics data.

**Algorithm steps**:

1. **Data preprocessing**: parse the time, SOC, and AC/DC energy columns as numeric; SOC=0 is treated as invalid (set to NaN)
2. **SOC-rise block detection**: scan the SOC sequence, marking adjacent increasing regions as candidate charge blocks
3. **Block merging**: if the gap between adjacent rising blocks is ≤ `plateau_window_min` with no SOC drop, they are merged into the same charge segment (eliminating brief SOC stalls/minor fluctuations during charging)
4. **Segment validation**:
   - delta_SOC ≥ `min_soc_rise` → confirmed as charging
   - delta_energy ≥ `min_energy_kwh` → enough energy
   - effective_capacity within the [cap_lo, cap_hi] range → capacity reasonable
5. **Energy computation**:
   - first choice: AC+DC column difference → `energy_source='ac_dc'`
   - alternative: SOC × nominal_kwh estimate → `energy_source='soc_estimate'`
6. **Charge type determination**: AC increment ≥ 0.5 kWh and DC increment ≥ 0.5 kWh → `Mix charge`; AC only → `AC charge`; DC only → `DC charge`; no AC/DC data → `estimated`
7. **effective_capacity**: `delta_energy_kwh / (delta_soc_pct / 100)`

**Parameters** (configured via the `charge_params` of `pipelines.json`):

| Parameter             | Function default                               | pipelines.json default | Description                                                                 |
| -------------------- | ---------------------------------------------- | ------------------ | --------------------------------------------------------------------------- |
| `plateau_window_min` | 60.0                                           | 60                 | merge window (minutes): merge if the gap between adjacent SOC-rise blocks is ≤ this value |
| `min_soc_rise`       | 5.0                                            | 5.0                | minimum SOC rise percentage (%); candidate segments below this value are discarded |
| `min_energy_kwh`     | 5.0                                            | 5.0                | minimum charge energy (kWh); candidate segments below this value are discarded |
| `cap_lo`             | None                                           | —                  | effective capacity lower bound (kWh), set by `run_segment_detection` to `nominal_kwh × 0.5` |
| `cap_hi`             | None                                           | —                  | effective capacity upper bound (kWh), set by `run_segment_detection` to `nominal_kwh × 2.0` |
| `ac_col`             | `'battery_pack_ac_watthours'`                  | —                  | AC energy cumulative column name (injected from vehicles.json) |
| `dc_col`             | `'battery_pack_dc_watthours'`                  | —                  | DC energy cumulative column name (injected from vehicles.json) |
| `moving_energy_col`  | `'electric_energy_wheelbased_speed_over_zero'` | —                  | moving energy column name |
| `nominal_kwh`        | None                                           | —                  | nominal battery capacity (kWh), used as the SOC estimate fallback (injected from vehicles.json) |

### 2. Discharge detection

Discharge segmentation has two parallel algorithms; the pipeline-configured `branch` field decides which is used. The two algorithms output an identical schema, so downstream modules need not distinguish them.

#### 2.1 Based on SOC change (`find_discharge_segments_by_soc`) — soc branch

Detects discharge/driving events with continuously falling SOC from sparse telematics data.

**Algorithm steps**:

1. **Data preprocessing**: same as charge detection; additionally parse the total_energy, moving_energy, odometer, and GPS columns
2. **SOC-drop block detection**: scan the SOC sequence, marking adjacent decreasing regions as candidate discharge blocks
3. **Block merging**: if the gap between adjacent dropping blocks is ≤ `plateau_window_min` **and** the maximum SOC recovery within the gap is < `soc_rise_abort_pct`, they are merged (eliminating brief SOC plateaus during driving, such as waiting at a red light)
4. **Abort condition**: SOC recovery within the gap ≥ `soc_rise_abort_pct` → treated as charging intervention, not merged
5. **Segment validation**:
   - |delta_SOC| ≥ `min_soc_drop` → enough SOC drop
   - |delta_energy| ≥ `min_energy_kwh` → enough energy consumption
   - effective_capacity within the [cap_lo, cap_hi] range
6. **Energy source cascade** (priority high to low):
   - `total_energy_col` difference → `energy_source='total_energy'`
   - `moving_energy_col` difference → `energy_source='moving_energy'`
   - SOC × nominal_kwh estimate → `energy_source='soc_estimate'`
7. **delta_moving_kwh**: independent of the main energy source, always computed from moving_energy_col (≥ 0 or None)

**Parameters** (configured via the `discharge_params` of `pipelines.json`):

| Parameter | Function default | pipelines.json default | Description |
|------|-----------|----------------------|------|
| `plateau_window_min` | 60.0 | 15 | merge window (minutes): attempt to merge if the gap between adjacent SOC-drop blocks is ≤ this value |
| `soc_rise_abort_pct` | 3.0 | 3.0 | SOC-recovery abort threshold (%): do not merge if SOC recovery within the gap ≥ this value |
| `min_soc_drop` | 10.0 | 5.0 | minimum SOC drop percentage (%) |
| `min_energy_kwh` | 2.0 | 2.0 | minimum energy consumption (kWh) |
| `cap_lo` | None | — | effective capacity lower bound (kWh) |
| `cap_hi` | None | — | effective capacity upper bound (kWh) |
| `total_energy_col` | `'total_electric_energy_used_plugged_in_included'` | — | total energy cumulative column name (injected from vehicles.json) |
| `moving_energy_col` | `'electric_energy_wheelbased_speed_over_zero'` | — | moving energy column name |
| `nominal_kwh` | None | — | nominal battery capacity (kWh) |

> Note: the `plateau_window_min` function default is 60 minutes, but all pipelines in `pipelines.json` are uniformly configured to **15 minutes** (used in conjunction with the subsequent `merge_discharge_by_mass`).

#### 2.2 Based on vehicle speed (`find_discharge_segments_by_speed`) — speed branch

Enabled when the pipeline's `branch` is `"speed"`. Trip boundaries are defined by vehicle speed (more precise than SOC),
while the SOC and energy columns are used only to compute segment metrics, not to determine boundaries.

**Trip boundary detection** — `find_speed_trips()`:

1. **Speed parsing**: NaN speed values are filled with 0; if the speed column is all ≤ `speed_threshold_kmh` there are no trips
2. **Driving-block detection**: continuous regions with speed > `speed_threshold_kmh` are raw driving blocks
3. **Bridging**: a zero-speed gap between two driving blocks < `min_stop_duration_min` → merged into the same trip (eliminating red lights, brief stops)
4. **Filtering**: trip duration < `min_trip_duration_min` → discarded (sensor noise or shunting movement)

**Energy metric computation** — `find_discharge_segments_by_speed()`:

1. Call `find_speed_trips()` to obtain trip time windows
2. For each trip window:
   - extract the first/last SOC reading within the window; when there is no SOC within the window, search outward to the window boundaries for the nearest value
   - SOC change filter: |delta_SOC| < `min_soc_drop` → skip
   - energy source cascade (same as the 2.1 SOC discharge detection): total_energy → moving_energy → soc_estimate
   - |delta_energy| < `min_energy_kwh` → skip
   - effective_capacity range validation
3. The output schema is **identical** to that of `find_discharge_segments_by_soc()`

**Fallback**: if the speed column is missing or all zeros (no trips), an empty list is returned; `run_segment_detection` automatically falls back to the 2.1 SOC-based `find_discharge_segments_by_soc()`.

**Parameters** (configured via the `speed_params` of `pipelines.json`):

| Parameter | Function default | pipelines.json default | Description |
|------|-----------|----------------------|------|
| `speed_col` | `'wheel_based_speed'` | — | speed column name (injected from `speed_col` of vehicles.json) |
| `speed_threshold_kmh` | 1.0 | 1.0 | driving-judgement speed threshold (km/h) |
| `min_stop_duration_min` | 5.0 | 5.0 | minimum stop duration (minutes); zero speed below this value is bridged |
| `min_trip_duration_min` | 2.0 | 2.0 | minimum trip duration (minutes); below this value it is discarded |
| `min_soc_drop` | 1.0 | 1.0 | minimum SOC drop percentage (%) (speed-defined boundaries are more precise, so a more lenient value is used) |
| `min_energy_kwh` | 1.0 | 1.0 | minimum energy loss (kWh) |
| `trip_endpoint_anchor` | `'first_motion'` | (injected at the pipeline top level) | trip endpoint anchoring strategy. `first_motion` (default) = the first/last in-trip v > threshold sample; `zero_speed` = extend the endpoint outward to the nearest v == 0 sample, not exceeding `max_extend_minutes`, falling back if exceeded. In zero_speed mode it additionally writes `motion_duration_s` (cumulative duration of the v > threshold sub-interval) into the seg dict, which `_seg_to_row` uses in place of the endpoint difference as the denominator of Average Speed. |
| `max_extend_minutes` | 5.0 | (injected at the pipeline top level) | the upper limit (minutes) of the endpoint extension window, effective only in zero_speed mode |
| `cap_lo` / `cap_hi` | None | — | effective capacity range (injected from run_segment_detection) |
| `total_energy_col` | `'total_electric_energy_used_...'` | — | total energy column name |
| `moving_energy_col` | `'electric_energy_wheelbased_...'` | — | moving energy column name |
| `nominal_kwh` | None | — | nominal battery capacity |

### 3. Mass post-processing

After discharge segmentation is complete, the mass data of the whole leg is first clustered, then the segments are split and merged based on the cluster labels.

#### 3.0 Mass clustering (`cluster_mass_data`)

Performs 1D clustering on the mass column of the telematics data, adding a `mass_cluster` column to `df_raw`.

**Typical clustering result**:
- cluster 0 ≈ 10-12 t — tractor kerb weight (no trailer)
- cluster 1 ≈ 18-20 t — tractor + empty trailer
- cluster 2+ ≈ 30-42 t — tractor + loaded trailer (possibly several load levels)

**Algorithm steps**:

1. Extract all valid (non-NaN, > 0) readings from the mass column
2. **Cluster boundaries/means are derived from *moving* readings only** (v2.2.4; see below). Sort those by value; split into separate clusters where the difference between adjacent sorted values is ≥ `min_cluster_gap_kg`
3. Compute the mean of each cluster; if the means of adjacent clusters differ by < `min_cluster_gap_kg`, merge them
4. Number the clusters by mean from smallest to largest: 0 = lowest mass
5. Assign **every** valid reading (moving **and** stationary) to the nearest cluster mean

Rows with NaN / invalid mass values keep `mass_cluster` as NaN and do not participate in the subsequent merge/split decisions.

**Moving-only cluster means + `mass_moving` (v2.2.4)**: the J1939 gross-combination-weight is unreliable while the vehicle is stationary (loading/unloading transients, default broadcasts) and pollutes the clustering. Cluster boundaries and means are therefore computed using only readings taken while `speed > speed_threshold_kmh` (NaN speed counts as not-moving). A new boolean column `mass_moving` marks the valid+moving rows so that downstream consumers can prefer them. Graceful degradation:
- if the whole leg has **no** moving mass readings (sparse-mass vehicles), cluster on all valid readings instead (legacy behaviour) and log an info message;
- if `speed_col` is absent (or not passed), `mass_moving` equals the "valid mass" mask and the behaviour is identical to pre-v2.2.4.

This is the clustering-level half of the standstill-mass change; the segment-level half is in `_get_seg_dominant_cluster` (§3.2) which **votes with moving rows first** and falls back to stationary votes only when a segment window contains no moving mass rows. The per-leg `Vehicle Mass (kg)` / `Vehicle Mass CV` columns (`report_builder._get_vehicle_mass`) follow the same rule: the leg mean/CV use moving samples (`speed > threshold`) when ≥ 2 are available, otherwise fall back to all `> 0` samples; if the speed column is absent the behaviour is unchanged. The diesel `_trip_metrics` CVW median applies the same moving-only-with-fallback rule (§Diesel).

**Parameters**:

| Parameter | Default | Description |
|------|--------|------|
| `mass_col` | `'gross_combination_vehicle_weight'` | mass column name |
| `min_cluster_gap_kg` | 2000.0 | minimum mass difference between clusters (kg): if the means of two clusters differ by < this value, they are merged into the same cluster |
| `speed_col` | `None` (caller passes `'wheel_based_speed'`) | speed column used to identify moving readings; `None`/absent → legacy all-readings behaviour |
| `speed_threshold_kmh` | `MOVING_SPEED_THRESHOLD_KMH` (1.0) | speed above which a reading counts as moving; aligned with the pipeline `speed_threshold_kmh` convention |
| `keep_tractor_only_label` | `False` | opt-in (v2.2.7). When `True`, the returned copy carries an extra boolean column `mass_tractor_only` marking exactly the readings that step 4 blanks from `mass_cluster` as tractor-only (cluster 0 mean < `TRACTOR_ONLY_MAX_KG`), so a caller can **recover** those report-excluded ~tractor-weight readings without changing the segmentation. Default (`False`) adds no column and leaves the output byte-identical to every existing caller (the report pipeline, `finetune`). Currently used only by `data_dashboard_detail._annotate_segment_mean_mass` to still *display* bare-tractor / bobtail events on the dashboard mass chart. |

#### 3.1 Mass splitting (`split_discharge_by_mass`)

Splits a discharge segment at the time points where the mass cluster label changes (loading/unloading event detection).

**Precondition**: `df_raw` already has a `mass_cluster` column added via `cluster_mass_data()`.

**Algorithm steps**:

1. For each discharge segment, detect `mass_cluster` label change points within its time window
2. A label change point = the time a loading/unloading event occurs
3. Split the segment into sub-segments at the change points (`_split_seg_at_times`)
4. The SOC of sub-segments is linearly interpolated from the raw data; energy is allocated from the parent segment in proportion to SOC
5. Sub-segments that do not satisfy `min_soc_drop` or `min_energy_kwh` are discarded

**Parameters**:

| Parameter | Default | Description |
|------|--------|------|
| `min_soc_drop` | 5.0 | minimum SOC drop of a sub-segment (%) |
| `min_energy_kwh` | 2.0 | minimum energy of a sub-segment (kWh) |

#### 3.2 Mass merging (`merge_discharge_by_mass`)

Merges adjacent discharge segments with the same dominant mass cluster, eliminating spurious splits caused by non-loading/unloading events (traffic congestion, red-light SOC plateaus).

**Precondition**: `df_raw` already has a `mass_cluster` column added via `cluster_mass_data()`.

**Algorithm steps**:

1. For each discharge segment, compute the dominant `mass_cluster` (the label appearing most often within the time window). **v2.2.4**: `_get_seg_dominant_cluster` votes with **moving** rows (`mass_moving == True`) first; only if the window has no moving mass rows does it fall back to stationary-row votes (required fallback "still use stationary mass data when no moving data is available"). If the `mass_moving` column is absent it reverts to voting with all valid rows.
2. Traverse the segment list from the start and merge greedily:
   - adjacent segments have the same dominant cluster → merge
   - adjacent segments have different dominant clusters → do not merge (loading/unloading event)
   - a charge segment exists between adjacent segments → do not merge
   - **long stationary gap** (opt-in): if `max_merge_gap_min` is supplied and the stationary gap between the two trips is ≥ that many minutes → do not merge (treat the long park as a trip boundary, even with unchanged mass)
   - any segment's cluster is None → conservatively do not merge
3. Merge strategy: start takes the former segment, end takes the latter segment, energy is summed, SOC is recomputed, energy_source takes the higher priority of the two

**Parameters**:

| Parameter | Default | Description |
|------|--------|------|
| `charge_segs` | None | list of charge segments; merging is blocked if there is a charge within the gap |
| `max_merge_gap_min` | None | max stationary gap (minutes) still allowed to merge; a gap ≥ this refuses the merge, keeping the two trips separate. `None` = disabled (default, byte-identical to historical behaviour). `run_segment_detection` passes it from the vehicle's `split_long_stops_min` config key (read per-vehicle from `vehicles.json`), so only vehicles carrying that key are affected: Nestlé Volvo line-haul EV73SAL / YK73WFN at `30`; urban / regional multi-drop N88GNW, AV24LXJ / AV24LXK / AV24LXL and TA70WTL at `45`. Vehicles sharing a pipeline but lacking the key (e.g. T88RNW on `renault_speed`) are unaffected. |

**Long-stop split (`split_long_stops_min`, added for the Nestlé fleet)**: speed-based trip detection (`find_speed_trips`) already cuts driving periods separated by a stop ≥ `min_stop_duration_min` (5 min) into adjacent trips; `merge_discharge_by_mass` then re-joins same-cluster, charge-free adjacent trips into one long trip. For Nestlé vehicles a multi-hour intra-day park (e.g. YK73WFN 2024-06-13: drive 05:34–06:05 → ~3.6 h park → drive 09:41–10:39, mass constant at ~19.6 t) was therefore reported as a single trip. Setting `split_long_stops_min: 30` in `vehicles.json` makes the merge refuse to bridge any stationary gap ≥ 30 min, so the long park becomes a trip boundary (a `Stop` row, gap > 60 s) and the two driving periods are reported as two trips with their own per-trip dSOC / energy / EP / mass (no proportional re-allocation — they are genuinely separate detections). The 30-min default comfortably clears routine short stops (red lights, ≤15-min loading dwells, which stay merged) while catching genuine depot/shift-break parks. Other fleets, lacking the key, are unaffected.

The Renault D Wide N88GNW exhibits the same symptom (e.g. 2026-05-12: a single constant-mass ~17.8 t discharge spanning 06:08–16:23 with three multi-hour parks — 61 / 78 / 51 min — was reported as one trip) and so also carries the key, but at **`45`** rather than 30. Its duty cycle is urban multi-drop distribution: the stationary-gap distribution (same mass cluster, charge-free, n≈2.1 k over 2024-10→2026-06) is smooth with no natural valley (p50 ≈ 20 min, p75 ≈ 38 min, p90 ≈ 59 min), and the 30–45 min band is densely populated by routine unloading/handling dwells. A 30-min cut would mis-split those dwells (e.g. 2024-10-14: two ~32 min delivery stops split a single round into 3 trips), whereas `45` sits above the 75th percentile, so only the upper-tail genuine parks become trip boundaries while ~30 min drop dwells stay merged (verified: 2026-05-12 splits 1 → 4 trips under `45`, identical to 30 on that leg since all three parks exceed 51 min). Residual risk: an occasional 45–60 min stop that is really a long delivery dwell could still be split, but such durations are rare and genuinely long for a single drop.

**Four more multi-drop vehicles carry the key at `45`** (added in v2.2.4, same rationale as N88GNW). A fleet-wide scan of merged same-mass, charge-free stationary gaps (2024-10 → 2026-06) confirmed the same "long park merged into one trip" symptom on three Volvo FM urban rigids (AV24LXJ / AV24LXK / AV24LXL) and one Renault E-Tech T tractor (TA70WTL). All four run urban / regional multi-drop duty with a 30–45 min band densely populated by routine unloading / handling dwells, so — like N88GNW and unlike the sparse Nestlé line-haul Volvos — a 30-min cut would mis-split genuine delivery dwells; `45` sits at or above each vehicle's 75th-percentile gap and only promotes the upper-tail multi-hour parks to trip boundaries:

| Vehicle | Make / model | Duty | Merged-gap p50 / p75 (min) | Threshold |
|---|---|---|---|---|
| AV24LXJ | Volvo FM Electric (rigid) | urban distribution | 31 / 71 | `45` |
| AV24LXK | Volvo FM Electric (rigid) | urban distribution | 23 / 55 | `45` |
| AV24LXL | Volvo FM Electric (rigid) | urban distribution | 15 / 36 | `45` |
| TA70WTL | Renault E-Tech T (tractor) | regional multi-drop | 24 / 45 | `45` |

TA70WTL is a tractor unit, which by analogy to the Nestlé line-haul tractors might suggest `30`; it is set to `45` because its gap distribution is not line-haul-sparse but carries a dense 15–45 min dwell band (131 + 90 gaps of 491) typical of regional trunking with intermediate drops, and because it shares the `renault_speed` pipeline with N88GNW. Verified on real legs (run with vs without the key, 2.2.4 raw telematics): AV24LXJ 2024-06-17 splits an 81-min park (mass 38.8 → 40.2 t, one cluster) 13 → 14 trips; AV24LXK 2024-06-14 a 99-min park (16.6 → 16.6 t) 17 → 18; AV24LXL 2024-06-12 a 173-min park (36.6 → 36.8 t) 17 → 18; TA70WTL 2025-05-03 a 113-min park (36.1 → 36.0 t) 1 → 2 — each new boundary has constant mass across the park (Δ < the 2000 kg cluster gap), so it is a genuine same-mass long stop, not a loading/unloading event.

**Pipeline-level switch `merge_by_mass`** (default `true`): set `merge_by_mass` to `false` at the top level of `pipelines.json`, and `run_segment_detection` will skip this step entirely, keeping only the split result of `split_discharge_by_mass`. Applicable scenarios:
- the mass signal is locked at a single constant (e.g. KY24LHT has long reported ~10 t), so all trips have an identical dominant cluster → they would be merged indiscriminately
- real load fluctuation is smaller than `min_cluster_gap_kg` (default 2000 kg; the 1–2 t fluctuation of Scania EX74JXW / EX74JXY falls within the same bucket), so merging would cross real trip boundaries

Pipelines currently set to `false` in `pipelines.json` in the fleet: `scania_speed_00`,
`scania_speed_01`, `volvo_speed_03`, `volvo_speed_04` (CMZ6260-specific: based on `volvo_speed_02`
with `merge_by_mass: false` + `trip_endpoint_anchor: zero_speed` + `max_extend_minutes: 5`
+ `min_stop_duration_min: 15` to suit its low-frequency telematics heartbeat and locked mass signal).

### 4. Kinetic-energy corrected energy efficiency

The `Energy Performance Kinetics Corrected (kWh/km)` column removes the effects of both gravitational potential energy and kinetic energy change at the same time:

```
EP_kin = (|E_battery| - E_gravity - ΔKE) / d
```

where:
- `E_gravity = m × g × Δh / 3,600,000` (kWh, the potential energy change caused by the altitude difference)
- `ΔKE = 0.5 × m × (v_end² - v_start²) / 3,600,000` (kWh, the kinetic energy change caused by the trip's start/end speeds)
- `v_start`, `v_end` are taken from the first/last non-NaN speed readings within the trip time window

**Post-processing recomputation**: when an effective capacity update causes `delta_energy_kwh` to change, the invariant `ΔKE/d = EP_corrected - EP_kinetics` is used to recompute the kinetics column in sync.

### 5. Effective Capacity post-processing

After report generation, effective capacity undergoes a two-step correction (implemented in `_generator.py`, `_correct_effective_capacity`):

1. **soc_estimate replacement**: replace nominal_kwh with the effective capacity of non-soc_estimate segments, and back-calculate delta energy. **v2.2.4**: the replacement is the **time-local (~1-month, ±`CAP_WINDOW_HALF_DAYS`) window mean** of donor capacities around each segment (charge-preferred within the window), widening progressively then falling back to the global mean and finally `fallback_kwh` — so battery ageing / seasonal drift in long reports is not flattened by one global mean.
2. **outlier correction**: detect anomalous capacities with a **global ±1σ** test (detection statistic — plain mean/σ over all rows, unchanged), and replace each outlier's *capacity column* with the **time-local window mean of the inlier donors** (not the global mean), so the same wrong-season bias is not re-injected. **v2.2.7 — `energy_source` gate (MODE A, the default for the whole fleet)**: the subsequent energy back-calculation is applied **only to `soc_estimate` legs** (which have no counter, so their energy was always `SOC × capacity`). For **counter-sourced legs** (`energy_source ∈ {'total_energy', 'moving_energy'}`) an outlier *implied* capacity usually means the denominator ΔSOC is unreliable — integer-% SOC quantisation under-counts a small drop on a short trip — **not** that the counter energy is wrong; their `delta_energy` / `Energy Performance` / elevation-corrected / kinetics columns are therefore **kept as the counter produced them** (only the display capacity column is corrected). Without this gate, back-calculating `energy = ΔSOC/100 × capacity` re-injected the integer-% under-count into short counter-sourced trips, producing a spurious low-EP band (≈ 0.7 kWh/km).

**v2.2.8 — per-vehicle SOC-energy fallback for stale counter anchors (opt-in).** On a handful of vehicles the Total-Energy-Used counter *anchors* (endpoint snapshots) are stale / bursty — far from the trip boundary — so a discharge leg's counter delta pairs an under-attribution with an over-attribution: a frozen anchor makes one leg read ≈ 0 kWh (implied capacity a few kWh, EP ≈ 0) while the very next leg swallows the whole backlog (implied capacity 2–3× the fleet median, EP 2.5–5 kWh/km). These are **counter-anchor failures, not ΔSOC failures** — on these vehicles the SOC channel is densely sampled and reliable. For a vehicle that opts in (`"soc_energy_fallback": true` in `vehicles.json`), step-2 gains a **gated SOC rewrite** on counter-sourced outliers: when the leg is an ±1σ capacity outlier **and** `|ΔSOC| ≥ soc_fallback_min_dsoc_pct` (default `SOC_FALLBACK_MIN_DSOC_PCT = 10 %`, which bounds the fallback's integer-% quantisation error to ≤ ~±5 %) **and** `|original implied cap − replacement cap| / replacement cap ≥ soc_fallback_min_dev` (default `SOC_FALLBACK_MIN_DEV = 0.30`), the leg's energy is re-derived from `ΔSOC/100 × replacement capacity` (signed, so discharge comes out negative — exactly like the `soc_estimate` branch), its **`Energy Source` is set to `'soc_fallback'`**, and EP / Battery Power / elevation-corrected / kinetics are recomputed via the shared helper. Otherwise the leg keeps the default MODE A behaviour (only the capacity column is corrected, counter energy kept). The **dual gate keeps the intervention surgical**: it fires only when the counter is *both* an outlier *and* has a large trustworthy ΔSOC, so ordinary short / small-ΔSOC legs (where SOC quantisation dominates and the counter is the better measurement) are untouched. Thresholds are overridable per vehicle (`soc_fallback_min_dsoc_pct` / `soc_fallback_min_dev`); no vehicle overrides them today.

**Vehicles enabled** (7, all EV with reliable dense SOC but bursty counter anchors): `YK73WFN` / `EV73SAL` / `N88GNW` / `T88RNW` (implied-capacity outlier share 6–12 %, the worst offenders — paired frozen-anchor / backlog legs), `TA70WTL` / `CMZ6260` / `KY24LHT` (lower share, still stale-anchor legs). **Deliberately NOT enabled**: `AV24LXJ/K/L` (user-verified high-rate trustworthy counters — see the MODE B rejection note below; leaving them off keeps their output byte-identical to v2.2.7), `EX74JXW/JXY` (logger-grade `moving_energy`), the SOC-only Mercedes `LN25NKE` / `YN25RSY` / `YN75NMA` (100 % `soc_estimate`, so the gate is moot), and diesel (no SOC/counter). The new `'soc_fallback'` **`Energy Source` value** is documented in the report's Definitions sheet; it is excluded from the measured-capacity donor pools (`_period_capacity_from_rows`, step-1 and step-2 donor filters) since it is SOC-derived, not a measured donor.

**v2.2.7 — ΔSOC-weighted donor aggregation**: every *within-donor-set* mean in both steps (step-1 global mean + time-local window mean, step-2 inlier-replacement global + window mean) and the persisted per-period donor capacity (`_period_capacity_from_rows`, and by delegation `capacity_backfill`) is the **ΔSOC-weighted / combined-ratio** estimator `Σ(C_i·|ΔSOC_i|)/Σ|ΔSOC_i| = 100·Σ|ΔE_i|/Σ|ΔSOC_i|` (helper `_soc_weighted_cap()`), **replacing the former plain mean** of donor capacities. This removes the small-ΔSOC upward inflation of the plain mean (a single leg's `C_i = |ΔE_i|/(|ΔSOC_i|/100)` is noisy and Jensen-biased when `|ΔSOC|` is small, because SOC is integer-%). A hard `|ΔSOC| ≥ X %` cutoff and `ΔSOC²`/inverse-variance weighting were considered and **rejected** (the cutoff is threshold-sensitive and discards data; ΔSOC² over-weights the largest legs and drifts low). Donor segments lacking a usable ΔSOC are excluded from the weighted sum, and `Σ|ΔSOC| == 0` degrades to a plain mean. The charge-preferred priority, the physical range gate, and the cross-quarter donor-**count**-weighted average are unchanged (see the capacity-priority block above for the verified AV24LXJ numbers). MODE A is untouched — counter-sourced EP is still never re-derived from SOC.

Both the window half-width (`CAP_WINDOW_HALF_DAYS = 15`) and the moving-speed threshold (`MOVING_SPEED_THRESHOLD_KMH = 1.0`) are module-level constants for tuning.

> **Rejected alternative (v2.2.7, MODE B — not adopted).** A SOC-magnitude-scaled outlier threshold was evaluated as an alternative to the binary `energy_source` gate: replace the fixed ±1σ test with a per-leg `σ_i = sqrt(σ_true² + σ_soc²)` (where `σ_soc = C·0.5/|ΔSOC%|` is the integer-% quantisation noise of the implied capacity `C`, and `σ_true` is a robust spread from clean large-ΔSOC (≥10%) legs), flag `|C − μ| > 2·σ_i`, and recompute energy from `ΔSOC × capacity` for flagged legs **regardless of `energy_source`**. A full AV24LXJ/K/L comparison **rejected** it: it fires mostly at **moderate ΔSOC (median 8%, only ~⅓ at ≥10%)**, where SOC quantisation is still ±5–12%, and there it overwrites the **measured counter energy** (which is a faithful direct measurement — per-trip counter deltas match the reported energy, with zero resets, monotonic, and snapshots that tightly bracket most trips) with an **inferred** `ΔSOC × fleet-mean capacity` value. This homogenises real EP variation and manufactures implausible EPs (tens of legs > 2.0 kWh/km per vehicle; e.g. a textbook EP 1.00 → 1.51, and 1.23 → 0.81). Both modes fix the original spurious low band identically (small-ΔSOC band legs are never flagged under either), so the simpler binary gate (MODE A) is kept.
>
> **Documented future investigations (not acted on).** (1) In the comparison diff-set the counter energies run **systematically below** the SOC inference (~248 legs raised vs 65 lowered) — this may reflect a **SOC-gauge nonlinearity on short/medium trips** and warrants a dedicated study, but should not be papered over by blindly substituting SOC. (2) The rare **stale-snapshot anchor-spillover** case (a counter snapshot long before the trip start inflates the trip's energy delta → artificially high EP) would be better handled by a **dedicated anchor-spillover guard** than by SOC recomputation.

### 6. Validation figures (`plot_leg_validation` / `plot_diesel_leg_validation`, debug mode)

A 4-panel PNG is generated for each FPS leg (electric) or SRFLOGGER leg (diesel).

**Electric** (`segment_algorithms.py::plot_leg_validation`):

1. **Panel 1 — SOC + Speed**: SOC (%) on the left axis, Telematics/Logger speed (km/h) on the right axis; charge/discharge segments highlighted
2. **Panel 2 — AC+DC Delta**: cumulative charge energy (kWh) line + charge anchors ▼▲ annotated
3. **Panel 3 — discharge energy Delta**: moving_energy or total_energy cumulative delta (kWh) + discharge anchors ▼▲
4. **Panel 4 — Vehicle Mass**: mass (kg) time-series scatter + optional Logger CVW; each segment shows a dashed line at its aggregated mass. The annotation uses the SAME window → valid (> 0) → moving-only sample filter and the SAME `mass_agg` aggregation (default `"mean"`; `"median"` / `"iqr_median"` / `"mad_median"` / `"iqr_mean"` / `"mad_mean"` / `"mad_tw_mean"` / `"trimmed_mean"` for opted-in vehicles — see `configs/pipelines.json`; for `"mad_tw_mean"` the figure threads the same per-sample time axis as the report) as the Excel `Vehicle Mass (kg)` column, so figure and report agree (v2.2.6).

Each segment is annotated with: dSOC, delta energy (kWh), effective capacity (kWh), energy performance (kWh/km).

> **v2.2.3 font + interactive overlay**: in-figure font
> sizes were doubled (`_LABEL_FONT` 10→20, `_TICK_FONT` 8→16, and the scattered
> annotation/legend sizes) and the figure enlarged to `(18, 12)` so the larger
> text stays clear of the ticks under `tight_layout(h_pad=1.4)`. As of **v2.2.3**
> **every** rounded-bbox *data label* — the Panel-1 `dSOC=…` boxes, the Panel-2/3
> `±X kWh` energy deltas + charger-meter total, the Panel-3 recuperation deltas
> and the Panel-4 mass labels — is **no longer baked into the PNG**: when
> `plot_leg_validation` is called with `export_dsoc_overlay=True` (the
> `ValidationGenerator.regenerate` path), `_export_overlay_boxes(fig)` walks every
> axis (primary + twins) after `fig.canvas.draw()`, picks out the text artists
> that carry a background patch (`get_bbox_patch() is not None`), converts each
> anchor to figure-fraction coordinates (origin top-left) via
> `get_unitless_position()`, **removes them from the figure**, and writes them to
> a sidecar `<png-stem>.boxes.json`. Chrome that is *not* a data label — axis
> titles, sub-titles, legends, tick labels — lives outside `ax.texts`, carries no
> bbox patch, and stays baked at 2× font. To keep the figure-fraction →
> saved-pixel mapping exact, export mode saves **without** `bbox_inches='tight'`
> (the PNG then spans the full figure `[0,1]×[0,1]`). `export_dsoc_overlay=False`
> (default, e.g. the finetune comparison path) keeps the legacy fully-baked
> behaviour. The reader still falls back to the legacy `<png-stem>.dsoc.json` for
> figures not yet re-painted.
>
> **v2.2.6 hover redesign + tagged sidecar schema**: the legend font was scaled
> to ~0.6× (`_LEGEND_FONT` 18→11; `_LABEL_FONT` unchanged) so the baked legends
> sit discreetly over the data lines. Every exported label is now tagged at its
> draw site with `set_gid("<seg>|p<panel>|<role>")` — `seg` = `d`/`c` (base
> discharge/charge) or `od`/`oc` (finetune overlay) + the segment's positional
> index, shared across panels so one segment's labels carry the same `seg` id in
> Panels 1–4; `role` = `info` (the Panel-1 dSOC block) or `value` (Panel-2/3/4
> energy + mass deltas). `_export_overlay_boxes(fig, soc_ax=None, seg_specs=None)`
> reads those gids and, **when given `soc_ax` + `seg_specs`** (the EV
> `plot_leg_validation` export), returns a **dict** sidecar
> `{"boxes": [...], "segments": [...], "soc_axis": {...}}`:
> - `boxes` — each label plus its `seg` / `role` / `panel` (all `null` for
>   untagged labels, e.g. the charger-meter session total);
> - `segments` — `[{seg, x0, x1}]`, each segment's figure-fraction x-range (mapped
>   through the SOC axis `transData`→figure), used to build full-height hover
>   hotzones;
> - `soc_axis` — the SOC panel's `{x0, y0, x1, y1}` in figure fraction (top-left
>   origin), the anchor for the pinned info box.
>
> The inspect HTML (`report_builder._write_html_viewer`) auto-detects the sidecar
> shape. **Dict** → the hover redesign: default view shows only the baked
> triangles/legends/titles (all labels hidden); one transparent hotzone per
> segment, on `mouseenter`, (a) fills + shows a single **pinned info box** at the
> SOC panel's bottom-left with that segment's dSOC block, (b) reveals that
> segment's value labels at their own coords, and (c) **de-collides** the shown
> set (greedy vertical nudge) then clamps each into the image rect; `mouseleave`
> hides them again. **Flat list** → the legacy ghosted-on-hover `.annot-box`
> behaviour, kept for back-compat with diesel figures
> (`_export_overlay_boxes(fig)` with no extras still returns a list) and EV
> vehicles whose sidecars have not yet been re-painted. Only EV figures regenerated
> under v2.2.6+ carry the dict schema; the finetune comparison path bakes labels
> (no sidecar) and is unaffected.

> **v2.2.6 one figure per calendar day (regenerate paths)**: SRF-logger diesel
> vehicles (WU70GLV, YT21EFD) split a single day into dozens of short logger legs,
> so the old one-figure-per-leg behaviour fragmented a day into dozens of figures /
> inspect-sidebar entries (`2025-09-01_0000`, `_0002`, `_0004`, …). Both
> overlay-regenerate paths now **group the per-leg raw CSVs by `<date>`** (shared
> `report_builder._group_paths_by_date`), concatenate each day's legs into one
> DataFrame, run segmentation on the day, and paint **one figure per calendar day**
> named `validation_<REG>_<date>.png` (no `_<NNNN>` suffix) spanning the full UTC
> day with **all** that day's trip/charge bands. EV uses
> `ValidationGenerator._concat_day_raw` (row-stack the `dtype=str` telematics CSVs,
> sort + de-dup by `TIME_COL`); diesel uses `diesel_pipeline._logger_day_df_from_csvs`
> (row-stack logger CSVs → `_finalise_logger_df`; cumulative LFC/VDHR counters stay
> monotonic across legs so per-trip deltas remain correct). The `.boxes.json`
> sidecar + inspect sidebar then have **one entry per day**. Before re-painting,
> `report_builder._clear_day_validation_figures` deletes the stale non-finetuned
> `validation_<REG>_*.{png,boxes.json,dsoc.json}` so the legacy per-leg fragments do
> not coexist with the consolidated day figures (`*_finetuned.*` are preserved).
> `_write_html_viewer` / `scripts/refresh_inspect_html.py` accept both names (date
> token followed by `.` *or* `_`). Day-level segmentation matches the per-leg xlsx
> In-Transit row count near-exactly (±1 at leg boundaries, where a continuous trip
> straddling two logger legs is merged into one). Empirically, WU70GLV collapses
> 717 per-leg figures → 84 per-day figures; the live `--debug` path still emits
> transient per-leg figures (cleared on the next regenerate).

**Diesel** (`diesel_pipeline.py::plot_diesel_leg_validation`):

1. **Panel 1 — Speed**: Logger CCVS / GPS speed (km/h); trip segments shaded green
2. **Panel 2 — Cumulative Fuel Used (L)**: LFC engine total fuel used zeroed curve + per-trip fuel consumption annotation
3. **Panel 3 — Cumulative Distance (km)**: VDHR hr total vehicle distance zeroed curve
4. **Panel 4 — GCVW (kg)**: CVW gross combination vehicle weight + per-trip average mass green dashed line

**Axis standards** (shared by electric / diesel, to ease switching and comparison in inspect.html):

| Panel | Axis | Range |
|---|---|---|
| 1 (Speed) | y | **fixed 0–100 km/h** |
| 2 (Fuel Used, diesel) | y | upper limit ≥ **5 L** (short trips forced to display 0–5 L) |
| 3 (Distance, diesel) | y | upper limit ≥ **10 km** (short trips forced to display 0–10 km) |
| 4 (GCVW, diesel) | y | fixed 0–50 000 kg, 5 equal divisions |

### Unified output schema (v2)

All segmentation algorithms output the same schema, ensuring consistent downstream processing:

| Field | Type | Charge segment | Discharge segment |
|------|------|--------|--------|
| `delta_soc_pct` | float | positive (SOC rises) | negative (SOC falls) |
| `delta_energy_kwh` | float | positive (energy inflow) | negative (energy outflow) |
| `energy_source` | str | `'ac_dc'` / `'soc_estimate'` | `'total_energy'` / `'moving_energy'` / `'soc_estimate'` |
| `delta_moving_kwh` | float/None | ≥ 0 | ≥ 0 |
| `effective_capacity_kwh` | float | delta_energy / (delta_soc/100) | \|delta_energy\| / (\|delta_soc\|/100) |
| `motion_duration_s` | float/None | — | present only when `trip_endpoint_anchor=="zero_speed"`: the cumulative duration (seconds) of the in-trip v > `speed_threshold_kmh` sub-interval. `report_builder._seg_to_row` uses it in place of the endpoint difference as the denominator of `Average Speed (km/h)`, avoiding dilution by zero-speed tails |

## Excel output

### Report worksheet

One segment per row; columns are defined by `HEADERS` in `report_builder.py`:
- green row = discharge (trip) segment
- red row = charge segment
- timestamp format: `yyyy-mm-dd hh:mm:ss`
- duration format: `[hh]:mm:ss` (stored as fractional days)
- URL: clickable hyperlink to the SRF platform visualisation

### Graphs worksheet

Scatter plots with linear trend lines, driven by the shared `CHART_SPECS` config
in `report_builder.py` (`CHART_SPECS_EV` / `CHART_SPECS_DIESEL`, selected via
`chart_specs_for(headers)`) plus a single `CHART_STYLE` visual config. Together
they are the single source of truth so that **every report uses identical fixed
axes, identical data filtering and an identical look** — the same chart type
looks the same across all vehicles and all reports, EV and diesel alike.

Both fuel types render the same three-panel set — the performance metric against
the three explanatory variables used in the paper:

EV charts (y = Energy Performance, 0–3 kWh/km):
1. EP vs Vehicle Mass (x 0–45000 kg)
2. EP vs Average Temperature (x −5…30 °C)
3. EP vs Average Speed (x 0–90 km/h)

Diesel charts (y = Fuel Consumption, 0–60 L/100km):
1. Fuel cons. vs Vehicle Mass (x 0–45000 kg)
2. Fuel cons. vs Average Temperature (x −5…30 °C)
3. Fuel cons. vs Average Speed (x 0–90 km/h)

> The former EV `Battery Power vs Energy Change` / `SOC Change vs Energy Change`
> and diesel `Distance vs Fuel Used` charts were dropped in the v2.2.4 visual
> pass so both reports share one comparable `{EP | Fuel cons.} vs {Mass / Temp /
> Speed}` set, matching the paper's definition.

**Fixed axes** — every axis `min`/`max`/`major_unit` is a constant (never
per-file autoscaling). Energy Performance (0–3), Vehicle Mass (0–45000) and
ambient Temperature (−5…30) match the fixed PDF-briefing / paper conventions
(`PERF_YLIM` / `MASS_XLIM` / `TEMP_XLIM`), so the Excel charts use the same
scales the PDF briefing does; the remaining axes (speed, fuel consumption) were
fixed from robust fleet-wide percentiles (1st/99th over the whole 2.2.3 set),
documented inline in each spec.

**Axis display title vs data column** — a spec's `x_hdr`/`y_hdr` is the *data*
reference (the series, categories and filter all look the column up by this exact
`Report`-sheet header). The optional `x_title`/`y_title` fields override only the
*printed* axis label and fall back to the header when absent. The mass charts use
this to show **`Vehicle gross weight (kg)`** (matching the paper's "Vehicle gross
weight" wording) while the series keeps pointing at the real `Vehicle Mass (kg)`
column; units stay kg.

**Shared look (`CHART_STYLE`)** — a single module-level dict drives the
appearance on both render paths:

- **single-colour scatter** — every point uses one muted steelblue (`#1F77B4`)
  at `scatter_opacity` (72 %) with no marker border. A scatter series left
  without an explicit fill makes Excel auto-vary the per-point colour (the old
  "five colours" artefact); pinning one `solidFill` + `<a:alpha>` fixes it.
- **legend in the top-right corner** (`top_right` / `tr`), not overlaying data,
  with a concise series name (`EP` / `Fuel cons.`).
- **title band + fit subtitle** — a short title (e.g. `EP vs Average Temperature
  (°C)`) sits on its own top band; the least-squares fit equation **and** R²
  are rendered as one second title line (`y = a·x + b  ·  R² = r`) by
  `_chart_subtitle()` instead of two overlapping floating trendline labels. The
  trendline itself is still drawn (its built-in `dispEq` / `dispRSqr` labels are
  switched off).
- **font sizes** — aligned with the `plot-figure` skill Style constants so the
  Excel charts read at the same scale as the published matplotlib figures:
  `title_font_size` 14 (bold), `axis_title_font_size` 14, `tick_font_size` 12,
  `legend_font_size` 9, `subtitle_font_size` 10. xlsxwriter takes these via each
  element's `name_font` / `num_font` / legend `font`; openpyxl (which ignores the
  font on a bare-string title/axis-title) builds `Title` / tick `txPr` objects
  carrying `CharacterProperties(sz=pt×100)`, so both paths render the same sizes.
- **light major gridlines** — both axes draw major gridlines in light grey
  (`grid_rgb` `#D9D9D9`) at high transparency (`grid_opacity` 30 %, matching the
  paper's `GRID_ALPHA` 0.3); minor gridlines are off. xlsxwriter uses the native
  `major_gridlines` line dict (complementary `transparency` = 100 − opacity);
  openpyxl wraps the colour in a full `<a:solidFill><a:srgbClr><a:alpha/>` block
  (a bare `<a:srgbClr>` under `<a:ln>` is invalid and Excel silently falls back
  to black gridlines).
- **larger charts** — both paths size the chart **explicitly** from the shared
  `chart_width_cm` / `chart_height_cm` (24 × 13 cm): xlsxwriter via `set_size`
  (cm → px), openpyxl via `chart.width` / `chart.height`. (The old xlsxwriter
  `x_scale` / `y_scale` were removed so the two paths render at the same physical
  size and one shared row step can place them identically.)
- **even vertical spacing between charts** — the three stacked charts are
  anchored a fixed number of worksheet rows apart, given by the shared
  `chart_row_step()` helper = `ceil(chart height in default rows) + chart_gap_rows`
  (a 13 cm chart ≈ 24.6 default rows, `chart_gap_rows` = 2 → step 27). The i-th
  chart is anchored at row `i × chart_row_step()`, so each chart starts in the
  clear ~2-row strip below the previous one and adjacent charts never overlap.
  Both render paths import the same helper (xlsxwriter `insert_chart(f'A{...}')`,
  openpyxl `add_chart(chart, f'A{...}')`), so the spacing can never drift; bumping
  `chart_height_cm` or `chart_gap_rows` re-derives the step automatically — never
  hand-tune per-path anchors.
- **pinned plot-area margins** (`plot_x` / `plot_y` / `plot_w` / `plot_h`) — the
  inner plot box is placed with a fixed manual layout (edge-anchored fractions of
  the chart area) instead of letting Excel auto-size it; this keeps every axis
  title OUTSIDE its tick labels (the rotated y-axis title clears the y tick
  numbers, the x-axis title clears the x tick numbers) at the enlarged
  plot-figure font sizes, where auto-layout used to overlap them. Both render
  paths consume the same fractions — xlsxwriter via
  `set_plotarea({'layout': {x, y, width, height}})` and openpyxl via
  `chart.layout = Layout(ManualLayout(layoutTarget='inner', xMode='edge',
  yMode='edge', x, y, w, h))` (note: openpyxl needs `layoutTarget='inner'` so the
  fractions address the plot box itself, matching xlsxwriter, and the layout must
  be set on `chart.layout`, not `chart.plot_area.layout`).

**Filtered series + trendline** — Energy-Performance / Fuel-Consumption charts
include only driving legs (charge / `Stop` / NaN rows excluded) with the metric
in range (e.g. EP ∈ (0.1, 3.0]) and the x-value in its window. Because xlsxwriter
/ openpyxl charts reference cell ranges and cannot filter in place, the cleaned
`(x, y)` pairs are written to a **hidden `GraphsData` sheet**; both the scatter
series and its linear trendline point at that block, so the fit is computed on
clean data only (matching the paper's definition). The single filtering routine
`_filtered_chart_points()` and the fit/subtitle helper `_chart_subtitle()` are
shared by the generator and the patch script.

**Graceful degradation when a chart has no data** — if a chart ends up with
**zero** filtered points it is *not* drawn as an empty scatter frame (which reads
like a bug). Instead a centred grey-italic note panel is written over the chart's
footprint — e.g. a vehicle whose `mass_col` is null for the whole period (so the
`Report` `Vehicle Mass (kg)` column is `#N/A` on every leg) gets **"No vehicle
mass data available for this vehicle"** in place of the `EP`/`Fuel cons.` vs Mass
chart, while its Temperature and Speed charts render normally. The rule is purely
point-count based (`≥ 1` point ⇒ normal chart), so it applies to *any* chart and
*any* fuel type, not just one vehicle. The note text per chart is the spec's
`empty_note` field (read via `empty_chart_note()`); the panel extent comes from
`empty_note_extent(gi)` (= the chart's row band × `chart_col_span()` columns, so
the remaining charts keep their positions); the panel style fields live in
`CHART_STYLE` (`empty_note_*`). The panel is a **merged cell**, deliberately — it
is the one primitive both render paths write identically (xlsxwriter
`merge_range`, openpyxl `merge_cells` with the styles applied before merging), so
the degraded look can never drift between the generator and the patch script. The
note is **not** an xlsxwriter textbox / openpyxl drawing (openpyxl has no clean
textbox API).

> **Re-chart tool (any version):**
> `.claude/skills/generate-excel-report/patch_graphs_2_2_3.py` (openpyxl) rebuilds
> the `Graphs` + `GraphsData` sheets of existing reports **from the current
> `CHART_SPECS` + `CHART_STYLE`**, WITHOUT re-running the pipeline — the cheap way
> to update already-generated reports after an axis / styling change (e.g. the
> temperature axis −5…35 → −5…30). Originally written for the 2.2.3 in-place
> styling pass, it is version-neutral: pass a report-database version
> (`--version 2.2.6 [--glob REG]`) **or** an explicit file / directory
> (`patch_graphs_2_2_3.py excel_report_database/2.2.6/<REG>`). It backs each file
> up to `.bak/`, leaves `Report`/`Definitions`/`Finetune Log` and `=NA()` formulas
> / hyperlinks untouched, and imports the same shared config so the generator and
> patch paths never drift. NB: because weather is a **post-hoc** step for non-Logger
> EVs, their Temperature chart is a "no data" note at generation time — re-chart
> them **after** the weather backfill so the Temperature chart is drawn with data.
> Files open in Excel are skipped (close them and re-run).

### Definitions worksheet

A glossary of key terms (SOC, Energy Source, Delta Moving Energy, Battery Capacity, etc.)

## Leg Type classification

The `Leg Type` field of each row in the xlsx report falls into three major categories, corresponding to three background colours in Excel:

**Green background — discharge / trip** (a driving trip for an EV or diesel vehicle):

| Type | Condition |
|------|------|
| `In House` | departs from base and returns to base, short distance |
| `Round Trip` | departs from base and returns to base, distance > 5 km |
| `Outbound` | departs from base, ends away |
| `Return` | departs from away, returns to base |
| `In Transit` | between two non-base locations (diesel trips default to this category) |

**Red background — charge** (EV only; never appears for diesel):

| Type | Condition |
|------|------|
| `AC Home` / `DC Home` / `AC/DC Home` | charging at base, with AC/DC/both energy |
| `AC Away` / `DC Away` / `AC/DC Away` | charging away |

**White background — standstill** (added in v2.2.2):

| Type | Condition |
|------|------|
| `Stop` | a gap segment > 60 s between a trip and a charge event |

Stop rows are synthesised by `report_builder._insert_stop_rows()` after `_correct_effective_capacity()`;
position / mass follow the endpoint of the previous segment, and `Start/End SOC` take the boundaries of the preceding and following rows respectively, exposing auxiliary drain.
They do not go through the segmentation algorithm and do not access `df_leg`. Diesel vehicles benefit too —— Stop rows have NaN for both fuel consumption and kWh.

The home point is automatically detected from the GPS coordinates of the first charge segment (EV only).
Charge segment classification post-processing: the first batch of charge segments may be classified as Away while the home_point is unknown, and they are automatically reclassified after report generation.

## SRF Logger data channels

### SRFLOGGER_V1 column names

Obtained via `leg.get_data_frame(type, resolution='1s')`; the column names are fixed as follows:

| Type | Column names | Description |
|------|------|------|
| `2` | `2 longitude`, `2 latitude`, `2 altitude`, `2 bearing`, `2 speed` | GPS positioning (longitude, latitude, altitude m, bearing angle, speed m/s) |
| `6` | `6 charge`, `6 temperature`, `6 capacity`, `6 charging` | battery status (SOC%, temperature °C, capacity, charging status) |
| `7` | `7 temperature`, `7 pressure`, `7 humidity`, `7 wind speed`, `7 wind direction`, `7 cloud cover` | OpenWeather weather snapshot (temperature °C, pressure hPa, humidity %, wind speed m/s, wind direction °, cloud cover %) |
| `11` | accelerometer x/y/z | three-axis acceleration sensor (high-frequency sampling) |
| `12` | gyroscope x/y/z | three-axis gyroscope (high-frequency sampling) |
| `13` | barometer reading | atmospheric pressure (hPa, high-frequency sampling) |
| `31` | CAN data frame | J1939 hex-encoded |
| `AMB` | `AMB ambient air temperature` | ambient temperature (°C, from the J1939 AMB PGN) |
| `CCVS` | `CCVS wheel based vehicle speed`, `CCVS cruise control set speed`, `CCVS cruise control active`, `CCVS brake switch`, `CCVS clutch switch` | vehicle speed (km/h), CC set speed (km/h), CC active status (0/1), brake switch (0/1), clutch switch (0/1), from the J1939 CCVS PGN |
| `ET1` | engine temperature | J1939 Engine Temperature 1 |
| `EEC1`/`EEC2` | engine control | J1939 Electronic Engine Controller |
| `ETC1`/`ETC2` | transmission control | J1939 Electronic Transmission Controller |
| `HRW` | high resolution wheel speed | J1939 High Resolution Wheel Speed |

### SRFLOGGER_V2

First seen on **LN25 NKE** (DAF XD Electric, onboarded v2.2.3). The V2 logger
exposes a much larger J1939 channel set than V1, but the column names of the
channels the report pipeline cares about are **identical to V1**, so no new
column mapping is required:

| Type | Column name(s) | Notes (LN25 NKE) |
|------|------|------|
| `CVW` | `CVW gross combination vehicle weight` | **GCVW total mass** — same column name as V1 / WU70GLV. The user's "Combination Vehicle Weight" channel. ~8.8–11.2 t observed (empty/light artic head). Only broadcast while moving. |
| `VW` | `VW axle weight`, `VW cargo weight`, `VW trailer weight`, `VW axle location` | Single-axle weight (~5–7 t); only `VW axle weight` is populated. The mass fallback after CVW. |
| `CCVS` | `CCVS wheel based vehicle speed`, … | km/h; same as V1. |
| `2` | `2 longitude/latitude/altitude/bearing/speed` | GPS; `2 speed` in m/s. |
| `6` | `6 charge`, `6 temperature`, `6 capacity`, `6 charging` | SOC% + battery temp. |
| `7` | `7 temperature/pressure/humidity/wind speed/wind direction/cloud cover` | OpenWeather snapshot, same as V1. |
| `AMB` | `AMB ambient air temperature` | engine-bay ambient temp. |
| `VDHR` | `VDHR hr total vehicle distance` | cumulative distance (km). |
| `EEC2` / `EBC1` | accelerator / brake pedal position | pedal histograms. |
| `EC` | `EC reference engine torque` (2470 Nm), `EC engine moment of inertia` | used for `max_torque_nm`. |
| others | `EEC1`, `ERC1`, `ETC2`, `ET1`, `RC`, `HOURS`, `TCO1`, `DI`, `VIN`, `FMS`, `11`/`12`/`13` (IMU/baro), `31` (raw CAN), `AIR1`, `CL`, `DM1`, `EEC14`, `SERV`, `RESET`, `TD`, `VH`, `pgn_*` | present in `leg.types` but mostly empty / not consumed by the report pipeline. |

> **V1 vs V2 detection**: the generator groups legs by `leg.trip.source`; both
> `SRFLOGGER_V1` and `SRFLOGGER_V2` match the `startswith("SRFLOGGER")` test, so
> the EV main flow collects and channel-loads them identically. The EV
> logger-mass fallback in `run_segment_detection` (telematics mass all-NaN →
> `merge_asof` Logger CVW into `mass_col`, 5 min tolerance) and `LoggerPatcher`
> both already list `CVW gross combination vehicle weight` as the preferred mass
> channel, so a V2 EV vehicle is **config-only** to onboard.

> **v2.2.4 standstill-mass limitation (logger-mass path)**: the moving-only mass
> filter in `cluster_mass_data` keys off the telematics `speed_col`. When mass is
> sourced from the Logger via the `merge_asof` fallback (e.g. LN25 NKE's
> SRFLOGGER_V2 CVW), the telematics speed column is usually unavailable for those
> rows, so `cluster_mass_data` automatically degrades to clustering on **all**
> valid readings (the documented no-moving-readings fallback) and `mass_moving`
> reduces to the valid mask. This is intentionally low-risk: no behavioural change
> for logger-mass vehicles, while telematics-mass EVs and diesel CVW get the
> moving-only filtering. Aligning Logger CVW with the Logger speed channel is left
> as future work.

> **Data sparsity caveat (LN25 NKE)**: this vehicle's logger legs (incl. CVW)
> exist only in **2025-08 / 2025-09**; from 2025-10 onward there are no logger
> legs at all. Logger CVW can therefore fill the `Vehicle Mass (kg)` column only
> for the handful of 2025-08/09 FPS trips whose time window overlaps a CVW leg;
> later periods report mass as `#N/A` and the EP-vs-Mass chart degrades to the
> "No vehicle mass data" note. The telematics `gross_combination_vehicle_weight`
> column is all-NaN throughout, which is exactly what triggers the logger
> fallback (no change needed).

### DAF XD Electric pipeline — LN25 NKE (added v2.2.3)

LN25 NKE is the fleet's first **SRFLOGGER_V2** vehicle and is configured as an
**EV** (not diesel — it is a battery-electric DAF XD). Onboarding was
**config-only**; no pipeline code changed.

- **pipeline** `daf_speed_00` — standard speed-branch segmentation (clone of
  `mercedes_speed`: `min_soc_drop` 1.0, the lenient speed-defined value).
- **energy / EP** — telematics has no AC/DC/moving-energy counters and
  `total_electric_energy_used` is all-NaN, so the energy-source cascade falls to
  `soc_estimate`: `delta_soc × effective_capacity` with `srf_capacity_kwh` =
  462 kWh as the seed (`effective_capacity_kwh` is `null` until the first report
  back-fills it).
- **mass** — `mass_col` kept as the standard telematics
  `gross_combination_vehicle_weight` (all-NaN) so the logger-CVW fallback
  engages; see the sparsity caveat above.
- **speed** — `speed_col` = `speed` (telematics), present on ~all FPS legs;
  the two all-NaN-speed legs fall back to SOC segmentation automatically.
- **no altitude column** in telematics → `altitude_col` `gnss_altitude`
  resolves to absent → elevation-corrected EP is NaN (safe degrade).
- **operators** — round-robin (`plot_config.json`): DP World → JLP → Welch →
  WS. The trailing **WS** operator's full name is not yet known; it uses the
  placeholder company key `WS` with colour cyan `#00BCD4`.

### Diesel pipeline (added in v2.2.2)

Adds `report_generator/diesel_pipeline.py`, providing a complete Logger-only report
generation path for diesel vehicles. Trigger condition: the vehicle configuration in `vehicles.json` contains `"fuel_type": "DIESEL"`.

**Key differences from the EV pipeline**:

| Step | EV pipeline | Diesel pipeline |
|------|---------|---------|
| main-loop leg source | `leg.trip.source == "FPS"` | `leg.trip.source == "SRFLOGGER_V1"` |
| speed source | `wheel_based_speed` / `speed` | `CCVS wheel based vehicle speed` + GPS fallback |
| energy source | AC/DC counter → total_energy → SOC estimate | `LFC engine total fuel used` × LHV |
| distance source | GNSS odometer integration | `VDHR hr total vehicle distance` differencing |
| mass source | `gross_combination_vehicle_weight` (telematics) | `CVW gross combination vehicle weight` (Logger) |
| temperature source | Logger Channel 7 / OpenWeather | `AMB ambient air temperature` |
| segmentation | speed-based trip detection + SOC check | `find_speed_trips()` only (no SOC) |
| charge events | detected via the SRF charger API | always empty |
| effective capacity correction | steps 1/2 | skipped |
| Charger / Logger patcher | both run | both skipped |

**Shared parts**: the `find_speed_trips()` segmentation helper, the `_insert_stop_rows()` post-processing,
and the `_write_excel_report()` formatting (column set selected via the `headers` keyword argument).

**Separate column sets**: electric vehicles use `HEADERS` (50 columns since v2.2.5, with `EP_exclude_aux` then `Operator` at the end), diesel uses `DIESEL_HEADERS` (26 columns, `Operator` last). The per-leg operator code is resolved by `report_generator/operators.py` (see the `Operator` column note above).
The diesel column set **does not contain** electricity-related columns such as SOC, AC/DC charge energy, Battery Capacity, Energy Performance (kWh/km),
instead expressing fuel consumption with `Fuel Used (L)` and `Fuel Consumption (L/100km)`.
`_row_col_index`, `_stop_row_from_neighbours`, `_insert_stop_rows`, and `_write_excel_report`
all accept a `headers=` parameter to support both layouts.

**Diesel vehicles.json example** (WU70 GLV):

```jsonc
"WU70GLV": {
  "srf_reg": "WU70 GLV",
  "make": "DAF", "model": "XF 450",
  "fuel_type": "DIESEL",
  "pipeline": "daf_diesel_logger",
  "leg_source": "SRFLOGGER_V1",
  "weight_class_t": 44.0,
  "diesel_lhv_kwh_per_l": 10.0,
  "speed_col": "CCVS wheel based vehicle speed",
  "speed_col_fallback": "2 speed",
  "fuel_energy_col": "LFC engine total fuel used",
  "fuel_rate_col": "LFE fuel rate",
  "distance_col": "VDHR hr total vehicle distance",
  "mass_col": "CVW gross combination vehicle weight",
  "altitude_col": "2 altitude",
  "ambient_temp_col": "AMB ambient air temperature"
}
```

**WU70 GLV first test result** (2025-06-25 ~ 2025-06-27, 21 legs):

- 16 trip + 15 Stop rows
- longest trip 55 km / 78 min / 42 km/h, vehicle weight 21.3 t, **fuel consumption 37.2 L/100km**
- fleet total 325 km / 108 L → 33.3 L/100km (typical 44t artic level ✓)

### Stop leg type (added in v2.2.2)

The xlsx report adds **Stop** as a third leg type, filling the gap segments > 60 s between trip and charge events,
helping the reader understand the vehicle's work rhythm and auxiliary/standby energy consumption.

Implementation points:

- `report_builder._insert_stop_rows(sorted_rows)` traverses adjacent row pairs after `sorted_rows` is sorted by time;
  if `next.start_time - prev.end_time > STOP_MIN_GAP_SECONDS` (default 60 s),
  it calls `_stop_row_from_neighbours(prev, next)` to synthesise a new row inserted between them.
- Synthesised Stop row fields: `Leg Type='Stop'`, start/end times being prev's endpoint / next's start point, `Duration`
  being Excel fractional days, `Origin` and `Destination` both taking prev's destination (falling back to
  next's origin), `Distance/Average Speed/Elevation Difference` all 0, `Vehicle Mass (kg)`
  and `Vehicle Mass CV (reliability)` inheriting from prev, `Start SOC` = prev.End SOC, `End SOC`
  = next.Start SOC, `SOC Change` exposing the auxiliary drain during the standstill. All other columns are NaN.
- This step is located after `_correct_effective_capacity()` in `_generator._generate_report()`,
  so the SOC/mass endpoints read by Stop rows are the final values after capacity correction.
- `_write_excel_report()` recognises `leg_type == 'Stop'` during formatting and uses a white-background format
  (`bg_color='#FFFFFF'`, light-grey border `#D0D0D0`), alongside the green-background Trip / red-background Charge.
- The same helper set can also be applied directly to post-hoc patch an existing xlsx: read rows → `_insert_stop_rows`
  → `_write_excel_report`, with no need to re-run the SRF API.

### Finetune — segmentation correction post-processing (with overlay comparison visualisation)

`report_generator/finetune.py` provides a **manual post-processing** pipeline for already-generated xlsx reports. Use case:
the segmentation algorithm (`segment_algorithms.py`), even after careful parameter tuning, still has visually noticeable segmentation errors (over-splitting, missed splits,
misclassification); in the main conversation we use LLM vision to review `validation_figures/*.png` and output an "operation list",
then call this module to apply the operations to the xlsx and regenerate the validation figures + inspect HTML.

**The original xlsx is not modified**; all outputs carry the `_finetuned` suffix:

```
excel_report_database/2.2.2/YK73WFN/
├── jolt_report_YK73WFN_20240601_20240901.xlsx              # original report (read-only)
├── jolt_report_YK73WFN_20240601_20240901_finetuned.xlsx    # new output
├── inspect_jolt_report_YK73WFN_20240601_20240901_finetuned.html
└── validation_figures/
    ├── validation_YK73WFN_2024-06-11_0000.png               # original
    └── validation_YK73WFN_2024-06-11_0000_finetuned.png    # new output
```

#### Three operations

```python
from jolt_toolkit.report_generator.finetune import (
    MergeOp, SplitOp, DeleteOp,
    apply_operations, reconstruct_segs_from_xlsx,
    regenerate_figures, regenerate_inspect_html,
)

operations = [
    # merge several consecutive rows into one (usually absorbing a middle Stop or joining two In Transit segments)
    MergeOp(rows=[5, 6, 7],                  # must be consecutive (xlsx 1-based row numbers)
            new_type='In Transit',           # optional; None inherits the first row
            reason='LLM: Stop is a red-light stop'),
    # split a row into two at a specified UTC time
    SplitOp(row=12,
            at_time='2024-06-15 14:32:10',
            new_types=('Outbound', 'Return'),
            reason='LLM: returned to depot mid-trip'),
    # delete a row (false trip / noise segment)
    DeleteOp(row=23, reason='LLM: shunting in car park < 1 min'),
]
```

#### Public API

| Function | Action |
|------|------|
| `apply_operations(xlsx, ops, raw_dir, out_path=None) → Path` | apply the operation list to the xlsx; preserve formatting with openpyxl; apply in descending row order (avoiding offsets); recompute derived fields; renumber Leg Number / Cumulative Distance; mark modified rows with a light-yellow `#FFFFCC` overlay; add a `Finetune Log` sheet; write to `*_finetuned.xlsx` |
| `reconstruct_segs_from_xlsx(xlsx, date) → (charge_segs, discharge_segs)` | reconstruct the seg dict list for a given day from the xlsx, in the same format accepted by `segment_algorithms.plot_leg_validation` |
| `regenerate_figures(xlsx, raw_dir, fig_dir, suffix='_finetuned', *, original_xlsx_path=None) → int` | traverse `raw_*.csv` over the xlsx date range and plot directly with `plot_leg_validation` (**without calling** `run_segment_detection`), outputting `validation_{REG}_{date}_{idx}{suffix}.png`. If `original_xlsx_path` is passed (or automatically inferred from the `_finetuned.xlsx` suffix), an identity check is performed on each day's segs: if segs are unchanged, the original PNG is directly `shutil.copy2`'d to `_finetuned.png`; if segs changed, an overlaid plot is drawn with **base = original (red/green) + overlay = finetuned (orange/cyan)**, and the legend is extended to 4 items |
| `regenerate_inspect_html(xlsx, out_path=None, fig_suffix='_finetuned') → Path` | generate an inspect HTML pointing to `_finetuned.png` (reusing the UI of `report_builder._write_html_viewer`, but switching the figure file suffix) |

#### Derived-field recomputation strategy

After each operation, `apply_operations()` recomputes by `Leg Type` classification:

- **In Transit / Trip (green)**: slice from the raw CSV by time window → Distance (odometer differencing) / Energy Change (`total_energy_col` or `moving_energy_col` differencing) / Start/End SOC / SOC Change / Vehicle Mass / Elevation Difference / Average Speed / Energy Performance / Energy Source
- **Charge (red)**: Energy Charged AC + DC (`ac_col` / `dc_col` differencing) / Start/End SOC / Vehicle Mass / Elevation Difference
- **Stop (white)**: Distance / Speed / Elevation Difference forced to 0, SOC endpoints retained (exposing auxiliary drain), EP columns cleared
- **Columns requiring pipeline-level context** (`Energy Performance Corrected by Elevation Difference`, `Energy Performance Kinetics Corrected`, `Battery Capacity`, `Wire Energy Efficiency`, `Battery Power`, `Peak/Average Charging`, `Recuperation Energy`, `CO2 *`, `Histogram *`) **are cleared and noted in the `Finetune Log` as "to be synced after the next full rerun"**

#### Invariants & boundaries

- `apply_operations(xlsx, [], raw_dir)` (**empty operation list**) produces a `*_finetuned.xlsx` that is **cell-by-cell bit-identical by value** to the original (the empty-operation case skips sort + renumber, guaranteeing the contract)
- operations are executed in **descending row order** (MergeOp uses `max(rows)`, SplitOp/DeleteOp use `row`)
- on Split, `at_time` must fall strictly inside the original row's `[Start, End]`
- Logger speed/mass overlay is best-effort: when `SRF_API_KEY` is not set or the API fails, the figure is still drawn normally, just without the Logger curve
- a report must have been generated in `--debug` mode (`raw_telematics/` exists) to use finetune; a report in `--fast` mode has no raw CSV and cannot be recomputed

#### Overlay comparison visualisation

`regenerate_figures` now by default shows **both before and after finetune** segment boundaries on `_finetuned.png`, to ease direct comparison:

| Case | Content of `_finetuned.png` |
|------|-------------------------|
| the day's segs are exactly the same as the original xlsx | the original PNG is directly `shutil.copy2`'d, **file bit-identical** |
| the day's segs changed | base = original red/green (`alpha=0.12`) + overlay = orange `#FF9933` / cyan `#00CCCC` (`alpha=0.40`, `z_base=2` stacked on top), annotations prefixed with `[FT]` and offset vertically by ~10% of axis height |
| `original_xlsx_path` is missing or not auto-inferred | only finetuned segs are drawn, no overlay |

The underlying mechanism is implemented via new kwargs of `plot_leg_validation` (keyword-only, default None, fully backward compatible):

```python
plot_leg_validation(
    df_leg, charge_segs=orig_c, discharge_segs=orig_d,   # base
    ..., 
    overlay_charge_segs=ft_c, overlay_discharge_segs=ft_d,   # overlay
    overlay_label_prefix='[FT]',
    overlay_color_discharge='#FF9933',
    overlay_color_charge='#00CCCC',
)
```

Panel 1's legend, when an overlay is present, is extended to 4 items (Original charge / Original discharge / Finetuned charge / Finetuned discharge). Panel 2/3/4 only overlay axvspan (no text), avoiding crowding out the annotation space for anchors / recuperation / mass.

#### Typical workflow

```bash
# 1. first generate the report with --debug (writes raw_telematics/ and validation_figures/ under excel_report_database/)
python .claude/skills/generate-excel-report/generate_report.py -veh YK73WFN -ds 2024-06-01 -de 2024-09-01 --debug

# 2. in the main conversation, Claude uses vision to review validation_figures/*.png and output an operation list

# 3. apply the operation list
python -c "
from jolt_toolkit.report_generator.finetune import (
    apply_operations, regenerate_figures, regenerate_inspect_html,
    MergeOp, DeleteOp,
)
from pathlib import Path
d = Path('excel_report_database/2.2.2/YK73WFN')
xlsx = d / 'jolt_report_YK73WFN_20240601_20240901.xlsx'
ops = [DeleteOp(row=23, reason='false trip')]
ft = apply_operations(xlsx, ops, d / 'raw_telematics')
regenerate_figures(ft, d / 'raw_telematics', d / 'validation_figures')
regenerate_inspect_html(ft)
"
```

### Boolean field conversion (fixed in v2.2.1)

Boolean fields in the SRF Logger (CC active, brake switch, clutch switch, etc.) are
serialised as the strings `"true"` / `"false"` when returned by the API. `srf_client.pandas.to_numeric` (the default conversion)
only tries `int` → `float`, and on encountering a boolean string indiscriminately returns `math.nan`, leaving the CSV columns entirely empty.

`_generator._logger_to_numeric` is a **strict superset** of `to_numeric`: it adds the
`"true"→1`, `"false"→0` mapping ahead of the original logic, with all other values behaving exactly as before. It is passed in when `_save_logger_data` calls
`leg.get_data_frame(..., conversion=_logger_to_numeric)`, allowing the raw Logger CSV
to correctly export all boolean fields. Before the fix, columns such as `CCVS cruise control active` were all NaN;
after the fix, the non-empty rate is about 99% (taking YK73WFN's 3 months of data as an example).

## SRF API caching architecture

Report generation uses a three-tier cache to accelerate SRF API access:

| Tier | Location | Cached content | Hit condition |
|------|------|----------|----------|
| Tier 1 — HTTP | `cache/srf_http/` | SRF REST API HTTP responses | URL + headers match (`SeparateBodyFileCache`) |
| Tier 2 — raw data | `cache/srf_raw/` | FPS leg raw telematics CSV | `leg.uri` hash match |
| Tier 3 — postcode | `cache/postcode_cache.json` | GPS coordinate → postcode mapping | coordinate precision 0.001° match |

- Tier 1 is injected into `srf_client.SRFData(cache=...)` via `SeparateBodyFileCache` in `_generator.py`, `charger_patcher.py`, and `logger_patcher.py`
- Tier 2 is implemented in the FPS leg processing loop: the first run downloads and saves the CSV, subsequent runs read it directly
- Tier 3 is implemented in `report_builder.py`: the JSON is loaded at startup, and new query results are appended and written back

## Data patching Patchers

Report generation adopts an FPS-first strategy: first use FPS telematics data to generate a base report,
then patch in the Charger/Logger/weather data via patchers.

In normal mode the generator automatically calls the ChargerPatcher and LoggerPatcher;
`--fast` mode skips them, and the patchers can be run independently afterwards to patch in.

### ChargerPatcher — charger links

Fetches charger transactions from the SRF API and patches the Charger Link column by
time-window matching (leg vs transaction, ±4 min tolerance).

```python
from jolt_toolkit.report_generator.charger_patcher import ChargerPatcher
ChargerPatcher().patch_file("excel_report_database/2.2.2/KY24LHT/jolt_report_KY24LHT_20250101_20250131.xlsx")
```

**Charging-leg matching (all charge types).** A row is treated as a charging leg when
its Leg Type contains any of `AC` / `DC` / **`Charge`**. The `Charge` case is essential:
the report builder emits the generic types `Charge Home` / `Charge Away` for every
charging leg of a vehicle whose AC/DC counters cannot be attributed (EX74JXW / EX74JXY /
LN25NKE / YN25RSY / YN75NMA) plus scattered legs on every other EV. Before this was
added, such legs never received a Charger Link even when SRF held the transactions.

**Multi-transaction legs.** A single charging leg can span several charger transactions —
dual-gun chargers (e.g. a Nidec `DC-360-360`) record two interleaved meter series, and a
long stop can hold several sequential sessions. `_find_charger_matches` collects **all**
windows overlapping the leg; the `Energy Output from Charger (kWh)` cell is written as the
**sum** of the non-None energies of every overlapping window (None if all are None), and
the hyperlink points at the earliest-starting window's charger URI.

**Merged `raw_charger/charger_transactions.csv` persistence.** In `--debug` runs the
generator saves the period's charger transactions via the shared helper
`charger_patcher.merge_save_charger_transactions()`, which **merges** with any existing
CSV (concat → de-duplicate by `uri`, keeping the newest → sort by `start_time`) instead of
overwriting. This keeps the per-vehicle CSV accumulating forward in time (each generation
run only sees its own period's transactions), so the dashboard raw-data base and the
data-collection monitor keep seeing the full charger history. `_generator._save_charger_data`
and the backfill CLI below both call this one helper, so they persist identically.

**Backfill CLI.** Charger transactions that arrive in SRF after a report was generated
(or reports rebuilt by `recompute_v227`, which preserves links verbatim) can be patched
in retroactively:

```bash
# a single report, a vehicle directory, or a whole version directory
python -m jolt_toolkit.report_generator.charger_patcher \
    excel_report_database/2.2.7/EX74JXY
python -m jolt_toolkit.report_generator.charger_patcher \
    excel_report_database/2.2.7 --persist-raw
```

- Accepts a single `jolt_report_*.xlsx`, a vehicle directory (patches every
  `jolt_report_*.xlsx` inside, skipping `*_finetuned*`), or a version directory (iterates
  the vehicle sub-directories, skipping `dashboard/`).
- For each report it fetches the SRF charger transactions for that report's own period
  (keyed by `vehicle.registration`) and fills **only empty** Charger Link cells — it is
  idempotent, never touching an already-linked cell, so re-running patches nothing new.
- Diesel vehicles (`fuel_type == DIESEL`: WU70GLV, YT21EFD) are skipped.
- `--persist-raw` also merge-saves each vehicle's fetched transactions into its
  `raw_charger/charger_transactions.csv` (same merge helper as above).
- `SRF_API_KEY` is read from the environment; if it is absent the CLI loads it from the
  repo-root `.env` (dependency-free manual parse).

### LoggerPatcher — Logger links + weather

Fetches Logger legs from the SRF API and patches the Logger Link and weather columns (Channel 7 data).

```python
from jolt_toolkit.report_generator.logger_patcher import LoggerPatcher
LoggerPatcher().patch_file("excel_report_database/2.2.2/YK73WFN/jolt_report_YK73WFN_20250820_20250822.xlsx")
```

### Weather patching — unified entry point (default coarse / fine opt-in)

Weather patching is a standalone post-hoc step (it is **not** run inside
`generate_report()`; the in-line Logger Channel 7 path fills weather for the few
Logger-equipped EVs during generation, and the diesel pipeline fills its own weather
in-line). For everything else, use the single dispatcher `patch_weather`, which is
the one place the **default strategy** lives:

- **`mode="coarse"` (default)** → `WeatherPatcher` (origin/destination 2-point
  average, de-duplicated across rows). Quota-friendly.
- **`mode="fine"` (explicit opt-in only)** → `FineGrainedWeatherPatcher`
  (in-trip GPS multi-sampling).

```python
from jolt_toolkit.report_generator.weather_patch import patch_weather

# Default — coarse, quota-friendly. target may be a single xlsx or a folder.
patch_weather("excel_report_database/2.2.3/KY24LHT/")

# Explicit opt-in — fine-grained (needs --debug raw_telematics CSVs).
patch_weather(
    "excel_report_database/2.2.3/YK73WFN/jolt_report_YK73WFN_20250601_20250830.xlsx",
    mode="fine",
    force_repatch=True,
)
```

CLI (same default-coarse / fine-opt-in behaviour):

```bash
# default coarse
python -m jolt_toolkit.report_generator.weather_patch \
    excel_report_database/2.2.3/KY24LHT/

# explicit fine-grained (--fine-grained == --mode fine); --diesel selects DIESEL_HEADERS
python -m jolt_toolkit.report_generator.weather_patch \
    excel_report_database/2.2.3/YK73WFN/jolt_report_YK73WFN_20250601_20250830.xlsx \
    --fine-grained --force-repatch
```

**Why coarse is the default**: fine-grained samples every GPS point in each trip
(~17k OpenWeather calls per vehicle, ~220k fleet-wide), which immediately trips the
OpenWeather subscription into HTTP 429 ("exceeding of requests limitation of your
subscription type") and temporarily bans the account. The coarse origin/destination
average is close to the fine aggregate while using two orders of magnitude fewer
calls, so it is the right default; fine-grained is reserved for analyses that
genuinely need high spatial resolution.

Requires the environment variable `OPENWEATHER_API_KEYS` (multiple comma-separated
API keys). Both underlying classes remain importable directly (below) for backward
compatibility — `patch_weather` only centralises which one is the default.

### WeatherPatcher — coarse OpenWeather API weather (the default)

For reports without Logger data, `WeatherPatcher` patches the weather columns
(temperature, pressure, humidity, wind speed, wind direction, weather type) via the
OpenWeather API, averaging the **origin + destination** of each leg. This is what
`patch_weather` calls by default; you can also use it directly:

```python
from jolt_toolkit.report_generator.weather_patcher import WeatherPatcher
WeatherPatcher().patch_folder("excel_report_database/2.2.2/KY24LHT/")
```

Requires the environment variable `OPENWEATHER_API_KEYS` (multiple comma-separated API keys).

### FineGrainedWeatherPatcher — in-trip multi-sample fine-grained weather (v2.2.3, opt-in)

`report_generator/weather_fetcher/fine_grained_patcher.py` provides `FineGrainedWeatherPatcher`,
which performs finer trip-level meteorological aggregation on top of an existing `--debug` mode xlsx + `raw_telematics/raw_*.csv`,
giving higher spatial resolution than the coarse "origin/destination 2-sample" default, serving analyses such as `ep_multifactor_regression`
that are sensitive to temperature / wind direction. **It is not the default** (its API volume trips OpenWeather 429); reach it explicitly via `patch_weather(..., mode="fine")` or directly:

```python
from jolt_toolkit.report_generator.weather_fetcher.fine_grained_patcher import (
    FineGrainedWeatherPatcher,
)
FineGrainedWeatherPatcher().patch_file(
    "excel_report_database/2.2.3/YK73WFN/jolt_report_YK73WFN_20250601_20250830.xlsx",
    force_repatch=True,
)
```

**Key design**:

- **multi-sampling**: all GPS points within the trip time window are down-sampled by `min_sample_interval_s` (default 60 s)
- **circular wind-direction averaging**: wind direction is vector-averaged using sin/cos components, **fixing the old patcher's 359°/1° → 180°
  arithmetic-mean bug**
- **quantised cache key**: `(lat:.2f, lon:.2f, hour_bucket)`, about **1 km × 1 h** granularity; a separate cache
  file `cache/weather/.weather_cache_fine.json`
- **dynamic column index derivation**: accepts the `headers=HEADERS / DIESEL_HEADERS` parameter, no longer hard-coding 1-based indices
- **Stop / Charge row fallback**: when raw_telematics has no moving GPS → fall back to the two origin/dest
  endpoints (consistent with the old patcher)
- **backward compatibility**: the old `WeatherPatcher` is left untouched, and the `enrich_weather_data` interface is unchanged

## Analysis figures (standalone script)

Analysis figure plotting has been moved out of the package and into the project-level standalone script `data_analysis_workspace/shared/generate_figures.py`.
For detailed figure types, style constants, and configuration descriptions, see the Claude skill document `.claude/skills/figure-plotter/SKILL.md`.

**Precondition**: there is already an xlsx report under `excel_report_database/<version>/`.

### Quick use

```bash
cd <project_root>
PYTHONPATH=src python data_analysis_workspace/shared/generate_figures.py --version 2.2.2
PYTHONPATH=src python data_analysis_workspace/shared/generate_figures.py --version 2.2.2 --anon
```

### Output figure types

The script generates three groups of figures in turn:

| Type | Output directory | Content |
|------|----------|------|
| per_operation | `fitline_with_scatter/` | each vehicle's individual scatter + fit line (6 figures/vehicle) |
| all_operations | `all_ops_*` | all vehicles merged (plain / errorbar / shaded × 4 metric combinations) |
| per_oem | `oem_*` | aggregated by OEM group (plain / errorbar / shaded × 4 metric combinations) |

### Configuration

Plotting metadata is configured in `configs/plot_config.json`. When adding a vehicle, you must register `company_assignment` and `vehicle_specs`, otherwise plotting will skip that vehicle.

### Weather data source priority

1. **LoggerPatcher** (Logger Channel 7) — automatically patched for vehicles with a Logger
2. **OpenWeather API** — manually patched when there is no Logger, via the unified
   `patch_weather` entry point: **coarse `WeatherPatcher` by default** (quota-friendly),
   fine-grained `FineGrainedWeatherPatcher` only when explicitly opted in (`mode="fine"`)

#### Logger vs OpenWeather data consistency

Based on cross-validation on YK73WFN (2025-03 ~ 2025-09, 117 discharge trips), the weather data from the two sources is highly consistent:

| Variable | Pearson r | MAE | Description |
|------|-----------|-----|------|
| Temperature (°C) | 0.976 | 1.1 | minimal deviation |
| Pressure (hPa) | 0.999 | 1.8 | almost perfectly consistent |
| Humidity (%) | 0.935 | 7.0 | good consistency, local deviation acceptable |
| Wind Speed (m/s) | 0.937 | 0.6 | magnitude and trend in agreement |

**Conclusion**: the two sources can be used interchangeably, and Logger weather is reliable as the preferred source.

#### Functional differences between Logger and the OpenWeather API

| Data item | Logger (Channel 7) | OpenWeather API |
|--------|-------------------|-----------------|
| Temperature | ✅ | ✅ |
| Pressure | ✅ | ✅ |
| Humidity | ✅ | ✅ |
| Wind Speed | ✅ | ✅ |
| Wind Direction | ✅ | ✅ |
| Cloud Cover | ✅ | ❌ |
| **Weather Type** | **❌ no such data** | **✅** (Clear / Clouds / Rain / Snow, etc.) |

Weather Type (weather category) is provided only by the OpenWeather API. For vehicles with Logger data only, weather category information cannot be obtained directly.

#### Relationship between humidity and road wet/dry state

An attempt was made to infer road wet/dry conditions (as a substitute for Weather Type) from Logger humidity data; the conclusion is that it is **not feasible**:

- mean humidity under Dry conditions 71.9%, mean humidity under Wet (Rain) conditions 81.4%
- t-test p = 0.029, the difference is statistically significant
- but the two distributions **overlap heavily**: many Dry trips have humidity > 80% (high humidity but no rain), and Wet trips also have humidity < 70%
- best threshold 90%: accuracy ~85%, but a 70% miss rate (only 30% of Wet trips detected)
- **Conclusion**: humidity cannot serve as a reliable substitute for Weather Type, and road wet/dry judgement still requires the OpenWeather API's Weather Type field

## Adding a vehicle

1. Add an entry to `configs/vehicles.json`, specifying the SRF registration name, nominal capacity, and telematics column names
2. If custom segmentation parameters are needed, add a pipeline entry to `configs/pipelines.json`
3. Test with `--debug` and confirm the segmentation quality via the validation figures

## Dependency graph

```
.claude/skills/generate-excel-report/generate_report.py
  └─ JOLTReportGenerator (report_generator/_generator.py)
       ├─ fetch_events() (data_fetcher.py)
       │    └─ srf_client.SRFData (external: SRF API)
       │
       ├─ [EV branch] cfg.fuel_type != "DIESEL"
       │  ├─ run_segment_detection() (segment_algorithms.py)
       │  │    ├─ VEHICLE_CONFIG ← configs/vehicles.json
       │  │    ├─ PIPELINE_CONFIGS ← configs/pipelines.json
       │  │    ├─ find_charge_segments_by_soc()
       │  │    ├─ find_discharge_segments_by_soc()  # soc branch
       │  │    ├─ find_discharge_segments_by_speed() # speed branch
       │  │    ├─ find_speed_trips()                # speed trip detection
       │  │    ├─ cluster_mass_data()               # mass clustering
       │  │    ├─ split_discharge_by_mass()          # cluster-label splitting
       │  │    ├─ merge_discharge_by_mass()          # cluster-label merging
       │  │    └─ plot_leg_validation() [debug]
       │  │    external deps: pandas, numpy, matplotlib
       │  │
       │  └─ _correct_effective_capacity() (post-processing)
       │
       ├─ [Diesel branch v2.2.2] cfg.fuel_type == "DIESEL"
       │  └─ process_diesel_leg() (diesel_pipeline.py)
       │       ├─ _build_logger_df() — fetch LFC/LFE/VDHR/CCVS/CVW/AMB/Ch2 per leg
       │       ├─ find_speed_trips() — the same helper
       │       ├─ _trip_metrics()   — per-trip fuel differencing, distance, median mass, L/100km
       │       │     (v2.2.4: CVW median uses moving-only samples, speed > speed_threshold_kmh,
       │       │      falling back to all m>0 when no moving sample; carry-over / weight_class chain unchanged)
       │       └─ _diesel_seg_to_row() — row tuple (EV columns all NaN)
       │       external deps: pandas, numpy, srf_client
       │       skips effective_capacity correction / charger patcher / logger patcher
       │
       ├─ _insert_stop_rows()  (v2.2.2, both branches take this)
       │    synthesise Stop rows between sorted rows (gap > 60 s)
       │
       ├─ report_builder.py
       │    ├─ _seg_to_row() [EV]
       │    ├─ _stop_row_from_neighbours() [v2.2.2]
       │    ├─ _write_excel_report() — green/red/white three colours
       │    └─ _write_html_viewer() [debug]
       │    external deps: xlsxwriter, geopy, srf_client
       │
       └─ [non-fast, non-diesel] data patching patchers
            ├─ ChargerPatcher (charger_patcher.py) → Charger Link
            └─ LoggerPatcher (logger_patcher.py)   → Logger Link + weather
            external deps: openpyxl, srf_client
```

## Related analysis modules

### `research_projects/regen_analysis/`

A regenerative braking energy recovery analysis framework (independent of the `jolt_toolkit` package, located under the project root's `research_projects/` directory).

It cross-compares Logger 1Hz CAN data (speed, torque, altitude) with the telematics cumulative regen energy counter,
quantifying the system-level regen efficiency eta_regen of YK73WFN (Volvo FM Electric).

For detailed methods and conclusions see [`research_projects/regen_analysis/report.md`](../../research_projects/regen_analysis/report.md).
