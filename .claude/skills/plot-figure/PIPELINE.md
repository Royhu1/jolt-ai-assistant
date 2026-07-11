# plot-figure — Pipeline

> Loads xlsx reports → filters driving legs → fits (linear/reciprocal) → renders
> energy-performance figures (EP/range vs mass, per-vehicle / per-OEM / all-ops).

**Invoke:** `/plot-figure …` · **In:**
`excel_report_database/<version>/<REG>/jolt_report_*.xlsx` (sheet `Report`) +
`plot_config.json` · **Out:** PNGs under `<out-dir>/named/` and `<out-dir>/anon/`

## Flow

1. **Route** — `SKILL.md` is a lean router over `manifest.yaml`: it always loads the two
   core contracts (`static/core/style-contract.md` — exact style constants + PNG-300dpi
   default; `static/core/persistence-contract.md` — mandatory persisted script), resolves
   the output destination (blocking gate; top-level `figures/` is deprecated), then loads
   exactly one mode fragment.
2. **Pick a mode:**
   - **standard-set** (reference pipeline): run
     `data_analysis_workspace/shared/generate_figures.py` for the full named+anon set
     as-is. This script is the executable source of truth for style + data-loading + fit
     logic.
   - **bespoke (default):** persist a self-contained, editable `plot_<name>.py` in the
     target workspace's `code/`/`scripts/` folder (style constants + filters + exclusion
     constant + `savefig`), run it, and report its path — never plot-and-delete.
3. **Load + derive** — read the Report sheet; derive `Max Range` (capacity ÷ EP) and
   `Payload+Trailer` (mass − tractor + trailer). Details: `references/data-contract.md`.
4. **Filter** — driving leg types only; EP ∈ (0.1, 3.0]; mass ∈ (0, 42000].
5. **Fit + style** — linear (≥3 pts) or reciprocal `c/(k·x+a)` (≥5 pts), optional ±1σ /
   errorbar bands (`references/fit-models.md`); apply the style contract exactly.
6. **Save + QA + report** — write PNG(s) to the destination dir; match the `templates/`
   exemplars; tell the user the persisted script path so the figure stays
   reproducible/tweakable. Vector formats (SVG/PDF) only on explicit request, added
   alongside the PNG (`references/output-formats.md`).

## Skill layout

```
plot-figure/
├── SKILL.md            # router: routing protocol only
├── manifest.yaml       # always_load + mode axis + on-demand reference table
├── PIPELINE.md         # this walk-through
├── static/
│   ├── core/           # style-contract.md + persistence-contract.md (always loaded)
│   └── fragments/mode/ # standard-set.md | bespoke.md (exactly one loaded)
├── references/         # figure-catalogue / data-contract / fit-models / output-formats
├── templates/          # authoritative visual exemplars (5 PNGs)
└── evaluations/        # per-run experience log
```

**Note:** the old top-level `figures/<version>/` is deprecated (moved to `archive/`); always
write to a `--out-dir` the user specifies. Use `--anon` / an `ANON` switch for anonymised
OEM labels. Ownership: `plot_config.json` and `src/jolt_toolkit/` changes route to
`jolt-toolkit-dev`; this skill only reads them.
