# Style contract (always load)

The JOLT figure style is **contract-fixed**: every figure this skill produces must be
visually identical to the exemplars in `templates/`. Style is not a creative variable —
apply the constants below exactly.

## Source of truth

The **executable** source of truth for style + data-loading + fit logic is
`data_analysis_workspace/shared/generate_figures.py`. The constants below are a mirror of
that script for prompt-side reference and MUST match it exactly. A deliberate style change
edits the script first, then this mirror — never one without the other.

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
MASS_CUTOFF    = 42000        # dashed fit-extension target: solid fit ends at the observed data max; dashed extends to 42 t (also the mass-filter upper bound)
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

## Output format

The canonical output format is **PNG at `DPI = 300`** via `fig.savefig(...)`. Do not switch
the default to a vector format — downstream consumers (LaTeX papers via PDF conversion,
python-pptx slide decks, HTML briefings) each have their own optimum, and the dense scatter
layers make vector files heavy. When the user explicitly asks for vector output, open
`references/output-formats.md` and add formats *alongside* the PNG, never instead of it.

## Visual reference gallery (`templates/`)

Representative finished figures — new plots must match these:

- `all_ops_kWhkm_vs_GVW_shaded.png` — EP vs mass, all ops, ±1σ band
- `oem_kWhkm_vs_GVW_shaded.png` — per-OEM aggregated
- `all_ops_Range_vs_GVW_reciprocal.png` — range vs mass (reciprocal fit)
- `anon_all_ops_kWhkm_vs_GVW_shaded.png` — anonymised-label variant
- `AV24LXJ_Volvo_KNOWLES_kWhkm_vs_GVW.png` — per-vehicle scatter + fit

(The full historical figure sets were moved to `archive/figures/<version>/`.)
