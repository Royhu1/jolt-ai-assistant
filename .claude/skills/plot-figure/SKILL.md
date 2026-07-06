---
name: plot-figure
description: |
  Generate energy-performance analysis figures from JOLT xlsx reports
  (EP vs mass scatter + fit lines, range vs mass, per-operation / per-OEM charts).
  Figures are written under a user-specified --out-dir (named/ + anon/ subdirs);
  the old top-level figures/ directory is deprecated (past outputs moved to archive/).
  Every run PERSISTS a self-contained, editable plotting script in the target
  workspace's code/ (or scripts/) folder and runs it from there — never
  plot-and-delete — so the figure stays reproducible and tweakable later.
  Triggers on:
  (1) "plot EP vs GVM / range vs mass for <vehicle>"
  (2) "generate / update analysis figures from reports"
  (3) "/plot-figure"
---

# Plot Figure — JOLT Report Analysis Figures

Generate energy-performance analysis figures from JOLT xlsx reports.
Pass an explicit output directory via `--out-dir`; `named/` (real names) and `anon/`
(anonymised OEM labels) are created under it. The old top-level `figures/<version>/` is
**deprecated** — past outputs were moved to `archive/figures/`, and representative style
exemplars live in this skill's `templates/`.

## Trigger

Use this skill when the user asks to:
- Generate analysis figures / plots from JOLT reports
- Update or regenerate `<out-dir>/`
- Plot EP vs mass, range vs mass, per-operation or per-OEM charts
- Run `/plot-figure`

---

## Style constants (authoritative — must match these exactly)

```python
FIG_W, FIG_H   = 10, 6        # figure size (inches)
FIG_H_SM       = 3.5          # small-variant height (per_operation)
DPI            = 300
FS_LABEL       = 14           # axes label font size
FS_TITLE       = 14           # axes title font size
FS_TICK        = 12           # tick label font size
FS_LEGEND      = 9            # legend font size
ALPHA_SC       = 0.25         # scatter alpha
MARKER_SIZE    = 10           # scatter marker size
FIT_LW         = 2            # fit line width
FIT_ALPHA      = 0.9          # fit line alpha
DASH_ALPHA     = 0.55         # dashed extension alpha
SHADE_ALPHA    = 0.15         # ±1σ shaded band alpha
GRID_ALPHA     = 0.3          # grid alpha

PERF_YLIM      = (0, 3)       # Energy Performance (kWh/km) y-axis
RANGE_YLIM     = (0, 900)     # Max Range (km) y-axis
MASS_XLIM      = (0, 45000)   # Vehicle Total Mass (kg) x-axis
PT_XLIM        = (0, 35000)   # Payload+Trailer (kg) x-axis
MASS_CUTOFF    = 42000        # solid fit line ends here; dashed extension to MASS_XLIM[1]
```

Apply style to every axis:
```python
ax.tick_params(labelsize=FS_TICK)
ax.xaxis.label.set_size(FS_LABEL)
ax.yaxis.label.set_size(FS_LABEL)
ax.set_title(..., fontsize=FS_TITLE)
ax.grid(True, alpha=GRID_ALPHA)
ax.legend(fontsize=FS_LEGEND, loc='best')
```

---

## Figure type catalogue

### 1. `per_operation` — per-vehicle scatter + fit line

**Output dir**: `<out-dir>/named/fitline_with_scatter/`
**Filename**: `{REG}_{Make}_{Company}_{metric}_vs_{dimension}.png`
**Size**: `(FIG_W, FIG_H_SM)` = (10, 3.5)

Five sub-variants per vehicle+company:
| Filename suffix | x-axis | y-axis | Fit |
|---|---|---|---|
| `kWhkm_vs_GVW` | Vehicle Total Mass (kg) | Energy Performance (kWh/km) | linear, dash extend to MASS_CUTOFF |
| `kWhkm_vs_PayloadTrailer` | Payload+Trailer (kg) | Energy Performance (kWh/km) | linear |
| `Range_vs_GVW` | Vehicle Total Mass (kg) | Max Range (km) | linear, dash extend |
| `Range_vs_GVW_reciprocal` | Vehicle Total Mass (kg) | Max Range (km) | reciprocal, dash extend |
| `Range_vs_PayloadTrailer` | Payload+Trailer (kg) | Max Range (km) | linear |
| `Range_vs_PayloadTrailer_reciprocal` | Payload+Trailer (kg) | Max Range (km) | reciprocal |

Scatter uses vehicle `Color` from `plot_config.json`. Skip operations with fewer than 5 data points.

### 2. `all_operations` — all vehicles merged, fit-line-only

**Output dir**: `<out-dir>/named/` (or `anon/`)
**Filename**: `all_ops_{metric}_vs_{dimension}[_{style}].png`

Four metric-dimension combinations × three styles (plain / errorbar / shaded):
| Combination | x-axis | y-axis | Fit |
|---|---|---|---|
| `kWhkm_vs_GVW` | Vehicle Total Mass | Energy Performance | linear |
| `kWhkm_vs_PayloadTrailer` | Payload+Trailer | Energy Performance | linear |
| `Range_vs_GVW` | Vehicle Total Mass | Max Range | reciprocal + `_reciprocal` + `_dual` extras |
| `Range_vs_PayloadTrailer` | Payload+Trailer | Max Range | reciprocal + `_dual` extra |

Styles:
- `plain` — fit lines only, no suffix in filename
- `errorbar` — fit lines + binned error bars (10 bins), suffix `_errorbar`
- `shaded` — fit lines + ±1σ shaded band, suffix `_shaded`

Each vehicle/operation is coloured by `Color` (named) or by OEM colour (anon).

### 3. `per_oem` — per-OEM aggregated fit lines

**Output dir**: `<out-dir>/named/` (or `anon/`)
**Filename**: `oem_{metric}_vs_{dimension}[_{style}].png`

Same four combinations × same three styles as `all_operations`.
Data is grouped by `Make` (named) or `OEM` (anon). Colours from `plot_config.json → colors.oem_by_make`.

---

## Configuration

All vehicle metadata (make, effective capacity, tractor weight, company assignment, colours) is in:
`src/jolt_toolkit/configs/plot_config.json`

Key fields used:
- `vehicle_specs.{REG}.make` — OEM name
- `vehicle_specs.{REG}.effective_capacity_kwh` — for Max Range calculation
- `vehicle_specs.{REG}.tractor_weight_kg` — for Payload+Trailer
- `company_assignment.simple.{REG}` — company label
- `company_assignment.round_robin.{REG}` — time-based company assignment
- `trailer_weights_kg.{company}` — trailer weight per company
- `colors.vehicle_override.{REG}` — per-vehicle colour
- `colors.company.{company}` — per-company colour
- `colors.oem_by_make.{make}` — OEM colour by make
- `oem_anonymization.{make}` — anonymised OEM label (e.g. "OEM A")
- `driving_leg_types` — list of Leg Type values to include

---

## Data loading

Read from `excel_report_database/{version}/{REG}/jolt_report_{REG}_{YYYYMMDD}_{YYYYMMDD}.xlsx`, sheet `Report`.

Required columns:
- `Vehicle Mass (kg)` — total vehicle mass
- `Energy Performance (kWh/km)` — energy per km (standard)
- `Battery Capacity (kWh)` — for reference
- `Distance (km)` — leg distance
- `Leg Type` — filter to `driving_leg_types` only
- `Start Time (UTC)` — for company round-robin assignment

Derived columns:
- `Max Range (km)` = `effective_capacity_kwh / Energy Performance (kWh/km)`
- `Payload+Trailer (kg)` = `Vehicle Mass - tractor_weight_kg + trailer_weight_kg`

Data quality filters (apply before plotting):
- `Leg Type in driving_leg_types`
- `Energy Performance > 0.1` and `<= 3.0`
- `Vehicle Mass > 0` and `<= 42000`

---

## Fit models

### Linear fit
```python
from sklearn.linear_model import LinearRegression
model = LinearRegression().fit(x.reshape(-1,1), y)
k, b = model.coef_[0], model.intercept_
r2 = model.score(x.reshape(-1,1), y)
label = f"y = {k:.2e}x + {b:.2e}  (R²={r2:.3f})"
```
Minimum 3 valid points required.

### Reciprocal fit
```python
from scipy.optimize import curve_fit
def recip_model(x, k, a, c): return c / (k*x + a)
# bootstrap p0 from 1/y linear regression, then refine with curve_fit
```
Minimum 5 valid points required.

### Binned stats (for errorbar style)
```python
bins = np.linspace(x.min(), x.max(), 11)  # 10 bins
# compute mean ± std per bin, min 2 points
```

---

## Generation: two modes

### Mode A — standard batch set (reference pipeline)

The standalone script `data_analysis_workspace/shared/generate_figures.py` implements the
full standard figure set (per-operation / all-operations / per-OEM, named + anon). Use it
when the user wants the whole standard set regenerated as-is.

```bash
cd <project_root>
PYTHONPATH=src python data_analysis_workspace/shared/generate_figures.py --out-dir <your/output/dir> [--version 2.2.7] [--anon]
```
Outputs: `<out-dir>/named/` (real names) and `<out-dir>/anon/` (anonymised OEM labels).
This script is also the **authoritative source of style + data-loading + fit logic** — any
per-task script (Mode B) must import from it or mirror its constants exactly.

### Mode B — a specific / customised figure (DEFAULT, with MANDATORY persistence)

Use this for **anything bespoke**: one figure type, a custom vehicle grouping or exclusion
(e.g. "exclude KY24"), a paper/analysis-specific panel, or any figure that will be tuned
later. In this mode you MUST leave behind a persisted, editable generator script — see the
next section. Do **not** improvise a throwaway `_tmp_*.py` and delete it.

---

## Persisting the generator script (MANDATORY for Mode B)

**Rule: every Mode-B invocation persists a self-contained, runnable plotting script in the
target workspace's code folder, runs it from there, and does NOT delete it.** Plot-and-delete
is forbidden — past throwaways are exactly why some published figures (e.g. the per-OEM
energy/range PNGs) have no findable generator.

1. **Where to write it** — the *target workspace's* code/scripts folder, i.e. the folder
   that owns the destination figures:
   - publication paper → `publication_workspace/<paper>/code/`
   - data-analysis topic → `data_analysis_workspace/<topic>/scripts/`
   - if the destination workspace is ambiguous, ask the user; default to the workspace that
     owns the `figures/` the output is going into.
2. **Naming** — descriptive `snake_case`, prefixed `plot_`, named after the figure(s) it
   produces: e.g. `plot_energy_per_oem.py`, `plot_range_cross_oem.py`. **Never** the
   gitignored throwaway names `_tmp_*.py` / `_patch_*.py` (those are deleted after use).
3. **Self-contained & reproducible** — the script runs standalone (`python <path>`) and
   contains: imports, the Style constants below (copied or imported from
   `shared/generate_figures.py`), data loading from `excel_report_database/<version>/`, the
   data-quality filters, any exclusion list (as a clearly-named module-level constant, e.g.
   `EXCLUDE_REGS = {...}`), the fit, and `fig.savefig(<dest>)`. A module docstring states
   what it plots, the data version, the exclusion criterion, and the output path(s).
4. **Output path** — write the PNG(s) directly to the destination `figures/` dir the user
   asked for (or the workspace default). Keep DPI/sizing per the Style constants.
5. **Run it, then report** — execute the persisted script, confirm the PNG(s) were written,
   and tell the user the script path so they can tweak and re-run it.
6. **Provenance** — when the figure feeds a paper, point the caption `Source:` / the paper
   README "copied from" table at the persisted script path (not at a tmp file).

> Idempotent re-runs: a Mode-B script should overwrite its own PNG cleanly on re-run, so the
> user's edit→re-run loop is friction-free.

---

## Style templates (authoritative visual reference)

Representative finished figures live in `.claude/skills/plot-figure/templates/` — new plots
must match these:
- `all_ops_kWhkm_vs_GVW_shaded.png` — EP vs mass, all ops, ±1σ band
- `oem_kWhkm_vs_GVW_shaded.png` — per-OEM aggregated
- `all_ops_Range_vs_GVW_reciprocal.png` — range vs mass (reciprocal fit)
- `anon_all_ops_kWhkm_vs_GVW_shaded.png` — anonymised-label variant
- `AV24LXJ_Volvo_KNOWLES_kWhkm_vs_GVW.png` — per-vehicle scatter + fit

(The full historical figure sets were moved to `archive/figures/<version>/`.)

---

## Workflow

1. Ensure reports exist for the chosen `--version` under `excel_report_database/<version>/`
   (regenerate via the `generate-excel-report` skill if missing; skip `--debug` to preserve
   patched weather data).
2. Decide the mode:
   - **Standard full set** → Mode A: `PYTHONPATH=src python data_analysis_workspace/shared/generate_figures.py --out-dir <dir> --version <version> [--anon]`.
   - **A specific / customised figure** (default) → Mode B: confirm the target workspace +
     its `code/`/`scripts/` folder, write a persisted `plot_<name>.py` there (self-contained,
     style + filters + exclusion constants + `savefig`), then run it: `python <path/to/plot_name.py>`.
3. Review the output PNG(s) in their destination dir; check against the style `templates/`.
4. Tell the user the **persisted script path** so they can tweak and re-run it. For anonymised
   publication variants, expose an `--anon`/`ANON` switch in the persisted script (or pass it
   through to Mode A).
