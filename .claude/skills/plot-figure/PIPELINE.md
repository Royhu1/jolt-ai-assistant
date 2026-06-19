# plot-figure — Pipeline

> Loads xlsx reports → filters driving legs → fits (linear/reciprocal) → renders
> energy-performance figures (EP/range vs mass, per-vehicle / per-OEM / all-ops).

**Invoke:** `/plot-figure …` · **In:**
`excel_report_database/<version>/<REG>/jolt_report_*.xlsx` (sheet `Report`) +
`plot_config.json` · **Out:** PNGs under `<out-dir>/named/` and `<out-dir>/anon/`

## Flow

1. **Ensure reports exist** for the chosen `--version` (else regenerate via
   `/generate-excel-report`).
2. **Pick a mode:**
   - **A — standard set** (reference pipeline): run
     `data_analysis_workspace/shared/generate_figures.py` for the full named+anon set as-is.
     This script is the authoritative source of style + data-loading + fit logic.
   - **B — bespoke figure (default):** persist a self-contained, editable `plot_<name>.py`
     in the target workspace's `code/`/`scripts/` folder (style constants + filters +
     exclusion constant + `savefig`), run it, and report its path — never plot-and-delete.
3. **Load + derive** — read the Report sheet; derive `Max Range` (capacity ÷ EP) and
   `Payload+Trailer` (mass − tractor + trailer).
4. **Filter** — driving leg types only; EP ∈ (0.1, 3.0]; mass ∈ (0, 42000].
5. **Fit + style** — linear (≥3 pts) or reciprocal `c/(k·x+a)` (≥5 pts), optional ±1σ /
   errorbar bands; apply the authoritative Style constants exactly.
6. **Save + report** — write PNG(s) to the destination dir; match the `templates/` exemplars;
   tell the user the persisted script path so the figure stays reproducible/tweakable.

**Note:** the old top-level `figures/<version>/` is deprecated (moved to `archive/`); always
write to a `--out-dir` the user specifies. Use `--anon` / an `ANON` switch for anonymised
OEM labels.
