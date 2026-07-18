# report-visuals — validation figures + inspect-HTML rendering

Self-contained owner of **all validation-figure and inspect-HTML rendering**
for generated JOLT reports (EV and diesel), including the `*_finetuned`
figure/HTML sets of the report-finetuner flow. Created in the v3.1.0
platform-slimming by moving the rendering code out of `src/jolt_toolkit` into
this skill — the package keeps segmentation and xlsx generation only, and
since Phase P2 paints nothing itself: the EV path supplies this skill's
painter to the package through `run_segment_detection`'s keyword-only
`figure_hook` seam (see `.claude/architecture/plan_v310_platform_slim.md`).

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
    ├── render_visuals.py       # THE entry CLI: repaint | rerender-html | repaint-finetuned
    ├── validation_figure.py    # EV painter: plot_leg_validation, _export_overlay_boxes,
    │                           #   _TEXT_BBOX + style constants (copy of
    │                           #   segmentation/validation_figure.py); ALSO the
    │                           #   figure_hook passed to the package (P2b)
    ├── diesel_visuals.py       # diesel painter + in-place repaint (plotting half of
    │                           #   diesel_pipeline.py: plot_diesel_leg_validation,
    │                           #   regenerate_diesel_validation)
    ├── validation_generator.py # overlay-regenerate orchestrator (ValidationGenerator;
    │                           #   copy of report_generator/validation_generator.py —
    │                           #   passes figure_hook=plot_leg_validation since P2b)
    ├── finetuned_visuals.py    # finetuned repaint (P2b): overlay painting loop +
    │                           #   finetuned inspect-HTML writer, moved from the
    │                           #   report-finetuner skill's finetune.py rendering half;
    │                           #   consumes the segments JSON (contract below)
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

# Rendering half of the report-finetuner flow (usually driven BY the
# report-finetuner skill's finetune.py wrappers via subprocess)
python .claude/skills/report-visuals/code/render_visuals.py \
    repaint-finetuned --xlsx <dir>/jolt_report_<REG>_<start>_<end>_finetuned.xlsx \
    --segs-json <segments.json> [--raw-dir ...] [--out-dir ...] \
    [--fig-suffix _finetuned] [--figures-only | --html-only] [--html-out <path>]
```

`repaint` flags: `--no-local-logger` forces the SRF-API logger fetch for the
EV speed/mass overlay (default prefers local `raw_logger_*/` CSVs — faster, no
API quota); `--cache-dir` sets the SRF cache (default `./cache`).
`rerender_inspect.py` and `refresh_inspect_html.py` also run standalone with
their original arguments.

### Finetuned-rendering CLI contract (`repaint-finetuned`)

The split with the report-finetuner skill: **xlsx reconstruction is
finetune-owned, painting is this skill's** — they meet only at this CLI + a
segments JSON (schema `report-visuals.finetuned-segs/v1`, full field list in
`code/finetuned_visuals.py`'s module docstring):

- the report-finetuner's `finetune.dump_segs_json` reconstructs per-date
  finetuned (+ original, when available) charge/discharge segs from the xlsx
  and serialises them (timestamps as ISO-8601 UTC; no anchors — this skill
  interpolates them from the raw CSVs);
- `repaint-finetuned --xlsx <p> --segs-json <p>` paints per raw leg:
  original present + segs identical → skip (stale finetuned PNG removed, the
  finetuned viewer falls back to the original figure); segs differ → base =
  original (red/green) + overlay = finetuned (orange/cyan, `[FT]` labels);
  no original → plain finetuned draw. Then (unless `--figures-only`) writes
  the `inspect_*_finetuned.html` viewer; `--html-only` skips painting and
  needs no JSON. Defaults: `--raw-dir <xlsx dir>/raw_telematics`,
  `--out-dir <xlsx dir>/validation_figures`, `--fig-suffix _finetuned`,
  `--html-out inspect_<xlsx stem[+suffix]>.html` next to the xlsx.
- summary lines `[report-visuals] repaint-finetuned: figures=<N>` /
  `html=<path>` are machine-parsed by the finetune wrappers — keep stable.
- outputs never overwrite non-finetuned originals (names always carry the
  suffix); the finetune library drives this CLI with `sys.executable`,
  `cwd=<repo root>` and inherited env — no cross-skill Python imports.

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
`*_finetuned.*` artefacts always survive the base modes.

`repaint-finetuned` additionally produces (never overwriting originals):

- `validation_figures/validation_<REG>_<date>_<idx>_finetuned.png` — only for
  days whose finetuned segs differ from the originals (unchanged days get
  none; a stale finetuned PNG is removed so the viewer falls back).
- `inspect_jolt_report_<REG>_<start>_<end>_finetuned.html` — finetuned viewer
  with per-day `[modified]` / `(unchanged — original)` tags.

## Pipeline

**Data in** → `raw_telematics/raw_<date>_<idx>.csv` (EV) or
`raw_logger_*/logger_<date>_<idx>.csv` (diesel), persisted by the
generate-excel-report skill's `--debug` / `--raw-only` runs, plus the
`jolt_report_*.xlsx` files (REG + period parsed from the filenames).

**Processing** → per-day grouping and concatenation; segmentation via
`jolt_toolkit` **read-only** (EV: `run_segment_detection` with this skill's
`plot_leg_validation` passed as its `figure_hook` — the package itself paints
nothing since v3.1.0 P2; diesel: the package's shared `_segments_from_df`);
EV logger speed/mass overlay from local CSVs (SRF-API fallback); painting +
overlay-label export; viewer HTML filled from
`code/assets/inspect_viewer_template.html`. The finetuned path skips
segmentation entirely — segs arrive pre-reconstructed in the segments JSON.

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
generation to paint figures + inspect HTML; `report-finetuner` delegates its
post-op repaint here (its `finetune.py` wrappers call
`repaint-finetuned` via subprocess — see the contract above); `param-tuner`
and the `report-finetuner` agent consume the figures read-only;
`vehicle-onboarding`'s initial-figures step points here.

## Status

- **P1**: code copied from the package (originals untouched); the EV repaint
  path still delegated painting to the package's inline path.
- **P2 (package slimming)**: package modules deleted; `figure_hook` seam added
  so the package stops importing matplotlib.
- **P2b (this change)**: the EV repaint passes
  `validation_figure.plot_leg_validation` as the `figure_hook` (identical
  figures, single pass — import-time assertion guards the hook signature);
  NEW `repaint-finetuned` mode absorbs the rendering half of the
  report-finetuner flow (the former P1 TODO about `--finetuned` support is
  resolved), fed by the segments-JSON contract documented above.
