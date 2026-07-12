# plot-figure — energy-performance analysis figures

> Loads xlsx reports → filters driving legs → fits (linear/reciprocal) → renders
> energy-performance figures (EP/range vs mass, per-vehicle / per-OEM / all-ops).
> This README is the skill's human-facing single source of truth; `SKILL.md` is the
> agent-facing router over `manifest.yaml`.

**Invoke:** `/plot-figure …` · **In:**
`excel_report_database/<version>/<REG>/jolt_report_*.xlsx` (sheet `Report`) +
`plot_config.json` · **Out:** PNGs under `<out-dir>/named/` and `<out-dir>/anon/`

## Directory map

```
plot-figure/
├── SKILL.md            # router: routing protocol only (agent entry point)
├── manifest.yaml       # always_load + mode axis + output gate + on-demand reference table
├── README.md           # this file — human-facing map + pipeline
├── static/
│   ├── core/           # style-contract.md + persistence-contract.md (always loaded)
│   └── fragments/mode/ # standard-set.md | bespoke.md (exactly one loaded per run)
├── references/         # figure-catalogue / data-contract / fit-models / output-formats
├── templates/          # authoritative visual exemplars (5 PNGs)
└── evaluations/        # per-run experience log
```

## Pipeline

1. **Route** — `SKILL.md` loads `manifest.yaml`: always-load the two core contracts
   (`style-contract.md` — exact style constants + PNG-300dpi default;
   `persistence-contract.md` — mandatory persisted script), resolve the output
   destination (blocking gate; top-level `figures/` is deprecated), then load exactly
   one mode fragment.
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

## How to run

Standard full set:

```bash
cd <project_root>
PYTHONPATH=src python data_analysis_workspace/shared/generate_figures.py --out-dir <dir> [--version 2.2.8] [--anon]
```

Bespoke figure: invoke `/plot-figure <request>` — the run leaves a persisted
`plot_<name>.py` in the owning workspace's code folder; tweak and re-run that script to
refine the figure.

## Ownership and neighbours

- The old top-level `figures/<version>/` is deprecated (moved to `archive/`); always
  write to a `--out-dir` the user specifies. Use `--anon` / an `ANON` switch for
  anonymised OEM labels.
- Chart-style boundary: **analysis figures** (10×6, legend, ±1σ band) belong to this
  skill; **partner-briefing charts** (square, no legend / no ±1σ band) belong to the
  `generate-pdf-report` skill — route style requests accordingly.
- `plot_config.json` and anything under `src/jolt_toolkit/` belong to the
  `jolt-toolkit-dev` agent; this skill only reads them.
- Missing source reports → generate via `/generate-excel-report` first.
