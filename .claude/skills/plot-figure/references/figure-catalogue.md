# Figure type catalogue

The three figure families of the JOLT standard set. Bespoke figures are normally a
customised member of one of these families — reuse the filenames and sub-variant grammar
so outputs stay recognisable.

## 1. `per_operation` — per-vehicle scatter + fit line

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

## 2. `all_operations` — all vehicles merged, fit-line-only

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

## 3. `per_oem` — per-OEM aggregated fit lines

**Output dir**: `<out-dir>/named/` (or `anon/`)
**Filename**: `oem_{metric}_vs_{dimension}[_{style}].png`

Same four combinations × same three styles as `all_operations`.
Data is grouped by `Make` (named) or `OEM` (anon). Colours from `plot_config.json → colors.oem_by_make`.
