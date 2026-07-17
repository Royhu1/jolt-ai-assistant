# report-visuals — validation figures + inspect-HTML rendering

Self-contained owner of **all validation-figure and inspect-HTML rendering**
for generated JOLT reports (EV and diesel). Created in the v3.1.0
platform-slimming (Phase P1) by moving the rendering code out of
`src/jolt_toolkit` into this skill — the package keeps segmentation and xlsx
generation only. During P1 the package still carries the originals
(copy-first); Phase P2 deletes them and adds the `figure_hook` seam (see
`.claude/architecture/plan_v310_platform_slim.md`).

## Directory map

```
report-visuals/
├── SKILL.md                    # router (lean — code-owner skill)
├── manifest.yaml               # loading contract + per-skill version
├── README.md                   # this file — single source of truth
├── static/core/
│   └── rendering-contract.md   # always-load: CLI modes, artefact naming, discipline
└── code/                       # self-contained rendering code (entry CLIs bootstrap
    │                           #   sys.path, so sibling imports work as plain scripts)
    ├── render_visuals.py       # THE entry CLI: repaint | rerender-html
    ├── validation_figure.py    # EV painter: plot_leg_validation, _export_overlay_boxes,
    │                           #   _TEXT_BBOX + style constants (copy of
    │                           #   segmentation/validation_figure.py)
    ├── diesel_visuals.py       # diesel painter + in-place repaint (plotting half of
    │                           #   diesel_pipeline.py: plot_diesel_leg_validation,
    │                           #   regenerate_diesel_validation)
    ├── validation_generator.py # overlay-regenerate orchestrator (ValidationGenerator;
    │                           #   copy of report_generator/validation_generator.py)
    ├── html_viewer.py          # inspect viewer builder + per-day bookkeeping helpers
    │                           #   (copy of report_generator/html_viewer.py)
    ├── assets/
    │   └── inspect_viewer_template.html   # the viewer's HTML/CSS/JS body
    ├── rerender_inspect.py     # HTML-only re-render across a DB version (copy)
    └── refresh_inspect_html.py # HTML-only refresh with per-vehicle stats (copy)
```

Each copied module carries a provenance header (source path, copy date,
symbols, what was adapted). Function bodies are identical to the v3.0.0
package sources — only imports were adapted.

## How to run

From the **repo root** (so `./cache`, `.env` and DB paths resolve), with the
jolt env python and `PYTHONUTF8=1`:

```bash
# Repaint figures + overlay sidecars + inspect HTML for one vehicle directory
python .claude/skills/report-visuals/code/render_visuals.py \
    repaint --dir excel_report_database/<ver>/<REG>

# Batch: every vehicle dir under a base directory (optional --reg filter)
python .claude/skills/report-visuals/code/render_visuals.py \
    repaint --dir excel_report_database/<ver> [--reg <REG>]

# Rewrite ONLY the inspect_*.html viewers (no PNG/sidecar re-render)
python .claude/skills/report-visuals/code/render_visuals.py \
    rerender-html --version <ver> --db-root excel_report_database [--reg <REG>]
```

`repaint` flags: `--no-local-logger` forces the SRF-API logger fetch for the
EV speed/mass overlay (default prefers local `raw_logger_*/` CSVs — faster, no
API quota); `--cache-dir` sets the SRF cache (default `./cache`).
`rerender_inspect.py` and `refresh_inspect_html.py` also run standalone with
their original arguments.

## Artefact paths

Inside the target vehicle report directory
(`excel_report_database/<ver>/<REG>/` or any directory with the same layout):

- `validation_figures/validation_<REG>_<YYYY-MM-DD>.png` — one figure per UTC
  day (EV: 4-panel SOC/energy/recuperation/mass; diesel: 4-panel
  speed/fuel/distance/GCVW).
- `validation_figures/validation_<REG>_<YYYY-MM-DD>.boxes.json` — interactive
  overlay sidecar (every rounded-bbox data label, figure-fraction coords).
- `inspect_jolt_report_<REG>_<start>_<end>.html` — offline viewer, one per
  non-finetuned period xlsx.

Stale non-finetuned figures/sidecars (including legacy per-leg
`validation_<REG>_<date>_<NNNN>.png`) are swept before a repaint;
`*_finetuned.*` artefacts always survive.

## Pipeline

**Data in** → `raw_telematics/raw_<date>_<idx>.csv` (EV) or
`raw_logger_*/logger_<date>_<idx>.csv` (diesel), persisted by the
generate-excel-report skill's `--debug` / `--raw-only` runs, plus the
`jolt_report_*.xlsx` files (REG + period parsed from the filenames).

**Processing** → per-day grouping and concatenation; segmentation via
`jolt_toolkit` **read-only** (EV: `run_segment_detection`; diesel: the
package's shared `_segments_from_df`); EV logger speed/mass overlay from local
CSVs (SRF-API fallback); painting + overlay-label export; viewer HTML filled
from `code/assets/inspect_viewer_template.html`.

**Artefacts out** → the per-day PNGs + `.boxes.json` sidecars +
`inspect_*.html` listed above.

**Ownership** — this skill owns every file under `code/` (including the viewer
template) and the rendered artefacts' naming contract. Route elsewhere:

| Change | Owner |
|---|---|
| xlsx generation, segmentation algorithms, raw persistence, package code | `jolt-toolkit-dev` agent (`src/jolt_toolkit/`) |
| Reviewing figures to tune segmentation parameters | `param-tuner` skill |
| Per-leg xlsx corrections (merge/split/delete → `*_finetuned`) | `report-finetuner` skill/agent |
| Figure/HTML *rendering* changes (panels, overlay, viewer UX) | **this skill** |

**Neighbours** — `generate-excel-report` chains this CLI after a debug
generation to paint figures + inspect HTML; `report-finetuner` will delegate
its post-op repaint here; `param-tuner` and the `report-finetuner` agent
consume the figures read-only; `vehicle-onboarding`'s initial-figures step
points here.

## Status / TODO

- **P1 (this change)**: code copied from the package (originals untouched);
  the EV repaint path still delegates painting to the package's
  `run_segment_detection` inline path — identical output, single pass.
- **P2 (package slimming)**: package modules deleted; `figure_hook` seam added
  so the package stops importing matplotlib and this skill passes
  `validation_figure.plot_leg_validation` as the hook.
- **TODO (later phase)**: explicit `--finetuned` support on the CLI for the
  report-finetuner workflow (repainting `*_finetuned` artefact sets). The
  copied code already *skips* finetuned artefacts correctly; it does not yet
  regenerate them.
